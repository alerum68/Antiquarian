"""
Voyageur (FS) - FamilySearch Gather.

Launches Voyageur.js's runFamilySearchGather() against a FamilySearch record page, waits for
its downloaded raw-scrape JSON, then converts that raw scrape into Paleographer/schema.json's
own shape (sheets -> records -> participants), so Archivist can process an already-indexed
FamilySearch collection exactly the same way it processes Paleographer's AI-transcribed
output. Event/fact vocabulary comes from the shared FactTypes.json (RootsMagic's own fact
types); participant role vocabulary comes from Parish.pmt's roles table, since every FS
gather so far is a parish/church register. Both are read directly as data (YAML/JSON) rather
than imported as code, keeping this tool self-contained like every other one in the toolbox.

Also handles same-person matching across duplicate index entries (stamping a shared link_id
rather than merging records - see Archivist's generate_uid, which already knows to prefer
link_id over its own hash).

Also fetches the source image itself (see downloadFsImage in Voyageur.js) - FamilySearch's
own image viewer's "Download" button turned out to fetch the complete page directly from its
deepzoomcloud storage service, keyed by the same item_id already scraped for citations, with
no tile-stitching needed at all.
"""

import json
import os
import re
import shutil
import sys
import time
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import yaml
from dotenv import load_dotenv, set_key
from thefuzz import fuzz

import census_schema

SCRIPTORIUM_DIR = Path(__file__).resolve().parent.parent
FACT_TYPES_PATH = SCRIPTORIUM_DIR / "FactTypes.json"
PARISH_PMT_PATH = SCRIPTORIUM_DIR / "Paleographer" / "prompts" / "Parish.pmt"

# ==========================================
# SHARED VOCABULARY (read as data, not imported as code - see module docstring)
# ==========================================


def load_event_types() -> Dict[str, Dict[str, str]]:
    """Loads the toolbox-wide fact/event vocabulary from FactTypes.json (RootsMagic's own
    FactTypeTable, defaults plus this project's customs). Person and family buckets are
    flattened into one lookup keyed by name - RootsMagic itself never reuses a name across
    the two (e.g. "Residence" vs "Residence (family)"), so a flat merge can't collide."""
    data = json.loads(FACT_TYPES_PATH.read_text(encoding="utf-8"))
    merged: Dict[str, Dict[str, str]] = {}
    for bucket in ("person", "family"):
        for name, entry in data.get(bucket, {}).items():
            merged[name] = {"code": entry["code"], "id_prefix": f"{entry['gedcom_tag']}-"}
    return merged


def load_roles() -> Dict[str, Dict[str, Optional[str]]]:
    """Loads Parish.pmt's participant role vocabulary (Primary/Father/Mother/Spouse/Father of
    Spouse/Mother of Spouse/godparents) - every FS gather so far is a parish register, so
    this is the right vocabulary source, same as Paleographer's own AI transcription uses."""
    raw = PARISH_PMT_PATH.read_text(encoding="utf-8")
    stripped = raw.lstrip()
    if not stripped.startswith("---"):
        return {}
    parts = stripped.split("---", 2)
    if len(parts) < 3:
        return {}
    front_matter = yaml.safe_load(parts[1]) or {}
    return front_matter.get("roles", {})


# Event Type values as FamilySearch's Image Index actually spells them, mapped to
# FactTypes.json's own fact names where they differ (e.g. FamilySearch says
# "Christening", RootsMagic's built-in fact is named "Christen").
EVENT_TYPE_ALIASES = {
    "Christening": "Christen",
}

# Column names as they actually appear in FamilySearch's Image Index table (dynamic per
# record type - a Baptism-only page has no Spouse columns at all, for example), mapped to
# Parish.pmt's own role names. Extend this table as new column names are seen on other
# collections; anything not listed here is simply not extracted rather than guessed at.
ROLE_COLUMN_MAP = {
    "Name": "Primary",
    "Father's Name": "Father",
    "Mother's Name": "Mother",
    "Spouse's Name": "Spouse",
    "Spouse's Father's Name": "Father of Spouse",
    "Spouse's Mother's Name": "Mother of Spouse",
}
SEX_COLUMN_MAP = {
    "Name": "Sex",
    "Father's Name": "Father's Sex",
    "Mother's Name": "Mother's Sex",
    "Spouse's Name": "Spouse's Sex",
    "Spouse's Father's Name": "Spouse's Father's Sex",
    "Spouse's Mother's Name": "Spouse's Mother's Sex",
}

# Keyword match used to auto-detect record_family from the collection title/catalog text -
# generalizes Scriptorium.py's existing _record_type_family() keyword-matching so Archivist's
# single "Generate GEDCOM" button can dispatch without a manual per-type pick.
RECORD_FAMILY_KEYWORDS = {
    "church": ["church", "baptism", "baptême", "marriage", "mariage", "burial", "sépulture",
               "parish", "paroiss", "christening", "confirmation"],
    "census": ["census", "population schedule"],
    "scrip": ["scrip"],
    "wills": ["will", "probate", "estate", "testament"],
}

