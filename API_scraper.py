import requests
from datetime import datetime
import json

# Define the base URL
base_url = "https://api.windfinder.com/v2/spots/de575/reports/"

# Define the parameters
params = {
    "limit": -1,
    "timespan": "2025-05-15T00:00:00+02:00/PT23H59M59S",
    "step": "1m"
}

# Set up headers to mimic a browser request
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.windfinder.com/",
    "DNT": "1",  # Do Not Track
    "Connection": "keep-alive",
    "wf-api-authorization": "WF-AUTH wfweb:1.0:f7af00b26a99c5998805b06c76d6f78f"
}

# Make the GET request
response = requests.get(base_url, params=params, headers=headers)

# Check if the request was successful
if response.status_code == 200:
    print(f"Request successful! Status code: {response.status_code}")
    
    # Parse and print the JSON response
    try:
        data = response.json()
        print(data)
        print("\nResponse Summary:")
        print(f"Number of items: {len(data.get('items', []))}")
        
        # Print first item as a sample if available
        if data.get('items') and len(data.get('items')) > 0:
            print("\nSample data (first item):")
            print(json.dumps(data['items'][0], indent=2))
            
    except json.JSONDecodeError:
        print("Could not parse response as JSON")
        print("Response content:", response.text[:200], "...")  # Show the first 200 characters
else:
    print(f"Request failed with status code: {response.status_code}")
    print("Response content:", response.text[:200], "...")  # Show the first 200 characters

# Optional: Save the full response to a file
with open("windfinder_data.json", "w") as f:
    f.write(response.text)
print("\nFull response saved to 'windfinder_data.json'")