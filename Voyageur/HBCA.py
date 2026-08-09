import argparse
import dataclasses
import json
import logging
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# pypdf logs "incorrect startxref pointer" / "parsing for Object Streams" as
# non-fatal recovery warnings for malformed archival PDFs; it still parses
# them successfully, so these are noise for this script.
logging.getLogger("pypdf").setLevel(logging.ERROR)

# Repo root on sys.path for sibling module imports
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

load_dotenv(_REPO_ROOT / ".env", override=False)
load_dotenv(Path(__file__).resolve().parent / ".env", override=False)


# ==========================================
# DATA STRUCTURES
# ==========================================
@dataclasses.dataclass
class BioSheetEntry:
    employee_name: str
    file_name: str
    letter: str
    pdf_url: str


# ==========================================
# PATH & CONFIG RESOLUTION
# ==========================================
def _safe_path(base: str, *parts: str) -> str:
    non_blank = [p for p in parts if p]
    if not non_blank:
        return ""
    res = base
    for p in non_blank:
        res = p if os.path.isabs(p) else os.path.join(res, p)
    return res


def resolve_generic_setting(document_type: str, generic_key: str, default: str = "") -> str:
    from Commissioner.record_registry import get_field_remap

    remap = get_field_remap(document_type)
    for k, v in remap.items():
        if v == generic_key:
            val = os.getenv(k)
            if val is not None and val.strip():
                return val.strip()
    return os.getenv(generic_key, default).strip()


PROGRAM_DIR = os.environ.get("PROGRAM_DIR", "").strip()
DEFAULT_INDEX_URL = "https://www.gov.mb.ca/chc/archives/hbca/biographical/index.html"
INDEX_URL = os.environ.get("HBCA_INDEX_URL", DEFAULT_INDEX_URL).strip() or DEFAULT_INDEX_URL
HBCA_IMAGE_DIR = resolve_generic_setting("HBCA", "IMAGE_DIR", "Images/HBCA")
HBCA_MASTER_DB_NAME = resolve_generic_setting("HBCA", "MASTER_DB_NAME", "MasterDB_HBCA.json")
CHECKPOINT_DIR = _safe_path(PROGRAM_DIR, os.environ.get("HBCA_CHECKPOINT_DIR", "Working/HBCA"))
MEDIA_DIR = _safe_path(PROGRAM_DIR, os.environ.get("MEDIA_DIR", "Media").strip())

KEYSTONE_BASE_URL = os.environ.get("KEYSTONE_BASE_URL", "https://pam.minisisinc.com/scripts/mwimain.dll").strip()
HBCA_RESOLVE_KEYSTONE = (
    os.environ.get("HBCA_RESOLVE_KEYSTONE", "false").lower() in ("true", "1", "yes")
)
HBCA_DOWNLOAD_KEYSTONE_MEDIA = (
    os.environ.get("HBCA_DOWNLOAD_KEYSTONE_MEDIA", "true").lower() in ("true", "1", "yes")
)
HBCA_MAX_WORKERS = int(os.environ.get("HBCA_MAX_WORKERS", "10").strip() or "10")


# ==========================================
# INDEX PARSER & FILTERS
# ==========================================
def parse_biographical_index_html(html_text: str, base_url: str = DEFAULT_INDEX_URL) -> List[BioSheetEntry]:
    """Parses Archives of Manitoba HBCA biographical index page for PDF links."""
    soup = BeautifulSoup(html_text, "html.parser")
    entries: List[BioSheetEntry] = []
    seen_urls: Set[str] = set()

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].strip()
        if not href.lower().endswith(".pdf"):
            continue

        # Match path structure .../<letter>/<filename>.pdf
        match = re.search(r"([a-z0-9])/([^/]+\.pdf)$", href, re.IGNORECASE)
        if match:
            letter = match.group(1).lower()
            file_name = match.group(2).lower()
        else:
            file_name = Path(href).name.lower()
            letter = file_name[0] if file_name else "a"

        full_url = urljoin(base_url, href)
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        name = a_tag.get_text(strip=True) or file_name.replace(".pdf", "").replace("_", " ").title()

        entries.append(
            BioSheetEntry(
                employee_name=name,
                file_name=file_name,
                letter=letter,
                pdf_url=full_url,
            )
        )

    return entries


