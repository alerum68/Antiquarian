"""
Archivist - the toolbox's Create step.

Reads a single JSON file produced by Voyageur (Gather) and/or Paleographer (Analysis),
either census-style (a flat list of people per scanned page, needing household-grouping
since census rows carry no explicit family relationships) or church-register-style
(explicit per-participant roles, no grouping needed), and emits GEDCOM 5.5.1 files in
both RootsMagic (RM) and Family Tree Maker (FTM) flavors.
"""

import calendar
import datetime
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Dict, Hashable, List, Literal, Optional, Tuple, TypedDict, Union, cast

import pandas as pd
import yaml
from dotenv import load_dotenv

# A raw scalar value as read from a JSON field or DataFrame cell.
CellValue = Union[str, int, float, bool, None]


class HouseholdUnit(TypedDict):
    """A candidate family unit built up while grouping census household members."""
    husband: Optional[pd.Series]
    wife: Optional[pd.Series]
    children: List[pd.Series]
    anchor: Optional[pd.Series]
    type: str


class FlagRecord(TypedDict):
    """A person flagged for manual review, with the reason and confidence score."""
    person: pd.Series
    reason: str
    confidence: float


# ==========================================
# CONFIGURATION
# ==========================================
# Global settings come from the project root's .env; this tool's own settings come
# from its own subfolder's .env, so Archivist stays runnable standalone. A church
# document's citation-source settings (call number, repository, etc.) are configured
# alongside its register/parish info in Paleographer's own settings tab, so Archivist
# also reads Paleographer's .env directly (never through Scriptorium.py) - see
# apply_record_type_field_remap, which resolves the actual values from whichever of
# these three .env files has them.
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
load_dotenv(Path(__file__).resolve().parent / ".env", override=False)
load_dotenv(Path(__file__).resolve().parent.parent / "Paleographer" / ".env", override=False)


def get_env_int(key: str, default: int) -> int:
    val = os.getenv(key, "")
    try:
        return int(str(val).strip()) if val and str(val).strip() else default
    except ValueError:
        return default


def safe_path(base: str, *parts: str) -> str:
    """Safely joins paths, allowing absolute paths to override the base. If every part is
    blank, returns "" rather than the bare base, so optional overrides (like
    GEDCOM_OUTPUT_PATH left blank) can still signal "no override" to their callers."""
    non_blank = [p for p in parts if p]
    if not non_blank:
        return ""
    res = base
    for p in non_blank:
        res = p if os.path.isabs(p) else os.path.join(res, p)
    return res


# Shared, generic settings (used regardless of which flavor of JSON is loaded).
ORG_NAME = os.getenv("ORG_NAME", "")
RESEARCHER = os.getenv("RESEARCHER", "")
SOFTWARE_NAME = os.getenv("SOFTWARE_NAME", "RootsMagic")
SOFTWARE_VERS = os.getenv("SOFTWARE_VERS", "11.0")
COPYRIGHT_START = os.getenv("COPYRIGHT_START", "2026")
GEDCOM_NOTE = os.getenv("GEDCOM_NOTE", "")
GEDCOM_CONC = os.getenv("GEDCOM_CONC", "")
REVIEW_COLOR = os.getenv("REVIEW_COLOR", "1")
SUBM_ADDRESS = os.getenv("SUBM_ADDRESS", "")
MGS_GROUP_URL = os.getenv("MGS_GROUP_URL", "")
ANCESTRY_GROUP_URL = os.getenv("ANCESTRY_GROUP_URL", "")
ROOT_SOURCE_ID = os.getenv("ROOT_SOURCE_ID", "@S1@")

CALL_NUMBER = os.getenv("CALL_NUMBER", "")
REPOSITORY = os.getenv("REPOSITORY", "")
REPOSITORY_LOC = os.getenv("REPOSITORY_LOC", "")
COLLECTION_URL = os.getenv("COLLECTION_URL", "")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "")
PUBLISHER = os.getenv("PUBLISHER", "")
PUB_LOC = os.getenv("PUB_LOC", "")

PROGRAM_DIR = os.getenv("PROGRAM_DIR", "")
RM_DIR = safe_path(PROGRAM_DIR, os.getenv("RM_DIR", ""))
FTM_DIR = safe_path(PROGRAM_DIR, os.getenv("FTM_DIR", ""))
JSON_DIR = safe_path(PROGRAM_DIR, os.getenv("JSON_DIR", ""))
GEDCOM_OUTPUT_PATH = safe_path(PROGRAM_DIR, os.getenv("GEDCOM_OUTPUT_PATH", ""))
GEDCOM_OUTPUT_NAME = os.getenv("GEDCOM_OUTPUT_NAME", "Family_Register.ged")
# Census has no .pmt (no field_remap table to resolve this from - see
# apply_record_type_field_remap, which handles church/scrip instead), so its own prefixed
# key is read directly here as a plain fallback, standalone, with no dependency on
# Scriptorium.py bridging CENSUS_IMAGE_DIR to the generic name.
IMAGE_DIR = safe_path(PROGRAM_DIR, os.getenv("IMAGE_DIR", "") or os.getenv("CENSUS_IMAGE_DIR", ""))
IMAGE_EXTENSION = os.getenv("IMAGE_EXTENSION", "").lstrip(".").lower()
FORM_TYPE = IMAGE_EXTENSION

JSON_FILE = os.getenv("JSON_FILE", "")
CURRENT_DATE = datetime.datetime.now().strftime('%d %b %Y').upper()

# Census-specific settings. None of these have a Scriptorium GUI field (deliberately, not
# an oversight) - they're power-user .env overrides for a value the gathered JSON's own
# per-row/per-page data doesn't already provide (see get_row_val/get_json_fallback), which
# covers normal usage; left blank, each falls back to its own row/page-derived value or a
# safe default (e.g. ANCESTRY_START_RECORD_ID's fallback offset is added to a DataFrame row
# index that's already unique within that one GEDCOM build on its own).
CENSUS_YEAR = get_env_int("CENSUS_YEAR", 0)
ANCESTRY_START_RECORD_ID = get_env_int("ANCESTRY_START_RECORD_ID", 0)
APID_DB = os.getenv("APID_DB", "")
ANCESTRY_IMAGE_BASE_ID = os.getenv("ANCESTRY_IMAGE_BASE_ID", "")
BASE_ID = ANCESTRY_IMAGE_BASE_ID.rstrip('_-')
STATE = os.getenv("STATE", "")
COUNTY = os.getenv("COUNTY", "")
TOWNSHIP = os.getenv("TOWNSHIP", "")
ENUMERATION_DISTRICT = os.getenv("ENUMERATION_DISTRICT", "")
FILM_NUMBER = os.getenv("FILM_NUMBER", "")
ROLL_NUMBER = os.getenv("ROLL_NUMBER", "")
MIN_MARRIAGE_AGE = get_env_int("MIN_MARRIAGE_AGE", 12)
MAX_SPOUSE_AGE_GAP = get_env_int("MAX_SPOUSE_AGE_GAP", 25)
HUSBAND_CHILD_AGE_GAP = (get_env_int("HUSBAND_CHILD_AGE_GAP_MIN", 14), get_env_int("HUSBAND_CHILD_AGE_GAP_MAX", 60))
WIFE_CHILD_AGE_GAP = (get_env_int("WIFE_CHILD_AGE_GAP_MIN", 12), get_env_int("WIFE_CHILD_AGE_GAP_MAX", 50))
REVIEW_THRESHOLD = 0.6


def get_census_era(year: int) -> str:
    if year <= 1840:
        return "pre1850"
    if year <= 1870:
        return "heuristic"
    return "relationship"


# RootsMagic 11's built-in census source templates (confirmed against a live .rmtree's
# SourceTemplateTable), keyed by which fields each one actually defines. The standard
# library tops out at "1880-1930"; there's no dedicated 1940/1950/1960 template, but
# those years use the same ED + dwelling/family schedule structure as 1880-1930, so 49
# is the correct template to keep reusing rather than a compromise.
CENSUS_TEMPLATES = {47: {"schedule": False, "ed": False, "household": False},   # 1790-1840 (Filmed)
                    48: {"schedule": True, "ed": False, "household": True},    # 1850-1870 (Filmed)
                    49: {"schedule": True, "ed": True, "household": True}}     # 1880-1930 (Filmed), reused 1940+


def get_census_template_id(year: int) -> int:
    if year <= 1840:
        return 47
    if year <= 1870:
        return 48
    return 49


CENSUS_ERA = get_census_era(CENSUS_YEAR)

# Church-specific settings.
CHURCH_CONFIG = {
    "parish_file_name": os.getenv("PARISH_FILE_NAME", "Parish_Export"),
    "parish_name": os.getenv("PARISH_NAME", "Parish Name"),
    "parish_city": os.getenv("PARISH_CITY", "City"),
    "parish_state": os.getenv("PARISH_STATE", "State"),
    "parish_location": (f"{os.getenv('PARISH_CITY', 'City')}, "
                        f"{os.getenv('PARISH_STATE', 'State')}").strip(", "),
    "parish_name_short": os.getenv("PARISH_NAME_SHORT", "Parish"),
    "volume_title": os.getenv("VOLUME_TITLE", ""),
    "volume_num": os.getenv("VOLUME_NUM", ""),
    "register_name": os.getenv("REGISTER_NAME", ""),
    "register_source_id": os.getenv("REGISTER_SOURCE_ID", "1"),
    "default_location": os.getenv("DEFAULT_EVENT_LOCATION", ""),
    "collection_url": os.getenv("COLLECTION_URL", ""),
    "collection_name": os.getenv("COLLECTION_NAME", ""),
    "transcription_header": os.getenv("TRANSCRIPTION_HEADER", "Original Transcription:"),
    "translation_header": os.getenv("TRANSLATION_HEADER", "English Translation:"),
    "role_clergy": os.getenv("ROLE_CLERGY", "Priest"),
    "clergy_honorific": os.getenv("CLERGY_HONORIFIC", "Father"),
    "role_default_witness": os.getenv("ROLE_DEFAULT_WITNESS", "Witness"),
}

# The same RootsMagic FactTypeTable mirror Paleographer's engine.py sources its event_type
# vocabulary from - loaded here only for its 'person' vs 'family' bucketing and gedcom_tag,
# so a record's own primary event (Baptism, Burial, Marriage, ...) resolves to the right
# GEDCOM tag and attachment point (an individual's own INDI vs the FAM record it creates)
# by table lookup instead of Archivist hardcoding a fixed list of known event types.
with open(Path(__file__).resolve().parent.parent / "FactTypes.json", "r", encoding="utf-8") as _fact_types_file:
    FACT_TYPES = json.load(_fact_types_file)


def get_event_gedcom_tag(event_type: str) -> str:
    """Looks up the GEDCOM tag for a record's own event_type (e.g. 'Baptism' -> 'BAPM',
    'Marriage' -> 'MARR'), checking the person bucket first since most record types are
    person-level events. Falls back to 'EVEN' (a generic custom event) for a fact type not
    found in either bucket, rather than guessing or raising."""
    entry = FACT_TYPES.get('person', {}).get(event_type) or FACT_TYPES.get('family', {}).get(event_type)
    return entry.get('gedcom_tag', 'EVEN') if entry else 'EVEN'


def is_family_event(event_type: str) -> bool:
    """True when event_type is a family-level fact (Marriage and its variants) rather than
    a person-level one - the only thing this distinction controls is whether the record's
    own primary event attaches to the FAM record it creates or to the primary participant's
    own INDI record. Family-position linking (FAMC/FAMS/associations) itself never depends
    on this - a spouse/parent/child role forms the same family structure regardless of what
    kind of record mentioned it."""
    return event_type in FACT_TYPES.get('family', {})


# ==========================================
# SHARED UTILITIES
# ==========================================
def clean_val(val: CellValue) -> str:
    """Scrubs literal nulls, normalizes spaces, and clears invisible characters."""
    if val is None or (isinstance(val, float) and pd.isna(val)) or val == "":
        return ""
    if isinstance(val, float) and val.is_integer():
        return str(int(val))
    val_str = re.sub(r' +', ' ',
                     str(val).replace('\xa0', ' ').replace('​', '').replace(' ', ' ')
                     ).strip()
    return "" if val_str.lower() in ["null", "none", ""] else val_str


def get_gender(val: Union[pd.Series, dict, CellValue]) -> str:
    if isinstance(val, (pd.Series, dict)):
        str_val = clean_val(val.get("Gender", ""))
    else:
        str_val = clean_val(val)
    if not str_val:
        return "U"
    v = str_val.upper()
    if v.startswith(("M", "MALE")):
        return "M"
    elif v.startswith(("F", "FEMALE")):
        return "F"
    return "U"


def format_gedcom_date(date_str: str) -> str:
    """
    Converts standard YYYY-MM-DD or YYYY-MM dates into GEDCOM standard format.
    Handles genealogical prefixes (BEF, AFT, ABT, CAL, EST).
    """
    date_str = clean_val(date_str)
    if not date_str:
        return ""

    prefix = ""
    valid_prefixes = ("BEF ", "AFT ", "ABT ", "CAL ", "EST ")
    if date_str.upper().startswith(valid_prefixes):
        prefix = date_str[:4].upper()
        date_str = date_str[4:].strip()

    try:
        parts = date_str.split('-')
        if len(parts) == 3 and len(parts[0]) == 4:
            dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
            return f"{prefix}{dt.day} {dt.strftime('%b').upper()} {dt.year}"
        elif len(parts) == 2 and len(parts[0]) == 4:
            dt = datetime.datetime.strptime(date_str, "%Y-%m")
            return f"{prefix}{dt.strftime('%b').upper()} {dt.year}"
    except ValueError:
        pass

    return prefix + date_str


def get_proof_status(date_str: str) -> str:
    """Evaluates date prefixes to assign proposed or proven proof status tags."""
    if date_str:
        upper_date = f"{date_str}".upper().strip()
        if upper_date.startswith(("BEF", "ABT", "AFT", "EST", "CAL")):
            return "proposed"
    return "proven"


