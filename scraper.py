import json
import os
import requests
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import credentials, firestore
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
LOCATION = "wannsee"
DEFAULT_TIMEOUT = 30  # seconds

def initialize_firestore():
    if 'FIREBASE_CREDENTIALS' in os.environ:
        cred_dict = json.loads(os.environ['FIREBASE_CREDENTIALS'])
        cred = credentials.Certificate(cred_dict)
    else:
        cred = credentials.Certificate(".secrets/serviceAccountKey.json")
    firebase_admin.initialize_app(cred)
    return firestore.client()

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
    except Exception as e:
        logger.error(f"Failed to save data to Firestore: {e}")
        raise

def fetch_wind_data(date):
    """Fetch wind data from Windfinder API."""
    params = {
        "limit": -1,
        "timespan": f"{date}T00:00:00+02:00/PT23H59M59S",
        "step": "1m"
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "application/json",
        "wf-api-authorization": "WF-AUTH wfweb:1.0:f7af00b26a99c5998805b06c76d6f78f"
    }

    try:
        response = requests.get(
            API_BASE_URL,
            params=params,
            headers=headers,
            timeout=DEFAULT_TIMEOUT
        )
        response.raise_for_status()
        return response.json().get('items', [])
    except RequestException as e:
        logger.error(f"API request failed for date {date}: {e}")
        raise
    except ValueError as e:
        logger.error(f"Failed to parse API response: {e}")
        raise

def transform_data(raw_data):
    """Transform raw API data into our desired format."""
    transformed = []
    for item in raw_data:
        try:
            transformed.append({
                'Time': item.get('timestamp', ''),
                'Wind Direction': f"{item.get('windDirection', 0)}°",
                'Wind Speed (kts)': round(float(item.get('windSpeed', 0), 1),
                'Wind Gusts (kts)': round(float(item.get('windGust', 0), 1),
                'Temperature': item.get('temperature'),
                'Humidity': item.get('humidity')
            })
        except (TypeError, ValueError) as e:
            logger.warning(f"Skipping malformed data item: {e}")
    return transformed

def get_processing_date():
    """Determine the date to process (yesterday by default)."""
    return (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

def main():
    try:
        processing_date = get_processing_date()
        logger.info(f"Starting data collection for {processing_date}")
        
        # Fetch data from API
        raw_data = fetch_wind_data(processing_date)
        if not raw_data:
            logger.warning("No data received from API")
            return

        # Transform data
        transformed_data = transform_data(raw_data)
        if not transformed_data:
            logger.warning("No valid data after transformation")
            return
        
        # Save to Firestore
        db = initialize_firestore()
        save_to_firestore(db, transformed_data, processing_date)
        
        logger.info("Script completed successfully")
    except Exception as e:
        logger.error(f"Script failed: {e}")
        raise SystemExit(1)

if __name__ == "__main__":
    main()