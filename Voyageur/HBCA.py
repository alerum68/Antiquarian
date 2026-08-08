import argparse
import dataclasses
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

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

        # Match path structure .../biographical/<letter>/<filename>.pdf
        match = re.search(r"biographical/([a-z0-9])/([^/]+\.pdf)$", href, re.IGNORECASE)
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
# TEXT PREFETCH & SCAFFOLD CREATION
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


def build_hbca_scaffold_sheet(entry: BioSheetEntry, raw_text: str = "") -> dict:
    """Builds a Commissioner-compliant placeholder sheet dict for an HBCA bio sheet."""
    return {
        "page_id": entry.file_name,
        "document_metadata": {
            "file_name": entry.file_name,
            "document_type": "HBCA",
            "source_name": "Hudson's Bay Company Archives: Biographical Sheets",
            "source_location": "Archives of Manitoba, Winnipeg, Manitoba, Canada",
            "employee_name": entry.employee_name,
            "pdf_url": entry.pdf_url,
            "raw_text": raw_text,
            "keystone_urls": [],
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
                "type_specific_fields": {},
                "participants": [],
            }
        ],
    }


# ==========================================
# CHECKPOINT & MASTER DB STORAGE
# ==========================================
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
    delay_sec: float = 0.2,
) -> int:
    """Headless gatherer: fetches index, downloads PDFs, prefetches text, builds scaffold sheets."""
    image_dir = image_dir or (Path(PROGRAM_DIR) / HBCA_IMAGE_DIR)
    master_db_path = master_db_path or (
        Path(PROGRAM_DIR) / os.environ.get("JSON_DIR", "JSON") / HBCA_MASTER_DB_NAME
    )
    checkpoint_dir = checkpoint_dir or Path(CHECKPOINT_DIR)

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
    for entry in filtered_entries:
        if entry.file_name in downloaded_set:
            continue

        target_file = image_dir / entry.letter / entry.file_name
        target_file.parent.mkdir(parents=True, exist_ok=True)

        if not target_file.exists():
            print(f"Downloading {entry.file_name} from {entry.pdf_url}...")
            pdf_resp = requests.get(entry.pdf_url, headers=headers, timeout=30)
            if pdf_resp.status_code == 200:
                with open(target_file, "wb") as f:
                    f.write(pdf_resp.content)
            else:
                print(f"[WARN] Failed to download {entry.pdf_url}: HTTP {pdf_resp.status_code}")
                continue

        raw_text = extract_text_from_pdf(target_file)
        sheet = build_hbca_scaffold_sheet(entry, raw_text=raw_text)
        append_scaffold_sheet(master_db_path, sheet)

        downloaded_set.add(entry.file_name)
        save_checkpoint(checkpoint_file, downloaded_set)
        new_downloads += 1

        if delay_sec > 0:
            time.sleep(delay_sec)

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
        "--headless",
        action="store_true",
        default=True,
        help="Run gatherer headlessly (default: True)",
    )
    args = parser.parse_args()

    gather_hbca_sheets(letter_filter=args.letter, index_url=args.index_url)


if __name__ == "__main__":
    main()
