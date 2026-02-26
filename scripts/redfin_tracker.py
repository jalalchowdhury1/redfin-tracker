import os
import re
import csv
import requests
import datetime
import json
import time
import random
import gspread
from google.oauth2.service_account import Credentials

# Configuration
REDFIN_URL = os.getenv("REDFIN_URL", "https://www.redfin.com/RI/Providence/384-Benefit-St-02903/unit-3/home/52248182")
SCRAPER_URL = os.getenv("SCRAPER_URL", "http://localhost:5006/scrape")
SHEET_URL = os.getenv("SHEET_URL", "https://docs.google.com/spreadsheets/d/1OrContixGYzHNT_DaO76p3rP1nvNamRs9r3fuJLsf-k/edit")
GOOGLE_SHEETS_CREDENTIALS = os.getenv("GOOGLE_SHEETS_CREDENTIALS") # Raw JSON string
HISTORY_FILE = "redfin_price_history.csv"

# Browser-like headers to help bypass firewalls
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.google.com/",
    "DNT": "1",
    "Upgrade-Insecure-Requests": "1"
}

def extract_price(html_content):
    """
    Extract the Redfin Estimate price from the HTML content.
    Targeting the 'abp-price' test ID which Redfin uses for the main price display.
    """
    # Primary: target the abp-price container (current estimate)
    abp_match = re.search(
        r'data-rf-test-id="abp-price"[^>]*>.*?\$([\d,]+)',
        html_content, re.DOTALL
    )
    if abp_match:
        return abp_match.group(1)

    # Fallback: RedfinEstimateValueHeader section
    esth_match = re.search(
        r'RedfinEstimateValueHeader[^>]*>.*?\$([\d,]+)',
        html_content, re.DOTALL
    )
    if esth_match:
        return esth_match.group(1)

    # Fallback 2: JSON blob "sectionPreviewText":"$NNN,NNN"
    json_match = re.search(r'"sectionPreviewText":\s*"\\?\$([\d,]+)', html_content)
    if json_match:
        return json_match.group(1)

    return None

def update_google_sheet(price_str):
    if not GOOGLE_SHEETS_CREDENTIALS:
        print("Warning: GOOGLE_SHEETS_CREDENTIALS not set, skipping sheet update.")
        return

    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets"]
        creds_dict = json.loads(GOOGLE_SHEETS_CREDENTIALS)
        service_account_email = creds_dict.get("client_email")
        print(f"Using service account: {service_account_email}")
        
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)
        
        # Open by URL and select "Redfin" sheet
        sh = client.open_by_url(SHEET_URL)
        worksheet = sh.worksheet("Redfin")
        
        # Today's date in format DD-MM-YYYY
        today_str = datetime.datetime.now().strftime("%d-%m-%Y")
        print(f"Searching for date: {today_str} in Column A...")
        
        # Get all values in Column A
        col_a = worksheet.col_values(1)
        
        row_index = -1
        for i, val in enumerate(col_a):
            if today_str in val:
                row_index = i + 1 # 1-indexed
                break
        
        if row_index != -1:
            # Update Column C (index 3)
            val_to_put = f"${price_str}"
            worksheet.update_cell(row_index, 3, val_to_put)
            print(f"✓ Updated Google Sheet row {row_index}, Column C with: {val_to_put}")
        else:
            print(f"Warning: Could not find row for date {today_str} in Column A.")
            
    except Exception as e:
        print(f"Error updating Google Sheet: {e}")

def run_scrape():
    """Performs a single scrape attempt."""
    print(f"[{datetime.datetime.now()}] Attempting scrape for: {REDFIN_URL}")
    
    payload = {
        "url": REDFIN_URL,
        "wait": 5000,
        "headers": HEADERS
    }

    try:
        response = requests.post(SCRAPER_URL, json=payload, stream=True, timeout=60)
        
        # Identifty Amazon WAF or general CAPTCHA
        is_waf_captcha = 'captcha' in response.headers.get('x-amzn-waf-action', '').lower()
        if is_waf_captcha:
            print("! Blocked by Amazon WAF CAPTCHA firewall")
            return None

        # Parse response parts
        content_type = response.headers.get("Content-Type", "")
        boundary_match = re.search(r'boundary=(.*)', content_type)
        if not boundary_match:
            print("Error: Multipart boundary not found")
            return None

        boundary = boundary_match.group(1)
        parts = response.content.split(f"--{boundary}".encode())

        html_content = ""
        for part in parts:
            if len(part) < 500:
                continue
            header_end = part.find(b"\r\n\r\n")
            if header_end == -1:
                continue
            body = part[header_end+4:].decode('utf-8', errors='ignore')

            # Detect CAPTCHA indicators in body
            if "captcha" in body.lower() and "verify" in body.lower():
                print("! CAPTCHA challenge detected in page content")
                return None
                
            if "data-rf-test-id" in body and len(body) > len(html_content):
                html_content = body

        if not html_content:
            print("Error: Could not find meaningful HTML in response")
            return None

        return extract_price(html_content)

    except Exception as e:
        print(f"Scrape attempt failed: {e}")
        return None

def main():
    max_retries = 3
    price_str = None

    for attempt in range(max_retries):
        if attempt > 0:
            wait_time = random.randint(20, 60)
            print(f"Waiting {wait_time}s before retry {attempt+1}/{max_retries}...")
            time.sleep(wait_time)

        price_str = run_scrape()
        if price_str:
            break
        
    if not price_str:
        print("Fatal: All scrape attempts failed or were blocked by CAPTCHA.")
        return

    print(f"Success! Final Price Extracted: ${price_str}")
    update_google_sheet(price_str)

    # Local backup
    price_numeric = price_str.replace(",", "")
    file_exists = os.path.isfile(HISTORY_FILE)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(HISTORY_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Timestamp", "Price", "URL"])
        writer.writerow([timestamp, price_numeric, REDFIN_URL])

    print(f"Price saved to local backup {HISTORY_FILE}")

if __name__ == "__main__":
    main()
