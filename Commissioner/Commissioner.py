"""
Commissioner: LAC-linked cross-referencing sitting between Paleographer and Archivist.
Pipeline: Voyageur -> Paleographer -> Commissioner -> Archivist.

Generic HTTP mechanics live in lac_client.py; this module is the genealogy/pipeline-
aware layer on top of it - resolving which LAC records matter for a given Scrip record
(or a whole volume) and writing results into the same JSON shape Archivist already
reads. No Archivist/GEDCOM concerns here - Commissioner only cross-references the
master DB JSON in place.

Two entry points, both built on the three-pass split locked in this session
(specifically to avoid ever needing to race a cf_clearance cookie's ~30-60 minute
lifetime):

- cross_check_claim_record: single-claim cross-check. Given one Paleographer-extracted
  Scrip record (with its own claim/affidavit/scrip numbers), search once for its related
  certificate/land-grant, download every digital object found, and append entries to
  record["source_documents"].

- retrieve_volume: Pass 1+2 for a whole volume. Pass 1 spends ONE search_volume() call
  to retrieve every PID in the volume. Pass 2 downloads record metadata + every digital
  object for each PID - no cookie needed for any of it, and progress is checkpointed to
  disk so a run spanning multiple cookie refreshes is safely resumable. Pass 3 (running
  the downloaded files through Paleographer/Agy) is a separate, later step - this module
  only gets the files onto disk.
"""

import argparse
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import lac_client

# ==========================================
# CONFIGURATION
# ==========================================
PROGRAM_DIR = os.getenv("PROGRAM_DIR", "")


def _safe_path(base: str, *parts: str) -> str:
    """Joins paths, letting an absolute part override the base - same convention as
    Archivist.py's own safe_path (not imported directly, to keep this module's only
    dependency ScriptoriumMCP-style generic mechanics, not another pipeline stage)."""
    non_blank = [p for p in parts if p]
    if not non_blank:
        return ""
    res = base
    for p in non_blank:
        res = p if os.path.isabs(p) else os.path.join(res, p)
    return res


JSON_DIR = _safe_path(PROGRAM_DIR, os.getenv("JSON_DIR", ""))
JSON_FILE = os.getenv("COMMISSIONER_JSON_FILE", "") or os.getenv("JSON_FILE", "")
MEDIA_DIR = _safe_path(PROGRAM_DIR, os.getenv("COMMISSIONER_MEDIA_DIR", "Media/Commissioner"))
CHECKPOINT_DIR = _safe_path(PROGRAM_DIR, os.getenv("COMMISSIONER_CHECKPOINT_DIR", "Working/Commissioner"))
COOKIE_FILE = _safe_path(PROGRAM_DIR, os.getenv("COMMISSIONER_COOKIE_FILE", "Working/Commissioner/lac_cookies.txt"))
DEFAULT_ARCHIVAL_NUMBER = os.getenv("COMMISSIONER_ARCHIVAL_NUMBER", "RG15")
CDP_PORT = int(os.getenv("COMMISSIONER_CDP_PORT", str(lac_client.DEFAULT_CDP_PORT)))


# Confirmed live: original affidavit PDFs the user already has follow a
# "..._{PID}.pdf" naming convention (e.g. BAC-LAC_fonandcol_1502188.pdf) - this is the
# cheap, no-network way to resolve a record's own PID before ever touching LAC. Files
# named by their e-number instead (e.g. e011349655.pdf) won't match; those fall back to
# search() by e-number (see build_claim_search_query).
_PID_FROM_FILENAME_RE = re.compile(r"_(\d+)\.pdf$", re.IGNORECASE)


def resolve_pid_from_filename(file_name: str) -> Optional[str]:
    """Returns the PID embedded in a locally-chosen filename, or None if the filename
    doesn't follow that convention (e.g. an e-number-named file, or anything not
    downloaded through this pipeline)."""
    if not file_name:
        return None
    match = _PID_FROM_FILENAME_RE.search(file_name)
    return match.group(1) if match else None


def resolve_pid_for_sheet_or_record(sheet: Dict[str, Any], record: Dict[str, Any]) -> Optional[str]:
    """Resolves the PID for a record from any known location: record.lac_pid,
    document_metadata.pid, or a PID-bearing file_name."""
    if record.get("lac_pid"):
        return str(record["lac_pid"]).strip()
    meta = sheet.get("document_metadata") or {}
    if meta.get("pid"):
        return str(meta["pid"]).strip()
    file_name = meta.get("file_name") or (record.get("document_metadata") or {}).get("file_name", "")
    return resolve_pid_from_filename(file_name)


# ==========================================
# CITATION PATTERNS & EXTRACTION
# ==========================================
CITATION_PATTERNS = {
    "claim_number": re.compile(r"claim no\.?:?\s*([^;]+)", re.I),
    "affidavit_number": re.compile(r"aff(?:idavit|dt)?\.?\s*no\.?:?\s*([^;]+)", re.I),
    "allotment_number": re.compile(r"allotment\s*no\.?:?\s*([^;]+)", re.I),
    "scrip_number": re.compile(r"scrip no\.?:?\s*([^;]+)", re.I),
    "grant_number": re.compile(r"grant no\.?:?\s*([^;]+)", re.I),
    "patent_number": re.compile(r"patent no\.?:?\s*([^;]+)", re.I),
    "scrip_amount": re.compile(r"amount:?\s*([^;]+)", re.I),
    "scrip_issue_date": re.compile(r"date of issue:?\s*([^;]+)", re.I),
    "issue_date": re.compile(r"date of issue:?\s*([^;]+)", re.I),
    "application_date": re.compile(r"date of application:?\s*([^;]+)", re.I),
}