NAME_MATCH_THRESHOLD = 85
PARENT_MATCH_THRESHOLD = 80

CITATION_RE = re.compile(
    r'^"(?P<collection_name>.+?),"\s+database with images,\s+(?P<repository>.+?)\s*\(.*?\),\s*'
    r'(?P<browse_path>.+?);\s*(?P<publisher>.+?),\s*(?P<pub_loc>[^,]+?)\.\s*$'
)

MONTH_NAMES = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sept": 9, "sep": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}
_ISO_DATE_PATTERN = re.compile(r"^\s*(\d{4})-(\d{2})-(\d{2})\s*$")
_ISO_YEAR_MONTH_PATTERN = re.compile(r"^\s*(\d{4})-(\d{2})\s*$")
_DATE_PATTERNS = [
    re.compile(r"^\s*([A-Za-z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{3,4})\s*$"),  # "December 12, 1850"
    re.compile(r"^\s*(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\.?,?\s+(\d{3,4})\s*$"),  # "12 December 1850"
    re.compile(r"^\s*([A-Za-z]+)\.?\s+(\d{3,4})\s*$"),                                # "December 1850"
    re.compile(r"^\s*(\d{3,4})\s*$"),                                                 # bare year "1850"
]


def parse_to_iso(reading: Optional[str]) -> Optional[str]:
    """Parses a plain English-language date reading into YYYY-MM-DD (or a coarser YYYY-MM /
    YYYY if day/month aren't stated). Mirrors Paleographer/postprocess.py's parse_to_iso -
    duplicated locally rather than imported, per this project's convention of every tool
    folder staying self-contained (see module docstring)."""
    if not reading:
        return None
    text = reading.strip()

    if _ISO_DATE_PATTERN.match(text) or _ISO_YEAR_MONTH_PATTERN.match(text):
        return text

    m = _DATE_PATTERNS[0].match(text)
    if m:
        month = MONTH_NAMES.get(m.group(1).lower())
        if month:
            return f"{int(m.group(3)):04d}-{month:02d}-{int(m.group(2)):02d}"

    m = _DATE_PATTERNS[1].match(text)
    if m:
        month = MONTH_NAMES.get(m.group(2).lower())
        if month:
            return f"{int(m.group(3)):04d}-{month:02d}-{int(m.group(1)):02d}"

    m = _DATE_PATTERNS[2].match(text)
    if m:
        month = MONTH_NAMES.get(m.group(1).lower())
        if month:
            return f"{int(m.group(2)):04d}-{month:02d}"

    m = _DATE_PATTERNS[3].match(text)
    if m:
        return f"{int(m.group(1)):04d}"

    return None


def derive_record_identity(record: Dict[str, Any], event_types_table: Dict[str, Dict[str, str]]) -> None:
    """Sets record_type_code and record_id (prefix + record_number) from event_type, looked
    up in the shared FactTypes.json table. No-ops if event_type isn't recognized."""
    event_type = record.get("event_type")
    entry = event_types_table.get(event_type) if event_type else None
    if not entry:
        return
    record["record_type_code"] = entry.get("code")
    record_number = record.get("record_number")
    if record_number:
        record["record_id"] = f"{entry.get('id_prefix', '')}{record_number}"


def derive_role_number(role_name: str, roles_table: Dict[str, Dict[str, Optional[str]]]) -> Optional[str]:
    """Looks up a participant's role_number from their plain-word role_name (case-insensitive
    match on the role's display name), same convention as Paleographer/postprocess.py."""
    name_to_number = {(role.get("name") or "").strip().lower(): number for number, role in roles_table.items()}
    return name_to_number.get((role_name or "").strip().lower())


def derive_role_semantic(role_number: Optional[str],
                         roles_table: Dict[str, Dict[str, Optional[str]]]) -> Optional[str]:
    """Looks up a participant's role_semantic from their already-resolved role_number, same
    convention as Paleographer/postprocess.py.derive_role_semantics - this is the field
    Archivist actually reads to build FAMC/FAMS/associations, so an indexed row's plain
    'Relationship'/'Role' column value has to reach it the same way an AI-read role_name
    does, not just role_number (which Archivist no longer uses for family linking)."""
    role = roles_table.get(role_number) if role_number else None
    return role.get("semantic") if role else None


