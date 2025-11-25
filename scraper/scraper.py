import requests
import csv
from bs4 import BeautifulSoup
import json
import logging
import os
from collections import OrderedDict
from hashlib import sha256
from urllib.parse import urljoin

# --- CONFIGURATION ---
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
BASE_URL = "https://my.jobstreet.com"

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def generate_hashed_id(job_info):
    raw_id = f"{job_info.get('jobTitle', '')}|{job_info.get('jobCompany', '')}"
    return sha256(raw_id.encode('utf-8')).hexdigest()

def fetch_data(url):
    # --- 🔴 PASTE COOKIE HERE 🔴 ---
    headers = {
        'User-Agent': USER_AGENT,
        'Cookie': '' 
    }

    if not headers['Cookie']:
        print("⚠️ WARNING: 'Cookie' is empty. You will likely be blocked.")

    print(f"🔎 Fetching URL: {url}...")

    try:
        response = requests.get(url=url, headers=headers, timeout=10)
        print(f"📡 Status Code: {response.status_code}")

        # DEBUG STEP: Save the raw HTML to see what we actually got
        with open("debug_page.html", "w", encoding="utf-8") as f:
            f.write(response.text)
        print("📝 Saved 'debug_page.html'. Open this file in Chrome to see if you were blocked!")

        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        
        # Try finding job cards
        job_listings = soup.select("[data-automation='normalJob']")
        print(f"👀 Found {len(job_listings)} raw job elements.")

        if not job_listings:
            print("❌ No jobs found. This usually means Cloudflare blocked you.")
            return []

        job_data = []
        for job in job_listings:
            job_info = OrderedDict()
            try:
                # Basic Parsing
                title_tag = job.find('a', {'data-automation': 'jobTitle'})
                company_tag = job.find('a', {'data-automation': 'jobCompany'})
                
                job_info['jobTitle'] = title_tag.get_text(strip=True) if title_tag else "N/A"
                job_info['jobCompany'] = company_tag.get_text(strip=True) if company_tag else "N/A"
                
                # Get Link
                if title_tag and title_tag.get('href'):
                    job_info['jobURL'] = urljoin(BASE_URL, title_tag.get('href'))
                else:
                    job_info['jobURL'] = "N/A"

                job_info['uniqueId'] = generate_hashed_id(job_info)
                job_data.append(job_info)

            except Exception as e:
                print(f"Error parsing a card: {e}")
                continue

        return job_data

    except Exception as e:
        print(f"💥 Critical Error: {e}")
        return []

def save_to_csv(job_data):
    if not job_data:
        print("⚠️ save_to_csv called with empty list. Nothing to save.")
        return
    
    filename = "job_results.csv"
    try:
        keys = job_data[0].keys()
        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(job_data)
        print(f"✅ SUCCESS: Created '{filename}' with {len(job_data)} rows.")
        print(f"📂 File location: {os.path.abspath(filename)}")
    except Exception as e:
        print(f"❌ Failed to write CSV: {e}")

if __name__ == "__main__":
    # 1. Test File Creation Permission
    try:
        with open("test_permission.csv", "w") as f:
            f.write("test,row\n1,2")
        print("✅ System Check: Write permissions are GOOD.")
    except Exception as e:
        print(f"❌ System Check Failed: Cannot write files. Error: {e}")
        exit()

    # 2. Run Scraper
    url = "https://my.jobstreet.com/engineering-intern-jobs/in-Kuala-Lumpur"
    jobs = fetch_data(url)
    
    if jobs:
        save_to_csv(jobs)
    else:
        print("⚠️ Program finished, but NO jobs were collected.")