def fix_mojibake(text: str) -> str:
    """Repairs UTF-8 strings that were decoded as CP1252 / ISO-8859-1 (mojibake)
    or lowercased while corrupted (e.g. 'Geneviã¨ve' -> 'Geneviève', 'mÃ©tis' -> 'métis')."""
    if not text:
        return ""
    if not isinstance(text, str):
        text = str(text)

    # 1. Normalize lowercased mojibake headers
    fixed = re.sub(
        r"ã([\x80-\xbf\u00a0-\u00bf\u0080-\u009f\u2018-\u201d\u2022\u20ac])",
        lambda m: 'Ã' + m.group(1),
        text
    )

    # 2. Attempt standard byte roundtrip (Latin-1 / CP1252 -> UTF-8)
    if any(ch in fixed for ch in ("Ã", "Â", "â", "ð")):
        try:
            fixed = fixed.encode("cp1252").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            try:
                fixed = fixed.encode("latin1").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass

    # 3. Direct replacement fallback map for any remaining damaged multi-byte sequences
    REPLACEMENT_MAP = {
        "ã¨": "è", "Ã¨": "è",
        "ã©": "é", "Ã©": "é",
        "ã¢": "â", "Ã¢": "â",
        "ãª": "ê", "Ãª": "ê",
        "ã«": "ë", "Ã«": "ë",
        "ã®": "î", "Ã®": "î",
        "ã¯": "ï", "Ã¯": "ï",
        "ã´": "ô", "Ã´": "ô",
        "ã»": "û", "Ã»": "û",
        "ã¹": "ù", "Ã¹": "ù",
        "ã¼": "ü", "Ã¼": "ü",
        "ã§": "ç", "Ã§": "ç",
        "ã ": "à", "Ã ": "à",
        "ã€": "À", "Ã€": "À",
        "ã‚": "Â", "Ã‚": "Â",
        "ã‡": "Ç", "Ã‡": "Ç",
        "ã‰": "É", "Ã‰": "É",
        "ãˆ": "È", "Ãˆ": "È",
        "ãŽ": "Î", "ÃŽ": "Î",
        "ã”": "Ô", "Ã”": "Ô",
        "Ã‰": "É", "Ãˆ": "È", "Ã€": "À", "Ã‡": "Ç", "Ã‚": "Â", "ÃŽ": "Î", "Ã”": "Ô",
        "â€™": "'", "â€˜": "'", "â€œ": '"', "â€\x9d": '"', "â€“": "-", "â€”": "-",
        "Â ": " ", "\xa0": " ",
    }
    for bad, good in REPLACEMENT_MAP.items():
        if bad in fixed:
            fixed = fixed.replace(bad, good)

    return fixed


COMPOUND_SURNAME_PREFIXES_2 = {
    "de la", "de le", "de les", "de los", "de las",
    "van der", "van den", "van de", "von der", "von den",
}

COMPOUND_SURNAME_PREFIXES_1 = {
    "st.", "st", "ste.", "ste", "saint", "sainte", "san", "santa",
    "de", "du", "des", "del", "della", "degli",
    "la", "le", "les", "l'", "d'",
    "van", "von", "der", "den", "ter", "ten",
    "fitz", "mac", "mc", "o'"
}


def clean_dit_name(dit_str: str) -> str:
    if not dit_str:
        return ""
    cleaned = re.sub(r'^dit\s+', '', (dit_str or "").strip(), flags=re.I).strip()
    return " ".join(w.capitalize() for w in cleaned.split())


def parse_single_name(raw: str, expected_surname: str = "") -> Tuple[str, str, str]:
    """Parses a raw 'FIRSTNAME LASTNAME' string (e.g. for father, mother, spouse)
    into (std_given, std_surname, dit_name).
    Properly handles compound French-Canadian / Métis / English surnames (St. Arnaud,
    De La Ronde, Le Blanc, Des Ruisseaux, etc.) and 'dit' names without leaking
    surname prefixes into std_given."""
    text = (raw or "").strip()
    if not text:
        return "", "", ""

    # Check for embedded dit name (e.g. 'Jean Baptiste Bruneau dit Charron')
    dit_name = ""
    m_dit = re.search(r'\s+\b(dit|dite)\b\s+(.+)$', text, flags=re.I)
    if m_dit:
        dit_name = clean_dit_name(m_dit.group(2))
        text = text[:m_dit.start()].strip()

    # If expected_surname is provided and text ends with it, split on it
    if expected_surname:
        exp_clean = expected_surname.strip()
        exp_base = re.split(r'\s+\b(dit|dite)\b\s+', exp_clean, flags=re.I)[0].strip()
        if exp_base and text.lower().endswith(exp_base.lower()):
            prefix = text[:-len(exp_base)].strip()
            if prefix:
                given = " ".join(w.capitalize() for w in prefix.split())
                surname = " ".join(w.capitalize() for w in exp_base.split())
                if dit_name:
                    surname = f"{surname} dit {dit_name}"
                return given, surname, dit_name

    parts = text.split()
    if not parts:
        return "", "", dit_name
    if len(parts) == 1:
        return parts[0].capitalize(), "", dit_name

    # Determine surname start index by checking 2-word then 1-word particles
    surname_idx = len(parts) - 1
    if len(parts) >= 3:
        two_word = f"{parts[-3]} {parts[-2]}".lower()
        if two_word in COMPOUND_SURNAME_PREFIXES_2:
            surname_idx = len(parts) - 3
        elif parts[-2].lower().rstrip('.') in COMPOUND_SURNAME_PREFIXES_1 or parts[-2].lower() in COMPOUND_SURNAME_PREFIXES_1:
            surname_idx = len(parts) - 2
    elif len(parts) == 2:
        if parts[0].lower().rstrip('.') in COMPOUND_SURNAME_PREFIXES_1:
            return "", " ".join(w.capitalize() for w in text.split()), dit_name

    given_parts = parts[:surname_idx]
    surname_parts = parts[surname_idx:]

    given = " ".join(w.capitalize() for w in given_parts)
    s_formatted = []
    for p in surname_parts:
        low = p.lower()
        if low in ("st", "st."):
            s_formatted.append("St.")
        elif low in ("ste", "ste."):
            s_formatted.append("Ste.")
        else:
            s_formatted.append(p.capitalize())
    surname = " ".join(s_formatted)

    if dit_name and not re.search(r'\s+\bdit\b\s+', surname, flags=re.I):
        surname = f"{surname} dit {dit_name}"

    return given, surname, dit_name