# ==========================================
# ROW -> RECORD MAPPING
# ==========================================
def split_name_and_dit(full: str) -> Tuple[str, str, Optional[str]]:
    """Splits a single displayed "Name" column into (given, surname, dit_name).
    FamilySearch's index doesn't carry given/surname separately, so this is a plain
    last-word-is-surname heuristic - correct for the vast majority of European-style names
    in these registers, and a single-word name (common for parents who aren't the record's
    own primary) is treated as surname-only rather than guessed at. A "dit" name (a second,
    commonly-used surname convention in French-Canadian and Métis families) is split out
    into its own field when present, e.g. "Jean Morin dit Lagimodiere" -> given="Jean",
    surname="Morin", dit_name="Lagimodiere" - matching how Archivist already reads
    participant['dit_name'] to emit the GEDCOM "dit Name" fact."""
    dit_match = re.search(r'\bdit\b', full, re.IGNORECASE)
    dit_name = None
    if dit_match:
        dit_name = full[dit_match.end():].strip() or None
        full = full[:dit_match.start()].strip()

    parts = full.split()
    if len(parts) >= 2:
        return " ".join(parts[:-1]), parts[-1], dit_name
    return "", full, dit_name


def sex_code(raw: str) -> str:
    raw = (raw or "").strip().lower()
    if raw.startswith("f"):
        return "F"
    if raw.startswith("m"):
        return "M"
    return ""


def build_participant(role_name: str, full_name: str, sex: str,
                      fsftid: str = "", person_ark: str = "") -> Dict[str, Any]:
    given, surname, dit_name = split_name_and_dit(full_name)
    type_specific_fields: Dict[str, Any] = {}
    if fsftid:
        type_specific_fields["fsftid"] = fsftid
    if person_ark:
        # This row's own ark - always present regardless of Family Tree attachment status
        # (see Voyageur.js's scrapeIndexRows) - used as the citation's web link, since it
        # points directly at this specific indexed entry on FamilySearch.
        type_specific_fields["person_ark"] = person_ark
    return {
        "role_number": None,
        "role_name": role_name,
        "std_given": given,
        "std_surname": surname or None,
        "raw_given": None,
        "raw_surname": None,
        "dit_name": dit_name,
        "prefix": None,
        "suffix": None,
        "sex": sex,
        "is_priest": False,
        "age": None,
        "occupation": None,
        "race": None,
        "religion": None,
        "residence": None,
        "birth_date": None,
        "birth_place": None,
        "death_date": None,
        "death_place": None,
        "review": False,
        "review_reason": None,
        "type_specific_fields": type_specific_fields,
    }


def row_to_record(row: dict, item_id: str, row_index: int) -> dict:
    """Converts one raw Image Index row into a schema.json-shaped record, reusing Parish.pmt's
    existing role vocabulary and the shared FactTypes.json event vocabulary rather than
    inventing new ones. Extracts every column FamilySearch's Image Index actually provides
    (not just Name/Father/Mother/Spouse), since a real register mixes Baptism, Christening,
    Marriage, and Burial rows with different column sets on the same page.

    item_id/row_index exist purely as a uniqueness fallback: Archivist's generate_uid/
    generate_fam_uid hash individuals and families from (vol, page, record_id, role) alone -
    no name is in the hash at all - on the assumption that a real page/record locator is
    always present, true for Paleographer's AI-read pages. FamilySearch's Image Index often
    has neither "Page Number" nor "Entry Number" (confirmed on real data: ~85% of rows in one
    real register), and leaving both blank would collapse hundreds of genuinely different
    people/families onto the same hash. Falling back to this row's own item_id/position
    keeps every record's (page, record_number) pair globally unique without touching
    Archivist's proven hashing scheme."""
    columns = row.get("columns", {})
    participants = []
    primary: Optional[Dict[str, Any]] = None
    for name_col, role_name in ROLE_COLUMN_MAP.items():
        full = (columns.get(name_col) or "").strip()
        if not full:
            continue
        fsftid = row.get("attached_fsftid", "") if role_name == "Primary" else ""
        person_ark = row.get("person_ark", "") if role_name == "Primary" else ""
        participant = build_participant(role_name, full, sex_code(columns.get(SEX_COLUMN_MAP[name_col], "")),
                                        fsftid, person_ark)
        participants.append(participant)
        if role_name == "Primary":
            primary = participant

    # Age/birth/death/legitimacy columns describe the record's own primary participant (the
    # baptized child, the deceased, etc.), not any of the other roles.
    if primary is not None:
        primary["age"] = (columns.get("Age") or "").strip() or None
        birth_date = (columns.get("Birth Date") or "").strip() or (columns.get("Birth Year (Estimated)") or "").strip()
        primary["birth_date"] = parse_to_iso(birth_date) or (birth_date or None)
        death_date = (columns.get("Death Date") or "").strip()
        primary["death_date"] = parse_to_iso(death_date) or (death_date or None)
        legitimacy = (columns.get("Legitimacy") or "").strip()
        if legitimacy:
            primary["type_specific_fields"]["legitimacy"] = legitimacy

    raw_event_type = (columns.get("Event Type") or "").strip()
    event_type = EVENT_TYPE_ALIASES.get(raw_event_type, raw_event_type)
    event_date_raw = (columns.get("Event Date") or "").strip()

    page = (columns.get("Page Number") or "").strip() or item_id
    record_number = (columns.get("Entry Number") or "").strip() or str(row_index + 1)

    return {
        "record_id": None,
        "page": page,
        "record_number": record_number,
        "record_type_code": None,
        "event_type": event_type,
        "year": (parse_to_iso(event_date_raw) or "")[:4] or None,
        "event_date": parse_to_iso(event_date_raw) or event_date_raw or None,
        "event_place": (columns.get("Event Place") or "").strip() or None,
        "english_translation": "",
        "original_transcription": "",
        "review": False,
        "review_reason": None,
        "type_specific_fields": {},
        "participants": participants,
    }


