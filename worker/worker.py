import requests
import csv
from bs4 import BeautifulSoup
import json
import logging
import os
import time  # Added for rate limiting
from collections import OrderedDict
from hashlib import sha256
from urllib.parse import urljoin

# --- CONFIGURATION ---
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
BASE_URL = "https://my.jobstreet.com"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def generate_hashed_id(job_info):
    raw_id = f"{job_info.get('jobTitle', '')}|{job_info.get('jobCompany', '')}|{job_info.get('jobLocation', '')}"
    return sha256(raw_id.encode('utf-8')).hexdigest()

def fetch_data(url):
    cookie_value = os.environ.get("JOBSTREET_COOKIE")
    
    headers = {
        'User-Agent': USER_AGENT,
        'Cookie': cookie_value if cookie_value else '' 
    }

    if not headers['Cookie']:
        logger.warning("⚠️ No Cookie provided. Cloudflare might block this request.")

    logger.info(f"Fetching data from: {url}")

    try:
        response = requests.get(url=url, headers=headers, timeout=10)

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            job_listings = soup.select("[data-automation='normalJob']")
            
            if not job_listings:
                logger.warning("No jobs found.")
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
                    job_info['jobSalary'] = salary_elem.get_text(strip=True).replace("\\xa", "") if salary_elem else "Not Specified"
                    job_info['jobListingDate'] = date_elem.get_text(strip=True) if date_elem else "N/A"

                    if title_elem and title_elem.get('href'):
                        raw_link = title_elem.get('href')
                        job_info['jobURL'] = urljoin(BASE_URL, raw_link) if not raw_link.startswith('http') else raw_link
                    else:
                        job_info['jobURL'] = "N/A"

                    job_info['uniqueId'] = generate_hashed_id(job_info)
                    job_data.append(job_info)

                except Exception as e:
                    continue

            logger.info(f"✅ Found {len(job_data)} valid jobs.")
            return job_data
        else:
            return []
    except Exception as e:
        logger.error(f"Network Request Error: {e}")
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
        logger.error(f"Failed to save CSV: {e}")
        return None

def send_chunk_to_discord(webhook_url, job_chunk, page_num, total_pages, file_path=None):
    """Helper function to send one batch of jobs."""
    
    embed = {
        "title": f"🚀 Job Scraper Report (Page {page_num}/{total_pages})",
        "color": 3066993,
        "fields": [],
        "footer": {"text": "JobStreet Automator"}
    }

    # Add jobs to this specific card
    for i, job in enumerate(job_chunk):
        salary_text = f" • {job['jobSalary']}" if job['jobSalary'] != "Not Specified" else ""
        field_value = f"🏢 **{job['jobCompany']}**\n📍 {job['jobLocation']}{salary_text}\n[👉 View Job]({job['jobURL']})"
        
        embed["fields"].append({
            "name": f"🔹 {job['jobTitle']}", 
            "value": field_value,
            "inline": False
        })

    payload_dict = {"embeds": [embed]}

    try:
        # Only attach the file on the LAST page to avoid spamming it
        if file_path and page_num == total_pages:
            with open(file_path, "rb") as f:
                multipart_data = {
                    "file": (os.path.basename(file_path), f),
                    "payload_json": (None, json.dumps(payload_dict))
                }
                requests.post(webhook_url, files=multipart_data)
        else:
            # Send just the JSON for intermediate pages
            requests.post(webhook_url, json=payload_dict)
            
        logger.info(f"✅ Sent Page {page_num}/{total_pages} to Discord.")
        
    except Exception as e:
        logger.error(f"Discord Chunk Error: {e}")

def send_to_discord(file_path, webhook_url, job_data):
    """
    Splits the job list into chunks of 10 and sends multiple messages.
    """
    if not job_data: return

    # Discord Limit: Max 25 fields per embed. We use 10 to be safe and readable.
    CHUNK_SIZE = 10
    
    # Break the list into chunks: [[job1..10], [job11..20], [job21..25]]
    chunks = [job_data[i:i + CHUNK_SIZE] for i in range(0, len(job_data), CHUNK_SIZE)]
    total_pages = len(chunks)

    logger.info(f"📤 Sending {len(job_data)} jobs in {total_pages} batches...")

    for i, chunk in enumerate(chunks):
        page_num = i + 1
        # Send the batch
        send_chunk_to_discord(webhook_url, chunk, page_num, total_pages, file_path)
        
        # Sleep for 1 second between messages to prevent Discord from banning the bot for spamming
        if page_num < total_pages:
            time.sleep(1)

def start_scraping_worker():
    logger.info("--- Worker Started ---")
    
    TARGET_URL = "https://my.jobstreet.com/electrical-engineering-intern-jobs/in-Kuala-Lumpur"
    
    # Retrieve Webhook from GitHub Secrets
    DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK")
    
    if not DISCORD_WEBHOOK:
        logger.error("❌ No Webhook found! Set DISCORD_WEBHOOK in GitHub Secrets.")
        return

    jobs = fetch_data(TARGET_URL)

    if jobs:
        # Note: In GitHub Actions, we don't need to save the CSV to disk 
        # permanently, but we generate it to attach it to the message.
        csv_path = save_to_csv(jobs)
        if csv_path:
            send_to_discord(csv_path, DISCORD_WEBHOOK, jobs)
    else:
        logger.info("No jobs found this run.")

    logger.info("--- Worker Finished ---")

if __name__ == "__main__":
    start_scraping_worker()