def fix_participant_name(p: Dict[str, Any], expected_surname: str = "") -> bool:
    """Checks participant's std_given and std_surname, ensuring compound surname
    prefixes (e.g. 'St.', 'Ste.', 'De La', 'Le', 'Des') at the end of std_given
    are moved to std_surname, and dit_name is populated properly. Returns True if modified."""
    given = (p.get("std_given") or "").strip()
    surname = (p.get("std_surname") or "").strip()
    dit_name = (p.get("dit_name") or "").strip()

    if not given and not surname:
        return False

    combined = f"{given} {surname}".strip()
    new_given, new_surname, new_dit = parse_single_name(combined, expected_surname=expected_surname)

    if dit_name and not new_dit:
        new_dit = dit_name
        if not re.search(r'\s+\bdit\b\s+', new_surname, flags=re.I):
            new_surname = f"{new_surname} dit {new_dit}".strip()

    modified = False
    if new_given != given:
        p["std_given"] = new_given
        modified = True
    if new_surname != surname:
        p["std_surname"] = new_surname
        modified = True
    if new_dit and p.get("dit_name") != new_dit:
        p["dit_name"] = new_dit
        modified = True

    return modified


def fix_all_participant_names_in_record(record: Dict[str, Any]) -> bool:
    """Repairs participant names across the entire record (Claimant, Father, Mother, Spouse)."""
    participants = record.get("participants", [])
    if not participants:
        return False

    primary = participants[0]
    primary_surname = (primary.get("std_surname") or "").strip()

    modified = False
    if fix_participant_name(primary):
        modified = True
        primary_surname = (primary.get("std_surname") or "").strip()

    for p in participants[1:]:
        role = p.get("role_semantic") or str(p.get("role_number"))
        exp = primary_surname if role in ("father", "6") else ""
        if fix_participant_name(p, expected_surname=exp):
            modified = True

    return modified


def build_composite_record_number(tf: Dict[str, Any], pid: str = "") -> str:
    """Builds standard composite key: [Claim Number]-[Allotment Number]-[Scrip Number]
    with '0' as placeholder for missing components."""
    claim = (tf.get("claim_number") or "").strip() or "0"
    allotment = (tf.get("allotment_number") or "").strip() or "0"
    scrip = (tf.get("scrip_number") or "").strip() or "0"
    return f"{claim}-{allotment}-{scrip}"


def resolve_maiden_name_for_record(record: Dict[str, Any], row_nee: str = "") -> bool:
    """If a wife is using her married surname, and her father's surname is known
    (or 'nee' is known), change her surname to use her maiden surname, preserving
    her married surname in alternate_names. Returns True if modified."""
    participants = record.get("participants", [])
    if not participants:
        return False

    primary = participants[0]
    father = next((p for p in participants if p.get("role_semantic") == "father" or str(p.get("role_number")) == "6"), None)
    spouse = next((p for p in participants if p.get("role_semantic") == "spouse" or str(p.get("role_number")) == "2"), None)

    f_surname = (father.get("std_surname") or "").strip() if father else ""
    c_surname = (primary.get("std_surname") or "").strip()
    c_given = (primary.get("std_given") or "").strip()
    nee = (row_nee or "").strip().title()

    maiden_surname = ""
    if f_surname and f_surname.lower() not in ("[illegible]", "unknown", ""):
        maiden_surname = f_surname
    elif nee and nee.lower() not in ("[illegible]", "unknown", ""):
        maiden_surname = nee

    if not maiden_surname:
        return False

    title_lower = (record.get("lac_catalog_title") or record.get("lac_catalog_title_live") or "").lower()
    is_female = (
        primary.get("sex") == "F"
        or (spouse and spouse.get("sex") == "M")
        or ("wife of" in title_lower)
        or ("widow of" in title_lower)
        or ("husband:" in title_lower)
    )

    modified = False
    if is_female:
        if primary.get("sex") != "F":
            primary["sex"] = "F"
            modified = True
        if spouse and not spouse.get("sex"):
            spouse["sex"] = "M"
            modified = True

        if c_surname and c_surname.lower() != maiden_surname.lower():
            alt_names = primary.setdefault("alternate_names", [])
            married_full = f"{c_given} {c_surname}".strip()
            if married_full and not any((a.get("value") or "").strip().lower() == married_full.lower() for a in alt_names):
                alt_names.append({"value": married_full})
            primary["std_surname"] = maiden_surname
            modified = True
        elif not c_surname:
            primary["std_surname"] = maiden_surname
            modified = True

    return modified


