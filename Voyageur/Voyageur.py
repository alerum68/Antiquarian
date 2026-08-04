"""
Voyageur - the toolbox's Gather step.

This file is self-contained: A.py, FS.py, LAC.py, and census_schema.py
are folded in directly below so no sibling-file imports
are required at runtime. The original subfiles are kept in place for test-suite
compatibility.

Dispatcher usage: python Voyageur.py <source>
  where <source> is one of: A, FS, LAC

Adding a new repository means a new section in this file and a new SOURCES entry.
"""

import json
import math
import os
import re
import shutil
import sys
import time
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd
import requests
import yaml
from dotenv import load_dotenv, set_key
from thefuzz import fuzz
from titlecase import titlecase

# ==============================================================================
# SHARED UTILITIES (cap_case, titlecase callback)
# ==============================================================================

PRESERVED_ACRONYMS = {"HBC", "NWT", "USA", "NWMP", "RCMP", "UK", "US", "ED", "PID", "RM", "FTM"}


def _titlecase_callback(word: str, **kwargs) -> str | None:
    w_clean = re.sub(r'^[^\w]+|[^\w]+$', '', word)
    if w_clean.upper() in PRESERVED_ACRONYMS:
        return word.replace(w_clean, w_clean.upper())
    if "-" in word:
        parts = word.split("-")
        return "-".join(
            (p.upper() if re.sub(r'^[^\w]+|[^\w]+$', '', p).upper() in PRESERVED_ACRONYMS
             else titlecase(p, callback=_titlecase_callback).capitalize())
            for p in parts
        )
    return None


def cap_case(text: str) -> str:
    if not text:
        return ""
    val = str(text).strip()
    if not val:
        return ""
    return titlecase(val, callback=_titlecase_callback)


# ==============================================================================
# CENSUS SCHEMA (folded from census_schema.py)
# Normalizes a raw census gather into the shared record schema.
# ==============================================================================

_FIELD_MAPS_DIR = Path(__file__).resolve().parent / "field_maps"


def _get_census_era(year: int) -> str:
    if year <= 1840:
        return "pre1850"
    if year <= 1870:
        return "heuristic"
    return "relationship"


def _load_field_map(name: str) -> Dict[str, Dict[str, str]]:
    """Loads a declarative field-map YAML file by name from Voyageur/field_maps/."""
    path = _FIELD_MAPS_DIR / f"{name}.yaml"
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return {
        "participant_fields": data.get("participant_fields", {}) or {},
        "participant_facts": data.get("participant_facts", {}) or {},
        "record_fields": data.get("record_fields", {}) or {},
    }


def _parse_year(value: Any) -> int:
    match = re.search(r'(1[789]\d0|19[0-4]\d|1950)', str(value or ""))
    return int(match.group(1)) if match else 0


def _household_key(columns: Dict[str, str], field_map: Dict[str, Dict[str, str]]) -> Optional[str]:
    """Finds this person's normalized family/dwelling number, the grouping key for which
    household they belong to."""
    for raw_key, target in field_map["record_fields"].items():
        if target in ("family_number", "dwelling_number") and raw_key in columns:
            val = str(columns[raw_key]).strip()
            if val:
                return val
    for raw_key, target in field_map["record_fields"].items():
        if target == "page_number_fallback" and raw_key in columns:
            val = str(columns[raw_key]).strip()
            if val:
                return f"page_{val}"
    return None


def _group_household(people: List[dict], field_map: Dict[str, Dict[str, str]]
                     ) -> List[Tuple[Optional[str], List[dict]]]:
    """Groups people sharing the same family/dwelling number into one household."""
    groups: Dict[Optional[str], List[dict]] = {}
    order: List[Optional[str]] = []
    fallback_counter = 0
    for person in people:
        columns = person.get("columns", {}) or {}
        key = _household_key(columns, field_map)
        if key is None:
            fallback_counter += 1
            key = f"__ungrouped_{fallback_counter}"
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(person)
    return [(None if k.startswith("__ungrouped_") else k, groups[k]) for k in order]


def _normalize_participant(person: dict, field_map: Dict[str, Dict[str, str]],
                           unmapped_seen: Set[str]) -> dict:
    columns = dict(person.get("columns", {}) or {})
    participant: Dict[str, Any] = {
        "role_number": None, "role_name": None,
        "std_given": "", "std_surname": None, "raw_given": None, "raw_surname": None,
        "dit_name": None, "alternate_names": person.get("alternate_names", []),
        "prefix": None, "suffix": None, "sex": "U", "is_priest": False,
        "age": None, "age_unit": None, "occupation": None, "race": None, "religion": None,
        "residence": None, "birth_date": None, "birth_place": None, "death_date": None,
        "death_place": None, "review": False, "review_reason": None,
        "facts": [], "type_specific_fields": {},
    }

    consumed: Set[str] = set()
    for raw_key, target in field_map["participant_fields"].items():
        if raw_key in columns:
            val = columns[raw_key]
            if target in ("role_name", "race", "birth_place", "death_place", "residence",
                          "occupation", "religion") and isinstance(val, str):
                val = cap_case(val)
            if target.startswith("type_specific_fields."):
                participant["type_specific_fields"][target.split(".", 1)[1]] = val
            else:
                participant[target] = val
            consumed.add(raw_key)

    for raw_key, fact_type in field_map["participant_facts"].items():
        if raw_key in columns and str(columns[raw_key]).strip():
            raw_v = str(columns[raw_key]).strip()
            val = (cap_case(raw_v) if fact_type in
                   ("Occupation", "Education", "Military", "Property", "Miscellaneous") else raw_v)
            participant["facts"].append({"fact_type": fact_type, "value": val})
            consumed.add(raw_key)

    for raw_key in field_map["record_fields"]:
        if raw_key in columns:
            consumed.add(raw_key)

    for passthrough_key in ("pid", "extracted_url", "fsftid", "person_ark", "familysearch_url"):
        if person.get(passthrough_key):
            participant["type_specific_fields"][passthrough_key] = person[passthrough_key]

    unmapped = {k: v for k, v in columns.items() if k not in consumed and str(v).strip()}
    if unmapped:
        participant["type_specific_fields"]["unmapped"] = unmapped
        participant["review"] = True
        participant["review_reason"] = ("Unmapped column(s), preserved but not normalized: "
                                        + ", ".join(sorted(unmapped)))
        unmapped_seen.update(unmapped.keys())

    if not participant["std_given"]:
        participant["std_given"] = "[unknown]"
        participant["review"] = True
        participant["review_reason"] = (participant["review_reason"] or "") + " No given-name column mapped."

    return participant


