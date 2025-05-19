import time
import re
import json
import tempfile
from datetime import datetime, timedelta
from os import environ
from selenium import webdriver   # type: ignore
from selenium.webdriver.common.by import By  # type: ignore
from selenium.webdriver.chrome.options import Options  # type: ignore
from selenium.webdriver.common.action_chains import ActionChains  # noqa: E501 # type: ignore
import firebase_admin  # type: ignore
from firebase_admin import credentials, firestore  # type: ignore


def extract_tooltip_data(tooltip_text):
    data = {}
    time_match = re.search(r'([A-Za-z]+),\s+(\d+:\d+)', tooltip_text)
    if time_match:
        data['Day'] = time_match.group(1)
        data['Time'] = time_match.group(2)

    dir_match = re.search(r'Wind direction:\s+(\d+°\s*/\s*[A-Z]+)',
                          tooltip_text)
    if dir_match:
        data['Wind Direction'] = dir_match.group(1).strip()

    speed_match = re.search(r'Wind speed:\s+([\d.]+)\s*kts', tooltip_text)
    if speed_match:
        try:
            speed_str = speed_match.group(1).replace(' ', '').strip()
            data['Wind Speed (kts)'] = float(speed_str)
        except ValueError:
            print(f"Could not parse wind speed: {speed_match.group(1)}")

    gusts_match = re.search(r'Wind gusts:\s+([\d.]+)\s*kts', tooltip_text)
    if gusts_match:
        try:
            gusts_str = gusts_match.group(1).replace(' ', '').strip()
            data['Wind Gusts (kts)'] = float(gusts_str)
        except ValueError:
            print(f"Could not parse wind gusts: {gusts_match.group(1)}")

    return data


def initialize_firestore():
    cred_json = environ.get('FIREBASE_CREDENTIALS')
    if not cred_json:
        raise ValueError(
            "No Firebase credentials found in environment variables")

    cred_dict = json.loads(cred_json)
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)
    return firestore.client()


def save_to_firestore(db, all_wind_data, data_date, location="wannsee"):
    try:
        doc_ref = db.collection("wind_data").document(data_date)
        data_to_store = {
            "location": location,
            "date": data_date,
            "records": all_wind_data,
            "timestamp": datetime.now()
        }
        doc_ref.set(data_to_store)
        print(f"""Data for {data_date} saved to Firestore
              with {len(all_wind_data)} records!""")
    except Exception as e:
        print(f"Error saving to Firestore: {e}")


def get_wind_banner(driver, wind_chart, x_start, x_offset, debug):
    actions = ActionChains(driver)
    actions.move_to_element_with_offset(wind_chart,
                                        x_offset + x_start,
                                        0).click().perform()
    time.sleep(1)

    data = {'Day': None,
            'Time': None,
            'Wind Direction': None,
            'Wind Speed (kts)': None,
            'Wind Gusts (kts)': None}
    try:
        tooltip = driver.find_element(By.CSS_SELECTOR, ".chart-tooltip")
        tooltip_text = tooltip.text
        data = extract_tooltip_data(tooltip_text)
    except Exception as e:
        print(f"No tooltip found: {e}")
    return data


def main():
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    user_data_dir = tempfile.mkdtemp()
    options.add_argument(f"--user-data-dir={user_data_dir}")

    driver = webdriver.Chrome(options=options)
    yesterday = datetime.now() - timedelta(days=1)
    data_date = yesterday.strftime('%Y-%m-%d')
    driver.get(f'https://www.windfinder.com/report/wannsee/{data_date}')
    time.sleep(5)

    try:
        wind_chart = driver.find_element(By.ID, 'entrypoint-wind-chart')
        x_start, x_offset = -300, 0
        wind_data_db = []
        for _ in range(24):
            data = get_wind_banner(driver,
                                   wind_chart,
                                   x_start,
                                   x_offset,
                                   False)
            wind_data_db.append(data)
            x_offset += 26

        db = initialize_firestore()
        save_to_firestore(db, wind_data_db, data_date, location="wannsee")

    except Exception as e:
        print(f"Error in script: {e}")
    finally:
        driver.quit()
        print("Script completed.")


if __name__ == "__main__":
    main()
