import logging
import os

# Toggle to enable or disable robots.txt check
CHECK_ROBOTS = False

# Scraper configuration
URL_TO_SCRAPE = "https://my.jobstreet.com/engineering-intern-jobs/in-Kuala-Lumpur" # Separate words with hyphen symbol (-)
BASE_URL = "/".join(URL_TO_SCRAPE.split("/")[:3]) # A Funny way to extract the base URL =P
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:95.0) Gecko/20100101 Firefox/95.0"

# File configuration
LOG_FILE = "logs/scraper.log"
DATABASE_FILE = "data/jobs.db"
CSV_FILE = "data/job_listings.csv"

# Logging setup
def setup_logging():
    # Clear any existing log handlers
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    # Create logger
    logger = logging.getLogger()

    # File handler for logging
    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setLevel(logging.DEBUG)  # Log only DEBUG and above to file
    file_formatter = logging.Formatter('%(asctime)s - [%(levelname)s] - %(message)s')
    file_handler.setFormatter(file_formatter)

    # Console handler for logging
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)  # Log all INFO and above to console
    console_formatter = logging.Formatter('%(asctime)s - [%(levelname)s] - %(message)s')
    console_handler.setFormatter(console_formatter)

    # Add both handlers to the logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    # Set the default logging level
    logger.setLevel(logging.DEBUG)  # Default to DEBUG, so that we get all levels

# Initialize folders
def ensure_directories_exist():
    """Ensure required directories exist."""
    required_dirs = ['data', 'logs']
    for directory in required_dirs:
        if not os.path.exists(directory):
            os.makedirs(directory)
            print(f"Created missing directory: {directory}")