def normalize_census_pages(raw: dict, field_map_name: str, collection_title: str,
                           record_type_name: str) -> dict:
    """Converts a raw {census_year, location, pages: [...]} gather into the shared
    sheets[].records[].participants[] schema, using the named declarative field map."""
    field_map = _load_field_map(field_map_name)
    census_year = _parse_year(raw.get("census_year"))
    era = _get_census_era(census_year)

    sheets = []
    citation: Dict[str, str] = {}
    for page in raw.get("pages", []):
        people = page.get("people", []) or []
        groups = _group_household(people, field_map)
        records = []
        for household_key, group_people in groups:
            unmapped_seen: Set[str] = set()
            participants = [_normalize_participant(p, field_map, unmapped_seen) for p in group_people]
            place = ", ".join(filter(None, [page.get("city"), page.get("county"), page.get("state")]))
            record_review = any(p["review"] for p in participants)
            type_specific: Dict[str, Any] = {}
            if household_key:
                type_specific["family_number"] = household_key
            if page.get("enumeration_district"):
                type_specific["enumeration_district"] = page["enumeration_district"]
            if page.get("roll_number"):
                type_specific["roll_number"] = page["roll_number"]
            if page.get("film_number"):
                type_specific["film_number"] = page["film_number"]
            for loc_key in ("state", "county", "city", "country", "apid_db"):
                if page.get(loc_key):
                    type_specific[loc_key] = page[loc_key]
            if era == "pre1850" and len(participants) == 1:
                pass
            records.append({
                "record_id": None, "page": str(page.get("page_number", "")),
                "record_number": household_key or "", "event_type": "Census (family)",
                "year": str(census_year) if census_year else "", "event_date": "",
                "event_place": place, "english_translation": "", "original_transcription": "",
                "review": record_review,
                "review_reason": "One or more participants have unmapped columns." if record_review else None,
                "continues_on_next_image": False, "continues_from_previous_image": False,
                "type_specific_fields": type_specific,
                "participants": participants,
            })

        sheets.append({
            "page_id": str(page.get("page_number", "")),
            "document_metadata": {
                "file_name": "", "file_type": "", "volume": "",
                "pages": str(page.get("page_number", "")),
                "source_name": page.get("repository", ""),
                "source_location": ", ".join(filter(None, [page.get("state"), page.get("country")])),
            },
            "records": records,
        })

        if not citation:
            citation = {
                "call_number": "", "collection_url": "", "collection_name": collection_title,
                "repository": page.get("repository", ""), "repository_loc": page.get("repository_loc", ""),
                "publisher": page.get("publisher", ""), "pub_loc": page.get("pub_loc", ""),
                "apid_db": page.get("apid_db", ""),
            }

    return {
        "collection_title": collection_title,
        "record_type_name": record_type_name,
        "citation": citation,
        "sheets": sheets,
    }


# ==============================================================================
# LAC GATHER (folded from LAC.py)
# Downloads Heritage Canadiana microfilm images via IIIF.
# ==============================================================================

def _lac_get_env_paths():
    """Reads the necessary foundational directories mapped by the Toolbox."""
    program_dir = os.environ.get("PROGRAM_DIR", "").strip()
    media_dir = os.environ.get("MEDIA_DIR", "Media").strip()
    raw_url = os.environ.get("LAC_URL", "").strip()

    if not raw_url:
        print("[Error] No LAC_URL found in environment variables.")
        sys.exit(1)

    return program_dir, media_dir, raw_url


def _lac_parse_url(raw_url):
    """Sanitizes the user's pasted URL into a proper IIIF manifest API call."""
    print(f"[Info] Target URL: {raw_url}")

    base_id_match = re.search(r'(oocihm\.lac_reel_[a-zA-Z0-9]+)', raw_url, re.IGNORECASE)
    if not base_id_match:
        print("[Error] Could not find a valid Canadiana identifier (oocihm.lac_reel...) in the URL.")
        sys.exit(1)

    base_id = base_id_match.group(1)

    roll_match = re.search(r'lac_reel_([a-zA-Z0-9]+)', base_id, re.IGNORECASE)
    roll_num = roll_match.group(1) if roll_match else "Unknown_Roll"
    print(f"[Info] Extracted Roll Number: {roll_num}")

    manifest_url = f"https://heritage.canadiana.ca/iiif/{base_id}/manifest"
    return roll_num, manifest_url


def _lac_setup_directories(program_dir, media_dir, roll_num):
    """Constructs the final output path relative to the user's media directory."""
    if os.path.isabs(media_dir):
        base_media = media_dir
    else:
        base_media = os.path.join(program_dir, media_dir)

    out_dir = os.path.join(base_media, "LAC", roll_num).replace("\\", "/")
    os.makedirs(out_dir, exist_ok=True)
    return out_dir


def _lac_download_manifest(manifest_url):
    """Fetches the IIIF structural blueprint for the film roll."""
    print("[Info] Downloading manifest file...")
    try:
        response = requests.get(manifest_url, timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"[Error] Failed to fetch or parse manifest: {e}")
        sys.exit(1)