# ==========================================
# SAME-PERSON MATCHING (within one item's own records)
# ==========================================
def normalize_date(raw: Optional[str]) -> str:
    """Normalizes a date string for grouping/comparison only (not stored) - "1847-04-17"
    and "17 April 1847" need to compare equal even though FamilySearch's two indexing passes
    don't always agree on date format."""
    if not raw:
        return ""
    try:
        return pd.to_datetime(raw, errors="raise").strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return raw.strip().lower()


def get_role(record: dict, role_name: str) -> Optional[dict]:
    for p in record.get("participants", []):
        if p.get("role_name") == role_name:
            return p
    return None


def full_name(participant: dict) -> str:
    return f"{participant.get('std_given', '') or ''} {participant.get('std_surname', '') or ''}".strip()


def match_and_link_records(records: List[dict]) -> None:
    """Groups a single item's records by normalized event date, fuzzy-matches candidate
    pairs within each date group (primary name plus role-aligned parent-name comparison -
    father-vs-father, mother-vs-mother, rather than Registrar's flat any-vs-any relative
    check, since these records already carry typed roles), and stamps a shared link_id onto
    matching participants. Matched records are NOT merged - both stay as their own complete
    record (e.g. one Baptism, one Christening); the shared link_id is what lets Archivist's
    generate_uid resolve them to one person with two event facts instead of two people."""
    by_date: Dict[str, List[int]] = {}
    for idx, rec in enumerate(records):
        key = normalize_date(rec.get("event_date"))
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
            primary_a = get_role(rec_a, "Primary")
            if not primary_a or not full_name(primary_a):
                continue

            for idx_b in idxs[i + 1:]:
                if idx_b in matched:
                    continue
                rec_b = records[idx_b]
                primary_b = get_role(rec_b, "Primary")
                if not primary_b or not full_name(primary_b):
                    continue

                if fuzz.token_set_ratio(full_name(primary_a), full_name(primary_b)) < NAME_MATCH_THRESHOLD:
                    continue

                conflict = False
                for role_name in ("Father", "Mother"):
                    pa, pb = get_role(rec_a, role_name), get_role(rec_b, role_name)
                    if pa and pb and full_name(pa) and full_name(pb):
                        if fuzz.token_set_ratio(full_name(pa), full_name(pb)) < PARENT_MATCH_THRESHOLD:
                            conflict = True
                            break
                if conflict:
                    continue

                date_key = normalize_date(rec_a.get("event_date"))
                link_seed = f"{date_key}_{full_name(primary_a).strip().lower()}"
                for role_name in ("Primary", "Father", "Mother", "Spouse"):
                    pa, pb = get_role(rec_a, role_name), get_role(rec_b, role_name)
                    if pa and pb:
                        shared = link_seed if role_name == "Primary" else f"{link_seed}_{role_name}"
                        pa.setdefault("type_specific_fields", {})["link_id"] = shared
                        pb.setdefault("type_specific_fields", {})["link_id"] = shared

                matched.add(idx_a)
                matched.add(idx_b)
                break


# ==========================================
# CITATION & RECORD-FAMILY DETECTION
# ==========================================
def parse_citation(text: str) -> Dict[str, str]:
    """Parses FamilySearch's own generated citation prose - it follows the same two-clause
    convention Ancestry's citations do (online-database repository, then original-data
    publisher/location), just phrased differently: '"<collection>," database with images,
    <repository> (<url> : <date>), <browse path>; <publisher>, <pub_loc>.'"""
    result = {"repository": "", "repository_loc": "", "publisher": "", "pub_loc": "",
              "collection_name": "", "collection_url": "", "browse_path": ""}
    if not text:
        return result

    # Requires a space before the colon, since a lazy \S+? with a bare \s* stops at the first
    # colon it meets - and FamilySearch ark URLs have colons inside the path itself
    # (ark:/61903/3:1:...), truncating the URL long before the real " : <date>" separator.
    url_match = re.search(r'\((https?://\S+)\s+:', text)
    if url_match:
        result["collection_url"] = url_match.group(1)

    m = CITATION_RE.match(text.strip())
    if m:
        result["collection_name"] = m.group("collection_name").strip()
        result["repository"] = m.group("repository").strip()
        result["publisher"] = m.group("publisher").strip()
        result["pub_loc"] = m.group("pub_loc").strip()
        result["browse_path"] = m.group("browse_path").strip()
    return result


