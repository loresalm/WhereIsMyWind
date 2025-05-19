import time
import schedule
import sys
import os

# Import your main function
try:
    # If your script is named paste.txt, we need to rename it or import differently
    # For now, let's assume you'll rename paste.txt to wind_scraper.py
    from wind_scraper import main as scraper_main
except ImportError:
    # Fallback if the file is still named paste.txt
    import importlib.util
    spec = importlib.util.spec_from_file_location("scraper", "paste.txt")
    scraper_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scraper_module)
    scraper_main = scraper_module.main

def run_scraper():
    """Run the wind scraper with error handling"""
    try:
        print(f"Starting wind scraper at {time.strftime('%Y-%m-%d %H:%M:%S')}")
        scraper_main()
        print(f"Scraper completed successfully at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    except Exception as e:
        print(f"Error running scraper: {e}")
        # Don't exit on error, wait for next scheduled run

# Schedule the scraper to run daily at 2 AM UTC
schedule.every().day.at("02:00").do(run_scraper)

# Run once immediately when the service starts (optional)
# run_scraper()

print("Wind scraper scheduler started. Waiting for scheduled times...")
print("Scheduled to run daily at 02:00 UTC")

# Keep the script running
while True:
    schedule.run_pending()
    time.sleep(60)  # Check every minute