def filter_entries_by_letter(
    entries: List[BioSheetEntry], letters: Optional[List[str]] = None
) -> List[BioSheetEntry]:
    """Filters biographical sheet entries by one or more initial letters."""
    if not letters:
        return entries
    target_letters = {letter.strip().lower() for letter in letters if letter.strip()}
    return [e for e in entries if e.letter in target_letters]


# ==========================================
# TEXT PREFETCH & LOCATION CODE EXTRACTION
# ==========================================
def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extracts text content from a downloaded PDF file using pypdf or pdfplumber."""
    text_chunks: List[str] = []
    try:
        import pypdf

        reader = pypdf.PdfReader(str(pdf_path))
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text_chunks.append(extracted)
    except Exception:
        try:
            import pdfplumber

            with pdfplumber.open(str(pdf_path)) as pdf:
                for page in pdf.pages:
                    extracted = page.extract_text()
                    if extracted:
                        text_chunks.append(extracted)
        except Exception as e:
            print(f"[WARN] Failed to extract text from {pdf_path}: {e}")

    return "\n".join(text_chunks).strip()


_CODE_REGEX = re.compile(
    r"\b([A-G]\.\d+/[a-z]/\d+[a-z]?(?:\s*-\s*\d+)?(?:\s+fo\.\s*\d+)?|[A-G]\.\d+/\d+[a-z]?(?:\s+fo\.\s*\d+)?)\b",
    re.IGNORECASE,
)
_SEARCH_FILE_REGEX = re.compile(r"(Search\s+File[:\s]+['\"]?[^'\"\n\r]+['\"]?)", re.IGNORECASE)


def extract_hbca_location_codes(text: str) -> List[str]:
    """Extracts HBCA archival reference location codes (e.g. B.239/g/1-4, A.32/21, E.4/1a) and Search Files."""
    if not text:
        return []
    codes: List[str] = []
    seen: Set[str] = set()

    for match in _CODE_REGEX.finditer(text):
        raw_code = match.group(1).strip()
        if raw_code and raw_code not in seen:
            seen.add(raw_code)
            codes.append(raw_code)

    for match in _SEARCH_FILE_REGEX.finditer(text):
        raw_sf = match.group(1).strip()
        if raw_sf and raw_sf not in seen:
            seen.add(raw_sf)
            codes.append(raw_sf)

    return codes


_FILENAME_FOOTER_REGEX = re.compile(
    r"Filename:.*?\((?:fl\.|b\.|d\.)\s*([^)]+)\)", re.IGNORECASE
)

def parse_bio_sheet_text(text: str) -> dict:
    data = {
        "parish_of_origin": "", "entered_service_year": "", "service_years_range": "",
        "vital_dates_summary": "", "birth_date_extracted": "", "death_date_extracted": "",
        "service_history": [],
    }

    parish_match = re.search(r'PARISH:\s*(.*?)(?:\s*ENTERED SERVICE:|\s*DATES:|\n)', text)
    if parish_match:
        data["parish_of_origin"] = parish_match.group(1).strip()

    service_match = re.search(r'ENTERED SERVICE:\s*(.*?)(?:\s*DATES:|\n)', text)
    if service_match:
        data["entered_service_year"] = service_match.group(1).strip()

    dates_match = re.search(r'DATES:\s*(.*?)(?:Appointments & Service|Outfit Year|Filename:|$)', text, re.DOTALL)
    if dates_match:
        data["vital_dates_summary"] = dates_match.group(1).strip()
    b_match = re.search(r'\bb\.\s*([^,;\n]+)', data["vital_dates_summary"])
    if b_match:
        data["birth_date_extracted"] = b_match.group(1).strip()
    d_match = re.search(r'\bd\.\s*([^,;\n]+)', data["vital_dates_summary"])
    if d_match:
        data["death_date_extracted"] = d_match.group(1).strip()

    # Fallback: floruit/vital range from the Filename metadata footer
    if not data["vital_dates_summary"]:
        footer_match = _FILENAME_FOOTER_REGEX.search(text)
        if footer_match:
            data["service_years_range"] = data["service_years_range"] or footer_match.group(1).strip()
            data["vital_dates_summary"] = footer_match.group(0).strip()

    row_pattern = r'^\s*(\d{4}(?:-\d{4})?)\s+(.+?)\s+([A-Z][.\w/]+(?:/\d+[a-z]?)?)(?:,.*)?$'
    for oy, middle_text, _ in re.findall(row_pattern, text, re.MULTILINE):
        codes = extract_hbca_location_codes(middle_text + " " + _)
        ref = codes[0] if codes else None
        if not ref:
            continue
        
        pos = ""
        post = ""
        for p in ["Clerk in charge", "Postmaster", "Clerk", "Apprentice"]:
            if middle_text.startswith(p):
                pos = p
                post = middle_text[len(p):].strip()
                break
        
        if not pos:
            parts = middle_text.split()
            pos = " ".join(parts[:2]) if len(parts) >= 2 else middle_text.strip()
            post = " ".join(parts[2:]) if len(parts) > 2 else ""

        district = ""
        if post == "The Pas Cumberland":
            post, district = "The Pas", "Cumberland"
        elif post == "Rapid River English River":
            post, district = "Rapid River", "English River"
        elif post == "Lake St. Anns Upper Saskatchewan":
            post, district = "Lake St. Anns", "Upper Saskatchewan"

        data["service_history"].append({
            "outfit_years": oy.strip(),
            "position": pos,
            "post": post,
            "district": district,
            "hbca_ref": ref,
        })

    data["needs_llm_structured_review"] = not any([
        data["parish_of_origin"], data["entered_service_year"],
        (data["vital_dates_summary"] if not data["vital_dates_summary"].startswith("Filename:") else ""),
        data["service_history"],
    ])
    return data


# ==========================================
# KEYSTONE RESOLVER & MEDIA DOWNLOADER
# ==========================================
import json
from pypdf import PdfWriter

def build_keystone_search_url(location_code: str, base_url: str = KEYSTONE_BASE_URL) -> str:
    """Builds a local HTML file that auto-submits a POST search to Keystone."""
    cleaned_code = location_code.split(" fo.")[0].strip()
    safe_name = "".join(c if c.isalnum() else "_" for c in cleaned_code)
    
    html_content = f"""<!DOCTYPE html>