def detect_record_family(text: str) -> str:
    lowered = text.lower()
    for family, keywords in RECORD_FAMILY_KEYWORDS.items():
        if any(k in lowered for k in keywords):
            return family
    return "other"


def dedup_catalog_items(items_raw: List[dict]) -> Dict[str, dict]:
    """The Film/Digital Note catalog table is collection-level metadata (the same physical
    film's alternate cataloged titles), not per-image data, even though it's re-scraped on
    every image. Dedup by item_number so it's only counted once."""
    catalog_items: Dict[str, dict] = {}
    for it in items_raw:
        for ci in it.get("catalog_items", []):
            item_number = ci.get("item_number", "")
            if item_number and item_number not in catalog_items:
                catalog_items[item_number] = ci
    return catalog_items


def detect_record_family_from_raw(raw: dict, catalog_items: Dict[str, dict]) -> str:
    collection_title = raw.get("collection_title", "")
    catalog_text = " ".join(f"{ci.get('label', '')} {ci.get('note', '')}" for ci in catalog_items.values())
    return detect_record_family(f"{collection_title} {catalog_text}")


# ==========================================
# ASSEMBLY
# ==========================================
def build_universal_json(raw: dict, items_raw: List[dict], catalog_items: Dict[str, dict],
                         record_family: str) -> dict:
    event_types_table = load_event_types()
    roles_table = load_roles()

    first_citation_text = next((it.get("citation_text", "") for it in items_raw if it.get("citation_text")), "")
    citation = parse_citation(first_citation_text)
    collection_title = raw.get("collection_title", "")

    sheets = []
    for it in items_raw:
        item_id = it.get("item_id", "")
        records = [row_to_record(row, item_id, idx) for idx, row in enumerate(it.get("rows", []))]
        records = [r for r in records if r["participants"]]
        match_and_link_records(records)

        for record in records:
            derive_record_identity(record, event_types_table)
            for participant in record["participants"]:
                role_number = derive_role_number(participant["role_name"], roles_table)
                if role_number is not None:
                    participant["role_number"] = role_number
                    role_semantic = derive_role_semantic(role_number, roles_table)
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


def parse_census_browse_path(browse_path: str) -> Dict[str, str]:
    """Splits FamilySearch's citation browse-path text (e.g. "Alabama > Autauga >
    Autaugaville > ED 3 > image 1 of 51") into a location hierarchy, mirroring how
    Ancestry's own JS parses its structured browsePath array (getEnumerationDistrict in
    Voyageur.js) - here from plain text instead, since FS's citation prose is all that's
    available. The trailing "image N of M" segment is stripped first."""
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


NARA_CITING_RE = re.compile(
    r'citing\s+NARA\s+microfilm\s+publication\s+(?P<publication>\S+?)\s*'
    r'\((?P<repo_loc>[^:()]+):\s*(?P<repo_name>[^,()]+),\s*n\.d\.\)',
    re.IGNORECASE
)

CATALOG_ROLL_RE = re.compile(r'NARA Series\s+(?P<series>[A-Za-z0-9]+),\s*Roll\s+(?P<roll>[A-Za-z0-9]+)',
                             re.IGNORECASE)


def parse_nara_citing_clause(citation_text: str) -> Dict[str, str]:
    """A US census citation ends in "...; citing NARA microfilm publication <ID> (<location>:
    <repository>, n.d.)." - a longer, differently-shaped tail than the simple "Publisher,
    Loc." ending church-register citations use. The general parse_citation() regex still
    technically matches this text (its trailing groups are greedy enough to consume it
    without erroring), but captures garbage into publisher/pub_loc rather than the real NARA
    holder - confirmed against a real "United States, Census, 1860" citation this session.
    This targets that clause specifically."""
    m = NARA_CITING_RE.search(citation_text or "")
    if not m:
        return {"publication": "", "repository": "", "repository_loc": ""}
    return {
        "publication": m.group("publication").strip(),
        "repository": m.group("repo_name").strip(),
        "repository_loc": m.group("repo_loc").strip(),
    }