def _lac_download_images(manifest_data, out_dir, roll_num):
    """Loops through the manifest canvases and downloads max-resolution files."""
    if "sequences" in manifest_data and manifest_data["sequences"]:
        canvases = manifest_data["sequences"][0].get("canvases", [])
    elif "items" in manifest_data:
        canvases = manifest_data.get("items", [])
    else:
        print("[Error] No valid sequences or items found in the manifest.")
        print(f"[Debug] Manifest Keys returned: {list(manifest_data.keys())}")
        sys.exit(1)

    total = len(canvases)

    if total == 0:
        print("[Error] No images found in the manifest.")
        sys.exit(1)

    print(f"[Info] Found {total} images to download.")

    session = requests.Session()

    for i, canvas in enumerate(canvases, 1):
        try:
            img_id = ""

            if "images" in canvas:
                images = canvas.get("images", [])
                if images:
                    resource = images[0].get("resource", {})
                    img_id = resource.get("@id", "")

            elif "items" in canvas:
                items = canvas.get("items", [])
                if items:
                    annotations = items[0].get("items", [])
                    if annotations:
                        body = annotations[0].get("body", {})
                        if isinstance(body, dict):
                            img_id = body.get("id", "")
                        elif isinstance(body, list) and body:
                            img_id = body[0].get("id", "")

            if not img_id:
                print(f"\n[Warning] Could not extract image URL for canvas {i}")
                continue

            filename = f"{roll_num}_{i:04d}.jpg"
            filepath = os.path.join(out_dir, filename)

            if os.path.exists(filepath):
                print(f"\rDownloading [{i}/{total}]...", end="", flush=True)
                continue

            print(f"\rDownloading [{i}/{total}]...", end="", flush=True)

            img_resp = session.get(img_id, timeout=20)
            img_resp.raise_for_status()

            with open(filepath, 'wb') as f:
                f.write(img_resp.content)

        except Exception as e:
            print(f"\n[Warning] Failed to download image {i}: {e}")

    print(f"\n\n[System] LAC Download for {roll_num} completed successfully!")


def _lac_main() -> None:
    print("========================================")
    print(" Voyageur (LAC) - LAC IIIF Image Download")
    print("========================================")

    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
    load_dotenv(Path(__file__).resolve().parent / ".env", override=False)

    p_dir, m_dir, url = _lac_get_env_paths()
    roll, manifest = _lac_parse_url(url)
    output_directory = _lac_setup_directories(p_dir, m_dir, roll)

    manifest_json = _lac_download_manifest(manifest)
    _lac_download_images(manifest_json, output_directory, roll)


# ==============================================================================
# ANCESTRY GATHER (folded from A.py)
# ==============================================================================

def _a_move_with_retry(src: Path, dst: Path, attempts: int = 5, delay: float = 0.5) -> None:
    """Chrome (or antivirus) can hold a freshly-downloaded file open briefly."""
    for attempt in range(1, attempts + 1):
        try:
            shutil.move(str(src), str(dst))
            return
        except OSError as e:
            if attempt == attempts:
                print(f"[ERROR] Could not move {src.name} to {dst} after {attempts} attempts: {e}")
                raise
            time.sleep(delay)


def _a_cleanup_checkpoint_files(downloads_dir: Path, prefix: str, start_time: float) -> None:
    """Deletes this run's own leftover periodic checkpoint downloads."""
    for p in downloads_dir.iterdir():
        if (p.is_file() and p.suffix.lower() == '.json' and p.name.startswith(prefix)
                and '[checkpoint' in p.name and p.stat().st_mtime >= start_time):
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass


def _a_parse_ancestry_url(url: str):
    """Extract APID (dbid) and Start Record ID from Ancestry URLs."""
    view_match = re.search(r'view/(\d+):(\d+)', url)
    if view_match:
        return view_match.group(2), view_match.group(1)

    col_match = re.search(r'collections/(\d+)', url)
    pid_match = re.search(r'[?&]pId=(\d+)', url, re.IGNORECASE)
    if col_match and pid_match:
        return col_match.group(1), pid_match.group(1)

    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query)
    if 'dbid' in qs and 'h' in qs:
        return qs['dbid'][0], qs['h'][0]

    return None, None


def _a_main() -> Path:
    print("========================================")
    print(" Voyageur (A) - Ancestry Gather Automation")
    print("========================================")

    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
    load_dotenv(Path(__file__).resolve().parent / ".env", override=False)

    program_dir = os.getenv("PROGRAM_DIR", "")
    url = os.getenv("CENSUS_URL", "").strip()
    json_dir = os.getenv("JSON_DIR", "Scriptorium/Working/Project/JSON")
    base_img_setting = os.getenv("CENSUS_IMAGE_DIR", "Census")

    if not url:
        print("[ERROR] Please enter an Ancestry URL in the Toolbox settings first.")
        sys.exit(1)

    dbid, start_id = _a_parse_ancestry_url(url)
    if not dbid or not start_id:
        print("[ERROR] Could not parse database ID (dbid) or record ID (h) from the URL.")
        sys.exit(1)

    print(f"[System] Extracted -> DBID: {dbid} | Start ID: {start_id}")

    start_time = time.time()
    auto_url = url + ("&mgs_auto=1" if "?" in url else "?mgs_auto=1")
    print("[System] Launching browser...")
    webbrowser.open(auto_url)

    print("\n[System] Waiting for Tampermonkey downloads (Auto-Batch will start automatically)...")

    downloads_dir = Path.home() / "Downloads"
    json_prefix = "TMP_A_"
    image_prefix = "TMP_A_Images_"
    json_file = None

    try:
        while True:
            # noinspection broad-exception
            try:
                candidates = [
                    p for p in downloads_dir.iterdir()
                    if p.is_file() and p.suffix.lower() == '.json'
                    and p.name.startswith(json_prefix)
                    and p.stat().st_mtime >= start_time
                    and '[checkpoint' not in p.name
                ]
                if candidates:
                    json_file = max(candidates, key=lambda p: p.stat().st_mtime)
                    print(f"[System] Detected Final JSON: {json_file.name}")
            except Exception:
                pass

            if json_file:
                break
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[System] Operation cancelled by user.")
        sys.exit(0)

    print("\n[System] Processing extracted files...")

    json_target_dir = Path(program_dir) / json_dir if program_dir else Path(json_dir)
    json_target_dir.mkdir(parents=True, exist_ok=True)

    final_json = json_target_dir / json_file.name[len(json_prefix):]
    _a_move_with_retry(json_file, final_json)
    _a_cleanup_checkpoint_files(downloads_dir, json_prefix, start_time)

    with open(final_json, "r", encoding="utf-8") as f:
        raw_gather = json.load(f)
    census_year_raw = raw_gather.get("census_year", "")
    collection_title = f"{census_year_raw} US Federal Census - {raw_gather.get('location', '')}".strip(" -")
    normalized = normalize_census_pages(
        raw_gather, "ancestry_census", collection_title, f"Census_{census_year_raw}")
    with open(final_json, "w", encoding="utf-8") as f:
        json.dump(normalized, f, indent=2, ensure_ascii=False)

    set_key(str(Path(__file__).resolve().parent.parent / "Archivist" / ".env"), "JSON_FILE", final_json.name)

    stem_parts = final_json.stem.split(' - ', 1)
    census_year = stem_parts[0].strip() if len(stem_parts) > 0 else "Unknown_Year"
    raw_location = stem_parts[1].strip() if len(stem_parts) > 1 else "Unknown_Location"

    location_folder = re.sub(r'^USA\s*-\s*', '', raw_location)
    census_folder = f"{census_year} US Federal Census"

    if os.path.isabs(base_img_setting):
        base_img_dir = Path(base_img_setting)
    else:
        media_setting = os.getenv("MEDIA_DIR", "Media")
        base_media_dir = Path(media_setting) if os.path.isabs(media_setting) else (
            Path(program_dir) / media_setting if program_dir else Path(media_setting))
        base_img_dir = base_media_dir / base_img_setting
    img_target_dir = base_img_dir / census_folder / location_folder
    img_target_dir.mkdir(parents=True, exist_ok=True)

    img_count = 0
    image_candidates = [
        p for p in downloads_dir.iterdir()
        if p.is_file() and p.suffix.lower() == '.jpg'
        and p.name.startswith(image_prefix) and p.stat().st_mtime >= start_time
    ]
    for file_path in image_candidates:
        # noinspection broad-exception
        try:
            final_img = img_target_dir / file_path.name[len(image_prefix):]
            _a_move_with_retry(file_path, final_img)
            img_count += 1
        except Exception:
            pass

    print(f"[System] Moved JSON and {img_count} images to Project folders.")
    print(f"[System] Gather complete. Run Archivist's \"Generate GEDCOM\" when you're ready to "
          f"build the GEDCOM ({final_json.name}).")

    return final_json


