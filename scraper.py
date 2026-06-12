import json
import os
import re
import time
import argparse
import requests
from datetime import datetime, timedelta
from requests.exceptions import RequestException
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
API_BASE_URL = "https://api.windfinder.com/v2/spots/de575/reports/"
REPORT_PAGE_URL = "https://de.windfinder.com/report/wannsee/{date}"
LOCATION = "wannsee"
DEFAULT_TIMEOUT = 30  # seconds
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Resilience settings
MAX_ATTEMPTS = 3        # re-harvest + retry this many times before giving up
RETRY_BACKOFF = 5       # seconds to wait between attempts
HARVEST_WAIT = 20       # seconds to wait for the page to fire an API call

# Any request header whose NAME matches this is treated as a credential and
# replayed verbatim. Broad on purpose: it survives Windfinder renaming the
# header or switching auth scheme (WF-AUTH -> Bearer, etc.) without code edits.
AUTH_HINT = re.compile(r"auth|token|api[-_]?key|bearer|wf-", re.I)


# Harvest the live credential header(s) from the Windfinder page.
#
# The token isn't in the page HTML -- it's minted inside the browser session and
# attached to the page's own api.windfinder.com calls. So we load the report
# page in a headless browser and copy whatever credential-looking header(s) it
# sends, then reuse them ourselves. We don't assume the header's name or format,
# so a future rename or scheme change keeps working.
def harvest_auth_headers(date, wait_seconds=HARVEST_WAIT):
    """Load the report page headless and capture the API credential header(s)."""
    from playwright.sync_api import sync_playwright

    url = REPORT_PAGE_URL.format(date=date)
    captured = {}        # header_name -> value (whatever auth the page uses)
    header_names_seen = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            locale="de-DE",
            timezone_id="Europe/Berlin",
            user_agent=USER_AGENT,
        )
        page = context.new_page()

        def on_request(req):
            if "api.windfinder.com" in req.url:
                try:
                    for name, value in req.headers.items():
                        lname = name.lower()
                        if lname.startswith(":"):   # skip HTTP/2 pseudo-headers
                            continue
                        header_names_seen.add(lname)
                        if AUTH_HINT.search(lname):
                            captured[lname] = value
                except Exception:
                    pass

        page.on("request", on_request)

        logger.info(f"Loading report page to harvest auth header(s): {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=60000)

        deadline = time.time() + wait_seconds
        while time.time() < deadline and not captured:
            page.wait_for_timeout(500)

        browser.close()

    if not captured:
        raise RuntimeError(
            "No credential-style header found on api.windfinder.com requests. "
            f"Header names seen were: {sorted(header_names_seen)}. "
            "Windfinder likely changed its auth scheme; widen AUTH_HINT to match "
            "one of the names above."
        )

    logger.info(f"Harvested credential header(s): {list(captured.keys())}")
    return captured


# Store wind data records in Firestore database
def save_to_firestore(db, data, data_date, location=LOCATION):
    """Save wind data to Firestore."""
    try:
        doc_ref = db.collection("wind_data").document(data_date)
        data_to_store = {
            "location": location,
            "date": data_date,
            "records": data,
            "timestamp": datetime.now(),
            "source": "API"
        }
        doc_ref.set(data_to_store)
        logger.info(f"Successfully saved data for {data_date} with {len(data)} records")
        return True
    except Exception as e:
        logger.error(f"Failed to save data to Firestore: {str(e)}")
        logger.error(f"Data being saved: {json.dumps(data_to_store, indent=2)[:500]}...")
        logger.error(f"Firestore document path: wind_data/{data_date}")
        raise


# Set up Firebase connection using service account credentials
def initialize_firestore():
    import firebase_admin
    from firebase_admin import credentials, firestore
    try:
        credential_paths = [
            ".secrets/serviceAccountKey.json",
            "serviceAccountKey.json"
        ]

        cred = None
        for path in credential_paths:
            if os.path.exists(path):
                try:
                    cred = credentials.Certificate(path)
                    logger.info(f"Using credentials from {path}")
                    break
                except ValueError as e:
                    logger.warning(f"Invalid credentials in {path}: {e}")
                    continue

        if not cred:
            raise FileNotFoundError("No valid Firebase credentials file found")

        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)

        return firestore.client()

    except Exception as e:
        logger.error(f"Firebase initialization failed: {str(e)}")
        logger.error("Contents of .secrets directory:")
        logger.error(os.listdir('.secrets') if os.path.exists('.secrets') else ".secrets doesn't exist")
        raise


