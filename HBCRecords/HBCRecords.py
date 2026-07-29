"""
HBC Bio Sheet Extraction & Scraper Script.

Extracts structured vitals locally using pdfplumber.
Delegates unstructured family notes to Gemini API.
Scrapes Archives of Manitoba (Keystone) for media links.
"""

import json
import os
import re
import time
from pathlib import Path
from typing import Dict

import pdfplumber
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from google import genai

# ==========================================
# CONFIGURATION
# ==========================================
# Global settings come from the project root's .env; this tool's own settings come from
# its own subfolder's .env, so HBCRecords stays runnable standalone.
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)
load_dotenv(Path(__file__).resolve().parent / ".env", override=True)
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Directories & Constants
PROGRAM_DIR = Path(os.getenv("PROGRAM_DIR", ""))
IMAGE_DIR = str(PROGRAM_DIR / os.getenv("HBC_PDF_DIR", ""))
MASTER_DB = str(PROGRAM_DIR / os.getenv("JSON_DIR", "") / os.getenv("HBC_MASTER_DB_NAME", ""))
KEYSTONE_URL = os.getenv("HBC_KEYSTONE_URL")
MODEL_ID = os.getenv("MODEL_NAME")

# Load our minimized schema
with open("hbc_notes_schema.json", "r", encoding="utf-8") as f:
    SCHEMA = json.load(f)


# ==========================================
# SCRAPER & PDF PROCESSING
# ==========================================
def scrape_keystone(location_code: str) -> str:
    """Scrapes Keystone database for the direct digitized microfilm URL."""
    try:
        # The payload to mimic the form submission
        payload = {"KEYWORD": "", "DIGITAL_COPIES": "Y",  # Check the digital copies box
                   "LOCATION_CODE": location_code}
        response = requests.post(KEYSTONE_URL, data=payload, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # Look for the primary link to the digital file
        # This selector depends heavily on Keystone's exact HTML layout
        media_link = soup.find('a', href=re.compile(r'\.pdf$|\.jpg$'))
        if media_link:
            return media_link['href']

    except requests.RequestException as e:
        print(f"   [!] Scrape failed for {location_code}: {e}")

    return ""


def process_pdf(pdf_path: str) -> Dict:
    """Extracts text, parses structured data locally, and queries Gemini for notes."""
    filename = os.path.basename(pdf_path)

    with pdfplumber.open(pdf_path) as pdf:
        text = "\n".join(page.extract_text() for page in pdf.pages if page.extract_text())

    # --- LOCAL PYTHON EXTRACTION ---
    employee_data = {"filename": filename, "name": "", "parish": "", "birth": "", "keystone_url": "",
                     "service_references": [], "family": {}}

    name_match = re.search(r"NAME:\s*(.*?)\s*(?:PARISH|ENTERED)", text)
    if name_match:
        employee_data["name"] = name_match.group(1).strip()

    dates_match = re.search(r"DATES:\s*(.*?)\n", text)
    if dates_match:
        employee_data["birth"] = dates_match.group(1).strip()

    # Find the HBCA location code (e.g., B.239/g/13) to scrape the image link
    # We grab the first valid post journal/account reference found
    ref_match = re.search(r"(B\.\d+/[a-z]+/\d+[a-z]?)", text)
    if ref_match:
        loc_code = ref_match.group(1)
        employee_data["service_references"].append(loc_code)
        print(f"   Searching Manitoba Archives for: {loc_code}...")
        employee_data["keystone_url"] = scrape_keystone(loc_code)

    # Isolate the unstructured notes at the bottom
    notes_block = ""
    notes_match = re.search(r"(Child:|Wife:|Married:.*)(Filename:.*)?", text, re.IGNORECASE | re.DOTALL)
    if notes_match:
        notes_block = notes_match.group(1).strip()

    # --- GEMINI API SUBROUTINE ---
    if notes_block:
        prompt = ("Extract the spouses, children, and their associated church record citations "
                  "from the following historical notes block. Output strictly matching the JSON schema.\n\n"
                  f"NOTES BLOCK:\n{notes_block}")

        response = client.models.generate_content(
            model=MODEL_ID, contents=[prompt],
            config=genai.types.GenerateContentConfig(
                response_mime_type="application/json", response_schema=SCHEMA, temperature=0.1
            )
        )
        employee_data["family"] = json.loads(response.text.strip())

    return employee_data


# ==========================================
# MAIN EXECUTION
# ==========================================
def run_batch():
    """Main Orchestration Loop"""
    all_pdfs = [f for f in os.listdir(IMAGE_DIR) if f.lower().endswith('.pdf')]
    master_data = []

    if os.path.exists(MASTER_DB):
        with open(MASTER_DB, 'r', encoding='utf-8') as f:
            master_data = json.load(f)

    processed_files = {doc["filename"] for doc in master_data}

    for index, filename in enumerate(all_pdfs, 1):
        if filename in processed_files:
            continue

        print(f"[{index}/{len(all_pdfs)}] Processing {filename}...")
        pdf_path = os.path.join(IMAGE_DIR, filename)

        try:
            data = process_pdf(pdf_path)
            master_data.append(data)

            # Save after every file to preserve progress
            with open(MASTER_DB, 'w', encoding='utf-8') as f:
                json.dump(master_data, f, indent=2)

            print(" DONE!")
            time.sleep(1)  # Be polite to the Manitoba web server

        except Exception as e:
            print(f" ERROR: {e}")


if __name__ == "__main__":
    run_batch()