def estimate_birth_from_age(event_date: str, age_str: str) -> str:
    """
    Calculates an estimated birthdate based on event date precision
    and detailed age metadata (years, months, weeks, days).
    """
    if not event_date or not age_str:
        return ""

    try:
        if len(f"{event_date}") == 10:
            dt = datetime.datetime.strptime(f"{event_date}"[:10], "%Y-%m-%d")
            precision = "day"
        elif len(f"{event_date}") == 7:
            dt = datetime.datetime.strptime(f"{event_date}"[:7], "%Y-%m")
            precision = "month"
        else:
            dt = datetime.datetime.strptime(f"{event_date}"[:4], "%Y")
            precision = "year"
    except ValueError:
        return ""

    age_str = f"{age_str}".strip().lower()
    years = sum(map(int, re.findall(r'(\d+)\s*(?:year|yr|y\b)', age_str)))
    months = sum(map(int, re.findall(r'(\d+)\s*(?:month|mo|m\b)', age_str)))
    weeks = sum(map(int, re.findall(r'(\d+)\s*(?:week|wk|w\b)', age_str)))
    days = sum(map(int, re.findall(r'(\d+)\s*(?:day|d\b)', age_str)))

    if not any([years, months, weeks, days]):
        match = re.search(r'\d+', age_str)
        if match:
            years = int(match.group())
        else:
            return ""

    if precision == "year" and (months or weeks or days):
        return f"CAL {dt.year - years}" if years else f"ABT {dt.year}"

    if precision == "month" and (weeks or days):
        if not (months or years):
            return f"ABT {dt.strftime('%Y-%m')}"
        weeks, days = 0, 0

    if weeks or days:
        dt -= datetime.timedelta(weeks=weeks, days=days)

    if months or years:
        total_months = dt.month - 1 - months
        new_year = dt.year - years + (total_months // 12)
        new_month = (total_months % 12) + 1
        last_day_of_month = calendar.monthrange(new_year, new_month)[1]
        dt = dt.replace(year=new_year, month=new_month, day=min(dt.day, last_day_of_month))

    if precision == "day" and any([months, weeks, days]):
        return f"CAL {dt.strftime('%Y-%m-%d')}"
    elif precision in ["day", "month"] and months:
        return f"CAL {dt.strftime('%Y-%m')}"

    return f"CAL {dt.year}"


def wrap_text(text: str, tag: str = "5 CONT") -> str:
    """Wraps text content natively for GEDCOM, slicing CONC tags mid-word to prevent layout artifacts."""
    if not text:
        return ""
    lines = clean_val(text).split('\n')
    wrapped = []

    for line in lines:
        if not line:
            continue
        wrapped.append(f"{tag} {line[:75]}")
        for i in range(75, len(line), 75):
            wrapped.append(f"{tag[:1]} CONC {line[i:i + 75]}")

    return "\n".join(wrapped)


def resolve_gedcom_output_path(target_software: str) -> Path:
    """Resolves the output .ged path for a given software flavor (RM/FTM), rooted in
    GEDCOM_OUTPUT_PATH if set, otherwise that flavor's own RM_DIR/FTM_DIR."""
    base_name, ext = Path(GEDCOM_OUTPUT_NAME).stem, Path(GEDCOM_OUTPUT_NAME).suffix
    out_dir = Path(str(GEDCOM_OUTPUT_PATH)) if GEDCOM_OUTPUT_PATH else (
        Path(str(RM_DIR)) if target_software == "RM" else Path(str(FTM_DIR)))
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"{base_name} - {target_software}{ext}"


def dedent_citation_lines(lines: List[str], skip_at_level: Optional[Tuple[int, str]] = None) -> List[str]:
    """Shifts a GEDCOM citation block up one level, for embedding inside a _TASK record.
    If skip_at_level is given as (level, prefix), lines at that exact level whose content
    starts with prefix are dropped entirely instead of shifted (e.g. dropping the 2 _PROOF
    line, which has no meaning inside a _TASK)."""
    result = []
    for line in lines:
        parts = line.split(" ", 1)
        if len(parts) == 2 and parts[0].isdigit():
            lvl = int(parts[0])
            if skip_at_level and lvl == skip_at_level[0] and parts[1].startswith(skip_at_level[1]):
                continue
            result.append(f"{lvl - 1} {parts[1]}")
        else:
            result.append(line)
    return result


def weblink_lines(url: str, name: str, target_software: str) -> List[str]:
    """
    RM keeps its proprietary _WEBTAG structure. FTM has no such tag; real Family Tree
    Maker exports use _LINK for the URL and duplicate it as a plain NOTE right after,
    a pattern confirmed against a genuine native FTM GEDCOM export.
    """
    if not url:
        return []
    if target_software == "RM":
        return ["1 _WEBTAG", f"2 NAME {name}", f"2 URL {url}"]
    return [f"1 _LINK {url}", f"1 NOTE {url}"]


# ==========================================
# CENSUS FLAVOR: HOUSEHOLD GROUPING
# ==========================================
def get_age(row: pd.Series) -> float:
    def parse_num(val: CellValue) -> Optional[float]:
        try:
            if pd.notna(val) and val is not None:
                val_str = str(val).strip()
                if val_str:
                    return float(val_str)
        except ValueError:
            pass
        return None

    b_yr = parse_num(row.get('Birth Year'))
    if b_yr is not None:
        return float(CENSUS_YEAR) - b_yr

    age = parse_num(row.get('Age'))
    return age if age is not None else -1.0


def spouse_evaluation(a: pd.Series, b: pd.Series) -> Tuple[bool, float, str]:
    g_a = get_gender(a.get('Gender', ''))
    g_b = get_gender(b.get('Gender', ''))
    if 'U' in (g_a, g_b) or g_a == g_b:
        return False, 0.0, "gender mismatch or unknown"
    age_a, age_b = get_age(a), get_age(b)
    if (age_a != -1 and age_a < MIN_MARRIAGE_AGE) or (age_b != -1 and age_b < MIN_MARRIAGE_AGE):
        return False, 0.0, "below minimum marriage age"
    if age_a != -1 and age_b != -1 and abs(age_a - age_b) >= MAX_SPOUSE_AGE_GAP:
        return False, 0.0, "spousal age gap too large"
    sur_a, sur_b = clean_val(a.get('Surname')), clean_val(b.get('Surname'))
    if sur_a and sur_b:
        if sur_a == sur_b:
            return True, 0.9, "matching surnames"
        else:
            return False, 0.0, "surnames differ"
    return True, 0.4, "surname missing for one party -- unverified pairing"


def child_evaluation(unit: HouseholdUnit, member: pd.Series) -> Tuple[bool, float, str]:
    h = unit.get('husband')
    w = unit.get('wife')
    if h is None and w is None:
        return False, 0.0, "no parents in unit"
    m_age = get_age(member)
    m_sur = clean_val(member.get('Surname'))
    if h is not None:
        u_sur = clean_val(h.get('Surname'))
    else:
        assert w is not None  # guaranteed: the check above ruled out both being None
        u_sur = clean_val(w.get('Surname'))
    if m_sur and u_sur and m_sur != u_sur:
        return False, 0.0, "surname mismatch"
    surname_conf = 0.9 if (m_sur and u_sur and m_sur == u_sur) else 0.5
    if m_age == -1:
        return True, min(surname_conf, 0.5), "no age data for child -- unverified"

    def in_rng(parent: Optional[pd.Series], gap_rng: Tuple[int, int]) -> Optional[bool]:
        if parent is None:
            return None
        p_age = get_age(parent)
        if p_age != -1:
            return gap_rng[0] <= (p_age - m_age) <= gap_rng[1]
        return None

    checks = []
    h_check = in_rng(h, HUSBAND_CHILD_AGE_GAP)
    if h_check is not None:
        checks.append(h_check)
    w_check = in_rng(w, WIFE_CHILD_AGE_GAP)
    if w_check is not None:
        checks.append(w_check)

    if checks:
        if not any(checks):
            return False, 0.0, "age gap outside plausible range for both parents"
        if not all(checks):
            surname_conf = min(surname_conf, 0.8)
    return True, surname_conf, "age and surname consistent with parentage"


def find_parent(units: List[HouseholdUnit], member: pd.Series) -> Optional[Tuple[int, float, str]]:
    best: Optional[Tuple[int, float, str]] = None
    for i in range(len(units) - 1, -1, -1):
        plausible, match_conf, match_rsn = child_evaluation(units[i], member)
        if plausible:
            if best is None:
                best = (i, match_conf, match_rsn)
            else:
                _, best_conf, _ = best
                if match_conf > best_conf:
                    best = (i, match_conf, match_rsn)
    return best


def parse_household(group: pd.DataFrame) -> Tuple[List[HouseholdUnit], List[pd.Series], List[FlagRecord]]:
    members = [row for _, row in group.iterrows()]
    n = len(members)
    flags: List[FlagRecord] = []
    units: List[HouseholdUnit] = []
    unrelated: List[pd.Series] = []
    consumed = set()

    def add_flag(person: pd.Series, flag_reason: str, flag_conf: float) -> None:
        if flag_conf < REVIEW_THRESHOLD:
            flags.append({'person': person, 'reason': flag_reason, 'confidence': flag_conf})

    # A merge-review reason set by MergedCensus.py (a cross-source field conflict, or a
    # person present in only one source) is a data-provenance flag, not a confidence-based
    # inference - always surface it as a review task rather than gating it on REVIEW_THRESHOLD.
    for person in members:
        merge_reason = clean_val(person.get('_MergeReviewReason'))
        if merge_reason:
            add_flag(person, merge_reason, 0.0)

    def make_unit(mem1: pd.Series, mem2: Optional[pd.Series] = None,
                  anchor_person: Optional[pd.Series] = None) -> HouseholdUnit:
        m1_gen = get_gender(mem1)
        h_unit, w_unit = (None, mem1) if m1_gen == 'F' else (mem1, None)
        if mem2 is not None:
            h_unit, w_unit = (mem2, mem1) if m1_gen == 'F' else (mem1, mem2)
        return {'husband': h_unit, 'wife': w_unit, 'children': [], 'anchor': anchor_person, 'type': 'main'}

    if not members:
        return units, unrelated, flags

    head = members[0]
    i = 1
    if n > 1:
        sp_mem = members[1]
        plausible, sp_conf, sp_reason = spouse_evaluation(head, sp_mem)
        head_gender = get_gender(head)
        sp_gender = get_gender(sp_mem)
        if not plausible and head_gender != sp_gender and 'U' not in (head_gender, sp_gender):
            sp_age = get_age(sp_mem)
            if sp_age != -1 and any(get_age(x) > sp_age for x in members[2:]):
                plausible, sp_conf, sp_reason = True, 0.8, "step-parent pattern"
        if plausible:
            units.append(make_unit(head, sp_mem))
            add_flag(sp_mem, f"Possible spouse: {sp_reason}", sp_conf)
            consumed.update({0, 1})
            i = 2

    if 0 not in consumed:
        units.append(make_unit(head))
        consumed.add(0)

    while i < n:
        if i in consumed:
            i += 1
            continue
        m = members[i]
        if i + 1 < n and (i + 1) not in consumed:
            nxt = members[i + 1]
            sub_plausible, sub_sp_conf, sub_sp_reason = spouse_evaluation(m, nxt)
            if sub_plausible:
                fit_m = find_parent(units, m)
                fit_nxt = find_parent(units, nxt)
                m_is_child = False
                m_unit_idx = -1
                if fit_m is not None:
                    m_unit_idx, m_conf, _ = fit_m
                    m_is_child = (m_conf >= REVIEW_THRESHOLD)
                nxt_is_child = False
                if fit_nxt is not None:
                    _, nxt_conf, _ = fit_nxt
                    nxt_is_child = (nxt_conf >= REVIEW_THRESHOLD)

                if m_is_child and nxt_is_child:
                    m_unit = units[m_unit_idx]
                    last_c_age = -1.0
                    if m_unit['children']:
                        last_c_age = get_age(m_unit['children'][-1])
                    m_age = get_age(m)
                    if last_c_age != -1 and m_age != -1 and m_age > last_c_age and m_age >= MIN_MARRIAGE_AGE:
                        anc_member = m if clean_val(m.get('Surname')) == clean_val(head.get('Surname')) else nxt
                        units[m_unit_idx]['children'].append(anc_member)
                        units.append(make_unit(m, nxt, anchor_person=anc_member))
                        flagged_person = nxt if anc_member is m else m
                        add_flag(flagged_person, "Paired as spouse due to age-sequence break.", 0.5)
                    else:
                        units[m_unit_idx]['children'].extend([m, nxt])
                    consumed.update({i, i + 1})
                    i += 2
                    continue
                elif m_is_child or nxt_is_child:
                    if m_is_child and fit_m is not None:
                        anc_member = m
                        anchor_idx, anchor_conf, anchor_rsn = fit_m
                    elif fit_nxt is not None:
                        anc_member = nxt
                        anchor_idx, anchor_conf, anchor_rsn = fit_nxt
                    else:
                        continue

                    units[anchor_idx]['children'].append(anc_member)
                    add_flag(anc_member, f"Possible child: {anchor_rsn}", anchor_conf)
                    units.append(make_unit(m, nxt, anchor_person=anc_member))
                    consumed.update({i, i + 1})
                    i += 2
                    continue
                else:
                    # Neither fits as a child of any existing unit - a plausible spouse
                    # pair that doesn't relate to the household's presumed head at all is
                    # a second, independent family sharing the same family/dwelling number
                    # (a boarder's own spouse and children, sharing a dwelling with an
                    # unrelated household - confirmed against real 1860 census data, where
                    # every member of such a family was previously falling through to
                    # "unrelated" one at a time simply because none of them matched the
                    # anchor unit). Forming their own unit here lets their own children
                    # attach correctly on the next iterations (find_parent checks newest
                    # units first), instead of every one of them being lost individually.
                    units.append(make_unit(m, nxt))
                    add_flag(nxt, f"Possible spouse (separate family unit): {sub_sp_reason}", sub_sp_conf)
                    consumed.update({i, i + 1})
                    i += 2
                    continue

        match = find_parent(units, m)
        if match:
            idx, match_conf, match_rsn = match
            units[idx]['children'].append(m)
            add_flag(m, f"Possible child: {match_rsn}", match_conf)
        else:
            m_sur = clean_val(m.get('Surname'))
            h_sur = clean_val(head.get('Surname'))
            if m_sur == h_sur and m_sur:
                units[0]['children'].append(m)
                add_flag(m, "Head-surname match; no age fit", 0.3)
            else:
                unrelated.append(m)
                add_flag(m, "Unrelated household member", 0.2)
        consumed.add(i)
        i += 1

    return units, unrelated, flags


# ==========================================
# CENSUS FLAVOR: RELATIONSHIP-COLUMN GROUPING
# ==========================================
RELATIONSHIP_COLUMN_CANDIDATES = ('Relationship to Head', 'Relationship', 'Relation to Head', 'Relation')
REL_HEAD = {'head', 'head of household', 'head of family', 'self', 'self head', 'housekeeper', 'partner'}
REL_SPOUSE = {'wife', 'husband', 'spouse'}
REL_CHILD = {'son', 'daughter', 'child', 'stepson', 'stepdaughter', 'step son', 'step daughter', 'adopted son',
             'adopted daughter', 'foster son', 'foster daughter'}
REL_SIBLING = {'brother', 'sister', 'half brother', 'half sister', 'stepbrother', 'stepsister', 'step brother',
               'step sister'}
REL_PARENT = {'father', 'mother', 'stepfather', 'stepmother', 'step father', 'step mother'}
REL_INLAW_SIBLING = {'brother in law', 'sister in law'}
REL_INLAW_PARENT = {'father in law', 'mother in law'}
REL_INLAW_CHILD = {'son in law', 'daughter in law'}
REL_GRANDCHILD = {'grandson', 'granddaughter', 'grandchild', 'great grandson', 'great granddaughter',
                  'great grandchild', 'step grandson', 'step granddaughter'}
REL_NIBLING = {'nephew', 'niece'}


def normalize_relationship(val: CellValue) -> str:
    v = clean_val(val).lower()
    v = v.replace('-', ' ')  # Convert hyphens to spaces before stripping non-alpha characters
    v = re.sub(r'[^a-z ]', '', v)
    return re.sub(r'\s+', ' ', v).strip()


def is_relationship_column(col_name: str) -> bool:
    norm = re.sub(r'[^a-z]', '', col_name.lower())
    return ('relation' in norm) and ('head' in norm)


def find_relationship_column(columns: Union[pd.Index, List[str]]) -> Optional[str]:
    # Exact match first (fast path for the known-common headers)
    exact = next((c for c in RELATIONSHIP_COLUMN_CANDIDATES if c in columns), None)
    if exact:
        return exact
    # Fuzzy fallback: real-world exports vary the header ("Relation to Head of House",
    # "Relationship to Head of Household", etc.) -- match on substance, not exact string,
    # so relationship data isn't silently dropped to the age/surname heuristic.
    return next((c for c in columns if is_relationship_column(str(c))), None)


def resolve_cross_family_links(
        units: List[HouseholdUnit], unrelated: List[pd.Series], flags: List[FlagRecord]
) -> Tuple[List[HouseholdUnit], List[pd.Series], List[FlagRecord]]:
    """
    Consolidates split family units by inferring maiden names from in-law relationships
    and linking them to a plausible parent/head of household with that surname.
    """
    for unit in units:
        if unit.get('type') == 'spouse_parents':
            wife = unit.get('anchor')
            if wife is None or not isinstance(wife, pd.Series):
                continue

            unit_children = unit.get('children')
            if not isinstance(unit_children, list):
                continue

            # Separate the wife from her siblings (who share her maiden surname)
            siblings = [c for c in unit_children if c is not wife]
            if not siblings or not isinstance(siblings[0], pd.Series):
                continue

            maiden_surname = clean_val(siblings[0].get('Surname'))
            if not maiden_surname:
                continue

            wife_age = get_age(wife)

            # Look for a plausible parent in the other household units
            plausible_parent_unit = None
            parent_name = ""
            for other_unit in units:
                if other_unit is unit:
                    continue

                # Check both potential husband (father) and wife (mother) in the unit
                parent_checks: List[Tuple[Literal['husband', 'wife'], Tuple[int, int]]] = [
                    ('husband', HUSBAND_CHILD_AGE_GAP), ('wife', WIFE_CHILD_AGE_GAP)]
                for parent_key, age_gap_range in parent_checks:
                    pp = other_unit.get(parent_key)
                    if isinstance(pp, pd.Series):
                        pp_sur = clean_val(pp.get('Surname'))
                        pp_age = get_age(pp)

                        # If the surname matches the maiden name and the age gap is plausible
                        if pp_sur == maiden_surname:
                            if pp_age == -1 or wife_age == -1 or (
                                    age_gap_range[0] <= (pp_age - wife_age) <= age_gap_range[1]):
                                plausible_parent_unit = other_unit
                                parent_name = clean_val(pp.get('Given Name'))
                                break
                if plausible_parent_unit:
                    break

            # If a matching parent unit is found, migrate the children
            if plausible_parent_unit:
                parent_children = plausible_parent_unit.get('children')
                if isinstance(parent_children, list):
                    if not any(wife is c for c in parent_children):
                        parent_children.append(wife)
                        flags.append({'person': wife,
                                      'reason': f"Inferred as child of {parent_name} {maiden_surname} via in-law links",
                                      'confidence': 0.85})

                    for sib in siblings:
                        if not any(sib is c for c in parent_children):
                            parent_children.append(sib)
                            flags.append({'person': sib,
                                          'reason': f"Inferred as child of {parent_name} {maiden_surname} via "
                                                    f"sibling link to head's spouse",
                                          'confidence': 0.85})

                # Clear migrated individuals from the spouse_parents unit
                unit['children'] = [c for c in unit_children if c is not wife and c not in siblings]
                if unit.get('husband') is None and unit.get('wife') is None and not unit.get('children'):
                    unit['type'] = 'merged'

    # Filter out any units we just emptied and merged
    units = [u for u in units if u.get('type') != 'merged']
    return units, unrelated, flags


def append_unit_if_not_empty(units: List[HouseholdUnit], unit: Optional[HouseholdUnit]) -> None:
    if unit and (unit['husband'] is not None or unit['wife'] is not None or len(unit['children']) > 1):
        units.append(unit)


def parse_household_relational(
        group: pd.DataFrame) -> Tuple[List[HouseholdUnit], List[pd.Series], List[FlagRecord]]:
    rel_col = find_relationship_column(group.columns)
    if rel_col is None:
        return parse_household(group)

    # Verify that a Head of Household exists before proceeding with relational logic.
    # If no head is found, fallback to heuristic logic so families don't collapse.
    has_head = any(normalize_relationship(m.get(rel_col, '')) in REL_HEAD for _, m in group.iterrows())
    if not has_head:
        return parse_household(group)

    flags: List[FlagRecord] = []
    unrelated: List[pd.Series] = []
    units: List[HouseholdUnit] = []

    # A merge-review reason set by MergedCensus.py (a cross-source field conflict, or a
    # person present in only one source) is a data-provenance flag, not a confidence-based
    # inference - always surface it as a review task.
    for _, m in group.iterrows():
        merge_reason = clean_val(m.get('_MergeReviewReason'))
        if merge_reason:
            flags.append({'person': m, 'reason': merge_reason, 'confidence': 0.0})

    current_unit: Optional[HouseholdUnit] = None
    primary_head: Optional[pd.Series] = None
    primary_spouse: Optional[pd.Series] = None
    last_child_inlaw_unit: Optional[HouseholdUnit] = None

    head_parents_unit: Optional[HouseholdUnit] = None
    spouse_parents_unit: Optional[HouseholdUnit] = None

    for _, m in group.iterrows():
        rel = normalize_relationship(m.get(rel_col, ''))

        # Flush and reset families if a new Head is encountered (e.g., Multi-family dwelling)
        if rel in REL_HEAD or current_unit is None or head_parents_unit is None or spouse_parents_unit is None:
            append_unit_if_not_empty(units, current_unit)
            append_unit_if_not_empty(units, head_parents_unit)
            append_unit_if_not_empty(units, spouse_parents_unit)

            current_unit = {'husband': None, 'wife': None, 'children': [], 'anchor': m, 'type': 'main'}
            head_parents_unit = {'husband': None, 'wife': None, 'children': [], 'anchor': m, 'type': 'head_parents'}
            spouse_parents_unit = {'husband': None, 'wife': None, 'children': [], 'anchor': None,
                                   'type': 'spouse_parents'}

            primary_head = None
            primary_spouse = None
            last_child_inlaw_unit = None

            if rel in REL_HEAD:
                current_unit = cast(HouseholdUnit, current_unit)
                head_parents_unit = cast(HouseholdUnit, head_parents_unit)
                if get_gender(m) == 'F':
                    current_unit['wife'] = m
                else:
                    current_unit['husband'] = m

                primary_head = m
                head_children = head_parents_unit.get('children')
                if isinstance(head_children, list):
                    head_children.append(m)
            else:
                unrelated.append(m)
                flags.append(
                    {'person': m, 'reason': f"First person in household not listed as Head (rel: {rel.title()})",
                     'confidence': 0.3})
            continue

        if rel in REL_SPOUSE and current_unit is not None:
            if get_gender(m) == 'F':
                current_unit['wife'] = m
            else:
                current_unit['husband'] = m

            if primary_spouse is None and primary_head is not None and spouse_parents_unit is not None:
                primary_spouse = m
                spouse_parents_unit['anchor'] = m
                spouse_children = spouse_parents_unit.get('children')
                if isinstance(spouse_children, list):
                    spouse_children.append(m)

        elif rel in REL_CHILD and current_unit is not None:
            curr_children = current_unit.get('children')
            if isinstance(curr_children, list):
                curr_children.append(m)

        elif rel in REL_INLAW_CHILD and current_unit is not None:
            spouse_candidate = None
            h_sub: Optional[pd.Series]
            w_sub: Optional[pd.Series]
            m_gender = get_gender(m)
            target_gender = 'F' if m_gender == 'M' else ('M' if m_gender == 'F' else None)

            curr_children = current_unit.get('children')
            if isinstance(curr_children, list):
                for child in reversed(curr_children):
                    if target_gender is None or get_gender(child) == target_gender:
                        spouse_candidate = child
                        break

            if spouse_candidate is not None:
                h_sub = m if m_gender == 'M' else spouse_candidate
                w_sub = spouse_candidate if m_gender == 'M' else m
                last_child_inlaw_unit = {'husband': h_sub, 'wife': w_sub, 'children': [], 'anchor': m, 'type': 'sub'}
                units.append(last_child_inlaw_unit)
                flags.append({'person': m, 'reason': f"Paired as in-law spouse in sub-family (rel: {rel.title()})",
                              'confidence': 0.8})
            else:
                h_sub = m if m_gender == 'M' else None
                w_sub = None if m_gender == 'M' else m
                last_child_inlaw_unit = {'husband': h_sub, 'wife': w_sub, 'children': [], 'anchor': m, 'type': 'sub'}
                units.append(last_child_inlaw_unit)
                flags.append(
                    {'person': m, 'reason': f"In-law listed without matching spouse child (rel: {rel.title()})",
                     'confidence': 0.5})

        elif rel in REL_GRANDCHILD and current_unit is not None:
            if last_child_inlaw_unit is not None:
                last_children = last_child_inlaw_unit.get('children')
                if isinstance(last_children, list):
                    last_children.append(m)
            else:
                curr_children = current_unit.get('children')
                if isinstance(curr_children, list):
                    curr_children.append(m)
                flags.append({'person': m, 'reason': f"Grandchild attached to head family unit (rel: {rel.title()})",
                              'confidence': 0.6})

        elif rel in REL_SIBLING and primary_head is not None and head_parents_unit is not None:
            head_children = head_parents_unit.get('children')
            if isinstance(head_children, list):
                head_children.append(m)

        elif rel in REL_PARENT and primary_head is not None and head_parents_unit is not None:
            if get_gender(m) == 'F':
                head_parents_unit['wife'] = m
            else:
                head_parents_unit['husband'] = m

        elif rel in REL_INLAW_SIBLING and primary_spouse is not None and spouse_parents_unit is not None:
            spouse_children = spouse_parents_unit.get('children')
            if isinstance(spouse_children, list):
                spouse_children.append(m)

        elif rel in REL_INLAW_PARENT and primary_spouse is not None and spouse_parents_unit is not None:
            if get_gender(m) == 'F':
                spouse_parents_unit['wife'] = m
            else:
                spouse_parents_unit['husband'] = m

        elif rel in REL_NIBLING and current_unit is not None:
            curr_children = current_unit.get('children')
            if isinstance(curr_children, list):
                curr_children.append(m)
            flags.append({'person': m, 'reason': f"Niece/Nephew attached to household unit (rel: {rel.title()})",
                          'confidence': 0.5})

        elif rel:
            unrelated.append(m)
            flags.append({'person': m,
                          'reason': f"Stated relationship to head: {rel.title()} -- review for correct "
                                    f"family placement",
                          'confidence': 0.5})
        else:
            unrelated.append(m)
            flags.append({'person': m, 'reason': "No relationship-to-head recorded -- review household placement",
                          'confidence': 0.2})

    append_unit_if_not_empty(units, current_unit)
    append_unit_if_not_empty(units, head_parents_unit)
    append_unit_if_not_empty(units, spouse_parents_unit)

    # Hook the resolution pass into the final return
    return resolve_cross_family_links(units, unrelated, flags)


# ==========================================
# CENSUS FLAVOR: GEDCOM EMISSION
# ==========================================
def get_row_val(r: pd.Series, cols: List[str], default: str) -> str:
    if default:
        return default
    for c in cols:
        if c in r.index:
            val = clean_val(r.get(c))
            if val:
                return val
    return ""


def build_census_citation(row: pd.Series, rec_id: str, m_id: str, real_page: str, target_software: str,
                          row_town: str, row_county: str, row_state: str, row_roll: str, row_film: str,
                          row_ed: str = "") -> List[str]:
    giv = clean_val(row.get('Given Name'))
    sur = clean_val(row.get('Surname'))
    person_str = f"{giv} {sur}".strip()

    fam_num = get_row_val(row, ['Family Number', 'Family', 'Household Number', 'Household'], '')
    dwell_num = get_row_val(row, ['Dwelling Number', 'Dwelling', 'House Number'], '')
    # get_row_val treats a truthy `default` as an already-resolved override and never even
    # looks at the row (correct for global settings like TOWNSHIP that should win when set)
    # - but 'X' here is a last-resort filler, not an override, and being truthy meant it was
    # *always* returned without ever reading the row's real Line Number. Fixed by passing an
    # empty default (so the row is actually checked) and applying 'X' only if that comes
    # back empty too.
    line_num = get_row_val(row, ['Line Number', 'Line'], '') or 'X'

    # Present only on a merged Ancestry+FamilySearch record (see MergedCensus.py) - a
    # single-source run leaves these blank, so the extra tag/link below never appear.
    fsftid = get_row_val(row, ['FSFTID'], '')
    fs_url = get_row_val(row, ['FamilySearch_URL'], '')

    # The real link Voyageur.js scraped directly off the page - prefer it over
    # reconstructing one from APID_DB/rec_id, since the reconstruction assumes rec_id is a
    # genuine Ancestry pid (it's a synthetic ANCESTRY_START_RECORD_ID-based one for a row
    # that never got a real pid), which would otherwise produce a URL to nothing.
    ancestry_url = get_row_val(row, ['Extracted_URL'], '') or \
        f"https://www.ancestry.com/search/collections/{APID_DB}/records/{rec_id}"

    cit = [f"2 SOUR @S_{CENSUS_YEAR}_CENSUS@"]

    caps = CENSUS_TEMPLATES[get_census_template_id(CENSUS_YEAR)]
    ed_suffix = f", ED {row_ed}" if (caps["ed"] and row_ed) else ""

    if target_software == "RM":
        page_parts = [row_roll, f"{row_town}{ed_suffix}", real_page]
        tmplt_fields = ["4 FIELD", "5 NAME RollNo", f"5 VALUE {row_roll}",
                        "4 FIELD", "5 NAME CivilDivision", f"5 VALUE {row_town}"]
        if caps["ed"]:
            tmplt_fields += ["4 FIELD", "5 NAME ED", f"5 VALUE {row_ed}"]
        tmplt_fields += ["4 FIELD", "5 NAME PageID", f"5 VALUE {real_page}"]
        if caps["household"]:
            page_parts.append(fam_num)
            tmplt_fields += ["4 FIELD", "5 NAME HouseholdID", f"5 VALUE {fam_num}"]
        page_parts.append(person_str)
        tmplt_fields += ["4 FIELD", "5 NAME PersonOfInterest", f"5 VALUE {person_str}"]

        collection_title = COLLECTION_NAME or f'{CENSUS_YEAR} United States Federal Census'
        cit.extend([f"3 PAGE {'; '.join(page_parts)}", "3 _TMPLT"] + tmplt_fields + [
                    f"3 NAME {sur}, {giv}: Page: {real_page}, Line: {line_num}, "
                    f"Dwelling: {dwell_num}, Family: {fam_num}",
                    "3 DATA", f"3 _APID 1,{APID_DB}::{rec_id}", "3 _WEBTAG",
                    f"4 NAME Anc- {collection_title}",
                    f"4 URL {ancestry_url}"])
        if fsftid:
            cit.append(f"3 _FSFTID {fsftid}")
        if fs_url:
            cit.extend(["3 _WEBTAG",
                        f"4 NAME FS- {collection_title}",
                        f"4 URL {fs_url}"])
        cit.extend(["3 QUAY 3", "3 _QUAL", "4 _SOUR O", "4 _INFO P", "4 _EVID D"])
        cit.append(f"3 OBJE {m_id}")
    else:
        link_url = ancestry_url
        cit.extend(
            [f"3 PAGE {person_str}; p. {real_page}, dwell. {dwell_num}, fam. {fam_num}; {row_town}{ed_suffix}; "
             f"{row_county}; {row_state}; Roll {row_roll}; Film {row_film}",
                "3 QUAY 3", f"3 _APID 1,{APID_DB}::{rec_id}",
                f"3 _LINK {link_url}", f"3 NOTE {link_url}"])
        if fsftid:
            cit.append(f"3 _FSFTID {fsftid}")
        if fs_url:
            cit.extend([f"3 _LINK {fs_url}", f"3 NOTE {fs_url}"])
        cit.append(f"3 OBJE {m_id}")
    return cit


def get_census_notes(row: pd.Series) -> List[str]:
    note_cols = ['Quality', 'Real Estate Value', 'Personal Estate Value', 'Cannot Read, Write', 'Disability Condition',
                 'Deaf Dumb Blind Insane', 'Idiotic Pauper Convict']
    notes = [f"{c}: {clean_val(row[c])}" for c in note_cols if c in row and clean_val(row[c])]
    if CENSUS_YEAR == 1870:
        flags = {'Father Foreign Born': "Father of foreign birth.", 'Mother Foreign Born': "Mother of foreign birth.",
                 'Male Citizen Over 21': "Male citizen of the United States of 21 years of age and upwards.",
                 'Voting Rights Denied': "Male citizen of 21 years of age and upwards whose right to vote is "
                                         "denied or abridged on grounds other than rebellion or other crime."}
        notes.extend([msg for flag_col, msg in flags.items() if clean_val(row.get(flag_col))])
    return notes


CORE_COLUMNS = {'given name', 'surname', 'gender', 'sex', 'age', 'birth year', 'birth month', 'month of birth', 'page',
                'page_number', 'real page', 'real_page', 'family number', 'household number', 'family', 'household',
                'dwelling number', 'dwelling', 'line number', 'line', 'household_id', 'row_index_id', 'birth place',
                'birthplace', 'occupation', 'occupation category', 'industry', 'trade or profession', 'race', 'color',
                'attended school', 'highest grade of school completed', 'highest grade completed',
                'married within year', 'relationship to head', 'relationship', 'relation to head', 'relation',
                'quality', 'real estate value', 'personal estate value', 'cannot read, write', 'disability condition',
                'deaf dumb blind insane', 'idiotic pauper convict', 'father foreign born', 'mother foreign born',
                'male citizen over 21', 'voting rights denied', 'image_id', 'country', 'state', 'county', 'city',
                'place_details', 'roll', 'film', 'enumeration_district', 'apid_db', 'extracted_url', 'pid', 'street',
                'street address', 'address', 'house number', 'publisher', 'publisher location',
                'repository', 'repository location', 'fsftid', 'familysearch_url', 'alternatenames',
                'alternatebirthplaces', '_mergereviewreason'}

DYNAMIC_EVENT_RULES = [(re.compile(r'immigrat', re.I), 'IMMI'),
                       (re.compile(r'year of naturali[sz]', re.I), 'NATU_DATE'),
                       (re.compile(r'naturali[sz]ation status|^naturali[sz]', re.I), 'NATU'),
                       (re.compile(r'veteran|military|regiment|survivor of union|confederate|which war|pension', re.I),
                        'MILITARY'), (re.compile(r'residence', re.I), 'RESI'),
                       (re.compile(r'religio|church affiliation', re.I), 'RELI'),
                       (re.compile(r'maiden name', re.I), 'MAIDEN')]

PRE1850_ALLOWED_TAGS = {'MILITARY'}
MONTH_ABBR = {'1': 'JAN', '01': 'JAN', 'JAN': 'JAN', 'JANUARY': 'JAN', '2': 'FEB', '02': 'FEB', 'FEB': 'FEB',
              'FEBRUARY': 'FEB', '3': 'MAR', '03': 'MAR', 'MAR': 'MAR', 'MARCH': 'MAR', '4': 'APR', '04': 'APR',
              'APR': 'APR', 'APRIL': 'APR', '5': 'MAY', '05': 'MAY', 'MAY': 'MAY', '6': 'JUN', '06': 'JUN',
              'JUN': 'JUN', 'JUNE': 'JUN', '7': 'JUL', '07': 'JUL', 'JUL': 'JUL', 'JULY': 'JUL', '8': 'AUG',
              '08': 'AUG', 'AUG': 'AUG', 'AUGUST': 'AUG', '9': 'SEP', '09': 'SEP', 'SEP': 'SEP', 'SEPT': 'SEP',
              'SEPTEMBER': 'SEP', '10': 'OCT', 'OCT': 'OCT', 'OCTOBER': 'OCT', '11': 'NOV', 'NOV': 'NOV',
              'NOVEMBER': 'NOV', '12': 'DEC', 'DEC': 'DEC', 'DECEMBER': 'DEC'}
RESIDENCE_YEAR_PATTERN = re.compile(r'(1[89]\d{2})')
RESIDENCE_RELATIVE_PATTERN = re.compile(r'(\d+)\s*year', re.I)


def get_occupation_value(row: pd.Series) -> str:
    parts = [clean_val(row[c]) for c in ('Occupation', 'Occupation Category', 'Trade or Profession') if
             c in row and clean_val(row[c])]
    if industry := clean_val(row.get('Industry', '')):
        parts.append(f"({industry})")
    return " ".join(parts).strip()


def get_education_value(row: pd.Series) -> Optional[str]:
    grade = clean_val(row.get('Highest Grade of School Completed', row.get('Highest Grade Completed', '')))
    if grade:
        return grade
    if clean_val(row.get('Attended School')):
        return ''
    return None


def get_birth_date(row: pd.Series, birth_year: float) -> str:
    month_str = get_row_val(row, ['Birth Month', 'Birth month', 'Month of Birth'], '')
    abbr = MONTH_ABBR.get(month_str.upper())
    return f"{abbr} {int(birth_year)}" if abbr else str(int(birth_year))


def build_residence_event(col_name: str, val: str, cit: List[str], loc: str, street: str = "") -> List[str]:
    year_match = RESIDENCE_YEAR_PATTERN.search(col_name)
    if year_match:
        date_val = year_match.group(1)
    else:
        rel_match = RESIDENCE_RELATIVE_PATTERN.search(col_name)
        date_val = str(CENSUS_YEAR - int(rel_match.group(1))) if rel_match else str(CENSUS_YEAR)

    evt = ["1 RESI", f"2 DATE {date_val}", f"2 PLAC {val or loc}"]
    if street:
        evt.append(f"2 ADDR {street}")
    evt.extend(["2 _PROOF proven"] + cit)
    return evt


def build_dynamic_events_and_notes(row: pd.Series, cit: List[str], giv: str, columns: List[str], loc: str,
                                   street: str) -> Tuple[List[str], List[str]]:
    events: List[str] = []
    notes: List[str] = []
    for col_str in columns:
        if col_str.strip().lower() in CORE_COLUMNS:
            continue
        if is_relationship_column(col_str):
            continue
        val = clean_val(row.get(col_str))
        if not val:
            continue
        tag = next((t for pat, t in DYNAMIC_EVENT_RULES if pat.search(col_str)), None)
        if CENSUS_ERA == 'pre1850' and tag not in PRE1850_ALLOWED_TAGS:
            tag = None

        if tag == 'IMMI':
            year_match = re.search(r'\d{4}', val)
            events.extend(["1 IMMI", f"2 DATE {year_match.group(0) if year_match else val}", "2 _PROOF proven"] + cit)
        elif tag == 'NATU_DATE':
            year_match = re.search(r'\d{4}', val)
            events.extend(["1 NATU", f"2 DATE {year_match.group(0) if year_match else val}", "2 _PROOF proven"] + cit)
        elif tag == 'NATU':
            events.extend(["1 NATU", f"2 DATE {CENSUS_YEAR}", f"2 NOTE {col_str}: {val}", "2 _PROOF proven"] + cit)
        elif tag == 'MILITARY':
            events.extend(["1 EVEN", "2 TYPE Military Service", f"2 DATE {CENSUS_YEAR}", f"2 NOTE {col_str}: {val}",
                           "2 _PROOF proven"] + cit)
        elif tag == 'RESI':
            events.extend(build_residence_event(col_str, val, cit, loc, street))
        elif tag == 'RELI':
            events.extend([f"1 RELI {val}", "2 _PROOF proven"] + cit)
        elif tag == 'MAIDEN':
            events.extend([f"1 NAME {giv} /{val}/", "2 TYPE maiden"] + cit)
            notes.append(f"Maiden name recorded ({val}) -- review for parental FAMC link")
        else:
            notes.append(f"{col_str}: {val}")
    return events, notes


def build_census_task(rec_id: str, giv: str, sur: str, record_label: str, reasons: List[Tuple[str, float]],
                      citation_block: List[str], media_path: Union[str, Path], media_title: str,
                      target_software: str) -> Tuple[List[str], str]:
    task_id = f"@T{rec_id}@"
    summary = "; ".join(r for r, _ in reasons)
    folder_raw = reasons[0][0]
    folder_name = re.sub(r"\(age \d+\)", "", folder_raw)
    folder_name = re.sub(r"of \w+", "", folder_name).replace("--", ":")
    folder_name = re.sub(r"\s+", " ", folder_name).strip(" :")
    min_c = min((c for _, c in reasons), default=1.0)
    priority = 1 if min_c < 0.3 else (2 if min_c < REVIEW_THRESHOLD else 3)

    task_citation = []
    if citation_block and citation_block[0].startswith("2 SOUR"):
        task_citation = dedent_citation_lines(citation_block)

    link_url = f"https://www.ancestry.com/search/collections/{APID_DB}/records/{rec_id}"
    weblink = weblink_lines(link_url, COLLECTION_NAME or f'{CENSUS_YEAR} United States Federal Census',
                            target_software)

    task_records = [f"0 {task_id} _TASK",
                    f"1 DESC {sur or '[No Surname]'}, {giv or '[No Given Name]'} ({record_label}): {summary}",
                    f"1 REFN {rec_id}", f"1 _LINK @I{rec_id}@", "1 TYPE 2", f"1 DATE {CURRENT_DATE}",
                    f"1 _LDATE {CURRENT_DATE}", f"1 NOTE {summary}", "1 STAT NEW", f"1 PRTY {priority}",
                    f"1 _COLOR {REVIEW_COLOR}"] + weblink + task_citation + [
        "1 OBJE", f"2 FILE {media_path}", "2 FORM jpg", f"2 TITL {media_title}", "2 _TYPE PHOTO"]
    return task_records, folder_name


def get_census_sources(target_software: str) -> List[str]:
    tid = get_census_template_id(CENSUS_YEAR)
    caps = CENSUS_TEMPLATES[tid]
    ed_frag = f", ED {ENUMERATION_DISTRICT}" if (caps["ed"] and ENUMERATION_DISTRICT) else ""
    schedule_frag = ", Population" if caps["schedule"] else ""

    if target_software == "RM":
        tmplt_fields = ["2 FIELD", "3 NAME CensusID", f"3 VALUE {CENSUS_YEAR} U.S. Federal Census",
                        "2 FIELD", "3 NAME Jurisdiction", f"3 VALUE {COUNTY}, {STATE}"]
        if caps["schedule"]:
            tmplt_fields += ["2 FIELD", "3 NAME Schedule", "3 VALUE Population"]
        if caps["ed"]:
            tmplt_fields += ["2 FIELD", "3 NAME ED", f"3 VALUE {ENUMERATION_DISTRICT}"]
        tmplt_fields += ["2 FIELD", "3 NAME PublishLoc", f"3 VALUE {PUB_LOC}",
                         "2 FIELD", "3 NAME Publisher", f"3 VALUE {PUBLISHER}",
                         "2 FIELD", "3 NAME PubType", "3 VALUE on-line image",
                         "2 FIELD", "3 NAME FilmID", f"3 VALUE {FILM_NUMBER}"]

        return [f"0 @S_{CENSUS_YEAR}_CENSUS@ SOUR", f"1 ABBR {CENSUS_YEAR} U.S. Federal Census",
                f"1 TITL , {CENSUS_YEAR} U.S. Federal Census, {COUNTY}, {STATE}{schedule_frag}{ed_frag}, ; "
                f"on-line image {FILM_NUMBER}, .",
                f"1 _SUBQ , {CENSUS_YEAR} U.S. Federal Census, {COUNTY}, {STATE}{schedule_frag}{ed_frag}, .",
                f"1 _BIBL {COUNTY}, {STATE}, {CENSUS_YEAR} U.S. Federal Census{schedule_frag}{ed_frag}. on-line "
                f"image {FILM_NUMBER}. {PUB_LOC}: {PUBLISHER}.",
                "1 REPO @R1@", "1 _TMPLT", f"2 TID {tid}"] + tmplt_fields + [
                f"0 {ROOT_SOURCE_ID} SOUR", f"1 TITL {ORG_NAME}", "1 AUTH",
                f"1 PUBL Researcher: {RESEARCHER}."] + weblink_lines(
            MGS_GROUP_URL, "Facebook Group", "RM") + weblink_lines(ANCESTRY_GROUP_URL, "Ancestry Group", "RM")
    else:
        return [f"0 @S_{CENSUS_YEAR}_CENSUS@ SOUR", f"1 TITL {CENSUS_YEAR} U.S. Federal Census",
                f"1 PUBL {PUB_LOC}: {PUBLISHER}", "1 REPO @R1@", f"1 _APID 1,{APID_DB}::0",
                f"0 {ROOT_SOURCE_ID} SOUR", f"1 TITL {ORG_NAME}", f"1 AUTH Research conducted by {RESEARCHER}.",
                f"1 _LINK {MGS_GROUP_URL}", "2 NAME Facebook Group", f"1 _LINK {ANCESTRY_GROUP_URL}",
                "2 NAME Ancestry Group"]


def get_location_string(row: pd.Series) -> str:
    # STATE/COUNTY/TOWNSHIP are global settings already resolved once for the whole gather
    # (run_census_flavor fills them from the JSON's own modal value if left blank) - correct
    # as a last-resort filler, but passing them directly as get_row_val's truthy `default`
    # meant the row's own per-page value was *never* read even when present, collapsing a
    # gather spanning multiple townships/counties (a real scenario - Voyageur.js re-scrapes
    # location per page specifically because it can change mid-roll) down to one value.
    row_state = get_row_val(row, ['State', 'State/Province'], '') or STATE
    row_county = get_row_val(row, ['County', 'Parish'], '') or COUNTY
    row_town = get_row_val(row, ['City', 'Township', 'Town', 'Civil Division', 'Ward'], '') or TOWNSHIP
    # Same fix as line_num above: 'USA' is a last-resort filler, not an override, so it must
    # not be passed as get_row_val's truthy `default` - that skipped reading the row's real
    # Country entirely, which broke Canadian census rows (Voyageur.js sets Country to
    # "Canada" there) into always citing "USA" regardless.
    row_country = get_row_val(row, ['Country'], '') or 'USA'

    # We filter none to prune trailing/leading commas, and empty items.
    return ", ".join(filter(None, [row_town, row_county, row_state, row_country]))


def split_full_name(full_name: str) -> Tuple[str, str]:
    """Splits a combined "Given Surname" string - the shape Ancestry's per-person Detail
    panel gives for a crowdsourced alternate-name submission, unlike the index table's
    own separate Given Name/Surname columns - into given/surname parts. Uses the last
    whitespace-separated token as the surname."""
    parts = full_name.strip().split()
    if len(parts) < 2:
        return full_name.strip(), ""
    return " ".join(parts[:-1]), parts[-1]


def parse_alternate_entries(row: pd.Series, column: str) -> List[dict]:
    """Alternate name/place submissions are carried through the JSON pipeline as a list
    of {value} dicts, JSON-encoded into a single DataFrame cell by load_census_dataframe
    (a plain column can't hold a list directly)."""
    raw = row.get(column)
    if not raw or (isinstance(raw, float) and pd.isna(raw)):
        return []
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []
    except (TypeError, ValueError):
        return []


def build_alternate_name_lines(alt_entries: List[dict], cit: List[str]) -> List[str]:
    """Ancestry's own per-person Detail panel surfaces crowdsourced alternate-reading
    submissions (bracketed values) alongside its own primary indexed reading. Kept as
    plain NAME facts - no /TYPE switch, not marked aka - since these are read the same way
    as the primary name, just unconfirmed rather than official. Proof status is "proposed"
    rather than "proven" (see get_proof_status), and each carries the same per-person
    census citation as every other tagged fact. Submitter attribution isn't captured -
    reading it required clicking through to a popup that had no reliable close control and
    froze a real gather (see Voyageur.js's readAlternateEntries)."""
    lines: List[str] = []
    for entry in alt_entries:
        value = clean_val(entry.get('value'))
        if not value:
            continue
        alt_giv, alt_sur = split_full_name(value)
        lines.append(f"1 NAME {alt_giv} /{alt_sur}/")
        lines.append("2 _PROOF proposed")
        lines.extend(cit)
    return lines


def build_alternate_birth_lines(alt_entries: List[dict], birth_year: Optional[float], row: pd.Series,
                                cit: List[str]) -> List[str]:
    """Same crowdsourced-alternate handling as build_alternate_name_lines, but for
    birthplace: GEDCOM's BIRT event only supports one PLAC, so each alternate reading
    becomes its own additional BIRT event (same birth date as the primary event, the
    alternate place substituted in for PLAC) rather than a second value on one event."""
    lines: List[str] = []
    for entry in alt_entries:
        value = clean_val(entry.get('value'))
        if not value:
            continue
        lines.append("1 BIRT")
        if birth_year is not None:
            lines.append(f"2 DATE {get_birth_date(row, birth_year)}")
        lines.append(f"2 PLAC {value}")
        lines.append("2 _PROOF proposed")
        lines.extend(cit)
    return lines


def build_gedcom_from_census(df_in: pd.DataFrame, target_software: str) -> None:
    df = df_in.copy()

    # Dynamically search for the correct Household/Family column based on the JSON's columns
    fam_col = next((c for c in ['Family Number', 'Family', 'Household Number', 'Household'] if c in df.columns), None)
    if not fam_col:
        fam_col = next((c for c in ['Dwelling Number', 'Dwelling', 'House Number'] if c in df.columns), None)

    if fam_col:
        df['Household_ID'] = (df[fam_col] != df[fam_col].shift()).cumsum()
    else:
        # Ultimate fallback if no family numbers exist in the census (treat every row individually)
        df['Household_ID'] = range(len(df))

    str_columns: List[str] = list(df.columns.astype(str))

    ged = ["0 HEAD", f"1 SOUR {SOFTWARE_NAME}", f"2 VERS {SOFTWARE_VERS}", f"2 CORP {ORG_NAME}", "1 GEDC",
           "2 VERS 5.5.1", "2 FORM LINEAGE-LINKED", "1 CHAR UTF-8", f"1 DATE {CURRENT_DATE}",
           f"1 COPR Copyright {COPYRIGHT_START}", "1 SUBM @SUB1@"]
    if GEDCOM_NOTE:
        ged.append(f"1 NOTE {GEDCOM_NOTE}")
        if GEDCOM_CONC:
            ged.append(f"2 CONC {GEDCOM_CONC}")

    fam_links: Dict[Hashable, List[str]] = {i: [] for i in df.index}
    fam_blocks: List[str] = []
    used_fam_ids = set()
    media_dict: Dict[str, Dict[str, Union[str, Path]]] = {}
    task_blocks: List[str] = []
    folder_tasks: Dict[str, List[str]] = {}
    review_flags: Dict[Hashable, List[Tuple[str, float]]] = {}

    for _, group in df.groupby('Household_ID'):
        units: List[HouseholdUnit]
        unrelated: List[pd.Series]
        flags: List[FlagRecord]
        if CENSUS_ERA == 'pre1850':
            units, unrelated, flags = [], [], []
        elif CENSUS_ERA == 'heuristic':
            units, unrelated, flags = parse_household(group)
        else:
            units, unrelated, flags = parse_household_relational(group)

        for flag in flags:
            flag_person = flag.get('person')
            if isinstance(flag_person, pd.Series):
                review_flags.setdefault(flag_person.name, []).append(
                    (str(flag.get('reason', '')), float(flag.get('confidence', 0.0))))

        for person in unrelated:
            review_flags.setdefault(person.name, [])

        for u in units:
            h = u.get('husband')
            w = u.get('wife')
            children_list = u.get('children', [])
            anc = u.get('anchor')
            u_type = u.get('type', 'main')

            if h is None and w is None and not children_list:
                continue

            anchor_row = h if isinstance(h, pd.Series) else (w if isinstance(w, pd.Series) else (
                anc if isinstance(anc, pd.Series) else (children_list[0] if children_list else None)))
            if not isinstance(anchor_row, pd.Series):
                continue

            anchor_pid = clean_val(anchor_row.get('PID')) or str(ANCESTRY_START_RECORD_ID + cast(int, anchor_row.name))

            base_f_id = f"@F{anchor_pid}_{u_type}@" if u_type != 'main' else f"@F{anchor_pid}@"
            f_id = base_f_id
            counter = 1
            while f_id in used_fam_ids:
                f_id = f"{base_f_id[:-1]}_{counter}@"
                counter += 1

            used_fam_ids.add(f_id)

            fam_blocks.append(f"0 {f_id} FAM")

            if isinstance(h, pd.Series):
                h_idx = clean_val(h.get('PID')) or str(ANCESTRY_START_RECORD_ID + cast(int, h.name))
                fam_blocks.append(f"1 HUSB @I{h_idx}@")
                fam_links[h.name].append(f"1 FAMS {f_id}")
            if isinstance(w, pd.Series):
                w_idx = clean_val(w.get('PID')) or str(ANCESTRY_START_RECORD_ID + cast(int, w.name))
                fam_blocks.append(f"1 WIFE @I{w_idx}@")
                fam_links[w.name].append(f"1 FAMS {f_id}")
            if isinstance(children_list, list):
                for child in children_list:
                    if isinstance(child, pd.Series):
                        c_idx = clean_val(child.get('PID')) or str(ANCESTRY_START_RECORD_ID + cast(int, child.name))
                        fam_blocks.append(f"1 CHIL @I{c_idx}@")
                        fam_links[child.name].append(f"1 FAMC {f_id}")

            if (isinstance(h, pd.Series) and pd.notna(h.get('Married within Year'))) or (
                    isinstance(w, pd.Series) and pd.notna(w.get('Married within Year'))):
                fam_blocks.extend(["1 MARR", f"2 DATE EST {CENSUS_YEAR}", "2 _PROOF proven"])

    current_line_page_key = None
    synthesized_line_num = 0
    for idx, row in df.iterrows():
        # Voyageur.js already synthesizes a Line Number when a collection's own index never
        # exposes one, but Archivist should not depend on that alone - JSON gathered by an
        # older script version, or a row whose Line Number cell is simply blank, would
        # otherwise cite a static "Line: X" filler forever (confirmed live). Mirrors the
        # same convention: sequential, 1-based, restarting at 1 on every new page (grouped
        # by the page metadata's own Page_Number, broadcast onto every person on that page
        # by load_census_dataframe).
        page_key = clean_val(row.get('Page_Number', ''))
        if page_key != current_line_page_key:
            current_line_page_key = page_key
            synthesized_line_num = 0
        synthesized_line_num += 1
        if not clean_val(row.get('Line Number', row.get('Line', ''))):
            row['Line Number'] = str(synthesized_line_num)

        row_pid = clean_val(row.get('PID', row.get('pid', '')))
        rec_id = row_pid if row_pid else str(ANCESTRY_START_RECORD_ID + cast(int, idx))
        giv = clean_val(row.get('Given Name'))
        sur = clean_val(row.get('Surname'))
        gen = get_gender(row)

        row_loc = get_location_string(row)

        # Extracted here so they're available for the citation block below. Global settings
        # (STATE/COUNTY/TOWNSHIP/ROLL_NUMBER/FILM_NUMBER/ENUMERATION_DISTRICT) are only a
        # last-resort filler here, not an override - get_row_val's truthy `default` used to
        # skip reading the row entirely, which collapsed per-page roll/ED/location variation
        # across a multi-page gather down to a single value (see get_location_string above).
        row_state = get_row_val(row, ['State', 'State/Province'], '') or STATE
        row_county = get_row_val(row, ['County', 'Parish'], '') or COUNTY
        row_town = get_row_val(row, ['City', 'Township', 'Town', 'Civil Division', 'Ward'], '') or TOWNSHIP
        row_street = get_row_val(row, ['Street', 'Street Address', 'Address', 'House Number'], '')

        row_roll = get_row_val(row, ['Roll', 'Roll Number', 'NARA Roll'], '') or ROLL_NUMBER
        row_film = get_row_val(row, ['Film', 'FHL Film Number', 'Microfilm'], '') or FILM_NUMBER
        row_ed = get_row_val(row, ['Enumeration District', 'Enumeration_District', 'ED'], '') or ENUMERATION_DISTRICT

        page = get_row_val(row, ['Page', 'Page_Number', 'Page Number'], '')
        real_page = get_row_val(row, ['Real Page', 'Real_Page', 'Page', 'Page_Number'], '')

        image_id_val = clean_val(row.get('Image_ID', ''))
        if not image_id_val:
            image_id_val = f"{BASE_ID}_{page.zfill(5)}"

        m_id = f"@M{image_id_val}@"
        image_name = image_id_val

        if image_name not in media_dict:
            img_path = Path(str(IMAGE_DIR)) / f"{image_name}.{IMAGE_EXTENSION}"
            media_dict[image_name] = {'id': m_id, 'img': img_path,
                                      'title': f"{CENSUS_YEAR} Census, {row_county}, Image {image_name}"}

        cit = build_census_citation(row, rec_id, m_id, real_page, target_software, row_town, row_county, row_state,
                                    row_roll, row_film, row_ed)

        alt_names = parse_alternate_entries(row, 'AlternateNames')
        ged.extend(
            [f"0 @I{rec_id}@ INDI", f"1 REFN {rec_id}", f"1 NAME {giv} /{sur}/"] + cit +
            build_alternate_name_lines(alt_names, cit) +
            [f"1 SEX {gen}", f"1 SOUR {ROOT_SOURCE_ID}", f"2 NAME Researcher: {RESEARCHER}",
             f"2 _TITL Researcher: {RESEARCHER}"]
        )

        if person_flags := review_flags.get(idx, []):
            fam_lbl_num = get_row_val(row, ['Family Number', 'Family', 'Household Number', 'Household'], '')
            lbl = f"{CENSUS_YEAR}, Fam {fam_lbl_num}, p.{real_page}"
            task_records, folder = build_census_task(rec_id, giv, sur, lbl, person_flags, cit,
                                                     media_dict[image_name]['img'],
                                                     str(media_dict[image_name]['title']), target_software)
            task_blocks.extend(task_records)
            folder_tasks.setdefault(folder, []).append(f"1 _TASK @T{rec_id}@")
            ged.extend([f"1 _TASK @T{rec_id}@", f"1 _COLOR {REVIEW_COLOR}"])

        b_yr = row.get('Birth Year')
        age = row.get('Age')
        birth_year = None
        if pd.notna(b_yr):
            try:
                birth_year = float(b_yr)
            except ValueError:
                pass
        elif pd.notna(age):
            try:
                birth_year = float(CENSUS_YEAR) - float(age)
            except ValueError:
                pass

        birth_place = clean_val(row.get('Birth Place', row.get('Birthplace', '')))

        if birth_year is not None or birth_place:
            ged.append("1 BIRT")
            if birth_year is not None:
                ged.append(f"2 DATE {get_birth_date(row, birth_year)}")
            if birth_place:
                ged.append(f"2 PLAC {birth_place}")
            ged.extend(cit)

        alt_birth_places = parse_alternate_entries(row, 'AlternateBirthPlaces')
        ged.extend(build_alternate_birth_lines(alt_birth_places, birth_year, row, cit))

        if occ := get_occupation_value(row):
            ged.extend([f"1 OCCU {occ}", f"2 DATE {CENSUS_YEAR}", f"2 PLAC {row_loc}", "2 _PROOF proven"] + cit)
        if race := clean_val(row.get('Race', row.get('Color', ''))):
            ged.extend([f"1 FACT {race}", "2 TYPE Race", f"2 DATE {CENSUS_YEAR}", "2 _PROOF proven"] + cit)
        edu_val = get_education_value(row)
        if edu_val is not None:
            ged.extend(["1 EDUC" + (f" {edu_val}" if edu_val else ""), f"2 DATE {CENSUS_YEAR}", f"2 PLAC {row_loc}",
                        "2 _PROOF proven"] + cit)

        dyn_events, dyn_notes = build_dynamic_events_and_notes(row, cit, giv, str_columns, row_loc, row_street)
        ged.extend(dyn_events)

        cens_evt = ["1 CENS", f"2 DATE {CENSUS_YEAR}", f"2 PLAC {row_loc}"]
        if row_street:
            cens_evt.append(f"2 ADDR {row_street}")
        cens_evt.extend(["2 _PROOF proven"] + cit)
        ged.extend(cens_evt)

        if notes := (get_census_notes(row) + dyn_notes):
            ged.append(f"2 NOTE {' | '.join(notes)}")
        ged.extend(fam_links.get(idx, []))

    ged.extend(fam_blocks)
    ged.extend(task_blocks)

    for folder, tasks in folder_tasks.items():
        ged.append(f"0 _FOLDER {folder}")
        ged.extend(tasks)

    ged.extend(get_census_sources(target_software))
    for m in media_dict.values():
        ged.extend([f"0 {m['id']} OBJE", f"1 FILE {m['img']}", f"2 FORM {FORM_TYPE}", f"1 TITL {m['title']}"])

    if target_software == "RM":
        ged.extend(
            ["0 _EVDEF Race", "1 TYPE P", "1 TITL Race", "1 ABBR Race", "1 SENT [person] was of [Desc] ethnicity.",
             "1 PLAC N", "1 DATE Y", "1 DESC Y", "0 _EVDEF EDUC", "1 TYPE P", "1 TITL Education", "1 ABBR Education",
             "1 SENT [person] was being educated < [Desc]>< [Date]>< [PlaceDetails]>< [Place].", "1 PLAC Y", "1 DATE Y",
             "1 DESC Y", "0 _EVDEF Military Service", "1 TYPE P", "1 TITL Military Service", "1 ABBR Mil. Service",
             "1 SENT [person] had military service.< [Desc]>< [Date]>.", "1 PLAC N", "1 DATE Y", "1 DESC Y"])

    ged.extend(["0 @SUB1@ SUBM", f"1 NAME {RESEARCHER}", f"1 ADDR {SUBM_ADDRESS}", f"1 NOTE {ORG_NAME}", "0 @R1@ REPO",
                f"1 NAME {REPOSITORY}", f"1 ADDR {REPOSITORY_LOC}", f"1 CALN {CALL_NUMBER}", "2 MEDI Electronic",
                f"2 _URL {COLLECTION_URL}", "0 TRLR"])

    output_path = resolve_gedcom_output_path(target_software)
    output_path.write_text("\n".join(ged), encoding="utf-8")
    print(f"Success! {len(df)} individuals converted and saved to {output_path}")


def get_json_fallback(df: pd.DataFrame, columns: List[str], current: str) -> str:
    if current and str(current).strip() and str(current).strip() != '0':
        return str(current)
    for c in columns:
        if c in df.columns:
            valid_vals = df[df[c].astype(str).str.strip() != ''][c]
            if not valid_vals.empty:
                modes = valid_vals.mode()
                if not modes.empty:
                    return clean_val(modes.iloc[0])
    return ""


def load_census_dataframe(data: dict) -> pd.DataFrame:
    """Flattens the nested {census_year, location, pages: [{..., people: [...]}]} shape
    (produced by Voyageur.js/FS.py/MergedCensus.py) into one row per person, broadcasting each page's
    metadata onto every person on that page, so the existing DataFrame-based household
    grouping keeps working unchanged."""
    rows = []
    for page in data.get('pages', []):
        page_meta = {
            'Page_Number': page.get('page_number', ''), 'Image_ID': page.get('image_id', ''),
            'Country': page.get('country', ''), 'State': page.get('state', ''),
            'County': page.get('county', ''), 'City': page.get('city', ''),
            'Place_Details': page.get('place_details', ''),
            'Enumeration_District': page.get('enumeration_district', ''),
            'Film': page.get('film_number', ''), 'Roll': page.get('roll_number', ''),
            'APID_DB': page.get('apid_db', ''),
            'Publisher': page.get('publisher', ''), 'Publisher Location': page.get('pub_loc', ''),
            'Repository': page.get('repository', ''), 'Repository Location': page.get('repository_loc', ''),
        }
        for person in page.get('people', []):
            row = dict(person.get('columns', {}))
            row.update(page_meta)
            row['PID'] = person.get('pid', '')
            row['Extracted_URL'] = person.get('extracted_url', '')
            row['FSFTID'] = person.get('fsftid', '')
            row['FamilySearch_URL'] = person.get('familysearch_url', '')
            # JSON-encoded since a DataFrame cell can't hold a list of {value} dicts
            # directly - see parse_alternate_entries.
            row['AlternateNames'] = json.dumps(person.get('alternate_names', []))
            row['AlternateBirthPlaces'] = json.dumps(person.get('alternate_birth_places', []))
            rows.append(row)
    df = pd.DataFrame(rows)
    for numeric_col in ['Age', 'Birth Year']:
        if numeric_col in df.columns:
            df[numeric_col] = pd.to_numeric(df[numeric_col], errors='coerce')
    return df


# Reverses Voyageur's field-map fact_type naming (Voyageur/field_maps/*.yaml) back into
# the column names build_dynamic_events_and_notes/get_occupation_value/get_education_value
# already key on (by exact name or by DYNAMIC_EVENT_RULES regex) - so a fact normalized at
# gather time renders exactly the way an old raw-column reading of the same data always
# did, without any of those functions needing to change.
FACT_TYPE_TO_COLUMN = {
    "Occupation": "Occupation", "Education": "Highest Grade Completed",
    "Immigration": "Immigration Year", "Naturalization": "Naturalization Status",
    "Military": "Military Service", "Residence": "Residence", "Religion": "Religion",
    "Property": "Real Estate Value", "Miscellaneous": "Miscellaneous Note",
}


def build_census_dataframe_from_unified(data: dict) -> Tuple[pd.DataFrame, str, str]:
    """Adapts the shared sheets[].records[].participants[] schema (as Voyageur's field-map
    normalization now produces for census gathers - see Voyageur/census_schema.py) into the
    same flat, old-column-named DataFrame shape load_census_dataframe has always produced,
    so every household-parsing/citation function below keeps working completely unchanged.
    This is the one place a census JSON's shared-schema shape is translated back into
    Archivist's own internal working shape; nothing downstream of this function needs to
    know the input was ever anything but that shape.

    Returns (dataframe, census_year_str, location_str) - the latter two replace what
    run_census_flavor used to read directly off the old top-level census_year/location
    keys, which the shared schema no longer carries at that level."""
    citation = data.get('citation', {}) or {}
    census_year_str = ""
    year_match = re.search(r'(\d{4})', data.get('record_type_name', '') or '')
    if year_match:
        census_year_str = year_match.group(1)

    location_str = ""
    rows = []
    fallback_family_counter = 0
    for sheet in data.get('sheets', []):
        doc_meta = sheet.get('document_metadata', {})
        for record in sheet.get('records', []):
            ts = record.get('type_specific_fields', {}) or {}
            if not location_str:
                location_str = ts.get('state', '') or doc_meta.get('source_location', '')

            fallback_family_counter += 1
            family_id = ts.get('family_number') or f"__record_{fallback_family_counter}"

            page_meta = {
                'Page_Number': sheet.get('page_id', ''), 'Image_ID': doc_meta.get('file_name', ''),
                'Country': ts.get('country', ''), 'State': ts.get('state', ''),
                'County': ts.get('county', ''), 'City': ts.get('city', ''),
                'Enumeration_District': ts.get('enumeration_district', ''),
                'Film': ts.get('film_number', ''), 'Roll': ts.get('roll_number', ''),
                'APID_DB': ts.get('apid_db', '') or citation.get('apid_db', ''),
                'Publisher': citation.get('publisher', ''), 'Publisher Location': citation.get('pub_loc', ''),
                'Repository': citation.get('repository', ''), 'Repository Location': citation.get('repository_loc', ''),
                'Family Number': family_id,
            }
            for p in record.get('participants', []):
                pts = p.get('type_specific_fields', {}) or {}
                row: Dict[str, Any] = dict(page_meta)
                row['Given Name'] = p.get('std_given', '') or ''
                row['Surname'] = p.get('std_surname', '') or ''
                row['Gender'] = p.get('sex', '') or ''
                if p.get('age'):
                    row['Age'] = p['age']
                if p.get('role_name'):
                    row['Relationship to Head'] = p['role_name']
                if pts.get('line_number'):
                    row['Line Number'] = pts['line_number']
                if p.get('birth_place'):
                    row['Birth Place'] = p['birth_place']
                if p.get('race'):
                    row['Race'] = p['race']
                for fact in p.get('facts', []) or []:
                    col = FACT_TYPE_TO_COLUMN.get(fact.get('fact_type', ''), fact.get('fact_type', ''))
                    row[col] = fact.get('value') or fact.get('date') or fact.get('place') or ''
                row['PID'] = pts.get('pid', '')
                row['Extracted_URL'] = pts.get('extracted_url', '')
                row['FSFTID'] = pts.get('fsftid', '')
                row['FamilySearch_URL'] = pts.get('familysearch_url', '')
                row['AlternateNames'] = json.dumps(p.get('alternate_names', []) or [])
                row['AlternateBirthPlaces'] = json.dumps(pts.get('alternate_birth_places', []) or [])
                if pts.get('merge_review_reason'):
                    row['_MergeReviewReason'] = pts['merge_review_reason']
                rows.append(row)

    df = pd.DataFrame(rows)
    for numeric_col in ['Age', 'Birth Year']:
        if numeric_col in df.columns:
            df[numeric_col] = pd.to_numeric(df[numeric_col], errors='coerce')
    return df, census_year_str, location_str


def run_census_flavor(data: dict) -> None:
    global STATE, COUNTY, TOWNSHIP, ENUMERATION_DISTRICT, ROLL_NUMBER, FILM_NUMBER, CENSUS_YEAR, CENSUS_ERA
    global APID_DB, COLLECTION_NAME, COLLECTION_URL, PUBLISHER, PUB_LOC, CALL_NUMBER, REPOSITORY_LOC, REPOSITORY
    global IMAGE_DIR

    # "pages" (Voyageur's original raw shape) is kept working for any already-gathered
    # file that predates the shared-schema normalization; "sheets" + a "Census_"-prefixed
    # record_type_name is what Voyageur now produces (see census_schema.py) - dispatched
    # on record_type_name, never guessed from shape alone, since the church flavor also
    # uses "sheets" now.
    if "pages" in data:
        census_df = load_census_dataframe(data)
        payload_year = clean_val(data.get('census_year'))
        payload_location = clean_val(data.get('location'))
    else:
        census_df, payload_year, payload_location = build_census_dataframe_from_unified(data)

    # Fallback to JSON columns if environment variables are missing or 0
    STATE = get_json_fallback(census_df, ['State', 'State/Province'], STATE)
    COUNTY = get_json_fallback(census_df, ['County', 'Parish'], COUNTY)
    TOWNSHIP = get_json_fallback(census_df, ['City', 'Township', 'Town', 'Civil Division', 'Ward'], TOWNSHIP)
    ENUMERATION_DISTRICT = get_json_fallback(census_df, ['Enumeration District', 'Enumeration_District', 'ED'],
                                             ENUMERATION_DISTRICT)
    ROLL_NUMBER = get_json_fallback(census_df, ['Roll', 'Roll Number', 'NARA Roll'], ROLL_NUMBER)
    FILM_NUMBER = get_json_fallback(census_df, ['Film', 'FHL Film Number', 'Microfilm'], FILM_NUMBER)

    # Extended fallbacks for metadata passed from the Extractor
    census_year_str = get_json_fallback(census_df, ['Census Year', 'Year', 'Census_Year'], str(CENSUS_YEAR))
    CENSUS_YEAR = int(census_year_str) if census_year_str and census_year_str.isdigit() else 0
    if not CENSUS_YEAR:
        CENSUS_YEAR = int(payload_year) if payload_year.isdigit() else 0
    CENSUS_ERA = get_census_era(CENSUS_YEAR)

    APID_DB = get_json_fallback(census_df, ['APID_DB', 'APID', 'Database ID', 'dbid'], APID_DB)
    COLLECTION_NAME = get_json_fallback(census_df, ['Collection Name', 'Collection_Name', 'Collection'],
                                        COLLECTION_NAME) or (f'{CENSUS_YEAR} United States Federal Census'
                                                             if CENSUS_YEAR else COLLECTION_NAME)
    COLLECTION_URL = get_json_fallback(census_df, ['Collection URL', 'Collection_URL', 'URL'], COLLECTION_URL) or (
        f"https://www.ancestry.com/search/collections/{APID_DB}" if APID_DB else COLLECTION_URL)
    PUBLISHER = get_json_fallback(census_df, ['Publisher', 'Census Publisher'], PUBLISHER)
    PUB_LOC = get_json_fallback(census_df, ['Publisher Location', 'Pub Loc'], PUB_LOC)
    REPOSITORY_LOC = get_json_fallback(census_df, ['Repository Location', 'Repo Loc'], REPOSITORY_LOC)
    REPOSITORY = get_json_fallback(census_df, ['Repository', 'Source Repository'], REPOSITORY)

    # A merged Ancestry+FamilySearch record (see Voyageur/MergedCensus.py) carries both an
    # apid and a fsftid. For those, cite the actual microfilm holder (NARA) rather than
    # either indexing site: Ancestry's own citation-scraping already parses NARA's
    # name/location into the publisher/pub_loc "original data" clause, so a merged run just
    # sources REPOSITORY from there instead of the repository/repository_loc "online host"
    # clause. Single-source runs (no FSFTID column, or all blank) are unaffected.
    if 'FSFTID' in census_df.columns and (census_df['FSFTID'].astype(str).str.strip() != '').any():
        REPOSITORY = PUBLISHER or REPOSITORY
        REPOSITORY_LOC = PUB_LOC or REPOSITORY_LOC
    # No JSON source for this: it's the archive's own catalog number for the collection, so
    # approximate it from the microfilm publication/roll Archivist already resolved.
    CALL_NUMBER = CALL_NUMBER or (f"{FILM_NUMBER}, roll {ROLL_NUMBER}".strip(", ")
                                  if (FILM_NUMBER or ROLL_NUMBER) else CALL_NUMBER)

    # Voyageur's Gather step (A.py) stages images into a nested {year} US Federal Census /
    # {location} subfolder rather than dumping every census collection's images into one flat
    # folder. Reconstruct that same subfolder from the JSON's own census_year/location fields
    # so Create works standalone from any complete JSON, without Gather having to hand off an
    # already-resolved path. Only overrides IMAGE_DIR when that nested folder actually exists,
    # so a flat/manually-organized IMAGE_DIR still works exactly as before.
    location_str = payload_location
    if IMAGE_DIR and CENSUS_YEAR and location_str:
        location_folder = re.sub(r'^USA\s*-\s*', '', location_str)
        nested_dir = Path(IMAGE_DIR) / f"{CENSUS_YEAR} US Federal Census" / location_folder
        if nested_dir.is_dir():
            IMAGE_DIR = str(nested_dir)

    for software in ["RM", "FTM"]:
        build_gedcom_from_census(census_df, software)


# ==========================================
# CHURCH FLAVOR: EXPLICIT ROLE PARSING
# ==========================================
def extract_volume(sheet: dict) -> str:
    """Aggressively extracts volume from metadata or sheet root, falling back to global CONFIG."""
    meta = sheet.get('document_metadata', {})
    if isinstance(meta, dict):
        for k, v in meta.items():
            if k.lower() == 'volume' and clean_val(v):
                return clean_val(v)

    for k, v in sheet.items():
        if k.lower() == 'volume' and clean_val(v):
            return clean_val(v)

    return clean_val(CHURCH_CONFIG.get('volume_num'))


def get_dynamic_source_id(vol_val: str) -> str:
    """Constructs a dynamic GEDCOM Source ID based on the volume."""
    base_id = re.sub(r'\D', '', f"{CHURCH_CONFIG.get('register_source_id', '1')}")
    if base_id.endswith('001') and len(base_id) > 1:
        base_id = base_id[:-3]
    vol_digits = re.sub(r'\D', '', f"{vol_val or '1'}") or '1'
    return f"@S{base_id or '1'}{vol_digits.zfill(3)}@"


def get_by_semantic(rec: dict, semantic: str) -> Optional[dict]:
    """Finds the first participant whose role_semantic matches (role_semantic is set by
    Paleographer's postprocess.derive_role_semantics from the active .pmt's roles table -
    Archivist never looks at role_name text or role_number digits to decide family
    position, only this small fixed vocabulary, so a new record type's roles table is the
    only thing that needs to change to support it)."""
    for p in rec.get('participants', []):
        if p.get('role_semantic') == semantic:
            return p
    return None


def get_all_by_semantic(rec: dict, semantics: Union[str, Tuple[str, ...]]) -> List[dict]:
    """Like get_by_semantic, but returns every match - used for the (up to two) parent-ish
    roles a family can carry, and for however many 'child' participants a record lists."""
    wanted = (semantics,) if isinstance(semantics, str) else semantics
    return [p for p in rec.get('participants', []) if p.get('role_semantic') in wanted]


def get_role_name(part: dict) -> str:
    """The display/citation name for a participant's role. role_name is already the AI's
    (or index-scrape's) own plain-word label - Archivist doesn't re-map it through a
    hardcoded per-position table; the one exception is clergy, whose occupation-style
    label (CHURCH_CONFIG['role_clergy']) takes priority over whatever role_name they were
    assigned (Officiant, Witness, ...), matching how their OCCU field is handled below."""
    if part.get('is_priest'):
        return CHURCH_CONFIG['role_clergy']
    return clean_val(part.get('role_name')) or CHURCH_CONFIG['role_default_witness']


def resolve_family_links(rec: dict) -> Dict[str, object]:
    """Works out this record's family structure purely from which family-position role
    semantics are present (primary/spouse/child/father/mother/father_in_law/mother_in_law)
    - the same logic for any record type. Primary forms a new family of their own
    (unsuffixed FAM id) only when a spouse or children are present - a union-type record.
    When primary is purely a child in this record (the common baptism/burial shape, no
    spouse or children recorded), their own parents' family keeps that unsuffixed id
    instead, exactly as before this generalization - so a plain parent/child record's FAM
    ids don't change just because the schema grew spouse/child/in-law support."""
    primary_forms_own_family = bool(get_by_semantic(rec, 'spouse') or get_all_by_semantic(rec, 'child'))
    return {
        'primary_forms_own_family': primary_forms_own_family,
        'main_suffix': "",
        'primary_parents_suffix': "G" if primary_forms_own_family else "",
        'spouse_parents_suffix': "B",
    }


def assign_spouses_by_sex(a: Optional[dict], b: Optional[dict]) -> Tuple[Optional[dict], Optional[dict]]:
    """Returns (husband, wife) for a couple, using each person's own sex field rather than
    assuming a fixed role always maps to a fixed gender. Ties (missing/matching sex data)
    default to (a, b) in whatever order they were given."""
    if a is not None and clean_val(a.get('sex'))[:1].upper() == 'F' and (
            b is None or clean_val(b.get('sex'))[:1].upper() != 'F'):
        return b, a
    return a, b


def evaluate_task_priority(task_note: str) -> tuple:
    """Evaluates task notes for keywords to assign a priority, color code, and dynamic folder name."""
    task_note_lower = f"{task_note}".lower()

    # (Keywords, Priority Level, RM Color Code, Target Folder Name)
    # noinspection SpellCheckingInspection
    rules = [
        (["conflict", "error", "mismatch", "discrepancy", "inconsistent", "contradict", "wrong"],
            1, "1", "Data Conflicts & Errors"),
        (["illegible", "unreadable", "hard to read", "faded", "damaged", "torn", "blot", "margin", "ink"],
            1, "1", "Legibility & Record Condition"),
        (["surname", "given name", "blank name", "no name", "unknown name", "alias", "dit name", "spelling",
          "identity"],
            1, "1", "Name & Identity Issues"),
        (["parent", "father", "mother", "sponsor", "godparent", "witness", "spouse", "bride", "groom", "relationship",
          "unknown parents"],
            2, "2", "Relationship & Participant Issues"),
        (["translate", "translation", "latin", "french", "language"],
            2, "2", "Translation Needed"),
        (["date", "year", "month", "day", "invalid", "chronology", "sequence", "estimated", "calculated", "age",
          "born"],
            3, "3", "Date & Chronology Issues"),
    ]

    for keywords, priority, color, folder in rules:
        if any(kw in task_note_lower for kw in keywords):
            return priority, color, folder

    return 3, REVIEW_COLOR, "General Review"


def generate_uid(rec: dict, part: dict, vol: str) -> str:
    """Generates a deterministic ID based on the physical location of the record to prevent
    typos from causing collisions. Clergy are the one exception: the same priest presides
    over many records across years and even across register volumes, so their ID is hashed
    purely from their own standardized name - independent of volume/page/record - so every
    mention of the same real person collapses onto one GEDCOM individual instead of a new
    one per record. This relies on std_given/std_surname already being the AI's normalized
    reading of the name (same historical spelling every time), not the raw transcription -
    an inherent limit of working from an unknown register with no pre-known clergy roster
    (a prior version of this prompt hardcoded a fixed list of named priests with permanent
    IDs for one specific parish; deliberately not restored, since it doesn't scale to an
    arbitrary register). A near-miss spelling variant of the same real priest across pages
    would hash to a different ID here; Registrar.py's fuzzy-duplicate matching (run after
    GEDCOM import) is the intended safety net for catching that, not this function.

    A gather source can also supply its own link_id (type_specific_fields.link_id) when it
    already knows two records describe the same real person - e.g. the same register
    duplicated across two overlapping physical volumes. That explicit signal takes priority
    over every other rule here, the same way the clergy name-hash already overrides the
    default per-record hash below."""
    src_id = re.sub(r'\D', '', get_dynamic_source_id(vol))

    link_id = clean_val((part.get('type_specific_fields') or {}).get('link_id'))
    if link_id:
        numeric_id = int(hashlib.md5(f"link_{link_id}".encode('utf-8')).hexdigest(), 16) % (10 ** 10)
        return f"{src_id}{numeric_id:010d}"

    if part.get('is_priest'):
        std_g = clean_val(part.get('std_given')).strip().lower()
        std_s = clean_val(part.get('std_surname')).strip().lower()
        std_name = f"{std_g} {std_s}".strip()
        numeric_id = int(hashlib.md5(f"clergy_{std_name}".encode('utf-8')).hexdigest(), 16) % (10 ** 10)
        return f"CLR{numeric_id:010d}"

    page_str = clean_val(rec.get('page'))
    rec_id = clean_val(rec.get('record_id'))
    role = f"{part.get('role_number', '0')}"

    participants = rec.get('participants', [])
    same_role = [i for i, p in enumerate(participants) if f"{p.get('role_number', '0')}" == role]
    pos = next((i for i, p in enumerate(participants) if p is part), None)
    occ = same_role.index(pos) if pos in same_role else 0

    unique_string = f"indi_{vol}_{page_str}_{rec_id}_{role}_{occ}"
    numeric_id = int(hashlib.md5(unique_string.encode('utf-8')).hexdigest(), 16) % (10 ** 10)
    return f"{src_id}{numeric_id:010d}"


def generate_media_uid(meta: dict, vol: str) -> str:
    """Generates a deterministic 10-digit numerical UID for a media file."""
    file_name = clean_val(meta.get('file_name'))
    image_dir = clean_val(IMAGE_DIR)

    if file_name:
        if image_dir:
            dir_base = os.path.basename(os.path.normpath(image_dir))
            unique_string = f"{dir_base}\\{file_name}"
        else:
            unique_string = file_name
    else:
        pages: Optional[str] = meta.get('pages')
        unique_string = f"vol_{vol}_pages_{pages}"

    numeric_id = int(hashlib.md5(unique_string.encode('utf-8')).hexdigest(), 16) % (10 ** 10)
    return f"M{numeric_id:010d}"


def generate_fam_uid(rec: dict, vol: str) -> str:
    """Generates a deterministic Family ID to match the INDI logic."""
    src_id = re.sub(r'\D', '', get_dynamic_source_id(vol))
    page_str = clean_val(rec.get('page'))
    rec_id = clean_val(rec.get('record_id'))

    unique_string = f"fam_{vol}_{page_str}_{rec_id}"
    numeric_id = int(hashlib.md5(unique_string.encode('utf-8')).hexdigest(), 16) % (10 ** 10)
    return f"{src_id}{numeric_id:010d}"


# ==========================================
# CHURCH FLAVOR: GEDCOM EMISSION
# ==========================================
def build_church_citation(rec: dict, part: dict, tag_name: str, vol: str, media_uid: str,
                          proof_status: str = "proven", target_software: str = "RM") -> str:
    """Constructs the standard source citation block for an event."""
    std_g = clean_val(part.get('std_given'))
    std_s = clean_val(part.get('std_surname'))
    page = clean_val(rec.get('page')) or 'X'
    rec_id = clean_val(rec.get('record_id')) or 'Unknown'
    year = clean_val(rec.get('year')) or 'Unknown'

    vol_clause = f"Vol. {vol}, " if vol else ""

    block = [
        f"2 _PROOF {proof_status}",
        f"2 SOUR {get_dynamic_source_id(vol)}",
        f"3 NAME {std_s}, {std_g}, {vol_clause}Page {page}, {rec_id}, {year}",
        f"3 _TITL {std_s}, {std_g}, {tag_name}, {year}",
        f"3 PAGE Page {page}, Record {rec_id}",
        "3 DATA",
        f"4 TEXT {CHURCH_CONFIG['translation_header']}"
    ]

    trans_text = wrap_text(clean_val(rec.get('english_translation')), '5 CONT')
    if trans_text:
        block.append(trans_text)

    block.append(f"3 NOTE {CHURCH_CONFIG['transcription_header']}")

    orig_text = wrap_text(clean_val(rec.get('original_transcription')), '4 CONT')
    if orig_text:
        block.append(orig_text)

    refn = clean_val(rec.get('record_number')) or rec_id
    if target_software == "RM":
        block.extend([
            f"3 REFN {refn}",
            "3 _TMPLT", "4 FIELD", "5 NAME ItemOfInterest",
            f"5 VALUE {f'{std_g} {std_s}'.strip()}", "4 FIELD", "5 NAME Page",
            f"5 VALUE Page {page}", "4 FIELD", "5 NAME DetailRef",
            f"5 VALUE {rec_id}",
            "3 QUAY 3", "3 _QUAL", "4 _SOUR O", "4 _INFO P",
            "4 _EVID D"
        ])
    else:
        block.extend([f"3 REFN {refn}", "3 QUAY 3"])

    # A gather source (Ancestry/FamilySearch-derived church records) can supply its own
    # per-person APID the same way the census flavor already does; only emitted when present
    # since most church records have no APID at all (this is a citation-level identifier, not
    # a general church-flavor field).
    apid_record_id = clean_val((part.get('type_specific_fields') or {}).get('apid'))
    if apid_record_id and APID_DB:
        block.append(f"3 _APID 1,{APID_DB}::{apid_record_id}")

    # A gather source can supply this participant's own FamilySearch record ark (always
    # present regardless of Family Tree attachment status - see Voyageur.js), giving the
    # citation a direct web link back to that specific indexed entry. weblink_lines() isn't
    # reused here since it hardcodes top-level (1 _WEBTAG) placement; this needs one level
    # deeper to nest under this citation's own "2 SOUR" line.
    person_ark = clean_val((part.get('type_specific_fields') or {}).get('person_ark'))
    if person_ark:
        record_url = f"https://www.familysearch.org/ark:/61903/1:1:{person_ark}"
        if target_software == "RM":
            block.extend(["3 _WEBTAG", "4 NAME FamilySearch Record", f"4 URL {record_url}"])
        else:
            block.extend([f"3 _LINK {record_url}", f"3 NOTE {record_url}"])

    if media_uid:
        block.append(f"3 OBJE @{media_uid}@")

    return "\n".join(block)


def build_custom_fact_lines(fact_name: str, value: str, rec: dict, part: dict, vol: str, media_uid: str,
                            target_software: str, date: str = "", place: str = "") -> List[str]:
    """Renders a RootsMagic custom fact (a person-bucket FactTypes.json entry with
    custom=True, e.g. Race/dit Name) as a generic EVEN/TYPE block using that fact's own
    use_value/use_date/use_place flags - the same shape RootsMagic itself expects to match
    a custom fact back to its FactTypeTable entry by TYPE text, so a new custom fact only
    ever needs an entry in FactTypes.json, never a bespoke code block here. Returns []
    (nothing to render) when value/date/place all come back empty."""
    entry = FACT_TYPES.get('person', {}).get(fact_name, {})
    val = clean_val(value) if entry.get('use_value', True) else ""
    fact_date = format_gedcom_date(date) if entry.get('use_date') and date else ""
    fact_place = clean_val(place) if entry.get('use_place') and place else ""

    if not (val or fact_date or fact_place):
        return []

    lines = [f"1 EVEN {val}".rstrip(), f"2 TYPE {fact_name}"]
    if fact_date:
        lines.append(f"2 DATE {fact_date}")
    if fact_place:
        lines.append(f"2 PLAC {fact_place}")
    lines.append(build_church_citation(rec, part, fact_name, vol, media_uid, target_software=target_software))
    return lines


def build_witness_links(rec: dict, witnesses: List[dict], vol: str, target_software: str) -> List[str]:
    """
    RM's proprietary _SHAR/ROLE tag links a witness/godparent directly to the shared
    event. FTM has no equivalent, so witnesses are instead summarized in one NOTE line.
    """
    if not witnesses:
        return []
    if target_software == "RM":
        lines = []
        for p in witnesses:
            lines.append(f"2 _SHAR @I{generate_uid(rec, p, vol)}@\n3 ROLE {get_role_name(p)}")
        return lines

    parts = []
    for p in witnesses:
        name = f"{clean_val(p.get('std_given'))} {clean_val(p.get('std_surname'))}".strip()
        role = get_role_name(p)
        parts.append(f"{name} ({role})" if name else role)
    return [f"2 NOTE Witnesses: {', '.join(parts)}"]


def build_individual(uid: str, rec: dict, part: dict, vol: str, media_uid: str, gedcom_date: str,
                     any_part_review: bool, target_software: str) -> tuple:
    """Builds a single individual's INDI block, along with their Task block if flagged for review."""
    event_type = clean_val(rec.get('event_type'))
    event_tag = get_event_gedcom_tag(event_type)
    is_family_evt = is_family_event(event_type)
    is_bap_or_chr = event_tag in ("BAPM", "CHR")

    semantic = part.get('role_semantic')
    is_primary = semantic == 'primary'
    is_parent = semantic in ('father', 'mother', 'father_in_law', 'mother_in_law')
    is_deceased = bool(part.get('deceased')) or bool(part.get('is_deceased'))

    std_g = clean_val(part.get('std_given'))
    std_s = clean_val(part.get('std_surname'))
    dit_name = re.sub(r'(?i)^dit\s+', '', clean_val(part.get('dit_name'))).strip()

    sex = clean_val(part.get('sex'))[:1]
    race = clean_val(part.get('race'))
    religion = clean_val(part.get('religion'))
    occu = clean_val(part.get('occupation'))
    resi = clean_val(part.get('residence'))

    age = clean_val(part.get('age'))
    raw_event_date = clean_val(rec.get('event_date'))
    raw_b = clean_val(part.get('birth_date'))
    raw_d = clean_val(part.get('death_date'))

    # Date heuristics
    if not raw_b and age and raw_event_date:
        raw_b = estimate_birth_from_age(raw_event_date, age)

    if raw_event_date:
        if is_bap_or_chr and is_primary:
            raw_b = raw_b or f"BEF {raw_event_date}"
        elif (not is_bap_or_chr and not is_family_evt and is_primary) or (is_parent and is_deceased):
            raw_d = raw_d or f"BEF {raw_event_date}"

        if not is_bap_or_chr and raw_b and not f"{raw_b}".upper().startswith("CAL "):
            if (f"{raw_event_date}"[:4] in raw_b and any(
                    m in f"{raw_b}".upper() for m in ["BEF", "ABT", "EST", "CAL"])):
                raw_b = ""

    b_date = format_gedcom_date(raw_b)
    d_date = format_gedcom_date(raw_d)
    b_place = clean_val(part.get('birth_place'))
    d_place = clean_val(part.get('death_place'))

    indi = [f"0 @I{uid}@ INDI"]
    if target_software == "RM":
        indi.append(f"1 _UID {uid}")
    indi.append(f"1 REFN {uid}")

    fsftid = clean_val((part.get('type_specific_fields') or {}).get('fsftid'))
    if fsftid:
        indi.append(f"1 _FSFTID {fsftid}")

    task_block, needs_review, folder_name = None, False, None

    # Handle Tasks / Review Flags -- always built the same way for both RM and FTM,
    # since real Family Tree Maker exports have no dedicated research/to-do tag of
    # their own to target instead.
    needs_primary_review = rec.get('review', False) and not any_part_review and is_primary
    if part.get('review', False) or needs_primary_review:
        needs_review = True
        reasons = [r for r in [clean_val(part.get('review_reason')), clean_val(rec.get('review_reason'))] if r]
        task_note = "; ".join(reasons) if reasons else "Review requested during extraction."

        priority, color_code, folder_name = evaluate_task_priority(task_note)

        indi.extend([f"1 _COLOR {color_code}", f"1 _TASK @T{uid}@"])

        raw_cit = build_church_citation(rec, part, f"Review {event_tag}", vol, media_uid,
                                        target_software=target_software).split('\n')

        task_citation = dedent_citation_lines(raw_cit, skip_at_level=(2, "_PROOF"))

        weblink = weblink_lines(clean_val(CHURCH_CONFIG.get('collection_url')),
                                CHURCH_CONFIG.get('collection_name', 'Collection Link'), target_software)

        task_lines = [
            f"0 @T{uid}@ _TASK", f"1 DESC {std_s or '[No Surname]'}, {std_g or '[No Given Name]'} "
            f"({clean_val(rec.get('record_id')) or 'Unknown'}): {task_note}", f"1 REFN {uid}",
            f"1 _LINK @I{uid}@", "1 TYPE 2", f"1 DATE {gedcom_date}",
            f"1 _LDATE {gedcom_date}", f"1 NOTE {task_note}", "1 STAT NEW", f"1 PRTY {priority}",
            f"1 _COLOR {color_code}"
        ]

        task_lines.extend(weblink)
        task_lines.extend(task_citation)
        if media_uid:
            task_lines.extend([f"1 OBJE @{media_uid}@"])
        task_block = "\n".join(task_lines)

    # Process Dit Names
    std_s_base = std_s
    if dit_name:
        if re.search(r'\s+dit\s+', std_s, flags=re.IGNORECASE):
            std_s_base = re.split(r'\s+dit\s+', std_s, flags=re.IGNORECASE)[0]
        else:
            std_s_base = std_s.replace(dit_name, "")
    std_s_base = re.sub(r'(?i)\s+dit\b', '', std_s_base).strip()

    indi.append(f"1 NAME {std_g} /{std_s_base}/")
    if clean_val(part.get('prefix')):
        indi.append(f"2 NPFX {clean_val(part.get('prefix'))}")
    elif part.get('is_priest'):
        indi.append(f"2 NPFX {CHURCH_CONFIG['clergy_honorific']}")

    if clean_val(part.get('suffix')):
        indi.append(f"2 NSFX {clean_val(part.get('suffix'))}")

    indi.extend([f"1 SOUR {ROOT_SOURCE_ID}", f"2 NAME Researcher: {RESEARCHER}",
                 f"2 _TITL Researcher: {RESEARCHER}"])

    if dit_name:
        indi.extend([f"1 NAME {std_g} /{std_s_base} dit {dit_name}/", f"1 NAME {std_g} /{dit_name}/"])
        indi.extend(build_custom_fact_lines('dit Name', dit_name, rec, part, vol, media_uid, target_software))

    # A margin note offering a different spelling of this person's name (a later
    # researcher's/transcriber's aid, not the priest's own entry - see Parish.pmt's
    # MARGIN ANNOTATIONS rule) - kept as its own NAME fact, proposed rather than proven,
    # same convention already used for census's crowdsourced alternate readings.
    alt_names = [n for n in (part.get('alternate_names') or []) if clean_val(n.get('value'))]
    for alt in alt_names:
        alt_giv, alt_sur = split_full_name(clean_val(alt.get('value')))
        indi.append(f"1 NAME {alt_giv} /{alt_sur}/")
        indi.append(build_church_citation(rec, part, 'Alternate Name', vol, media_uid, "proposed", target_software))

    if sex:
        indi.append(f"1 SEX {sex}")
    if race:
        indi.extend(build_custom_fact_lines('Race', race, rec, part, vol, media_uid, target_software))
    if religion:
        indi.extend([f"1 RELI {religion}",
                     build_church_citation(rec, part, "RELI", vol, media_uid, target_software=target_software)])

    final_occu = CHURCH_CONFIG['role_clergy'] if part.get('is_priest') else occu
    if final_occu:
        indi.extend([f"1 OCCU {final_occu}",
                     build_church_citation(rec, part, "OCCU", vol, media_uid, target_software=target_software)])
    if resi:
        indi.extend([f"1 RESI\n2 PLAC {resi}",
                     build_church_citation(rec, part, "RESI", vol, media_uid, target_software=target_software)])

    if b_date or b_place:
        indi.append("1 BIRT")
        if b_date:
            indi.append(f"2 DATE {b_date}")
        if b_place:
            indi.append(f"2 PLAC {b_place}")
        indi.append(build_church_citation(rec, part, "BIRT", vol, media_uid, get_proof_status(b_date),
                                          target_software))

    if d_date or d_place:
        indi.append("1 DEAT")
        if d_date:
            indi.append(f"2 DATE {d_date}")
        if d_place:
            indi.append(f"2 PLAC {d_place}")
        if age:
            indi.append(f"2 AGE {age}")
        indi.append(build_church_citation(rec, part, "DEAT", vol, media_uid, get_proof_status(d_date),
                                          target_software))

    # Link the record's own primary event, when it's a person-level fact (BAPM/BURI/DEAT/
    # a custom fact like Scrip/...). A family-level fact (Marriage) attaches to the FAM
    # record instead, built in build_family. event_tag falling back to 'EVEN' (no standard
    # GEDCOM tag for this event_type) means RootsMagic needs a '2 TYPE' line to recognize
    # which custom fact this is, same convention as build_custom_fact_lines - and, since a
    # custom fact's own extra_fields (Scrip's scrip_number/scrip_amount/...) have no
    # standard GEDCOM slots of their own, they're rendered generically as this event's own
    # value text, by field name, rather than Archivist ever knowing a specific field exists.
    if is_primary and not is_family_evt:
        event_value = ""
        if event_tag == 'EVEN':
            extra_fields = rec.get('type_specific_fields') or {}
            value_parts = [f"{k.replace('_', ' ').title()}: {clean_val(v)}"
                           for k, v in extra_fields.items() if clean_val(v)]
            event_value = f" {'; '.join(value_parts)}" if value_parts else ""
        indi.append(f"1 {event_tag}{event_value}")
        if event_tag == 'EVEN':
            indi.append(f"2 TYPE {event_type}")
        indi.extend([f"2 DATE {format_gedcom_date(raw_event_date)}" if raw_event_date else "",
                     f"2 PLAC {clean_val(rec.get('event_place')) or CHURCH_CONFIG['default_location']}"])
        if age:
            indi.append(f"2 AGE {age}")
        if alt_names:
            alt_values = ", ".join(clean_val(a.get('value')) for a in alt_names)
            indi.append(f"2 NOTE Margin note suggests alternate spelling: {alt_values}")

        witnesses = [p for p in rec.get('participants', []) if p.get('role_semantic') != 'primary']
        indi.extend(build_witness_links(rec, witnesses, vol, target_software))
        indi.append(build_church_citation(rec, part, event_tag, vol, media_uid, get_proof_status(raw_event_date),
                                          target_software))

    # Link families - driven entirely by which family-position role semantics are present
    # (see resolve_family_links), not by which record type this is.
    if get_by_semantic(rec, 'primary'):
        f_uid = generate_fam_uid(rec, vol)
        links = resolve_family_links(rec)
        has_parents = bool(get_all_by_semantic(rec, ('father', 'mother')))
        has_in_laws = bool(get_all_by_semantic(rec, ('father_in_law', 'mother_in_law')))

        if semantic == 'primary':
            if links['primary_forms_own_family']:
                indi.append(f"1 FAMS @F{f_uid}{links['main_suffix']}@")
                if has_parents:
                    indi.append(f"1 FAMC @F{f_uid}{links['primary_parents_suffix']}@")
            else:
                # build_family always creates this FAM (even with neither parent recorded,
                # just to hold primary's own CHIL link) to match this record type's GEDCOM
                # output from before family/child/in-law roles existed - primary's own FAMC
                # line has to point at it unconditionally too, not only when parents exist.
                indi.append(f"1 FAMC @F{f_uid}{links['primary_parents_suffix']}@")
        elif semantic == 'spouse':
            indi.append(f"1 FAMS @F{f_uid}{links['main_suffix']}@")
            if has_in_laws:
                indi.append(f"1 FAMC @F{f_uid}{links['spouse_parents_suffix']}@")
        elif semantic in ('father', 'mother'):
            indi.append(f"1 FAMS @F{f_uid}{links['primary_parents_suffix']}@")
        elif semantic in ('father_in_law', 'mother_in_law'):
            indi.append(f"1 FAMS @F{f_uid}{links['spouse_parents_suffix']}@")
        elif semantic == 'child':
            indi.append(f"1 FAMC @F{f_uid}{links['main_suffix']}@")

    return [line for line in indi if line], task_block, needs_review, folder_name


def build_family(rec: dict, vol: str, media_uid: str, target_software: str) -> list:
    """Builds FAM records for primary's own family (with spouse/children, if any) and for
    primary's and their spouse's parents, if present - driven entirely by which
    family-position role semantics this record's participants carry (see
    resolve_family_links), not by which record type this is."""
    primary = get_by_semantic(rec, 'primary')
    if not primary:
        return []

    spouse = get_by_semantic(rec, 'spouse')
    children = get_all_by_semantic(rec, 'child')
    links = resolve_family_links(rec)
    fam_uid = generate_fam_uid(rec, vol)
    event_type = clean_val(rec.get('event_type'))

    fams = []

    def add_parent_family(parent_a: Optional[dict], parent_b: Optional[dict], suffix: str, child: dict) -> None:
        """Helper to deduplicate parent family record generation. Skipped entirely when
        neither parent is present (unlike primary's own no-spouse/no-children family
        below, which always exists once primary does)."""
        if not (parent_a or parent_b):
            return
        husb, wife = assign_spouses_by_sex(parent_a, parent_b)
        p_fam = [f"0 @F{fam_uid}{suffix}@ FAM"]
        if husb:
            p_fam.append(f"1 HUSB @I{generate_uid(rec, husb, vol)}@")
        if wife:
            p_fam.append(f"1 WIFE @I{generate_uid(rec, wife, vol)}@")
        p_fam.append(f"1 CHIL @I{generate_uid(rec, child, vol)}@")
        fams.append("\n".join(p_fam))

    parents = get_all_by_semantic(rec, ('father', 'mother'))
    parent_a, parent_b = (parents + [None, None])[:2]

    if links['primary_forms_own_family']:
        husb, wife = assign_spouses_by_sex(primary, spouse)
        main_fam = [f"0 @F{fam_uid}{links['main_suffix']}@ FAM"]
        if husb:
            main_fam.append(f"1 HUSB @I{generate_uid(rec, husb, vol)}@")
        if wife:
            main_fam.append(f"1 WIFE @I{generate_uid(rec, wife, vol)}@")
        for child in children:
            main_fam.append(f"1 CHIL @I{generate_uid(rec, child, vol)}@")

        if is_family_event(event_type):
            event_tag = get_event_gedcom_tag(event_type)
            event_date = format_gedcom_date(clean_val(rec.get('event_date')))
            main_fam.extend([f"1 {event_tag}", f"2 DATE {event_date}" if event_date else "",
                             f"2 PLAC {clean_val(rec.get('event_place')) or CHURCH_CONFIG['default_location']}"])

            if clean_val(primary.get('age')):
                slot = "HUSB" if husb is primary else "WIFE"
                main_fam.append(f"2 {slot}\n3 AGE {clean_val(primary.get('age'))}")
            if spouse and clean_val(spouse.get('age')):
                slot = "WIFE" if wife is spouse else "HUSB"
                main_fam.append(f"2 {slot}\n3 AGE {clean_val(spouse.get('age'))}")

            for person in (primary, spouse):
                if person is None:
                    continue
                alt_names = [n for n in (person.get('alternate_names') or []) if clean_val(n.get('value'))]
                if alt_names:
                    alt_values = ", ".join(clean_val(a.get('value')) for a in alt_names)
                    who = clean_val(person.get('std_given'))
                    main_fam.append(f"2 NOTE Margin note suggests alternate spelling for {who}: {alt_values}")

            witnesses = [p for p in rec.get('participants', [])
                        if p.get('role_semantic') not in ('primary', 'spouse')]
            main_fam.extend(build_witness_links(rec, witnesses, vol, target_software))
            main_fam.append(build_church_citation(rec, primary, event_tag, vol, media_uid,
                                                   get_proof_status(event_date), target_software))

        fams.append("\n".join([line for line in main_fam if line]))

        add_parent_family(parent_a, parent_b, links['primary_parents_suffix'], primary)
        if spouse:
            in_laws = get_all_by_semantic(rec, ('father_in_law', 'mother_in_law'))
            in_law_a, in_law_b = (in_laws + [None, None])[:2]
            add_parent_family(in_law_a, in_law_b, links['spouse_parents_suffix'], spouse)
    else:
        # Primary is purely a child in this record (the baptism/burial shape): their
        # parents' family always exists once primary does, even with neither parent
        # recorded, matching this record type's GEDCOM output from before family/child/
        # in-law roles existed at all.
        husb, wife = assign_spouses_by_sex(parent_a, parent_b)
        fam_tag = [f"0 @F{fam_uid}{links['primary_parents_suffix']}@ FAM"]
        if husb:
            fam_tag.append(f"1 HUSB @I{generate_uid(rec, husb, vol)}@")
        if wife:
            fam_tag.append(f"1 WIFE @I{generate_uid(rec, wife, vol)}@")
        fam_tag.append(f"1 CHIL @I{generate_uid(rec, primary, vol)}@")
        fams.append("\n".join(fam_tag))

    return fams


def get_source_root(target_software: str) -> list:
    """Generates the static organization-level source record."""
    return [
        f"0 {ROOT_SOURCE_ID} SOUR",
        f"1 TITL {ORG_NAME}", "1 AUTH",
        f"1 PUBL Researcher: {RESEARCHER}."
    ] + weblink_lines(MGS_GROUP_URL, "Facebook Group", target_software) + weblink_lines(
        ANCESTRY_GROUP_URL, "Ancestry Group", target_software)


def get_volume_sources(volumes_used: set, target_software: str) -> list:
    """Generates register-specific source records dynamically based on volumes used."""
    loc_full = CHURCH_CONFIG['parish_location']
    sour_lines = []

    for vol in sorted(list(volumes_used)):
        s_id = get_dynamic_source_id(vol)
        v_clause = f", Volume {vol}" if vol else ""
        v_title = f"{CHURCH_CONFIG['volume_title']}{v_clause}"

        if target_software == "RM":
            block = [f"0 {s_id} SOUR",
                     f"1 ABBR {CHURCH_CONFIG['parish_name']} {v_title}",
                     f"1 REFN {s_id.replace('@S', '').replace('@', '')}",
                     f"1 TITL {CHURCH_CONFIG['parish_name']}, , {CHURCH_CONFIG['register_name']}{v_clause} ; "
                     f"{v_title}, {CHURCH_CONFIG['parish_name']}, {loc_full}.",
                     f"1 _SUBQ {CHURCH_CONFIG['parish_name']} - {loc_full}.",
                     f"1 _BIBL {CHURCH_CONFIG['parish_name']}. {v_title}. {CHURCH_CONFIG['parish_name']}, {loc_full}.",
                     "1 _TMPLT", "2 TID 355",
                     "2 FIELD", "3 NAME Church_Author", f"3 VALUE {CHURCH_CONFIG['parish_name']}", "2 FIELD",
                     "3 NAME Title", f"3 VALUE {CHURCH_CONFIG['volume_title']}",
                     "2 FIELD", "3 NAME Location", f"3 VALUE {loc_full}", "2 FIELD", "3 NAME ChurchLoc",
                     f"3 VALUE {CHURCH_CONFIG['parish_name']}",
                     "2 FIELD", "3 NAME RegisterName", f"3 VALUE {CHURCH_CONFIG['register_name']}"]

            if vol:
                block.extend(["2 FIELD", "3 NAME Volume", f"3 VALUE Volume {vol}"])

            block.extend(["2 FIELD", "3 NAME ArchRegNo", f"3 VALUE {CALL_NUMBER}",
                          "2 FIELD", "3 NAME Repository", f"3 VALUE {REPOSITORY}",
                          "2 FIELD", "3 NAME RepositoryLoc", f"3 VALUE {REPOSITORY_LOC}"])
            block.extend(weblink_lines(COLLECTION_URL, COLLECTION_NAME, "RM"))
        else:
            block = [f"0 {s_id} SOUR",
                     f"1 TITL {CHURCH_CONFIG['parish_name']}, {v_title}",
                     f"1 AUTH {CHURCH_CONFIG['parish_name']}",
                     f"1 PUBL {REPOSITORY_LOC}: {REPOSITORY}", f"1 REFN {s_id.replace('@S', '').replace('@', '')}"]
            block.extend(weblink_lines(COLLECTION_URL, COLLECTION_NAME, "FTM"))

        sour_lines.extend(block)

    return sour_lines


def build_gedcom_from_church(json_data: dict, target_software: str) -> str:
    """Main builder orchestrating the conversion from the loaded JSON to a raw GEDCOM string."""
    now = datetime.datetime.now()
    gedcom_date = now.strftime('%d %b %Y').upper()

    ged = [
        "0 HEAD",
        f"1 FILE {CHURCH_CONFIG['parish_file_name']}.ged",
        f"1 SOUR {SOFTWARE_NAME}",
        f"2 VERS {SOFTWARE_VERS}",
        f"2 NAME {SOFTWARE_NAME}",
        f"2 CORP {SOFTWARE_NAME}, Inc.",
        f"1 DEST {SOFTWARE_NAME}",
        f"1 DATE {gedcom_date}",
        f"2 TIME {now.strftime('%H:%M:%S')}",
        "1 SUBM @SUBM1@", f"1 COPR Copyright (c) {COPYRIGHT_START}-{now.year} {ORG_NAME}. All rights reserved.",
        f"1 NOTE {GEDCOM_NOTE}",
        f"2 CONC {GEDCOM_CONC}",
        "1 GEDC",
        "2 VERS 5.5.1",
        "2 FORM LINEAGE-LINKED",
        "1 CHAR UTF-8",
        "0 @SUBM1@ SUBM",
        f"1 NAME {RESEARCHER}",
        f"2 ADDR {SUBM_ADDRESS}",
        f"1 NOTE {ORG_NAME}"
    ]

    fam_recs, task_recs, media_recs = [], [], []
    printed_indis, printed_media, vols_used = set(), set(), set()
    folder_tasks: Dict[str, List[str]] = {}
    review_count = 0

    # Process all sheets and records
    for sheet in json_data.get('sheets', []):
        meta = sheet.get('document_metadata', {}) or {}
        vol = extract_volume(sheet)
        vols_used.add(vol)

        media_uid = generate_media_uid(meta, vol)
        file_name = clean_val(meta.get('file_name'))
        media_title = (f"{CHURCH_CONFIG['parish_name_short']} - Vol {vol or 'Unknown'} - "
                       f"Page {clean_val(meta.get('pages')) or 'X'}")

        # Build media object if new
        if media_uid not in printed_media:
            file_path = os.path.join(IMAGE_DIR, file_name)
            form_type = clean_val(meta.get('file_type', 'jpg')).lower()
            if form_type == 'jpeg':
                form_type = 'jpg'

            media_block = [f"0 @{media_uid}@ OBJE", f"1 FILE {file_path}",
                           f"2 FORM {form_type}",
                           f"2 TITL {media_title}"]
            media_recs.append("\n".join(media_block))
            printed_media.add(media_uid)

        # Build Individuals and Families
        for rec in sheet.get('records', []):
            any_review = any(p.get('review') for p in rec.get('participants', []))

            for part in rec.get('participants', []):
                uid = generate_uid(rec, part, vol)
                if uid in printed_indis:
                    continue
                printed_indis.add(uid)

                indi_block, t_block, flagged, folder = build_individual(uid, rec, part, vol, media_uid, gedcom_date,
                                                                        any_review, target_software)

                ged.extend(indi_block)
                if t_block and folder:
                    task_recs.append(t_block)
                    folder_tasks.setdefault(folder, []).append(f"1 _TASK @T{uid}@")
                if flagged:
                    review_count += 1

            fam_recs.extend(build_family(rec, vol, media_uid, target_software))

    # Compile the final GEDCOM file layout
    ged.extend(fam_recs)
    ged.extend(task_recs)

    for folder, tasks in folder_tasks.items():
        ged.append(f"0 _FOLDER {folder}")
        ged.extend(tasks)

    ged.extend(media_recs)
    ged.extend(get_source_root(target_software))
    ged.extend(get_volume_sources(vols_used, target_software))
    ged.append("0 TRLR")

    if review_count > 0:
        print(f"Flagged {review_count} individual(s) with priority-based Tasks and Folders.")

    return "\n".join(ged)


def apply_record_type_field_remap(record_type_name: str) -> None:
    """Resolves this document's own citation-source settings (CALL_NUMBER, COLLECTION_URL,
    COLLECTION_NAME, REPOSITORY, REPOSITORY_LOC, IMAGE_DIR, GEDCOM_OUTPUT_NAME) via the
    matching .pmt's field_remap table (see Paleographer/prompts/*.pmt's front matter),
    reading whichever of that record type's own prefixed .env keys is actually set - the
    same mechanism Paleographer.py's own resolve_setting uses. record_type_name is read
    directly off the loaded JSON (set by Paleographer itself - see its load_master_db),
    never guessed or hardcoded as a family-name string here. A record type with no
    matching .pmt (or no field_remap entry for a given setting) leaves that setting
    exactly as already resolved from Archivist's own .env - this only ever adds
    resolution, never removes a value that was already set."""
    global CALL_NUMBER, COLLECTION_URL, COLLECTION_NAME, REPOSITORY, REPOSITORY_LOC, IMAGE_DIR, GEDCOM_OUTPUT_NAME

    pmt_path = Path(__file__).resolve().parent.parent / "Paleographer" / "prompts" / f"{record_type_name}.pmt"
    if not record_type_name or not pmt_path.is_file():
        return

    raw = pmt_path.read_text(encoding="utf-8")
    stripped = raw.lstrip()
    if not stripped.startswith("---"):
        return
    parts = stripped.split("---", 2)
    if len(parts) < 3:
        return
    front_matter = yaml.safe_load(parts[1]) or {}
    field_remap = front_matter.get("field_remap", {}) or {}

    resolved: Dict[str, str] = {}
    for prefixed_key, target in field_remap.items():
        val = os.getenv(prefixed_key, "")
        if val:
            resolved[target] = val

    CALL_NUMBER = resolved.get("CALL_NUMBER") or CALL_NUMBER
    COLLECTION_URL = resolved.get("COLLECTION_URL") or COLLECTION_URL
    COLLECTION_NAME = resolved.get("COLLECTION_NAME") or COLLECTION_NAME
    REPOSITORY = resolved.get("REPOSITORY") or REPOSITORY
    REPOSITORY_LOC = resolved.get("REPOSITORY_LOC") or REPOSITORY_LOC
    if resolved.get("IMAGE_DIR"):
        IMAGE_DIR = safe_path(PROGRAM_DIR, resolved["IMAGE_DIR"])
    if resolved.get("GEDCOM_OUTPUT_NAME") and not os.getenv("GEDCOM_OUTPUT_NAME", "").strip():
        GEDCOM_OUTPUT_NAME = resolved["GEDCOM_OUTPUT_NAME"]


def run_church_flavor(data: dict) -> None:
    global REPOSITORY, REPOSITORY_LOC
    apply_record_type_field_remap(data.get("record_type_name", ""))

    # REPOSITORY/REPOSITORY_LOC are shared generic names with the census flavor (which
    # relies on them defaulting blank so its own JSON-scraped values via get_json_fallback
    # aren't masked), so the church-specific default is applied here rather than as a
    # module-level default.
    REPOSITORY = REPOSITORY or "FamilySearch.org"
    REPOSITORY_LOC = REPOSITORY_LOC or "Granite Mountain, UT"

    for software in ["RM", "FTM"]:
        gedcom_text = build_gedcom_from_church(data, software)

        final_path = resolve_gedcom_output_path(software)
        final_path.write_text(gedcom_text, encoding="utf-8")
        print(f"Successfully generated {final_path}")


def resolve_json_input(json_file: str, json_dir: str) -> Path:
    """Resolves the JSON file to convert. An explicit JSON_FILE setting must exist (a typo
    there is a real error, not a reason to guess). Left blank, falls back to whichever
    *.json file in JSON_DIR was created most recently, so tools like Archivist's
    "Generate GEDCOM" button work as a plain fallback without needing a filename typed in
    every time."""
    if json_file:
        candidate = Path(json_file) if os.path.isabs(json_file) else Path(str(json_dir)) / json_file
        if candidate.is_file():
            return candidate
        raise FileNotFoundError(f"JSON file not found: {candidate}")

    search_dir = Path(str(json_dir))
    candidates = sorted(search_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError(
            f"No JSON_FILE was set, and no *.json files were found in {search_dir} to fall back to.")
    return candidates[0]


# ==========================================
# MAIN EXECUTION
# ==========================================
if __name__ == "__main__":
    input_path = resolve_json_input(JSON_FILE, JSON_DIR)
    print(f"[System] Using JSON file: {input_path}" + ("" if JSON_FILE else " (auto-selected, most recent)"))

    with open(input_path, "r", encoding="utf-8") as json_fh:
        loaded_data = json.load(json_fh)

    # Census and church-register documents both use the "sheets" shape now (see the
    # design spec) - which builder applies is read from the document's own
    # record_type_name, never guessed from JSON shape alone. "pages" (Voyageur's
    # original raw census shape) is kept working for any already-gathered file that
    # predates the shared-schema normalization.
    is_census = loaded_data.get("record_type_name", "").startswith("Census_") or "pages" in loaded_data
    if is_census:
        # Census runs have no settings field for this (only the church flavor's
        # CHURCH_GEDCOM_NAME sets GEDCOM_OUTPUT_NAME), so left unset this always fell
        # through to the module-level default "Family_Register.ged" - not the name the
        # gather actually produced. Match the gathered JSON's own filename instead,
        # same convention the original CensusConverter.py used (CSV_FILE.replace('.csv',
        # '.ged')), unless the user explicitly set GEDCOM_OUTPUT_NAME themselves.
        if not os.getenv("GEDCOM_OUTPUT_NAME", "").strip():
            GEDCOM_OUTPUT_NAME = input_path.stem + ".ged"
        run_census_flavor(loaded_data)
    elif "sheets" in loaded_data:
        run_church_flavor(loaded_data)
    else:
        raise ValueError(
            f"Could not determine JSON flavor for {input_path}: expected a top-level "
            f"'sheets' key with a record_type_name, or a legacy 'pages' key (census)."
        )