# Retrieve wind data from Windfinder API for specified date
def fetch_report_response(date, auth_headers):
    """Call the reports API with the harvested credential header(s)."""
    params = {
        "limit": -1,
        "timespan": f"{date}T00:00:00+02:00/PT23H59M59S",
        "step": "1m"
    }
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
    headers.update(auth_headers)  # carry whatever credential header(s) we found
    logger.info("Calling reports API")
    return requests.get(
        API_BASE_URL,
        params=params,
        headers=headers,
        timeout=DEFAULT_TIMEOUT
    )


# Self-healing collection: each attempt harvests a fresh token and validates it
# by actually using it. On an auth rejection (401/403) or any failure, it
# re-harvests and retries. This is the "check and update auth" routine -- since
# the job runs once a day, a few extra seconds to guarantee a good token is fine.
def collect_wind_data(date):
    """Harvest auth, fetch the day's report, retrying with a fresh token on failure."""
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        logger.info(f"Collection attempt {attempt}/{MAX_ATTEMPTS}")
        try:
            auth_headers = harvest_auth_headers(date)
            response = fetch_report_response(date, auth_headers)

            if response.status_code in (401, 403):
                last_error = f"auth rejected (HTTP {response.status_code})"
                logger.warning(f"{last_error}; re-harvesting a fresh token")
                time.sleep(RETRY_BACKOFF)
                continue

            response.raise_for_status()
            logger.info(f"API response status: {response.status_code}")

            response_data = response.json()
            if isinstance(response_data, list):
                items = response_data
            elif isinstance(response_data, dict):
                items = response_data.get('items', [])
            else:
                raise ValueError(f"Unexpected response format: {type(response_data)}")

            if not items:
                last_error = "API returned no records"
                logger.warning(f"{last_error}; retrying")
                time.sleep(RETRY_BACKOFF)
                continue

            logger.info(f"API returned {len(items)} records")
            return items

        except (RequestException, ValueError, RuntimeError) as e:
            last_error = e
            logger.warning(f"Attempt {attempt} failed: {e}")
            time.sleep(RETRY_BACKOFF)

    raise RuntimeError(
        f"Failed to collect data after {MAX_ATTEMPTS} attempts. "
        f"Last error: {last_error}"
    )


# Convert raw API data into structured format with time, wind direction, speed, gusts, and temperature
def transform_data(raw_data):
    """Transform raw API data into our desired format."""
    transformed = []
    for item in raw_data:
        try:
            full_time = item.get('dtl', '')
            if full_time:
                time_only = datetime.fromisoformat(full_time).strftime('%H:%M')
            else:
                time_only = ''
            transformed.append({
                'Time': time_only,
                'Wind Direction': f"{item.get('wd', 0)}°",
                'Wind Speed (kts)': item.get('ws', 0),
                'Wind Gusts (kts)': item.get('wg', 0),
                'Temperature': item.get('at')
            })
        except (TypeError, ValueError) as e:
            logger.warning(f"Skipping malformed data item: {e}")
    return transformed


# Calculate yesterday's date for data processing
def get_processing_date():
    """Determine the date to process (yesterday by default)."""
    return (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')


# Main execution function that orchestrates the entire data collection process
def main(dry_run=False):
    try:
        processing_date = get_processing_date()
        logger.info(f"Starting data collection for {processing_date}")

        # Harvest a fresh token and fetch, retrying with a new token on failure.
        raw_data = collect_wind_data(processing_date)
        if not raw_data:
            logger.warning("No data received from API")
            return

        transformed_data = transform_data(raw_data)
        if not transformed_data:
            logger.warning("No valid data after transformation")
            return
        logger.info(f"Transformed {len(transformed_data)} records")

        if dry_run:
            logger.info("DRY RUN -- not saving to Firestore. Data preview below:")
            print(f"\nDate: {processing_date}   Records: {len(transformed_data)}")
            print(f"{'Time':>6}  {'Direction':>10}  {'Speed(kts)':>11}  "
                  f"{'Gusts(kts)':>11}  {'Temp':>5}")
            print("-" * 52)
            for r in transformed_data:
                print(f"{r['Time']:>6}  {r['Wind Direction']:>10}  "
                      f"{str(r['Wind Speed (kts)']):>11}  "
                      f"{str(r['Wind Gusts (kts)']):>11}  "
                      f"{str(r['Temperature']):>5}")
            logger.info("Dry run complete (nothing written to Firebase).")
            return

        db = initialize_firestore()
        save_to_firestore(db, transformed_data, processing_date)

        logger.info("Script completed successfully")
    except Exception as e:
        logger.error(f"Script failed: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Windfinder wind data collector")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Fetch and print the data without saving to Firebase "
             "(needs no credentials and no firebase-admin)."
    )
    args = parser.parse_args()
    main(dry_run=args.dry_run)