import requests
import csv
from bs4 import BeautifulSoup
import json
import logging
import os
import sys  # Added to force-fail the build on error
import time
from collections import OrderedDict
from hashlib import sha256
from urllib.parse import urljoin

# --- CONFIGURATION ---
USER_AGENT = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1"
BASE_URL = "https://my.jobstreet.com"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def generate_hashed_id(job_info):
    raw_id = f"{job_info.get('jobTitle', '')}|{job_info.get('jobCompany', '')}|{job_info.get('jobLocation', '')}"
    return sha256(raw_id.encode('utf-8')).hexdigest()

def fetch_data(url):
    # 1. Check for Cookie
    cookie_value = os.environ.get("JOBSTREET_COOKIE")
    if not cookie_value:
        logger.error("❌ CRITICAL: 'JOBSTREET_COOKIE' secret is missing. The bot will be blocked.")
        # We don't exit here, we try anyway, but expect failure.
    
    headers = {
        'User-Agent': USER_AGENT,
        'Cookie': cookie_value if cookie_value else '' 
    }

    logger.info(f"Fetching data from: {url}")

    try:
        response = requests.get(url=url, headers=headers, timeout=10)

        # 2. Check for "Verify you are human" (Cloudflare Block)
        if "challenge-platform" in response.text or "Verify you are human" in response.text:
            logger.error("⛔ BLOCKED: JobStreet is asking for a Captcha. Your Cookie is invalid/expired.")
            return []

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            job_listings = soup.select("[data-automation='normalJob']")
            
            if not job_listings:
                logger.warning("⚠️ Access Successful, but NO jobs found. (Check CSS Selectors)")
                return []

            job_data = []
            for job in job_listings:
                try:
                    job_info = OrderedDict()
                    
                    title_elem = job.find('a', {'data-automation': 'jobTitle'})
                    company_elem = job.find('a', {'data-automation': 'jobCompany'})
                    loc_elem = job.find_all('a', {'data-automation': 'jobLocation'})
                    salary_elem = job.find('span', {'data-automation': 'jobSalary'})
                    date_elem = job.find('span', {'data-automation': 'jobListingDate'})

                    job_info['jobTitle'] = title_elem.get_text(strip=True) if title_elem else "N/A"
                    job_info['jobCompany'] = company_elem.get_text(strip=True) if company_elem else "N/A"
                    job_info['jobLocation'] = ", ".join([l.get_text(strip=True) for l in loc_elem]) if loc_elem else "N/A"
                    
                    # Safe replace for non-breaking spaces
                    salary_text = salary_elem.get_text(strip=True) if salary_elem else "Not Specified"
                    job_info['jobSalary'] = salary_text.replace(u'\xa0', ' ').replace('\\xa', '')

                    if title_elem and title_elem.get('href'):
                        raw_link = title_elem.get('href')
                        job_info['jobURL'] = urljoin(BASE_URL, raw_link) if not raw_link.startswith('http') else raw_link
                    else:
                        job_info['jobURL'] = "N/A"

                    job_info['uniqueId'] = generate_hashed_id(job_info)
                    job_data.append(job_info)

                except Exception:
                    continue

            logger.info(f"✅ Found {len(job_data)} valid jobs.")
            return job_data
        else:
            logger.error(f"❌ Failed to fetch page. Status Code: {response.status_code}")
            return []
    except Exception as e:
        logger.error(f"❌ Network Request Error: {e}")
        return []

def save_to_csv(job_data, filename="job_results.csv"):
    if not job_data: return None
    try:
        file_path = os.path.join(os.getcwd(), filename)
        keys = job_data[0].keys()
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(job_data)
        return file_path
    except Exception as e:
        logger.error(f"❌ Failed to save CSV: {e}")
        return None

def send_chunk_to_discord(webhook_url, job_chunk, page_num, total_pages, file_path=None):
    embed = {
        "title": f"🚀 Job Scraper Report (Page {page_num}/{total_pages})",
        "color": 3066993,
        "fields": [],
        "footer": {"text": "JobStreet Automator"}
    }

    for job in job_chunk:
        salary_text = f" • {job['jobSalary']}" if job['jobSalary'] != "Not Specified" else ""
        field_value = f"🏢 **{job['jobCompany']}**\n📍 {job['jobLocation']}{salary_text}\n[👉 View Job]({job['jobURL']})"
        
        embed["fields"].append({
            "name": f"🔹 {job['jobTitle']}", 
            "value": field_value,
            "inline": False
        })

    payload_dict = {"embeds": [embed]}

    try:
        # Only attach the file on the LAST page
        if file_path and page_num == total_pages:
            with open(file_path, "rb") as f:
                multipart_data = {
                    "file": (os.path.basename(file_path), f),
                    "payload_json": (None, json.dumps(payload_dict))
                }
                requests.post(webhook_url, files=multipart_data)
        else:
            requests.post(webhook_url, json=payload_dict)
            
        logger.info(f"✅ Sent Page {page_num}/{total_pages} to Discord.")
        
    except Exception as e:
        logger.error(f"❌ Discord Chunk Error: {e}")

def send_to_discord(file_path, webhook_url, job_data):
    if not job_data: return
    CHUNK_SIZE = 10
    chunks = [job_data[i:i + CHUNK_SIZE] for i in range(0, len(job_data), CHUNK_SIZE)]
    total_pages = len(chunks)

    logger.info(f"📤 Sending {len(job_data)} jobs in {total_pages} batches...")

    for i, chunk in enumerate(chunks):
        send_chunk_to_discord(webhook_url, chunk, i + 1, total_pages, file_path)
        if i + 1 < total_pages:
            time.sleep(1)

def start_scraping_worker():
    logger.info("--- Worker Started ---")
    
    # 3. Check for Webhook
    DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK")
    if not DISCORD_WEBHOOK:
        logger.error("❌ FATAL: DISCORD_WEBHOOK is missing. Check GitHub Secrets and YAML file.")
        sys.exit(1) # This forces the GitHub Action to fail Red ❌

    TARGET_URL = "https://my.jobstreet.com/electrical-engineering-intern-jobs/in-Kuala-Lumpur"
    
    jobs = fetch_data(TARGET_URL)

    if jobs:
        csv_path = save_to_csv(jobs)
        if csv_path:
            send_to_discord(csv_path, DISCORD_WEBHOOK, jobs)
    else:
        logger.info("💤 No jobs found this run.")

    logger.info("--- Worker Finished ---")

if __name__ == "__main__":
    start_scraping_worker()