def resolve_dataset_maiden_names(data: Dict[str, Any]) -> int:
    """Iterates through all sheets and records in data, fixing any mojibake encoding
    artifacts and resolving married surnames to maiden surnames when father's surname
    (or 'nee') is known. Returns count of modified records."""
    modified_count = 0
    for sheet in data.get("sheets", []):
        for record in sheet.get("records", []):
            if record.get("lac_catalog_title"):
                record["lac_catalog_title"] = fix_mojibake(record["lac_catalog_title"])
            if record.get("lac_catalog_title_live"):
                record["lac_catalog_title_live"] = fix_mojibake(record["lac_catalog_title_live"])

            for p in record.get("participants", []):
                for k in ("std_given", "std_surname", "race", "birth_place", "death_place"):
                    if p.get(k):
                        p[k] = fix_mojibake(p[k])

            fix_all_participant_names_in_record(record)
            if resolve_maiden_name_for_record(record):
                modified_count += 1

    return modified_count


def extract_citation_fields(citation: str) -> Dict[str, str]:
    """Extracts structured scrip metadata fields (claim_number, affidavit_number,
    allotment_number, scrip_number, issue_date, etc.) from an LAC catalog title or
    citation string without requiring an LLM."""
    fields = {}
    if not citation:
        return fields
    citation = fix_mojibake(citation)
    for key, pattern in CITATION_PATTERNS.items():
        m = pattern.search(citation)
        if m:
            val = m.group(1).strip().rstrip(".")
            if val:
                fields[key] = val
    if "scrip_issue_date" in fields and "issue_date" not in fields:
        fields["issue_date"] = fields["scrip_issue_date"]
    elif "issue_date" in fields and "scrip_issue_date" not in fields:
        fields["scrip_issue_date"] = fields["issue_date"]
    return fields


# ==========================================
# COLLECTION CLASSIFICATION & PARTITIONING
# ==========================================
COLLECTIONS = [
    ("RG15-D-II-8-a", "Affidavits, 1870-1885", "Finding Aid 15-19", 1319, 1324),
    ("RG15-D-II-8-b", "Applications, 1885", "Finding Aid 15-20", 1325, 1330),
    ("RG15-D-II-8-c", "Applications, 1886-1906", "Finding Aid 15-21", 1331, 1372),
]
UNKNOWN_COLLECTION_LABEL = "Unclassified (no rg_series_code or inferable volume yet)"


def collection_for_series_code(code: Optional[str]) -> Optional[Tuple[str, str, str, str]]:
    if not code:
        return None
    for series_code, title, finding_aid, _lo, _hi in COLLECTIONS:
        if code.startswith(series_code):
            return series_code, title, finding_aid, "confirmed"
    return None


def collection_for_volume(volume: Any, volume_range: Any) -> Optional[Tuple[str, str, str, str]]:
    def in_range(v):
        try:
            v_int = int(v)
            for series_code, title, finding_aid, lo, hi in COLLECTIONS:
                if lo <= v_int <= hi:
                    return series_code, title, finding_aid, "inferred"
        except (ValueError, TypeError):
            pass
        return None

    if volume and str(volume).isdigit():
        res = in_range(volume)
        if res:
            return res
    if volume_range:
        parts = str(volume_range).split("-")
        if len(parts) == 2 and all(p.strip().isdigit() for p in parts):
            lo_res = in_range(parts[0].strip())
            hi_res = in_range(parts[1].strip())
            if lo_res and hi_res and lo_res[0] == hi_res[0]:
                return lo_res
    return None


def classify_sheet_collection(sheet: Dict[str, Any]) -> Tuple[Optional[str], str, Optional[str], str]:
    """Determines collection (series_code, title, finding_aid, classification_status)
    for a sheet, based first on rg_series_code and falling back to volume / volume_range."""
    records = sheet.get("records", [])
    if records:
        record = records[0]
        series_code = (record.get("type_specific_fields") or {}).get("rg_series_code")
        res = collection_for_series_code(series_code)
        if res:
            return res

    meta = sheet.get("document_metadata", {})
    res = collection_for_volume(meta.get("volume"), meta.get("volume_range"))
    if res:
        return res

    return None, UNKNOWN_COLLECTION_LABEL, None, "unclassified"