def parse_catalog_roll(catalog_items: Dict[str, dict]) -> Dict[str, str]:
    """Extracts the NARA microfilm series + roll from the Catalog Record table's Film/Digital
    Note (e.g. "Alabama: Autauga, Baldwin, and Barbour Counties (NARA Series M653, Roll 1)"),
    combined below into an "M653_1"-style string matching Ancestry's own Roll citation-field
    convention, so MergedCensus.py's page-locator matching has a real chance of lining the two
    sources up instead of always falling back to ED + page_number alone."""
    for ci in catalog_items.values():
        note = ci.get("note", "") or ci.get("label", "")
        m = CATALOG_ROLL_RE.search(note)
        if m:
            return {"series": m.group("series"), "roll": m.group("roll")}
    return {"series": "", "roll": ""}


def split_full_name(full_name: str) -> Tuple[str, str]:
    """Splits FamilySearch's single combined "Given Surname" Name field - unlike Ancestry's
    census index, which already exposes separate Given Name/Surname columns - into the same
    two-field shape, using the last whitespace-separated token as the surname. Same
    convention as Archivist.py's own split_full_name (used there for a different field, but
    the same "Given Surname" shape)."""
    parts = full_name.strip().split()
    if len(parts) < 2:
        return full_name.strip(), ""
    return " ".join(parts[:-1]), parts[-1]


def build_census_json(raw: dict, items_raw: List[dict], catalog_items: Dict[str, dict]) -> dict:
    """Converts FamilySearch's raw census gather into the same {census_year, location,
    pages: [...]} shape Ancestry's own gather already produces (see Voyageur/A.py), instead
    of the church schema.json shape - census data has no sacramental roles, it needs
    dwelling/family numbers and relationship-to-head, which Archivist's existing
    census-flavor pipeline already knows how to handle. Column names are carried through as
    FamilySearch provides them rather than remapped to Ancestry's own naming - reconciling
    the two sources' naming is MergedCensus.py's job, not this per-source conversion step."""
    first_citation_text = next((it.get("citation_text", "") for it in items_raw if it.get("citation_text")), "")
    citation = parse_citation(first_citation_text)
    location_info = parse_census_browse_path(citation.get("browse_path", ""))

    nara_info = parse_nara_citing_clause(first_citation_text)
    roll_info = parse_catalog_roll(catalog_items)
    roll_number = (f"{roll_info['series']}_{roll_info['roll']}" if roll_info['series'] and roll_info['roll']
                   else roll_info['series'] or nara_info['publication'])

    # The general parse_citation() regex captures garbage into publisher/pub_loc for census
    # citations (see parse_nara_citing_clause) - prefer the NARA-specific parse for those two
    # fields when it found a match; repository/repository_loc (the online-host clause, e.g.
    # "FamilySearch") are unaffected, since the general regex parses that clause correctly.
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
            # FamilySearch's census index never exposes an actual Line Number on any year
            # checked (confirmed live across all 17 US census years this session) - synthesize
            # from row position the same way Ancestry's own JS already does when a collection
            # lacks one, so MergedCensus.py has a locator to match people by.
            columns = dict(row.get("columns", {}))
            if not any(re.search(r'line', k, re.IGNORECASE) for k in columns):
                columns["Line Number"] = str(row_index + 1)

            # Archivist's census-flavor person loop reads 'Given Name'/'Surname' (Ancestry's
            # own column split) - FamilySearch's index only ever exposes a single combined
            # 'Name' field (confirmed live across all rows checked), so left as-is, every
            # FamilySearch-sourced person came out with no name at all (surfacing as literal
            # "nan" once merged into a DataFrame alongside Ancestry rows that do have the
            # split columns). Split it the same way Archivist splits a combined name
            # elsewhere, and drop the raw 'Name' key so it doesn't also leak through as a
            # redundant dynamic note.
            name_val = columns.pop("Name", None)
            if name_val and not columns.get("Given Name") and not columns.get("Surname"):
                given, surname = split_full_name(str(name_val))
                columns["Given Name"] = given
                columns["Surname"] = surname

            # Archivist's census-flavor loop uses 'pid' directly as this person's REFN/@I@ id
            # and folds it into the _APID citation tag (see build_census_citation) - it needs
            # to be one clean identifier, not a compound one. This used to be
            # "{item_id}-{row_index}" (item_id is itself a full page-level ARK, e.g.
            # "3:1:33S7-9YBJ-9PD7"), which read as two identifiers glued together once
            # rendered ("3:1:33S7-9YBJ-9PD7-1"). person_ark is this row's own real,
            # already-distinct per-person FamilySearch identifier (e.g. "MF36-Z6D") - use that
            # instead, falling back to the old compound form only on the rare row where
            # person_ark itself is missing.
            person_ark = row.get("person_ark", "")
            people.append({
                "columns": columns,
                "pid": person_ark or f"{item_id}-{row_index + 1}",
                "fsftid": row.get("attached_fsftid", ""),
                "person_ark": person_ark,
                # load_census_dataframe reads this directly (same construction
                # MergedCensus.py uses for a merged person) - without it, an FS-only
                # (non-merged) census run had no FamilySearch web link on its citation
                # at all, even though person_ark was already right here to build one.
                "familysearch_url": f"https://www.familysearch.org/ark:/61903/1:1:{person_ark}" if person_ark else "",
            })

        pages.append({
            "page_number": page_number,
            "image_id": item_id,
            "country": country,
            "state": location_info["state"],
            "county": location_info["county"],
            "city": location_info["city"],
            "place_details": "",
            "enumeration_district": location_info["enumeration_district"],
            "film_number": "",
            "roll_number": roll_number,
            "apid_db": "",
            "repository": citation.get("repository", ""),
            "repository_loc": citation.get("repository_loc", ""),
            "publisher": publisher,
            "pub_loc": pub_loc,
            "people": people,
        })

    return {"census_year": census_year, "location": location_info["state"], "pages": pages}