# ==============================================================================
# FAMILYSEARCH GATHER (folded from FS.py)
# ==============================================================================

_SCRIPTORIUM_DIR = Path(__file__).resolve().parent.parent
_FACT_TYPES_PATH = _SCRIPTORIUM_DIR / "FactTypes.json"
_PARISH_PMT_PATH = _SCRIPTORIUM_DIR / "Paleographer" / "prompts" / "Parish.pmt"


def _fs_load_event_types() -> Dict[str, Dict[str, str]]:
    """Loads the toolbox-wide fact/event vocabulary from FactTypes.json."""
    data = json.loads(_FACT_TYPES_PATH.read_text(encoding="utf-8"))
    merged: Dict[str, Dict[str, str]] = {}
    for bucket in ("person", "family"):
        for name, entry in data.get(bucket, {}).items():
            merged[name] = {"code": entry["code"], "id_prefix": f"{entry['gedcom_tag']}-"}
    return merged


def _fs_load_roles() -> Dict[str, Dict[str, Optional[str]]]:
    """Loads Parish.pmt's participant role vocabulary."""
    raw = _PARISH_PMT_PATH.read_text(encoding="utf-8")
    stripped = raw.lstrip()
    if not stripped.startswith("---"):
        return {}
    parts = stripped.split("---", 2)
    if len(parts) < 3:
        return {}
    front_matter = yaml.safe_load(parts[1]) or {}
    return front_matter.get("roles", {})


_FS_EVENT_TYPE_ALIASES = {
    "Christening": "Christen",
}

_FS_ROLE_COLUMN_MAP = {
    "Name": "Primary",
    "Father's Name": "Father",
    "Mother's Name": "Mother",
    "Spouse's Name": "Spouse",
    "Spouse's Father's Name": "Father of Spouse",
    "Spouse's Mother's Name": "Mother of Spouse",
}
_FS_SEX_COLUMN_MAP = {
    "Name": "Sex",
    "Father's Name": "Father's Sex",
    "Mother's Name": "Mother's Sex",
    "Spouse's Name": "Spouse's Sex",
    "Spouse's Father's Name": "Spouse's Father's Sex",
    "Spouse's Mother's Name": "Spouse's Mother's Sex",
}

_FS_RECORD_FAMILY_KEYWORDS = {
    "church": ["church", "baptism", "baptême", "marriage", "mariage", "burial", "sépulture",
               "parish", "paroiss", "christening", "confirmation"],
    "census": ["census", "population schedule"],
    "scrip": ["scrip"],
    "wills": ["will", "probate", "estate", "testament"],
}

_FS_NAME_MATCH_THRESHOLD = 85
_FS_PARENT_MATCH_THRESHOLD = 80

_FS_CITATION_RE = re.compile(
    r'^"(?P<collection_name>.+?),"\s+database with images,\s+(?P<repository>.+?)\s*\(.*?\),\s*'
    r'(?P<browse_path>.+?);\s*(?P<publisher>.+?),\s*(?P<pub_loc>[^,]+?)\.\s*$'
)

_FS_MONTH_NAMES = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sept": 9, "sep": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}
_FS_ISO_DATE_PATTERN = re.compile(r"^\s*(\d{4})-(\d{2})-(\d{2})\s*$")
_FS_ISO_YEAR_MONTH_PATTERN = re.compile(r"^\s*(\d{4})-(\d{2})\s*$")
_FS_DATE_PATTERNS = [
    re.compile(r"^\s*([A-Za-z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{3,4})\s*$"),
    re.compile(r"^\s*(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\.?,?\s+(\d{3,4})\s*$"),
    re.compile(r"^\s*([A-Za-z]+)\.?\s+(\d{3,4})\s*$"),
    re.compile(r"^\s*(\d{3,4})\s*$"),
]

_FS_NARA_CITING_RE = re.compile(
    r'citing\s+NARA\s+microfilm\s+publication\s+(?P<publication>\S+?)\s*'
    r'\((?P<repo_loc>[^:()]+):\s*(?P<repo_name>[^,()]+),\s*n\.d\.\)',
    re.IGNORECASE
)

_FS_CATALOG_ROLL_RE = re.compile(
    r'NARA Series\s+(?P<series>[A-Za-z0-9]+),\s*Roll\s+(?P<roll>[A-Za-z0-9]+)',
    re.IGNORECASE
)