def partition_json_by_collection(data: Dict[str, Any], output_dir: Path) -> Dict[str, Path]:
    """Partitions a master Scrip dataset into separate JSON files grouped by official LAC
    collection/series, saved into output_dir. Returns mapping of collection_key -> Path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    buckets: Dict[str, Dict[str, Any]] = {}
    for sheet in data.get("sheets", []):
        code, title, finding_aid, _status = classify_sheet_collection(sheet)
        key = code or "unclassified"
        if key not in buckets:
            buckets[key] = {
                "series_code": code,
                "title": title,
                "finding_aid": finding_aid,
                "sheets": [],
            }
        buckets[key]["sheets"].append(sheet)

    written_files = {}
    for key, info in buckets.items():
        clean_title = re.sub(r'[\s,:-]+', '_', info['title'].strip())
        filename = f"{key}_{clean_title}.json" if key != "unclassified" else "unclassified.json"
        out_file = output_dir / filename
        dataset = {
            "record_type_name": data.get("record_type_name", "Scrip"),
            "collection_title": info["title"],
            "finding_aid": info["finding_aid"],
            "rg_series_code": info["series_code"],
            "sheets": info["sheets"],
        }
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(dataset, f, indent=2, ensure_ascii=False)
        written_files[key] = out_file

    return written_files


_SCRIP_RANGE_RE = re.compile(r"^\s*(\d+)\s*(?:to|-|–)\s*(\d+)\s*$", re.IGNORECASE)


def expand_scrip_number_range(scrip_number: Optional[str]) -> List[str]:
    """Expands a range like "2234 to 2241" into every individual number in it. A scrip
    claim awarded a range represents MULTIPLE separate certificates, not one (confirmed
    live: Margaret Sabiston's real claim showed exactly this) - searching only the
    range's own literal text as a single query would miss every certificate but whichever
    one happens to match that exact string. Returns [scrip_number] unchanged when it's
    already a single number or doesn't parse as a range - never invents numbers beyond
    what's actually stated, and a wildly large or inverted span (more likely a misread
    than a real award) is left unexpanded too, rather than generating hundreds of
    speculative searches."""
    if not scrip_number:
        return []
    match = _SCRIP_RANGE_RE.match(scrip_number.strip())
    if not match:
        return [scrip_number]
    low, high = int(match.group(1)), int(match.group(2))
    if high < low or high - low > 200:
        return [scrip_number]
    return [str(n) for n in range(low, high + 1)]


def build_claim_search_queries(record: Dict[str, Any]) -> List[str]:
    """Builds the free-text quer(ies) search() needs to find a claim's related documents.
    Confirmed live: "claim: {n} Scrip: {n}" together reliably surfaces both the
    affidavit and the award certificate - scrip numbers alone are reused across claims
    and not unique enough to search on solo (per the user). Falls back to affidavit
    number if claim_number is missing, and to the record's own e-number (parsed from
    document_metadata.file_name) if nothing else is available.

    Returns one query PER individual scrip number when scrip_number is a range (see
    expand_scrip_number_range) - so every certificate in the range actually gets searched
    for. Returns [] when there's genuinely not enough to search on - callers should flag
    the record for review rather than skip it silently."""
    claim_number = record.get("claim_number")
    affidavit_number = record.get("affidavit_number")
    scrip_numbers = expand_scrip_number_range(record.get("scrip_number"))

    primary = claim_number or affidavit_number
    if primary and scrip_numbers:
        return [f"claim: {primary} Scrip: {n}" for n in scrip_numbers]
    if primary:
        return [f"claim: {primary}"]
    if scrip_numbers:
        return [f"Scrip: {n}" for n in scrip_numbers]

    file_name = (record.get("document_metadata") or {}).get("file_name", "")
    e_number_match = re.search(r"(e\d{6,})", file_name, re.IGNORECASE)
    if e_number_match:
        return [e_number_match.group(1)]

    return []


def build_claim_search_query(record: Dict[str, Any]) -> Optional[str]:
    """Backward-compatible single-query form - the first of build_claim_search_queries(),
    or None if there's nothing to search on. Prefer build_claim_search_queries directly
    for anything that should actually search every number in a scrip_number range."""
    queries = build_claim_search_queries(record)
    return queries[0] if queries else None


def _document_type_for_asset(asset: "lac_client.DigitalObject") -> str:
    """A downloaded LAC asset's label often isn't genealogically meaningful on its own
    (e.g. "Page 1") - this exists so callers can override with something more useful
    once they know WHY this PID was fetched (e.g. "Scrip Certificate" for a related-item
    download); on its own it just falls back to whatever label LAC's manifest gave."""
    return asset.label or "LAC Digital Object"


def download_pid_bundle(pid: str, media_dir: str,
                        document_type_override: Optional[str] = None) -> Dict[str, Any]:
    """Pass 2, per-PID: fetches record metadata + manifest, downloads every digital
    object to media_dir/{pid}/{asset_id}.{ext}, and returns a small bundle describing
    what was saved - one entry per asset, shaped to append directly into a record's
    source_documents list (media_path instead of transcription text, per the plan).
    No cookie needed for any of this - record/manifest/asset endpoints are unguarded."""
    metadata = lac_client.get_record_metadata(pid)
    assets = lac_client.get_manifest(pid)

    pid_dir = Path(media_dir) / pid
    pid_dir.mkdir(parents=True, exist_ok=True)

    entries: List[Dict[str, Any]] = []
    for asset in assets:
        ext = "pdf" if asset.op == "pdf" else "jpg"
        file_path = pid_dir / f"{asset.asset_id}.{ext}"
        if not file_path.exists():
            data = lac_client.download_asset(asset.asset_id, asset.op)
            file_path.write_bytes(data)

        entries.append({
            "document_type": document_type_override or _document_type_for_asset(asset),
            "media_path": str(file_path),
            "lac_pid": pid,
            "lac_asset_id": asset.asset_id,
            "source": "LAC",
        })

    return {
        "pid": pid,
        "lac_catalog_title": metadata.title,
        "reel_numbers": metadata.reel_numbers,
        "series_code": metadata.series_code,
        "source_documents": entries,
    }