<html>
<head><title>Redirecting to Keystone Search...</title></head>
<body onload="document.forms[0].submit()">
    <p>Searching Archives of Manitoba for {cleaned_code}...</p>
    <form method="POST" action="{base_url}/144/PAM_LISTINGS?DIRECTSEARCH">
        <input type="hidden" name="LOCATION_CODE" value="{cleaned_code}">
        <input type="hidden" name="FLD_OP1" value="AND_WORD">
    </form>
</body>
</html>"""
    
    out_dir = Path(CHECKPOINT_DIR) / "SearchLinks"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"Search_{safe_name}.html"
    
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(html_content)
        
    return out_file.absolute().as_uri()


def parse_keystone_search_response(html_text: str, base_url: str = KEYSTONE_BASE_URL) -> Dict[str, Any]:
    """Parses Keystone HTML search results for finding aid URLs, metadata, and digitized media links."""
    soup = BeautifulSoup(html_text, "html.parser")
    record_urls: List[str] = []
    media_urls: List[str] = []
    seen_records: Set[str] = set()
    seen_media: Set[str] = set()
    metadata: Dict[str, str] = {}

    for div in soup.find_all("div"):
        text = div.get_text(strip=True)
        if text == "Item Description":
            nxt = div.find_next_sibling("div")
            if nxt: metadata["item_description"] = nxt.get_text(strip=True)
        elif text == "Microfilm No.":
            nxt = div.find_next_sibling("div")
            if nxt: metadata["microfilm_no"] = nxt.get_text(strip=True)

    textarea = soup.find("textarea", {"id": "share_link_url"})
    if textarea:
        url = textarea.get_text(strip=True)
        if url and url not in seen_records:
            seen_records.add(url)
            record_urls.append(url)

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].strip()
        full_url = urljoin(base_url, href)
        href_lower = href.lower()

        is_media_ext = any(href_lower.endswith(ext) for ext in (".pdf", ".jpg", ".jpeg", ".tif", ".tiff", ".png", ".mp4"))
        if is_media_ext or "/assets/media/" in href_lower:
            if full_url not in seen_media:
                seen_media.add(full_url)
                media_urls.append(full_url)
        elif "record" in href_lower or "/pam_listings/" in href_lower or "/unionsearch/" in href_lower:
            if full_url not in seen_records:
                seen_records.add(full_url)
                record_urls.append(full_url)

    for img_tag in soup.find_all("img", src=True):
        src = img_tag["src"].strip()
        full_img_url = urljoin(base_url, src)
        if "/thumbs/" not in src.lower() and full_img_url not in seen_media:
            seen_media.add(full_img_url)
            media_urls.append(full_img_url)

    return {"record_urls": record_urls, "media_urls": media_urls, "metadata": metadata}


def query_keystone_for_code(
    location_code: str,
    base_url: str = KEYSTONE_BASE_URL,
    session: Optional[requests.Session] = None,
    cache_file: Optional[str] = None,
) -> Dict[str, Any]:
    """Queries Keystone database for a given location code."""
    if cache_file and Path(cache_file).exists():
        try:
            with open(cache_file, "r") as f:
                cache = json.load(f)
                if location_code in cache:
                    return cache[location_code]
        except Exception:
            pass

    client = session or requests.Session()
    headers = {"User-Agent": "Scriptorium/1.0 (Genealogy Keystone Resolver)"}
    landing_url = f"{base_url}/144/PAM_LISTINGS?DIRECTSEARCH"
    result = {"record_urls": [], "media_urls": [], "metadata": {}}

    try:
        resp = client.get(landing_url, headers=headers, timeout=20)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            form = next((f for f in soup.find_all("form") if "?SEARCH" in f.get("action", "")), None)
            if form and form.get("action"):
                action_url = urljoin(base_url, form["action"])
                data = {}
                for input_tag in form.find_all("input"):
                    name = input_tag.get("name")
                    if name:
                        if input_tag.get("type") == "radio" and not input_tag.has_attr("checked"):
                            continue
                        data[name] = input_tag.get("value", "")
                data["LOCATION_CODE"] = location_code
                
                post_resp = client.post(
                    action_url,
                    data=data,
                    headers=headers,
                    timeout=20
                )
                if post_resp.status_code == 200:
                    result = parse_keystone_search_response(post_resp.text, base_url)
    except Exception as e:
        print(f"[WARN] Failed to query Keystone for {location_code}: {e}")

    result["record_urls"] = [build_keystone_search_url(location_code, base_url)]

    if cache_file:
        try:
            cache = {}
            if Path(cache_file).exists():
                with open(cache_file, "r") as f:
                    cache = json.load(f)
            cache[location_code] = result
            with open(cache_file, "w") as f:
                json.dump(cache, f)
        except Exception:
            pass

    return result


def download_keystone_media(
    media_urls: List[str],
    target_dir: Path,
    session: Optional[requests.Session] = None,
) -> List[str]:
    """Downloads digitized microfilm or document media files from Keystone."""
    target_dir.mkdir(parents=True, exist_ok=True)
    client = session or requests.Session()
    headers = {"User-Agent": "Scriptorium/1.0 (Genealogy Keystone Media Downloader)"}
    downloaded_paths: List[str] = []

    for url in media_urls:
        filename = Path(url.split("?")[0]).name or f"media_{len(downloaded_paths)+1}.jpg"
        dest_file = target_dir / filename
        if not dest_file.exists():
            try:
                resp = client.get(url, headers=headers, timeout=30)
                if resp.status_code == 200:
                    with open(dest_file, "wb") as f:
                        f.write(resp.content)
            except Exception as e:
                print(f"[WARN] Failed to download media from {url}: {e}")
                continue
        if dest_file.exists():
            downloaded_paths.append(str(dest_file))

    return downloaded_paths


def download_and_merge_keystone_media(
    media_urls: List[str],
    target_dir: Path,
    output_name: str,
    session: Optional[requests.Session] = None,
) -> Path:
    """Downloads PDFs from Keystone and merges them if there are multiple reels."""
    downloaded = download_keystone_media(media_urls, target_dir, session)
    merged_path = target_dir / output_name

    merger = PdfWriter()
    pdfs_added = 0
    for pdf in downloaded:
        if pdf.lower().endswith(".pdf"):
            merger.append(pdf)
            pdfs_added += 1

    if pdfs_added > 0:
        merger.write(merged_path)
    merger.close()

    return merged_path
# ==========================================
# SCAFFOLD & MASTER DB STORAGE
# ==========================================
def build_hbca_scaffold_sheet(
    entry: BioSheetEntry,
    raw_text: str = "",
    keystone_urls: Optional[List[str]] = None,
    keystone_records: Optional[Dict[str, Any]] = None,
) -> dict:
    """Builds a Commissioner-compliant placeholder sheet dict for an HBCA bio sheet."""
    codes = extract_hbca_location_codes(raw_text)
    parsed = parse_bio_sheet_text(raw_text)
    scaffold = {
        "page_id": entry.file_name,
        "document_metadata": {
            "file_name": entry.file_name,
            "document_type": "HBCA",
            "source_name": "Hudson's Bay Company Archives: Biographical Sheets",
            "source_location": "Archives of Manitoba, Winnipeg, Manitoba, Canada",
            "employee_name": entry.employee_name,
            "pdf_url": entry.pdf_url,
            "raw_text": raw_text,
            "keystone_urls": keystone_urls or [],
        },
        "records": [
            {
                "record_id": None,
                "page": entry.file_name,
                "record_number": "1",
                "event_type": "Employment",
                "year": None,
                "event_date": None,
                "event_place": None,
                "citation_details": f"HBCA Biographical Sheet: {entry.employee_name}",
                "citation_text": entry.pdf_url,
                "review": False,
                "continues_on_next_image": False,
                "continues_from_previous_image": False,
                "type_specific_fields": {
                    "hbca_references": codes,
                    "keystone_urls": keystone_urls or [],
                    "keystone_records": keystone_records or {},
                },
                "participants": [],
            }
        ],
    }
    scaffold["records"][0]["type_specific_fields"].update(parsed)
    return scaffold


def load_checkpoint(checkpoint_file: Path) -> Set[str]:
    """Loads set of completed file names from checkpoint file."""
    if not checkpoint_file.exists():
        return set()
    try:
        with open(checkpoint_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            return set(data.get("downloaded_files", []))
    except Exception as e:
        print(f"[WARN] Failed to read checkpoint {checkpoint_file}: {e}")
        return set()


def save_checkpoint(checkpoint_file: Path, downloaded_files: Set[str]) -> None:
    """Saves completed file names to checkpoint file."""
    checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
    temp_file = checkpoint_file.with_suffix(".tmp")
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump({"downloaded_files": sorted(downloaded_files)}, f, indent=2)
    temp_file.replace(checkpoint_file)


def append_scaffold_sheet(master_db_path: Path, sheet: dict) -> None:
    """Loads or creates MasterDB_HBCA.json and appends a scaffold sheet if not present."""
    from Commissioner.record_registry import validate_soft

    master_db_path.parent.mkdir(parents=True, exist_ok=True)

    data: Dict[str, Any] = {
        "collection_title": "Hudson's Bay Company Archives: Biographical Sheets",
        "sheets": [],
    }

    if master_db_path.exists():
        try:
            with open(master_db_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass

    existing_page_ids = {s.get("page_id") for s in data.get("sheets", [])}
    if sheet.get("page_id") not in existing_page_ids:
        data.setdefault("sheets", []).append(sheet)

    validate_soft(data, "HBCA", str(master_db_path))

    temp_path = master_db_path.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    temp_path.replace(master_db_path)


# ==========================================
# MAIN GATHER WORKFLOW
# ==========================================
def gather_hbca_sheets(
    letter_filter: Optional[List[str]] = None,
    index_url: str = INDEX_URL,
    image_dir: Optional[Path] = None,
    master_db_path: Optional[Path] = None,
    checkpoint_dir: Optional[Path] = None,
    media_dir: Optional[Path] = None,
    resolve_keystone: bool = HBCA_RESOLVE_KEYSTONE,
    download_keystone: bool = HBCA_DOWNLOAD_KEYSTONE_MEDIA,
    delay_sec: float = 0.0,
    max_workers: int = HBCA_MAX_WORKERS,
) -> int:
    """
    Headless gatherer: fetches index, downloads PDFs, prefetches text,
    resolves Keystone links, builds scaffold sheets.
    """
    image_dir = image_dir or Path(_safe_path(str(media_dir or MEDIA_DIR), HBCA_IMAGE_DIR))
    master_db_path = master_db_path or (
        Path(PROGRAM_DIR) / os.environ.get("JSON_DIR", "JSON") / HBCA_MASTER_DB_NAME
    )
    checkpoint_dir = checkpoint_dir or Path(CHECKPOINT_DIR)
    media_dir = media_dir or Path(MEDIA_DIR)

    image_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_file = checkpoint_dir / "hbca_checkpoint.json"

    downloaded_set = load_checkpoint(checkpoint_file)

    print(f"Fetching HBCA biographical index from {index_url}...")
    headers = {"User-Agent": "Scriptorium/1.0 (Genealogy Research Pipeline)"}
    resp = requests.get(index_url, headers=headers, timeout=30)
    resp.raise_for_status()

    entries = parse_biographical_index_html(resp.text, base_url=index_url)
    print(f"Found {len(entries)} total biographical sheets in index.")

    filtered_entries = filter_entries_by_letter(entries, letter_filter)
    if letter_filter:
        print(f"Filtered to {len(filtered_entries)} sheets matching letter(s): {letter_filter}")

    new_downloads = 0
    db_lock = threading.Lock()

    def process_entry(entry: BioSheetEntry) -> bool:
        if entry.file_name in downloaded_set:
            return False

        target_file = image_dir / "Bios" / entry.letter / entry.file_name
        target_file.parent.mkdir(parents=True, exist_ok=True)

        session = requests.Session()
        if not target_file.exists():
            print(f"Downloading {entry.file_name} from {entry.pdf_url}...")
            pdf_resp = session.get(entry.pdf_url, headers=headers, timeout=30)
            if pdf_resp.status_code == 200:
                with open(target_file, "wb") as f:
                    f.write(pdf_resp.content)
            else:
                print(f"[WARN] Failed to download {entry.pdf_url}: HTTP {pdf_resp.status_code}")
                return False

        raw_text = extract_text_from_pdf(target_file)
        keystone_urls: List[str] = []
        keystone_records: Dict[str, Any] = {}

        if resolve_keystone:
            codes = extract_hbca_location_codes(raw_text)
            for code in codes:
                res = query_keystone_for_code(code, session=session)
                keystone_urls.extend(res.get("record_urls", []))
                keystone_records[code] = res
                if download_keystone and res.get("media_urls"):
                    clean_code = re.sub(r"[^\w\.-]", "_", code)
                    dest_media_dir = media_dir / "HBCA" / "Archives" / clean_code
                    download_keystone_media(res["media_urls"], dest_media_dir, session=session)

        sheet = build_hbca_scaffold_sheet(
            entry, raw_text=raw_text, keystone_urls=keystone_urls, keystone_records=keystone_records
        )

        with db_lock:
            append_scaffold_sheet(master_db_path, sheet)
            downloaded_set.add(entry.file_name)
            save_checkpoint(checkpoint_file, downloaded_set)

        if delay_sec > 0:
            time.sleep(delay_sec)

        return True

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_entry, e) for e in filtered_entries]
        for future in as_completed(futures):
            if future.result():
                new_downloads += 1

    print(f"Gather complete. {new_downloads} new sheets downloaded and indexed.")
    return new_downloads


def main() -> None:
    parser = argparse.ArgumentParser(description="Voyageur HBCA Biographical Sheets Gatherer")
    parser.add_argument(
        "--letter",
        nargs="+",
        help="Filter by starting letter(s), e.g. --letter A or --letter A B C",
    )
    parser.add_argument(
        "--index-url",
        default=INDEX_URL,
        help="Index URL for HBCA biographical sheets",
    )
    parser.add_argument(
        "--resolve-keystone",
        action="store_true",
        default=HBCA_RESOLVE_KEYSTONE,
        help="Resolve HBCA location codes against Keystone database",
    )
    parser.add_argument(
        "--download-media",
        action="store_true",
        default=HBCA_DOWNLOAD_KEYSTONE_MEDIA,
        help="Download digitized media from Keystone",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help="Run gatherer headlessly (default: True)",
    )
    args = parser.parse_args()

    env_letter_filter = os.environ.get("HBCA_LETTER_FILTER", "").strip()
    if not args.letter and env_letter_filter:
        args.letter = env_letter_filter.split()

    gather_hbca_sheets(
        letter_filter=args.letter,
        index_url=args.index_url,
        resolve_keystone=args.resolve_keystone,
        download_keystone=args.download_media,
    )


if __name__ == "__main__":
    main()
