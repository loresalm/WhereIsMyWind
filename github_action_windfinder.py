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
from selenium.webdriver.support.ui import WebDriverWait  # type: ignore
from selenium.webdriver.support import expected_conditions as EC  # type: ignore
from selenium.common.exceptions import TimeoutException, WebDriverException  # type: ignore
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
            speed_str = speed_match.group(1).replace(' ', '').strip()
            data['Wind Speed (kts)'] = float(speed_str)
        except ValueError:
            print(f"Could not parse wind speed: {speed_match.group(1)}")

    gusts_match = re.search(r'Wind gusts:\s+([\d.]+)\s*kts', tooltip_text)
    if gusts_match:
        try:
            gusts_str = gusts_match.group(1).replace(' ', '').strip()
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


def create_driver_with_retries(max_retries=3):
    """Create Chrome driver with enhanced options and retry logic"""
    for attempt in range(max_retries):
        try:
            options = Options()
            options.add_argument('--headless')
            options.add_argument('--disable-gpu')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-extensions')
            options.add_argument('--disable-background-timer-throttling')
            options.add_argument('--disable-backgrounding-occluded-windows')
            options.add_argument('--disable-renderer-backgrounding')
            options.add_argument('--window-size=1920,1080')
            
            # Set timeouts
            options.add_argument('--timeout=300')
            options.add_argument('--page-load-strategy=normal')
            
            user_data_dir = tempfile.mkdtemp()
            options.add_argument(f"--user-data-dir={user_data_dir}")

            driver = webdriver.Chrome(options=options)
            
            # Set timeouts programmatically as well
            driver.set_page_load_timeout(300)  # 5 minutes
            driver.implicitly_wait(30)  # 30 seconds
            
            print(f"Successfully created Chrome driver on attempt {attempt + 1}")
            return driver
            
        except Exception as e:
            print(f"Attempt {attempt + 1} failed to create driver: {e}")
            if attempt == max_retries - 1:
                raise
            time.sleep(5)  # Wait before retry


def load_page_with_retries(driver, url, max_retries=3):
    """Load a page with retry logic"""
    for attempt in range(max_retries):
        try:
            print(f"Attempting to load {url} (attempt {attempt + 1})")
            driver.get(url)
            
            # Wait for page to be ready
            WebDriverWait(driver, 60).until(
                lambda driver: driver.execute_script("return document.readyState") == "complete"
            )
            
            print(f"Successfully loaded page on attempt {attempt + 1}")
            return True
            
        except (TimeoutException, WebDriverException) as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            if attempt == max_retries - 1:
                raise
            time.sleep(10)  # Wait before retry


def main():
    driver = None
    try:
        # Create driver with retries
        driver = create_driver_with_retries()
        
        yesterday = datetime.now() - timedelta(days=1)
        data_date = yesterday.strftime('%Y-%m-%d')
        url = f'https://www.windfinder.com/report/wannsee/{data_date}'
        
        # Load page with retries
        load_page_with_retries(driver, url)
        
        # Wait additional time for JavaScript to load
        print("Waiting for page to fully load...")
        time.sleep(10)

        # Wait for the wind chart to be present
        wait = WebDriverWait(driver, 60)
        wind_chart = wait.until(
            EC.presence_of_element_located((By.ID, 'entrypoint-wind-chart'))
        )
        print("Wind chart found!")
        
        # Additional wait for chart to be interactive
        time.sleep(5)
        
        x_start, x_offset = -300, 0
        wind_data_db = []
        
        for i in range(24):
            print(f"Processing hour {i + 1}/24")
            try:
                data = get_wind_banner(driver, wind_chart, x_start, x_offset, False)
                wind_data_db.append(data)
                x_offset += 26
            except Exception as e:
                print(f"Error processing hour {i + 1}: {e}")
                # Add empty data to maintain 24-hour structure
                wind_data_db.append({
                    'Day': None,
                    'Time': None,
                    'Wind Direction': None,
                    'Wind Speed (kts)': None,
                    'Wind Gusts (kts)': None
                })

        print(f"Collected {len(wind_data_db)} data points")
  
        # Save to Firestore
        db = initialize_firestore()
        save_to_firestore(db, wind_data_db, data_date, location="wannsee")

    except Exception as e:
        print(f"Error in script: {e}")
        raise  # Re-raise the exception to make GitHub Actions aware of the failure
    finally:
        if driver:
            driver.quit()
        print("Script completed.")


if __name__ == "__main__":
    main()