# ==========================================
# SINGLE-CLAIM CROSS-CHECK
# ==========================================
def cross_check_claim_record(record: Dict[str, Any], cookies: Dict[str, str], media_dir: str
                             ) -> Dict[str, Any]:
    """Single-claim cross-check: resolves this Scrip record's own PID (cross-checking
    metadata against LAC's catalog), searches once for any related documents tied to the
    same claim (certificate/land-grant), and downloads everything found - appending to
    record["source_documents"] rather than overwriting anything already there from
    Paleographer's own extraction. Mutates and returns `record`.

    Cross-checking is deliberately conservative: LAC's catalog title is stored verbatim
    (record["lac_catalog_title"]) rather than auto-parsed and diffed field-by-field
    against the extraction - the one confirmed-live mismatch this session (a birth year
    misread) was caught by a human reading both side by side, not by a regex diff, and a
    brittle automatic parser risks manufacturing false "mismatch" flags. Downstream
    review (human or Archivist) reads both fields side by side instead."""
    file_name = (record.get("document_metadata") or {}).get("file_name", "")
    own_pid = resolve_pid_from_filename(file_name)

    if own_pid:
        record["lac_pid"] = own_pid  # Archivist.generate_uid prefers this over record_id
        try:
            own_bundle = download_pid_bundle(own_pid, media_dir,
                                             document_type_override=record.get("document_type"))
            record["lac_catalog_title"] = fix_mojibake(own_bundle["lac_catalog_title"])
            # reel_numbers/series_code are LAC catalog metadata, not something printed on
            # the page itself - Paleographer never extracts them, only Commissioner can.
            # Archivist reads these for a citation's Microfilm field and (series_code)
            # as a more authoritative signal than commission_reference free text for
            # picking which of the 5 real Scrip source templates a claim belongs to.
            type_fields = record.setdefault("type_specific_fields", {})
            if own_bundle.get("reel_numbers"):
                type_fields["reel_numbers"] = ", ".join(own_bundle["reel_numbers"])
            if own_bundle.get("series_code"):
                type_fields["rg_series_code"] = own_bundle["series_code"]

            # Re-check citation fields and maiden name
            parsed = extract_citation_fields(record["lac_catalog_title"])
            for k, v in parsed.items():
                if not type_fields.get(k):
                    type_fields[k] = v
            resolve_maiden_name_for_record(record)
        except lac_client.LacCallError as e:
            record.setdefault("review_reason", []).append(f"Commissioner: failed to fetch own PID {own_pid}: {e}")

    queries = build_claim_search_queries(record)
    if not queries:
        record.setdefault("review_reason", []).append(
            "Commissioner: no claim_number/affidavit_number/scrip_number/e-number available to search LAC with")
        return record

    # Usually one query; more than one only when scrip_number was a range (see
    # build_claim_search_queries) - every number in the range gets its own search, since
    # each represents a separate certificate. An expired cookie fails every remaining
    # query identically, so stop entirely on the first LacSearchAuthError rather than
    # retrying it N more times; a plain LacCallError is treated as a one-off blip on that
    # specific query and doesn't abort the rest.
    all_found_pids = set()
    for query in queries:
        try:
            all_found_pids.update(lac_client.search(query, cookies))
        except lac_client.LacSearchAuthError as e:
            record.setdefault("review_reason", []).append(f"Commissioner: search cookie expired/invalid: {e}")
            break
        except lac_client.LacCallError as e:
            record.setdefault("review_reason", []).append(f"Commissioner: search failed for {query!r}: {e}")

    related_pids = sorted(p for p in all_found_pids if p != own_pid)
    source_documents = record.setdefault("source_documents", [])
    for related_pid in related_pids:
        try:
            bundle = download_pid_bundle(related_pid, media_dir)
            source_documents.extend(bundle["source_documents"])
        except lac_client.LacCallError as e:
            record.setdefault("review_reason", []).append(
                f"Commissioner: failed to fetch related PID {related_pid}: {e}")

    return record


# ==========================================
# METADATA ENRICHMENT (no cookies needed)
# ==========================================
def enrich_record_from_lac_metadata(sheet: Dict[str, Any], record: Dict[str, Any],
                                    metadata: "lac_client.RecordMetadata") -> None:
    """Applies live LAC catalog metadata (title, reel_numbers, series_code, and parsed citation fields)
    to a sheet and record without overwriting existing field extractions."""
    clean_title = fix_mojibake(metadata.title)
    record["lac_catalog_title_live"] = clean_title
    meta = sheet.setdefault("document_metadata", {})
    if metadata.reel_numbers:
        meta["reel_numbers"] = metadata.reel_numbers

    type_fields = record.setdefault("type_specific_fields", {})
    if metadata.series_code and not type_fields.get("rg_series_code"):
        type_fields["rg_series_code"] = metadata.series_code
    if metadata.reel_numbers and not type_fields.get("reel_numbers"):
        type_fields["reel_numbers"] = ", ".join(metadata.reel_numbers)

    # If live catalog title exists, parse citation fields for any missing type_specific_fields
    parsed = extract_citation_fields(clean_title)
    for k, v in parsed.items():
        if not type_fields.get(k):
            type_fields[k] = v

    # Update composite record_number if needed
    if not record.get("record_number") or record.get("record_number") == "0-0-0":
        record["record_number"] = build_composite_record_number(type_fields, record.get("lac_pid", ""))

    # Fix compound surnames and dit names across participants
    fix_all_participant_names_in_record(record)

    # Resolve maiden surname if applicable
    resolve_maiden_name_for_record(record)


def enrich_json_data(data: Dict[str, Any], checkpoint_path: Optional[str] = None,
                     delay_seconds: float = 0.4, limit: Optional[int] = None,
                     checkpoint_every: int = 50) -> Dict[str, Any]:
    """Iterates through all records in a JSON dataset, fetching live LAC metadata for each PID
    without requiring cookies. Checkpointed and rate-limited."""
    checkpoint = load_checkpoint(checkpoint_path) if checkpoint_path else {"done_pids": [], "failed_pids": {}}
    done = set(checkpoint.get("done_pids", []))
    failed = checkpoint.get("failed_pids", {})

    sheets = data.get("sheets", [])
    processed = 0
    since_checkpoint = 0

    for sheet in sheets:
        if limit is not None and processed >= limit:
            break
        records = sheet.get("records", [])
        if not records:
            continue
        for record in records:
            pid = resolve_pid_for_sheet_or_record(sheet, record)
            if not pid:
                continue
            if pid in done:
                continue

            try:
                metadata = lac_client.get_record_metadata(pid)
                enrich_record_from_lac_metadata(sheet, record, metadata)
                done.add(pid)
                failed.pop(pid, None)
                processed += 1
                since_checkpoint += 1
            except lac_client.LacCallError as e:
                failed[pid] = str(e)
                processed += 1

            if checkpoint_path and since_checkpoint >= checkpoint_every:
                checkpoint["done_pids"] = sorted(done)
                checkpoint["failed_pids"] = failed
                save_checkpoint(checkpoint_path, checkpoint)
                since_checkpoint = 0

            if delay_seconds > 0:
                time.sleep(delay_seconds)

    if checkpoint_path:
        checkpoint["done_pids"] = sorted(done)
        checkpoint["failed_pids"] = failed
        save_checkpoint(checkpoint_path, checkpoint)

    resolve_dataset_maiden_names(data)
    return data