def _read_text_with_retry(path: Path, attempts: int = 5, delay: float = 0.5) -> str:
    """Chrome (or antivirus scanning it) can still hold a freshly-downloaded file open for
    a brief moment after it appears in the folder listing, so an immediate read can lose to
    a transient PermissionError/WinError 32 on Windows. Same reasoning as A.py's
    _move_with_retry."""
    for attempt in range(1, attempts + 1):
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            if attempt == attempts:
                raise
            time.sleep(delay)


def _unlink_with_retry(path: Path, attempts: int = 5, delay: float = 0.5) -> None:
    for attempt in range(1, attempts + 1):
        try:
            path.unlink(missing_ok=True)
            return
        except OSError:
            if attempt == attempts:
                raise
            time.sleep(delay)


def _move_with_retry(src: Path, dst: Path, attempts: int = 5, delay: float = 0.5) -> None:
    """Same reasoning as A.py's own _move_with_retry: Chrome (or antivirus scanning it) can
    still hold a freshly-downloaded file open for a brief moment after it appears in the
    folder listing."""
    for attempt in range(1, attempts + 1):
        try:
            shutil.move(str(src), str(dst))
            return
        except OSError as e:
            if attempt == attempts:
                print(f"[ERROR] Could not move {src.name} to {dst} after {attempts} attempts: {e}")
                raise
            time.sleep(delay)


def _cleanup_checkpoint_files(downloads_dir: Path, prefix: str, start_time: float) -> None:
    """Deletes this run's own leftover periodic checkpoint downloads (see
    downloadCheckpointJson in Voyageur.js) now that the final combined JSON has already
    been written - they're superseded and, unlike the final JSON, nothing else ever cleans
    them up, so a long gather would otherwise leave several of them sitting in the
    Downloads folder permanently. Best-effort: a checkpoint that can't be deleted (still
    briefly locked, already gone) is left in place rather than raising."""
    for p in downloads_dir.iterdir():
        if (p.is_file() and p.suffix.lower() == '.json' and p.name.startswith(prefix)
                and '[checkpoint' in p.name and p.stat().st_mtime >= start_time):
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass


def build_clean_census_filename(year: str, normalized_data: dict) -> Optional[str]:
    """Builds a "{year} - {state} - {county} - {city} - FS.json" name (matching A.py/
    Ancestry's own "{year} - {locationStr} - ANC" convention, so both sources' output files
    are named the same way and the provider is obvious at a glance) from the first record
    carrying any of those fields, instead of the raw browser-provided name (document.title,
    which for a FamilySearch collection page often includes the page's own ark URL).
    Returns None if no sheet/record has any of these fields at all, so the caller can fall
    back rather than silently invent a location."""
    for sheet in normalized_data.get("sheets", []):
        for record in sheet.get("records", []):
            fields = record.get("type_specific_fields", {}) or {}
            parts = [year] + [fields[key] for key in ("state", "county", "city") if fields.get(key)]
            if len(parts) > 1:
                safe = " - ".join(parts)
                safe = re.sub(r'[/\\?%*:|"<>]', "-", safe)
                return f"{safe} - FS.json"
    return None