def _fs_parse_to_iso(reading: Optional[str]) -> Optional[str]:
    """Parses an English-language date reading into ISO form."""
    if not reading:
        return None
    text = reading.strip()
    if _FS_ISO_DATE_PATTERN.match(text) or _FS_ISO_YEAR_MONTH_PATTERN.match(text):
        return text
    m = _FS_DATE_PATTERNS[0].match(text)
    if m:
        month = _FS_MONTH_NAMES.get(m.group(1).lower())
        if month:
            return f"{int(m.group(3)):04d}-{month:02d}-{int(m.group(2)):02d}"
    m = _FS_DATE_PATTERNS[1].match(text)
    if m:
        month = _FS_MONTH_NAMES.get(m.group(2).lower())
        if month:
            return f"{int(m.group(3)):04d}-{month:02d}-{int(m.group(1)):02d}"
    m = _FS_DATE_PATTERNS[2].match(text)
    if m:
        month = _FS_MONTH_NAMES.get(m.group(1).lower())
        if month:
            return f"{int(m.group(2)):04d}-{month:02d}"
    m = _FS_DATE_PATTERNS[3].match(text)
    if m:
        return f"{int(m.group(1)):04d}"
    return None


def _fs_derive_record_identity(record: Dict[str, Any], event_types_table: Dict[str, Dict[str, str]]) -> None:
    event_type = record.get("event_type")
    entry = event_types_table.get(event_type) if event_type else None
    if not entry:
        return
    record["record_type_code"] = entry.get("code")
    record_number = record.get("record_number")
    if record_number:
        record["record_id"] = f"{entry.get('id_prefix', '')}{record_number}"


def _fs_derive_role_number(role_name: str, roles_table: Dict[str, Dict[str, Optional[str]]]) -> Optional[str]:
    name_to_number = {(role.get("name") or "").strip().lower(): number for number, role in roles_table.items()}
    return name_to_number.get((role_name or "").strip().lower())


def _fs_derive_role_semantic(role_number: Optional[str],
                             roles_table: Dict[str, Dict[str, Optional[str]]]) -> Optional[str]:
    role = roles_table.get(role_number) if role_number else None
    return role.get("semantic") if role else None


def _fs_split_name_and_dit(full: str) -> Tuple[str, str, Optional[str]]:
    """Splits a single displayed Name column into (given, surname, dit_name)."""
    dit_match = re.search(r'\bdit\b', full, re.IGNORECASE)
    dit_name = None
    if dit_match:
        dit_name = full[dit_match.end():].strip() or None
        full = full[:dit_match.start()].strip()
    parts = full.split()
    if len(parts) >= 2:
        return " ".join(parts[:-1]), parts[-1], dit_name
    return "", full, dit_name


def _fs_sex_code(raw: str) -> str:
    raw = (raw or "").strip().lower()
    if raw.startswith("f"):
        return "F"
    if raw.startswith("m"):
        return "M"
    return ""


def _fs_build_participant(role_name: str, full_name: str, sex: str,
                          fsftid: str = "", person_ark: str = "") -> Dict[str, Any]:
    given, surname, dit_name = _fs_split_name_and_dit(full_name)
    type_specific_fields: Dict[str, Any] = {}
    if fsftid:
        type_specific_fields["fsftid"] = fsftid
    if person_ark:
        type_specific_fields["person_ark"] = person_ark
    return {
        "role_number": None, "role_name": cap_case(role_name),
        "std_given": given, "std_surname": surname or None,
        "raw_given": None, "raw_surname": None,
        "dit_name": dit_name, "prefix": None, "suffix": None,
        "sex": sex, "is_priest": False, "age": None, "occupation": None,
        "race": None, "religion": None, "residence": None,
        "birth_date": None, "birth_place": None, "death_date": None, "death_place": None,
        "review": False, "review_reason": None, "type_specific_fields": type_specific_fields,
    }


def _fs_row_to_record(row: dict, item_id: str, row_index: int) -> dict:
    """Converts one raw Image Index row into a schema.json-shaped record."""
    columns = row.get("columns", {})
    participants = []
    primary: Optional[Dict[str, Any]] = None
    for name_col, role_name in _FS_ROLE_COLUMN_MAP.items():
        full = (columns.get(name_col) or "").strip()
        if not full:
            continue
        fsftid = row.get("attached_fsftid", "") if role_name == "Primary" else ""
        person_ark = row.get("person_ark", "") if role_name == "Primary" else ""
        participant = _fs_build_participant(role_name, full,
                                            _fs_sex_code(columns.get(_FS_SEX_COLUMN_MAP[name_col], "")),
                                            fsftid, person_ark)
        participants.append(participant)
        if role_name == "Primary":
            primary = participant

    if primary is not None:
        primary["age"] = (columns.get("Age") or "").strip() or None
        birth_date = (columns.get("Birth Date") or "").strip() or (columns.get("Birth Year (Estimated)") or "").strip()
        primary["birth_date"] = _fs_parse_to_iso(birth_date) or (birth_date or None)
        death_date = (columns.get("Death Date") or "").strip()
        primary["death_date"] = _fs_parse_to_iso(death_date) or (death_date or None)
        legitimacy = (columns.get("Legitimacy") or "").strip()
        if legitimacy:
            primary["type_specific_fields"]["legitimacy"] = legitimacy

    raw_event_type = (columns.get("Event Type") or "").strip()
    event_type = cap_case(_FS_EVENT_TYPE_ALIASES.get(raw_event_type, raw_event_type))
    event_date_raw = (columns.get("Event Date") or "").strip()

    page = (columns.get("Page Number") or "").strip() or item_id
    record_number = (columns.get("Entry Number") or "").strip() or str(row_index + 1)

    return {
        "record_id": None, "page": page, "record_number": record_number,
        "record_type_code": None, "event_type": event_type,
        "year": (_fs_parse_to_iso(event_date_raw) or "")[:4] or None,
        "event_date": _fs_parse_to_iso(event_date_raw) or event_date_raw or None,
        "event_place": cap_case((columns.get("Event Place") or "").strip()) or None,
        "english_translation": "", "original_transcription": "",
        "review": False, "review_reason": None, "type_specific_fields": {},
        "participants": participants,
    }


