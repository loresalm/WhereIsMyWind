import requests
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import credentials, firestore


# Initialize Firebase Firestore
def initialize_firestore():
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)
    return firestore.client()


def save_to_firestore(db, data, data_date, location="wannsee"):
    try:
        doc_ref = db.collection("wind_data").document(data_date)
        data_to_store = {
            "location": location,
            "date": data_date,
            "records": data,
            "timestamp": datetime.now()
        }
        doc_ref.set(data_to_store)
        print(f"Data for {data_date} saved to Firestore with {len(data)} records!")
    except Exception as e:
        print(f"Error saving to Firestore: {e}")
        raise

def fetch_wind_data(date):
    base_url = "https://api.windfinder.com/v2/spots/de575/reports/"
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
        response = requests.get(base_url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json().get('items', [])
    except requests.exceptions.RequestException as e:
        print(f"API request failed: {e}")
        raise

def transform_data(raw_data):
    transformed = []
    for item in raw_data:
        transformed.append({
            'Time': item.get('timestamp', ''),
            'Wind Direction': f"{item.get('windDirection', 0)}°",
            'Wind Speed (kts)': item.get('windSpeed', 0),
            'Wind Gusts (kts)': item.get('windGust', 0)
        })
    return transformed

def main():
    try:
        # Get yesterday's date
        yesterday = datetime.now() - timedelta(days=1)
        data_date = yesterday.strftime('%Y-%m-%d')
        
        # Fetch data from API
        raw_data = fetch_wind_data(data_date)
        if not raw_data:
            print("No data received from API")
            return

        # Transform data for Firestore
        transformed_data = transform_data(raw_data)
        
        # Initialize and save to Firestore
        db = initialize_firestore()
        save_to_firestore(db, transformed_data, data_date)
        
        print("Script completed successfully")
    except Exception as e:
        print(f"Script failed: {e}")
        raise

if __name__ == "__main__":
    main()