# ==========================================
# VOLUME RETRIEVAL (checkpointed, resumable)
# ==========================================
def load_checkpoint(checkpoint_path: str) -> Dict[str, Any]:
    if os.path.exists(checkpoint_path):
        with open(checkpoint_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"pids": [], "downloaded_pids": [], "failed_pids": {}}


def save_checkpoint(checkpoint_path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(checkpoint_path) or ".", exist_ok=True)
    with open(checkpoint_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def retrieve_volume_pids(vol: str, cookies: Dict[str, str], checkpoint_path: str,
                         archival_number: str = "RG15") -> List[str]:
    """Pass 1: the one cookie-gated call per volume. Idempotent/resumable - if the
    checkpoint already has PIDs for this volume (from an earlier partial run), skips the
    search entirely rather than spending cookie budget again."""
    checkpoint = load_checkpoint(checkpoint_path)
    if checkpoint.get("pids"):
        return checkpoint["pids"]

    pids = lac_client.search_volume(vol, cookies, archival_number=archival_number)
    checkpoint["pids"] = pids
    checkpoint["volume"] = vol
    save_checkpoint(checkpoint_path, checkpoint)
    return pids


def download_volume_assets(pids: List[str], media_dir: str, checkpoint_path: str) -> Dict[str, Any]:
    """Pass 2: bulk, unattended download for a whole volume's worth of PIDs - no cookie
    needed for any of it. Checkpoints after every PID (not just at the end) so a crash
    or interruption partway through a large volume doesn't lose completed work, and a
    re-run picks up exactly where it left off. One PID's failure doesn't abort the rest
    of the volume - it's recorded in failed_pids and the loop continues."""
    checkpoint = load_checkpoint(checkpoint_path)
    downloaded = set(checkpoint.get("downloaded_pids", []))
    failed = checkpoint.get("failed_pids", {})

    for pid in pids:
        if pid in downloaded:
            continue
        try:
            download_pid_bundle(pid, media_dir)
            downloaded.add(pid)
            failed.pop(pid, None)
        except lac_client.LacCallError as e:
            failed[pid] = str(e)

        checkpoint["downloaded_pids"] = sorted(downloaded)
        checkpoint["failed_pids"] = failed
        save_checkpoint(checkpoint_path, checkpoint)

    return checkpoint


def retrieve_volume(vol: str, cookies: Dict[str, str], media_dir: str, checkpoint_path: str,
                    archival_number: str = "RG15") -> Dict[str, Any]:
    """Pass 1 + Pass 2 for one volume: retrieve every PID (one cookie-gated call, skipped
    if already checkpointed), then bulk-download everything found (no cookie needed).
    Pass 3 - running the downloaded files through Paleographer/Agy - is intentionally
    not part of this function; it's a separate, later, fully-decoupled step."""
    pids = retrieve_volume_pids(vol, cookies, checkpoint_path, archival_number=archival_number)
    return download_volume_assets(pids, media_dir, checkpoint_path)


# ==========================================
# MAIN EXECUTION
# ==========================================
def resolve_json_input(json_file: str, json_dir: str) -> Path:
    """Same convention as Archivist.resolve_json_input: an explicit path wins; blank
    falls back to whichever *.json in json_dir was modified most recently, so Commissioner
    runs against whatever Paleographer/Archivist are already pointed at without a
    filename typed in separately."""
    if json_file:
        candidate = Path(json_file) if os.path.isabs(json_file) else Path(str(json_dir)) / json_file
        if candidate.is_file():
            return candidate
        raise FileNotFoundError(f"JSON file not found: {candidate}")

    search_dir = Path(str(json_dir))
    candidates = sorted(search_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError(f"No JSON file was set, and no *.json files were found in {search_dir}.")
    return candidates[0]


def load_cookies(cookie_file: str, cdp_port: int = CDP_PORT) -> Dict[str, str]:
    """Cookies for the search endpoint - tries reading them live from a debuggable
    Chrome/Edge instance first (see lac_client.load_cookies_from_cdp; the user launches
    one with --remote-debugging-port, solves the LAC search there, no DevTools copy-paste
    needed), falling back to the manually-maintained cookie file (COMMISSIONER_COOKIE_FILE)
    if no debuggable browser is reachable on that port. Either path ultimately needs the
    user to have solved a real search recently (~30-60 min) - neither obtains a cookie on
    its own."""
    try:
        return lac_client.load_cookies_from_cdp(port=cdp_port)
    except lac_client.LacCallError:
        pass  # no debuggable browser on that port - fall through to the file

    path = Path(cookie_file)
    if not path.is_file():
        raise FileNotFoundError(f"No cookie file at {path}.")
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        raise ValueError(f"Cookie file {path} is empty.")
    return lac_client.parse_cookie_header(raw)


def main() -> None:
    parser = argparse.ArgumentParser(description="Commissioner: LAC-linked cross-referencing and metadata enrichment for Scrip records")
    parser.add_argument("mode", choices=["crosscheck", "retrieve", "enrich", "partition", "resolve-names"], nargs="?", default="crosscheck",
                        help="'crosscheck' searches and attaches related claim documents (requires cookies); "
                             "'retrieve' bulk-downloads one whole volume's worth of PIDs; "
                             "'enrich' fills reel numbers, series codes, and live titles from LAC (no cookies); "
                             "'partition' splits a master JSON file into series-specific files under by_collection/; "
                             "'resolve-names' cleans mojibake and resolves married surnames to maiden surnames.")
    parser.add_argument("--json", default="", help="Path to input JSON file (defaults to auto-selected most recent in JSON_DIR).")
    parser.add_argument("--volume", default=os.getenv("COMMISSIONER_VOLUME", ""),
                        help="Volume/box number to retrieve (retrieve mode only).")
    parser.add_argument("--output-dir", default="", help="Output directory for partitioned collections (partition mode only).")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of records to process (enrich mode).")
    parser.add_argument("--delay", type=float, default=0.4, help="Pacing delay in seconds between LAC requests (default 0.4s).")
    args = parser.parse_args()

    os.makedirs(MEDIA_DIR, exist_ok=True)
    os.makedirs(CHECKPOINT_DIR, exist_ok=True)

    if args.mode == "retrieve":
        if not args.volume:
            print("[FATAL ERROR] --volume is required for retrieve mode (or set COMMISSIONER_VOLUME).")
            return

        print("Loading search cookies...")
        try:
            cookies = load_cookies(COOKIE_FILE)
        except (FileNotFoundError, ValueError) as e:
            print(f"[FATAL ERROR] {e} Search LAC once in a real browser, then paste its Cookie header "
                  f"into that file. Opening the search page now.")
            lac_client.open_search_browser_for_refresh()
            return

        checkpoint_path = str(Path(CHECKPOINT_DIR) / f"volume_{args.volume}.json")
        print(f"Retrieving volume {args.volume} (archival number {DEFAULT_ARCHIVAL_NUMBER})...")
        try:
            result = retrieve_volume(args.volume, cookies, MEDIA_DIR, checkpoint_path,
                                     archival_number=DEFAULT_ARCHIVAL_NUMBER)
        except lac_client.LacSearchAuthError as e:
            print(f"[FATAL ERROR] {e} Opening the search page now.")
            lac_client.open_search_browser_for_refresh()
            return

        print(f"Found {len(result.get('pids', []))} PID(s); downloaded "
              f"{len(result.get('downloaded_pids', []))}, {len(result.get('failed_pids', {}))} failed. "
              f"Re-run to resume/retry failures - already-downloaded PIDs are skipped.")
        return

    # Modes operating on JSON: crosscheck, enrich, partition
    target_json = args.json or JSON_FILE
    input_path = resolve_json_input(target_json, JSON_DIR)
    print(f"[System] Using JSON file: {input_path}" + ("" if target_json else " (auto-selected, most recent)"))
    with open(input_path, "r", encoding="utf-8") as f:
        master_data = json.load(f)

    record_type_name = master_data.get("record_type_name", "")
    if record_type_name != "Scrip":
        print(f"[System] record_type_name is '{record_type_name}', not 'Scrip' - Commissioner only "
              f"operates on Scrip records today. Nothing to do.")
        return

    if args.mode == "partition":
        resolve_dataset_maiden_names(master_data)
        out_dir = Path(args.output_dir) if args.output_dir else input_path.parent / "by_collection"
        print(f"Partitioning {input_path.name} by collection into {out_dir}...")
        partitions = partition_json_by_collection(master_data, out_dir)
        for key, pth in partitions.items():
            print(f"  - [{key}] -> {pth}")
        print(f"Successfully partitioned into {len(partitions)} collection file(s).")
        return

    if args.mode == "resolve-names":
        print(f"Resolving maiden names and cleaning encodings in {input_path.name}...")
        modified = resolve_dataset_maiden_names(master_data)
        with open(input_path, "w", encoding="utf-8") as f:
            json.dump(master_data, f, indent=2, ensure_ascii=False)
        print(f"Name resolution complete: {modified} record(s) updated. Saved to {input_path}")
        return

    if args.mode == "enrich":
        checkpoint_path = str(Path(CHECKPOINT_DIR) / f"enrich_{input_path.stem}.json")
        print(f"Enriching metadata from LAC (delay: {args.delay}s, checkpoint: {checkpoint_path})...")
        enrich_json_data(master_data, checkpoint_path=checkpoint_path, delay_seconds=args.delay,
                         limit=args.limit)
        with open(input_path, "w", encoding="utf-8") as f:
            json.dump(master_data, f, indent=2, ensure_ascii=False)
        print(f"Enrichment complete. Updated {input_path}")
        return

    # crosscheck mode
    print("Loading search cookies...")
    try:
        cookies = load_cookies(COOKIE_FILE)
    except (FileNotFoundError, ValueError) as e:
        print(f"[Warning] {e} Proceeding without search cookies - only own-PID lookups (from the "
              f"source filename) will resolve; related-document discovery will be flagged for "
              f"review on every record instead.")
        cookies = {}

    processed_count = 0
    for sheet in master_data.get("sheets", []):
        for record in sheet.get("records", []):
            cross_check_claim_record(record, cookies, MEDIA_DIR)
            processed_count += 1

    resolve_dataset_maiden_names(master_data)
    with open(input_path, "w", encoding="utf-8") as f:
        json.dump(master_data, f, indent=2, ensure_ascii=False)
    print(f"Cross-checked {processed_count} record(s). Saved to {input_path}")


if __name__ == "__main__":
    main()
