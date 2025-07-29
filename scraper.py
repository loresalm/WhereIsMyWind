import json
import os
import requests
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import credentials, firestore
from requests.exceptions import RequestException
import logging
import re

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
API_BASE_URL = "https://api.windfinder.com/v2/spots/de575/reports/"
LOCATION = "wannsee"
DEFAULT_TIMEOUT = 30  # seconds


# Extract authentication token from Windfinder website
def get_token():
    url = "https://de.windfinder.com/report/wannsee/2025-05-18"
    response = requests.get(url)
    token = re.search(r'window\.API_TOKEN\s*=\s*["\']([^"\']+)["\']', response.text).group(1)
    print("new token found: ----> ", token)
    return token


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
        logger.error(f"Data being saved: {json.dumps(data_to_store, indent=2)[:500]}...")  # Log first 500 chars
        logger.error(f"Firestore document path: wind_data/{data_date}")
        raise

# Set up Firebase connection using service account credentials
def initialize_firestore():
    try:
        # Check both possible locations for the credentials file
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
            
        # Initialize only if not already initialized
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
            
        return firestore.client()
        
    except Exception as e:
        logger.error(f"Firebase initialization failed: {str(e)}")
        logger.error("Contents of .secrets directory:")
        logger.error(os.listdir('.secrets') if os.path.exists('.secrets') else logger.error(".secrets doesn't exist"))
        raise


# Retrieve wind data from Windfinder API for specified date
def fetch_wind_data(date, token):
    """Fetch wind data from Windfinder API."""
    params = {
        "limit": -1,
        "timespan": f"{date}T00:00:00+02:00/PT23H59M59S",
        "step": "1m"
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "application/json",
        "wf-api-authorization": f"WF-AUTH wfweb:1.0:{token}"
    }

    try:
        logger.info("Calling API")
        response = requests.get(
            API_BASE_URL,
            params=params,
            headers=headers,
            timeout=DEFAULT_TIMEOUT
        )
        response.raise_for_status()
        logger.info(f"API response status: {response.status_code}")
        
        # Parse response
        response_data = response.json()
        
        # Handle both possible response formats:
        if isinstance(response_data, list):
            return response_data  # Directly return the list
        elif isinstance(response_data, dict):
            return response_data.get('items', [])  # Return items from dict
        else:
            logger.error(f"Unexpected response format: {type(response_data)}")
            return []
            
    except RequestException as e:
        logger.error(f"API request failed for date {date}: {e}")
        raise
    except ValueError as e:
        logger.error(f"Failed to parse API response: {e}")
        raise


# Convert raw API data into structured format with time, wind direction, speed, gusts, and temperature
def transform_data(raw_data):
    """Transform raw API data into our desired format."""
    transformed = []
    for item in raw_data:
        try:
            # Parse the full timestamp
            full_time = item.get('dtl', '')
            if full_time:
                # Extract just the time portion (HH:MM)
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
    print(transformed)
    return transformed


# Calculate yesterday's date for data processing
def get_processing_date():
    """Determine the date to process (yesterday by default)."""
    return (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')


# Main execution function that orchestrates the entire data collection process
def main():
    try:
        token = get_token()

        processing_date = get_processing_date()
        logger.info(f"Starting data collection for {processing_date}")

        # Fetch data from API
        raw_data = fetch_wind_data(processing_date, token)
        if not raw_data:
            logger.warning("No data received from API")
            return
        print("got data from API")

        # Transform data
        transformed_data = transform_data(raw_data)
        if not transformed_data:
            logger.warning("No valid data after transformation")
            return
        print("data transformed")

        # Save to Firestore
        db = initialize_firestore()
        save_to_firestore(db, transformed_data, processing_date)
        print("data saved to firebase")

        logger.info("Script completed successfully")
    except Exception as e:
        logger.error(f"Script failed: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()