def _fs_normalize_date(raw: Optional[str]) -> str:
    if not raw:
        return ""
    try:
        return pd.to_datetime(raw, errors="raise").strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return raw.strip().lower()


def _fs_get_role(record: dict, role_name: str) -> Optional[dict]:
    for p in record.get("participants", []):
        if p.get("role_name") == role_name:
            return p
    return None


def _fs_full_name(participant: dict) -> str:
    return f"{participant.get('std_given', '') or ''} {participant.get('std_surname', '') or ''}".strip()


def _fs_match_and_link_records(records: List[dict]) -> None:
    """Groups a single item's records by date, fuzzy-matches candidates, stamps a shared
    link_id onto matching participants."""
    by_date: Dict[str, List[int]] = {}
    for idx, rec in enumerate(records):
        key = _fs_normalize_date(rec.get("event_date"))
        if key:
            by_date.setdefault(key, []).append(idx)

    for idxs in by_date.values():
        if len(idxs) < 2:
            continue
        matched = set()
        for i, idx_a in enumerate(idxs):
            if idx_a in matched:
                continue
            rec_a = records[idx_a]
            primary_a = _fs_get_role(rec_a, "Primary")
            if not primary_a or not _fs_full_name(primary_a):
                continue

            for idx_b in idxs[i + 1:]:
                if idx_b in matched:
                    continue
                rec_b = records[idx_b]
                primary_b = _fs_get_role(rec_b, "Primary")
                if not primary_b or not _fs_full_name(primary_b):
                    continue

                if fuzz.token_set_ratio(_fs_full_name(primary_a), _fs_full_name(primary_b)) < _FS_NAME_MATCH_THRESHOLD:
                    continue

                conflict = False
                for role_name in ("Father", "Mother"):
                    pa, pb = _fs_get_role(rec_a, role_name), _fs_get_role(rec_b, role_name)
                    if pa and pb and _fs_full_name(pa) and _fs_full_name(pb):
                        if fuzz.token_set_ratio(_fs_full_name(pa), _fs_full_name(pb)) < _FS_PARENT_MATCH_THRESHOLD:
                            conflict = True
                            break
                if conflict:
                    continue

                date_key = _fs_normalize_date(rec_a.get("event_date"))
                link_seed = f"{date_key}_{_fs_full_name(primary_a).strip().lower()}"
                for role_name in ("Primary", "Father", "Mother", "Spouse"):
                    pa, pb = _fs_get_role(rec_a, role_name), _fs_get_role(rec_b, role_name)
                    if pa and pb:
                        shared = link_seed if role_name == "Primary" else f"{link_seed}_{role_name}"
                        pa.setdefault("type_specific_fields", {})["link_id"] = shared
                        pb.setdefault("type_specific_fields", {})["link_id"] = shared

                matched.add(idx_a)
                matched.add(idx_b)
                break


def _fs_parse_citation(text: str) -> Dict[str, str]:
    """Parses FamilySearch's own generated citation prose."""
    result = {"repository": "", "repository_loc": "", "publisher": "", "pub_loc": "",
              "collection_name": "", "collection_url": "", "browse_path": ""}
    if not text:
        return result

    url_match = re.search(r'\((https?://\S+)\s+:', text)
    if url_match:
        result["collection_url"] = url_match.group(1)

    m = _FS_CITATION_RE.match(text.strip())
    if m:
        result["collection_name"] = m.group("collection_name").strip()
        result["repository"] = m.group("repository").strip()
        result["publisher"] = m.group("publisher").strip()
        result["pub_loc"] = m.group("pub_loc").strip()
        result["browse_path"] = m.group("browse_path").strip()
    return result


def _fs_detect_record_family(text: str) -> str:
    lowered = text.lower()
    for family, keywords in _FS_RECORD_FAMILY_KEYWORDS.items():
        if any(k in lowered for k in keywords):
            return family
    return "other"


def _fs_dedup_catalog_items(items_raw: List[dict]) -> Dict[str, dict]:
    catalog_items: Dict[str, dict] = {}
    for it in items_raw:
        for ci in it.get("catalog_items", []):
            item_number = ci.get("item_number", "")
            if item_number and item_number not in catalog_items:
                catalog_items[item_number] = ci
    return catalog_items


def _fs_detect_record_family_from_raw(raw: dict, catalog_items: Dict[str, dict]) -> str:
    collection_title = raw.get("collection_title", "")
    catalog_text = " ".join(f"{ci.get('label', '')} {ci.get('note', '')}" for ci in catalog_items.values())
    return _fs_detect_record_family(f"{collection_title} {catalog_text}")


def _fs_build_universal_json(raw: dict, items_raw: List[dict], catalog_items: Dict[str, dict],
                             record_family: str) -> dict:
    event_types_table = _fs_load_event_types()
    roles_table = _fs_load_roles()

    first_citation_text = next((it.get("citation_text", "") for it in items_raw if it.get("citation_text")), "")
    citation = _fs_parse_citation(first_citation_text)
    collection_title = raw.get("collection_title", "")

    sheets = []
    for it in items_raw:
        item_id = it.get("item_id", "")
        records = [_fs_row_to_record(row, item_id, idx) for idx, row in enumerate(it.get("rows", []))]
        records = [r for r in records if r["participants"]]
        _fs_match_and_link_records(records)

        for record in records:
            _fs_derive_record_identity(record, event_types_table)
            for participant in record["participants"]:
                role_number = _fs_derive_role_number(participant["role_name"], roles_table)
                if role_number is not None:
                    participant["role_number"] = role_number
                    role_semantic = _fs_derive_role_semantic(role_number, roles_table)
                    if role_semantic is not None:
                        participant["role_semantic"] = role_semantic

        sheets.append({
            "page_id": item_id,
            "document_metadata": {
                "file_name": "", "file_type": "", "volume": "", "pages": "",
                "source_name": "", "source_location": "",
            },
            "records": records,
        })

    return {
        "collection_title": collection_title,
        "record_family": record_family,
        "citation": {**citation, "apid_db": "", "catalog_items": list(catalog_items.values())},
        "sheets": sheets,
    }


