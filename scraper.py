import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
import tempfile
import os
import pandas as pd 
import re
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta


def extract_tooltip_data(tooltip_text):
    data = {}
    # Extract day and time (keep time as a string)
    time_match = re.search(r'([A-Za-z]+),\s+(\d+:\d+)', tooltip_text)
    if time_match:
        data['Day'] = time_match.group(1)  # e.g., "Wednesday"
        data['Time'] = time_match.group(2)  # e.g., "06:00" (as string)
    # Extract wind direction (keep as string)
    dir_match = re.search(r'Wind direction:\s+(\d+°\s*/\s*[A-Z]+)', tooltip_text)
    if dir_match:
        data['Wind Direction'] = dir_match.group(1).strip()  # e.g., "280° / W"
    # Extract wind speed (convert to float)
    speed_match = re.search(r'Wind speed:\s+([\d.]+)\s*kts', tooltip_text)
    if speed_match:
        try:
            # Remove non-breaking space (\u202f) and convert to float
            speed_str = speed_match.group(1).replace('\u202f', '').strip()
            data['Wind Speed (kts)'] = float(speed_str)  # e.g., 5.2
        except ValueError:
            print(f"Could not parse wind speed: {speed_match.group(1)}")
    
    # Extract wind gusts (convert to float)
    gusts_match = re.search(r'Wind gusts:\s+([\d.]+)\s*kts', tooltip_text)
    if gusts_match:
        try:
            # Remove non-breaking space (\u202f) and convert to float
            gusts_str = gusts_match.group(1).replace('\u202f', '').strip()
            data['Wind Gusts (kts)'] = float(gusts_str)  # e.g., 11.5
        except ValueError:
            print(f"Could not parse wind gusts: {gusts_match.group(1)}")

    return data


def get_wind_banner(driver, x_start, x_offset, debug):
    # Move to the center of the chart
    actions = ActionChains(driver)
    actions.move_to_element_with_offset(wind_chart, x_offset + x_start, 0).click().perform() 
    print(f"Moved to {x_offset + x_start} of wind chart")

    # Wait for tooltip to appear
    time.sleep(1)

    if debug:
        # Take a screenshot
        os.makedirs("screenshots", exist_ok=True)
        driver.save_screenshot(f"screenshots/wind_chart_{x_offset}.png")
        print("Screenshot saved")
    data = {'Day': None,
            'Time': None,
            'Wind Direction': None,
            'Wind Speed (kts)': None,
            'Wind Gusts (kts)': None}
    try:
        tooltip = driver.find_element(By.CSS_SELECTOR, ".chart-tooltip")
        tooltip_text = tooltip.text
        print("------------------------")
        print("Tooltip content:")
        print(tooltip_text)
        data = extract_tooltip_data(tooltip_text)
        print("Extracted content:")
        print(data)
        print("------------------------")
    except Exception as e:
        print(f"no tooltip found {e}")
    return data


# Initialize Firebase Firestore
def initialize_firestore():
    cred = credentials.Certificate("serviceAccountKey.json")  # Replace with your JSON file
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    return db


def save_to_firestore(db, all_wind_data, data_date, location="wannsee"):
    try:
        # Create a document with the date as ID
        doc_ref = db.collection("wind_data").document(data_date)

        # Prepare the data to be stored
        data_to_store = {
            "location": location,
            "date": data_date,
            "records": all_wind_data,  # This stores all 24 records as an array
            "timestamp": datetime.now()
        }

        # Add data to Firestore
        doc_ref.set(data_to_store)

        print(f"Data for {data_date} saved to Firestore with {len(all_wind_data)} records!")
    except Exception as e:
        print(f"Error saving to Firestore: {e}")

debug = False 
# Selenium setup
options = Options()
options.add_argument('--headless')
options.add_argument('--disable-gpu')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')

# Set a unique user data directory to avoid session conflicts
user_data_dir = tempfile.mkdtemp()
options.add_argument(f"--user-data-dir={user_data_dir}")

# Explicitly setting the ChromeDriver path
driver = webdriver.Chrome(options=options)

yesterday = datetime.now() - timedelta(days=1)
data_date = yesterday.strftime('%Y-%m-%d')
# data_date = "2025-05-09"

# Open the webpage
driver.get(f'https://www.windfinder.com/report/wannsee/{data_date}')

# Wait for the page to fully load
time.sleep(5)

# Handle the cookie banner if it appears
try:
    # Using the ID from the HTML snippet you provided
    accept_button = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.ID, "accept-choices"))
    )
    accept_button.click()
    print("Cookie banner accepted.")
    time.sleep(2)
except Exception as e:
    print(f"No cookie banner found or already accepted: {e}")

# Locate the wind chart
try:
    wind_chart = driver.find_element(By.ID, 'entrypoint-wind-chart')
    size = wind_chart.size
    location = wind_chart.location
    x_loc = location['x']
    wchar = size['width']
    print("Wind chart found!")
    print(f"width char: {wchar}")
    print(f"x loaction char: {x_loc}")
    driver.execute_script("arguments[0].scrollIntoView(true);", wind_chart)
    time.sleep(1)
    x_start = -300
    x_offset = 0
    wind_data = {'Day': [],
                 'Time': [],
                 'Wind Direction': [],
                 'Wind Speed (kts)': [],
                 'Wind Gusts (kts)': []}
    wind_data_db = []
    for i in range(24):
        data = get_wind_banner(driver, x_start, x_offset, debug)
        wind_data_db.append(data)
        if debug:
            for key, value in data.items():
                wind_data[key].append(value)
        x_offset += 26

    if debug:
        wind_df = pd.DataFrame(wind_data)
        wind_df.to_csv('wind_data.csv', index=False)
    # Initialize and save data
    db = initialize_firestore()
    save_to_firestore(db, wind_data_db, data_date, location="wannsee")

except Exception as e:
    print(f"Error in main script: {e}")

finally:
    # Close the driver
    driver.quit()
    print("Script completed.")






