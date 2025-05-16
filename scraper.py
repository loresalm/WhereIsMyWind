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

# Open the webpage
driver.get('https://www.windfinder.com/report/wannsee/2025-05-14')

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

# Scroll to the bottom to ensure the plot is visible
# driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
# time.sleep(2)
# Locate the wind chart
try:
    wind_chart = driver.find_element(By.ID, 'entrypoint-wind-chart')
    print("Wind chart found!")
    driver.execute_script("arguments[0].scrollIntoView(true);", wind_chart)
    time.sleep(1)
    
    # Move to the center of the chart
    actions = ActionChains(driver)
    actions.move_to_element(wind_chart).perform()
    print("Moved to center of wind chart")
    
    # Wait for tooltip to appear
    time.sleep(1)
    
    # Take a screenshot
    os.makedirs("screenshots", exist_ok=True)
    driver.save_screenshot("screenshots/wind_chart_center.png")
    print("Screenshot saved")
    
    # Try different selectors for the tooltip element
    tooltip_selectors = [
        "div.tooltip", 
        "div.chartTooltip", 
        "div[role='tooltip']",
        ".tooltip-container",
        "#chart-tooltip",
        ".chart-tooltip",
        ".wf-tooltip"
    ]
    
    tooltip_found = False
    
    # Try each selector
    for selector in tooltip_selectors:
        try:
            tooltip = driver.find_element(By.CSS_SELECTOR, selector)
            tooltip_text = tooltip.text
            print(f"Found tooltip with selector: {selector}")
            print("Tooltip content:")
            print(tooltip_text)
            tooltip_found = True
            break
        except:
            continue
    
    # If none of the predefined selectors worked, try finding by tooltip content
    if not tooltip_found:
        print("Trying to find tooltip by content...")
        try:
            # Try to find elements containing wind information
            elements = driver.find_elements(By.XPATH, "//*[contains(text(), 'Wind direction') or contains(text(), 'Wind speed')]")
            
            if elements:
                # Find the parent container of the tooltip
                for element in elements:
                    # Go up to potential container element
                    parent = element
                    for _ in range(3):  # Try up to 3 levels up
                        if parent:
                            parent = parent.find_element(By.XPATH, "..")
                            print(f"Parent element text: {parent.text}")
                            if "Wind direction" in parent.text and "Wind speed" in parent.text:
                                print("Found tooltip container by content!")
                                print("Tooltip content:")
                                print(parent.text)
                                tooltip_found = True
                                break
                    if tooltip_found:
                        break
        except Exception as e:
            print(f"Error finding tooltip by content: {e}")
    
    # If still not found, dump the page HTML for inspection
    if not tooltip_found:
        print("Could not find tooltip element. Dumping page HTML for inspection.")
        with open("page_dump.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        print("Page source dumped to page_dump.html")
        
        # Also try printing all visible text on the page to find the tooltip
        try:
            print("All visible text elements on page:")
            text_elements = driver.find_elements(By.XPATH, "//*[text()]")
            for i, elem in enumerate(text_elements[:30]):  # Print first 30 text elements
                try:
                    if elem.is_displayed():
                        print(f"Text element {i}: {elem.text[:100]}...")  # Print first 100 chars
                except:
                    pass
        except Exception as e:
            print(f"Error listing text elements: {e}")

except Exception as e:
    print(f"Error in main script: {e}")
    
finally:
    # Close the driver
    driver.quit()
    print("Script completed.")