def _fs_parse_census_browse_path(browse_path: str) -> Dict[str, str]:
    """Splits FamilySearch's citation browse-path text into a location hierarchy."""
    empty = {"state": "", "county": "", "city": "", "enumeration_district": ""}
    if not browse_path:
        return empty

    segments = [s.strip() for s in browse_path.split(">")]
    segments = [s for s in segments if s and not re.match(r'^image\s+\d+\s+of\s+\d+$', s, re.IGNORECASE)]

    ed_index = next((i for i, s in enumerate(segments)
                     if re.search(r'\bED\b|enumeration district', s, re.IGNORECASE)), None)
    enumeration_district = segments[ed_index] if ed_index is not None else ""
    location_segments = [s for i, s in enumerate(segments) if i != ed_index]

    return {
        "state": location_segments[0] if len(location_segments) > 0 else "",
        "county": location_segments[1] if len(location_segments) > 1 else "",
        "city": location_segments[2] if len(location_segments) > 2 else "",
        "enumeration_district": enumeration_district,
    }


def _fs_parse_nara_citing_clause(citation_text: str) -> Dict[str, str]:
    """Extracts the NARA-specific citing clause from a US census citation."""
    m = _FS_NARA_CITING_RE.search(citation_text or "")
    if not m:
        return {"publication": "", "repository": "", "repository_loc": ""}
    return {
        "publication": m.group("publication").strip(),
        "repository": m.group("repo_name").strip(),
        "repository_loc": m.group("repo_loc").strip(),
    }


def _fs_parse_catalog_roll(catalog_items: Dict[str, dict]) -> Dict[str, str]:
    """Extracts NARA microfilm series + roll from the Catalog Record table."""
    for ci in catalog_items.values():
        note = ci.get("note", "") or ci.get("label", "")
        m = _FS_CATALOG_ROLL_RE.search(note)
        if m:
            return {"series": m.group("series"), "roll": m.group("roll")}
    return {"series": "", "roll": ""}


def _fs_split_full_name(full_name: str) -> Tuple[str, str]:
    parts = full_name.strip().split()
    if len(parts) < 2:
        return full_name.strip(), ""
    return " ".join(parts[:-1]), parts[-1]


def _fs_build_census_json(raw: dict, items_raw: List[dict], catalog_items: Dict[str, dict]) -> dict:
    """Converts FamilySearch's raw census gather into the {census_year, location, pages}
    shape Ancestry's own gather already produces."""
    first_citation_text = next((it.get("citation_text", "") for it in items_raw if it.get("citation_text")), "")
    citation = _fs_parse_citation(first_citation_text)
    location_info = _fs_parse_census_browse_path(citation.get("browse_path", ""))

    nara_info = _fs_parse_nara_citing_clause(first_citation_text)
    roll_info = _fs_parse_catalog_roll(catalog_items)
    roll_number = (f"{roll_info['series']}_{roll_info['roll']}" if roll_info['series'] and roll_info['roll']
                   else roll_info['series'] or nara_info['publication'])

    publisher = nara_info["repository"] or citation.get("publisher", "")
    pub_loc = nara_info["repository_loc"] or citation.get("pub_loc", "")

    collection_title = raw.get("collection_title", "")
    year_match = re.search(r'(1[789]\d0|19[0-4]\d|1950)', collection_title)
    census_year = year_match.group(1) if year_match else ""
    country = "Canada" if "canada" in collection_title.lower() else "USA"

    pages = []
    for page_number, it in enumerate(items_raw, start=1):
        item_id = it.get("item_id", "")
        people = []
        for row_index, row in enumerate(it.get("rows", [])):
            columns = dict(row.get("columns", {}))
            if not any(re.search(r'line', k, re.IGNORECASE) for k in columns):
                columns["Line Number"] = str(row_index + 1)

            name_val = columns.pop("Name", None)
            if name_val and not columns.get("Given Name") and not columns.get("Surname"):
                given, surname = _fs_split_full_name(str(name_val))
                columns["Given Name"] = given
                columns["Surname"] = surname

            person_ark = row.get("person_ark", "")
            people.append({
                "columns": columns,
                "pid": person_ark or f"{item_id}-{row_index + 1}",
                "fsftid": row.get("attached_fsftid", ""),
                "person_ark": person_ark,
                "familysearch_url": f"https://www.familysearch.org/ark:/61903/1:1:{person_ark}" if person_ark else "",
            })

        pages.append({
            "page_number": page_number, "image_id": item_id, "country": country,
            "state": location_info["state"], "county": location_info["county"],
            "city": location_info["city"], "place_details": "",
            "enumeration_district": location_info["enumeration_district"],
            "film_number": "", "roll_number": roll_number, "apid_db": "",
            "repository": citation.get("repository", ""),
            "repository_loc": citation.get("repository_loc", ""),
            "publisher": publisher, "pub_loc": pub_loc, "people": people,
        })

    return {"census_year": census_year, "location": location_info["state"], "pages": pages}


def _fs_read_text_with_retry(path: Path, attempts: int = 5, delay: float = 0.5) -> str:
    for attempt in range(1, attempts + 1):
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            if attempt == attempts:
                raise
            time.sleep(delay)


def _fs_unlink_with_retry(path: Path, attempts: int = 5, delay: float = 0.5) -> None:
    for attempt in range(1, attempts + 1):
        try:
            path.unlink(missing_ok=True)
            return
        except OSError:
            if attempt == attempts:
                raise
            time.sleep(delay)


def _fs_move_with_retry(src: Path, dst: Path, attempts: int = 5, delay: float = 0.5) -> None:
    for attempt in range(1, attempts + 1):
        try:
            shutil.move(str(src), str(dst))
            return
        except OSError as e:
            if attempt == attempts:
                print(f"[ERROR] Could not move {src.name} to {dst} after {attempts} attempts: {e}")
                raise
            time.sleep(delay)


def _fs_cleanup_checkpoint_files(downloads_dir: Path, prefix: str, start_time: float) -> None:
    for p in downloads_dir.iterdir():
        if (p.is_file() and p.suffix.lower() == '.json' and p.name.startswith(prefix)
                and '[checkpoint' in p.name and p.stat().st_mtime >= start_time):
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass


