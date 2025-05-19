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
            
            # Enhanced headless options for stability
            options.add_argument('--headless=new')  # Use new headless mode
            options.add_argument('--disable-gpu')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-extensions')
            options.add_argument('--disable-background-timer-throttling')
            options.add_argument('--disable-backgrounding-occluded-windows')
            options.add_argument('--disable-renderer-backgrounding')
            options.add_argument('--disable-features=TranslateUI')
            options.add_argument('--disable-ipc-flooding-protection')
            
            # Memory and performance optimization
            options.add_argument('--max_old_space_size=4096')
            options.add_argument('--disable-background-networking')
            options.add_argument('--disable-default-apps')
            options.add_argument('--disable-sync')
            
            # Window and display options
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--start-maximized')
            options.add_argument('--disable-infobars')
            
            # Security and stability options
            options.add_argument('--disable-web-security')
            options.add_argument('--allow-running-insecure-content')
            options.add_argument('--ignore-certificate-errors')
            options.add_argument('--ignore-ssl-errors')
            options.add_argument('--ignore-certificate-errors-spki-list')
            
            # User agent to avoid detection
            options.add_argument('--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            
            # Crash handling
            options.add_argument('--disable-crash-reporter')
            options.add_argument('--crash-dumps-dir=/tmp')
            
            # Create temporary user data directory
            user_data_dir = tempfile.mkdtemp()
            options.add_argument(f"--user-data-dir={user_data_dir}")
            
            # Set page load strategy to none to avoid hanging
            options.page_load_strategy = 'none'

            driver = webdriver.Chrome(options=options)
            
            # Set timeouts
            driver.set_page_load_timeout(60)  # Reduced timeout
            driver.implicitly_wait(10)  # Reduced implicit wait
            
            # Test if driver is working by navigating to a simple page
            driver.get("about:blank")
            
            print(f"Successfully created Chrome driver on attempt {attempt + 1}")
            return driver
            
        except Exception as e:
            print(f"Attempt {attempt + 1} failed to create driver: {e}")
            if attempt == max_retries - 1:
                raise
            time.sleep(5)  # Wait before retry


def load_page_with_retries(driver, url, max_retries=3):
    """Load a page with retry logic and better error handling"""
    for attempt in range(max_retries):
        try:
            print(f"Attempting to load {url} (attempt {attempt + 1})")
            
            # First check if driver is still alive
            try:
                driver.current_url
            except Exception as e:
                print(f"Driver appears to be dead: {e}")
                raise WebDriverException("Driver session lost")
            
            # Use execute_script to navigate as it's more reliable
            driver.execute_script(f"window.location.href = '{url}';")
            
            # Wait for page to start loading
            time.sleep(3)
            
            # Wait for page to be ready with a shorter timeout
            max_wait_time = 30
            start_time = time.time()
            
            while time.time() - start_time < max_wait_time:
                try:
                    ready_state = driver.execute_script("return document.readyState")
                    if ready_state == "complete":
                        break
                    elif ready_state == "interactive":
                        # Page is interactive, wait a bit more but don't wait for complete
                        time.sleep(2)
                        break
                    time.sleep(1)
                except Exception as e:
                    print(f"Error checking ready state: {e}")
                    time.sleep(1)
            
            # Verify we actually loaded the page
            current_url = driver.current_url
            if url.split('/')[-1] in current_url:
                print(f"Successfully loaded page on attempt {attempt + 1}")
                return True
            else:
                print(f"Page loaded but URL mismatch. Expected: {url}, Got: {current_url}")
                if attempt == max_retries - 1:
                    return True  # Accept partial success on last attempt
                
        except (TimeoutException, WebDriverException) as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            if attempt == max_retries - 1:
                raise
            time.sleep(10)  # Wait before retry
            
            # Try to recover the driver if it seems dead
            try:
                driver.current_url
            except:
                # Driver is dead, we need to recreate it
                print("Driver appears dead, will need to recreate...")
                raise WebDriverException("Driver needs recreation")


def main():
    driver = None
    driver_recreated = False
    
    try:
        # Create driver with retries
        driver = create_driver_with_retries()
        
        yesterday = datetime.now() - timedelta(days=1)
        data_date = yesterday.strftime('%Y-%m-%d')
        url = f'https://www.windfinder.com/report/wannsee/{data_date}'
        
        # Load page with retries and driver recreation if needed
        max_load_attempts = 2
        for load_attempt in range(max_load_attempts):
            try:
                load_page_with_retries(driver, url)
                break
            except WebDriverException as e:
                if "Driver needs recreation" in str(e) and load_attempt < max_load_attempts - 1:
                    print("Recreating driver due to failure...")
                    if driver:
                        try:
                            driver.quit()
                        except:
                            pass
                    driver = create_driver_with_retries()
                    driver_recreated = True
                else:
                    raise
        
        # Wait additional time for JavaScript to load
        print("Waiting for page to fully load...")
        time.sleep(10)

        # Try to find the wind chart with multiple selectors
        chart_selectors = [
            'entrypoint-wind-chart',
            'wind-chart',
            '.wind-chart',
            '[id*="wind"]',
            '[class*="chart"]'
        ]
        
        wind_chart = None
        for selector in chart_selectors:
            try:
                if selector.startswith('.') or selector.startswith('['):
                    wind_chart = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                else:
                    wind_chart = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.ID, selector))
                    )
                print(f"Wind chart found with selector: {selector}")
                break
            except:
                continue
        
        if not wind_chart:
            print("Could not find wind chart element. Available elements:")
            elements = driver.find_elements(By.TAG_NAME, '*')
            for elem in elements[:20]:  # Print first 20 elements for debugging
                try:
                    print(f"Tag: {elem.tag_name}, ID: {elem.get_attribute('id')}, Class: {elem.get_attribute('class')}")
                except:
                    pass
            raise Exception("Wind chart element not found")
        
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
        # Print additional debugging information
        if driver:
            try:
                print(f"Current URL: {driver.current_url}")
                print(f"Page title: {driver.title}")
            except:
                print("Could not retrieve driver information")
        raise  # Re-raise the exception to make GitHub Actions aware of the failure
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
        print("Script completed.")


if __name__ == "__main__":
    main()