# ==========================================
# MAIN EXECUTION
# ==========================================
def main() -> None:
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

    # Voyageur.js used GM_download to land these in their own Downloads subfolder, but
    # confirmed live this was unreliable - GM_download's own "downloads" permission grant
    # resets every time the script's content changes in Tampermonkey, and even when
    # granted, it sometimes ignored the requested name/folder and saved a hash-named file
    # in the Downloads root instead. Reverted to the plain <a download> method the
    # original CensusExtractor.js used in production (no special grant to lose), which
    # always honors the exact name given - real filenames are guaranteed. Chrome silently
    # replaces "/" in a download attribute with "_" instead of creating subfolders though,
    # so these land flat in the Downloads root with a "TMP_FS_" filename prefix (set in
    # Voyageur.js) instead of a real subfolder - stripped back off below once found, since
    # it's not part of the actual desired filename.
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

    raw_data = json.loads(_read_text_with_retry(raw_json_file))
    items_raw = raw_data.get("items", [])
    catalog_items = dedup_catalog_items(items_raw)
    record_family = detect_record_family_from_raw(raw_data, catalog_items)

    clean_name = None
    if record_family == "census":
        print("\n[System] Converting raw scrape into census Gather JSON...")
        raw_census = build_census_json(raw_data, items_raw, catalog_items)
        # Normalize at gather time: translate FamilySearch's own raw column header text
        # into the shared record schema's field names via the declarative field map, the
        # same as A.py does for Ancestry - so Archivist reads one shape regardless of
        # source, and never has to guess among several possible header spellings.
        collection_title = raw_data.get("collection_title", "")
        final_data = census_schema.normalize_census_pages(
            raw_census, "familysearch_census", collection_title,
            f"Census_{raw_census.get('census_year', '')}")
        clean_name = build_clean_census_filename(raw_census.get("census_year", ""), final_data)
    else:
        print("\n[System] Converting raw scrape into the universal Gather JSON...")
        final_data = build_universal_json(raw_data, items_raw, catalog_items, record_family)

    json_target_dir = Path(program_dir) / json_dir if program_dir else Path(json_dir)
    json_target_dir.mkdir(parents=True, exist_ok=True)

    # The browser side names the raw download after document.title, which for a
    # FamilySearch collection page is often the full search-result title plus its own ark
    # URL - unusable as a real filename. Prefer a clean "{year} - {location}" name built
    # from the same normalized location fields Archivist itself reads, matching Ancestry's
    # own naming convention (A.py's downloadFinalJson uses this exact "{year} - {location}"
    # shape); fall back to the raw browser-provided name only if no location was found at
    # all (e.g. a record with no state/county/city stated anywhere).
    out_name = clean_name or raw_json_file.name[len(json_prefix):]
    final_json = json_target_dir / out_name
    final_json.write_text(json.dumps(final_data, indent=2, ensure_ascii=False), encoding="utf-8")
    _unlink_with_retry(raw_json_file)
    _cleanup_checkpoint_files(downloads_dir, json_prefix, start_time)

    # Mirrors A.py's own nested {year} US Federal Census / {location} image folder
    # convention, derived from this same run's own clean filename (when one was built) so
    # both sources' images land under a comparable structure.
    stem = re.sub(r' - FS$', '', final_json.stem)
    stem_parts = stem.split(' - ', 1)
    census_year = stem_parts[0].strip() if stem_parts and stem_parts[0].strip() else "Unknown_Year"
    location_folder = stem_parts[1].strip() if len(stem_parts) > 1 else "Unknown_Location"
    census_folder = f"{census_year} US Federal Census"

    # CENSUS_IMAGE_DIR is a subfolder *of the Base Media Directory* (MEDIA_DIR), not of
    # PROGRAM_DIR directly - confirmed live: running this standalone (bypassing
    # Scriptorium.py's GUI, which normally pre-resolves this into an absolute path before
    # launching the subprocess) put a stray "Census" folder at the program root instead of
    # nested under the user's actual RootsMagic media folder. Resolved here independently
    # so this script produces correct output standalone, with nothing else open - matching
    # every other tool in this project. An already-absolute CENSUS_IMAGE_DIR (whether
    # GUI-resolved or set directly by the user) is used as-is, never re-nested.
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
            _move_with_retry(file_path, final_img)
            img_count += 1
        except Exception:
            pass

    print(f"[System] Moved {img_count} image(s) to Project folder.")

    # JSON_FILE is read by Archivist (see its own ARCHIVIST_VARS entry in Scriptorium.py),
    # so it's written to Archivist's own .env, not this script's own subfolder one -
    # confirmed live this was the actual bug behind Archivist immediately failing with
    # FileNotFoundError right after a real gather succeeded: this used to write to
    # Voyageur/.env, a file Archivist never reads at all.
    set_key(str(Path(__file__).resolve().parent.parent / "Archivist" / ".env"), "JSON_FILE", final_json.name)

    # Both branches now produce the same sheets[].records[].participants[] shape (the
    # census path is normalized above via census_schema, same as A.py) - one summary
    # line path for both on that basis, where before there were two differently-shaped
    # ones. The two branches still label themselves differently at the top level
    # (record_type_name vs record_family) - reconciling that is separately tracked
    # (Archivist's record-type dispatch rework), not done here.
    total_records = sum(len(sheet["records"]) for sheet in final_data["sheets"])
    label = final_data.get("record_type_name") or final_data.get("record_family", "")
    print(f"[System] Gather complete: {len(final_data['sheets'])} image(s), {total_records} record(s), "
          f"record type '{label}'.")
    print(f"[System] Run Archivist's \"Generate GEDCOM\" when you're ready ({final_json.name}).")

    return final_json


if __name__ == "__main__":
    main()