def _fs_build_clean_census_filename(year: str, normalized_data: dict) -> Optional[str]:
    """Builds a "{year} - {state} - {county} - {city} - FS.json" name."""
    for sheet in normalized_data.get("sheets", []):
        for record in sheet.get("records", []):
            fields = record.get("type_specific_fields", {}) or {}
            parts = [year] + [fields[key] for key in ("state", "county", "city") if fields.get(key)]
            if len(parts) > 1:
                safe = " - ".join(parts)
                safe = re.sub(r'[/\\?%*:|"<>]', "-", safe)
                return f"{safe} - FS.json"
    return None


def _fs_main() -> Optional[Path]:
    print("========================================")
    print(" Voyageur (FS) - FamilySearch Gather Automation")
    print("========================================")

    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
    load_dotenv(Path(__file__).resolve().parent / ".env", override=False)

    program_dir = os.getenv("PROGRAM_DIR", "")
    url = os.getenv("FS_URL", "").strip()
    json_dir = os.getenv("JSON_DIR", "Scriptorium/Working/Project/JSON")

    if not url:
        print("[ERROR] Please enter a FamilySearch record URL in the Toolbox settings first.")
        sys.exit(1)

    start_time = time.time()
    auto_url = url + ("&mgs_auto=1" if "?" in url else "?mgs_auto=1")
    print("[System] Launching browser...")
    webbrowser.open(auto_url)

    print("\n[System] Waiting for Tampermonkey downloads (Auto-Batch will start automatically)...")

    downloads_dir = Path.home() / "Downloads"
    json_prefix = "TMP_FS_"
    image_prefix = "TMP_FS_Images_"
    raw_json_file = None

    try:
        while True:
            # noinspection broad-exception
            try:
                candidates = [
                    p for p in downloads_dir.iterdir()
                    if p.is_file() and p.suffix.lower() == '.json'
                    and p.name.startswith(json_prefix)
                    and p.stat().st_mtime >= start_time
                    and '[checkpoint' not in p.name
                ]
                if candidates:
                    raw_json_file = max(candidates, key=lambda p: p.stat().st_mtime)
                    print(f"[System] Detected raw gather JSON: {raw_json_file.name}")
            except Exception:
                pass

            if raw_json_file:
                break
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[System] Operation cancelled by user.")
        sys.exit(0)

    raw_data = json.loads(_fs_read_text_with_retry(raw_json_file))
    items_raw = raw_data.get("items", [])
    catalog_items = _fs_dedup_catalog_items(items_raw)
    record_family = _fs_detect_record_family_from_raw(raw_data, catalog_items)

    clean_name = None
    if record_family == "census":
        print("\n[System] Converting raw scrape into census Gather JSON...")
        raw_census = _fs_build_census_json(raw_data, items_raw, catalog_items)
        collection_title = raw_data.get("collection_title", "")
        final_data = normalize_census_pages(
            raw_census, "familysearch_census", collection_title,
            f"Census_{raw_census.get('census_year', '')}")
        clean_name = _fs_build_clean_census_filename(raw_census.get("census_year", ""), final_data)
    else:
        print("\n[System] Converting raw scrape into the universal Gather JSON...")
        final_data = _fs_build_universal_json(raw_data, items_raw, catalog_items, record_family)

    json_target_dir = Path(program_dir) / json_dir if program_dir else Path(json_dir)
    json_target_dir.mkdir(parents=True, exist_ok=True)

    out_name = clean_name or raw_json_file.name[len(json_prefix):]
    final_json = json_target_dir / out_name
    final_json.write_text(json.dumps(final_data, indent=2, ensure_ascii=False), encoding="utf-8")
    _fs_unlink_with_retry(raw_json_file)
    _fs_cleanup_checkpoint_files(downloads_dir, json_prefix, start_time)

    stem = re.sub(r' - FS$', '', final_json.stem)
    stem_parts = stem.split(' - ', 1)
    census_year = stem_parts[0].strip() if stem_parts and stem_parts[0].strip() else "Unknown_Year"
    location_folder = stem_parts[1].strip() if len(stem_parts) > 1 else "Unknown_Location"
    census_folder = f"{census_year} US Federal Census"

    base_img_setting = os.getenv("CENSUS_IMAGE_DIR", "Census")
    if os.path.isabs(base_img_setting):
        base_img_dir = Path(base_img_setting)
    else:
        media_setting = os.getenv("MEDIA_DIR", "Media")
        base_media_dir = Path(media_setting) if os.path.isabs(media_setting) else (
            Path(program_dir) / media_setting if program_dir else Path(media_setting))
        base_img_dir = base_media_dir / base_img_setting
    img_target_dir = base_img_dir / census_folder / location_folder
    img_target_dir.mkdir(parents=True, exist_ok=True)

    img_count = 0
    image_candidates = [
        p for p in downloads_dir.iterdir()
        if p.is_file() and p.suffix.lower() == '.jpg'
        and p.name.startswith(image_prefix) and p.stat().st_mtime >= start_time
    ]
    for file_path in image_candidates:
        # noinspection broad-exception
        try:
            final_img = img_target_dir / file_path.name[len(image_prefix):]
            _fs_move_with_retry(file_path, final_img)
            img_count += 1
        except Exception:
            pass

    print(f"[System] Moved {img_count} image(s) to Project folder.")

    set_key(str(Path(__file__).resolve().parent.parent / "Archivist" / ".env"), "JSON_FILE", final_json.name)

    total_records = sum(len(sheet["records"]) for sheet in final_data["sheets"])
    label = final_data.get("record_type_name") or final_data.get("record_family", "")
    print(f"[System] Gather complete: {len(final_data['sheets'])} image(s), {total_records} record(s), "
          f"record type '{label}'.")
    print(f"[System] Run Archivist's \"Generate GEDCOM\" when you're ready ({final_json.name}).")

    return final_json


# ==============================================================================
# DISPATCHER
# ==============================================================================

SOURCES = ("A", "FS", "LAC")

_SOURCE_MAINS = {
    "A": _a_main,
    "FS": _fs_main,
    "LAC": _lac_main,
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in SOURCES:
        print(f"[ERROR] Usage: python Voyageur.py <source>, where <source> is one of: "
              f"{', '.join(SOURCES)}.")
        sys.exit(1)

    _SOURCE_MAINS[sys.argv[1]]()


if __name__ == "__main__":
    main()
