import os
import re
import csv
import requests
import datetime

# Configuration
REDFIN_URL = os.getenv("REDFIN_URL", "https://www.redfin.com/RI/Providence/384-Benefit-St-02903/unit-3/home/52248182")
SCRAPER_URL = os.getenv("SCRAPER_URL", "http://localhost:5006/scrape")
HISTORY_FILE = "redfin_price_history.csv"

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

def main():
    print(f"[{datetime.datetime.now()}] Starting scrape for: {REDFIN_URL}")

    try:
        response = requests.post(SCRAPER_URL, json={"url": REDFIN_URL, "wait": 3000}, stream=True)
        if response.status_code != 200:
            print(f"Error: Scraper returned status {response.status_code}")
            return

        # Parse multipart/mixed response
        content_type = response.headers.get("Content-Type", "")
        boundary_match = re.search(r'boundary=(.*)', content_type)
        if not boundary_match:
            print("Error: Multipart boundary not found")
            return

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
            # Pick the largest part that contains Redfin-specific HTML
            if "data-rf-test-id" in body and len(body) > len(html_content):
                html_content = body

        if not html_content and len(parts) > 2:
            header_end = parts[2].find(b"\r\n\r\n")
            html_content = parts[2][header_end+4:].decode('utf-8', errors='ignore')

        if not html_content:
            print("Error: Could not find HTML part in response")
            return

        price_str = extract_price(html_content)
        if not price_str:
            print("Error: Could not extract price from HTML")
            return

        price = price_str.replace(",", "")
        print(f"Success! Current Redfin Estimate: ${price_str}")

        # Append to history CSV
        file_exists = os.path.isfile(HISTORY_FILE)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with open(HISTORY_FILE, "a", newline="") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["Timestamp", "Price", "URL"])
            writer.writerow([timestamp, price, REDFIN_URL])

        print(f"Price saved to {HISTORY_FILE}")

    except Exception as e:
        print(f"Fatal Error: {e}")

if __name__ == "__main__":
    main()
