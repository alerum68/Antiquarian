"""
Generic mechanical post-processing for Paleographer records.

Every function here is fully generic across record types: they take the
active type's parsed front-matter tables (event types, roles, defaults) as
plain arguments and never contain type-specific logic themselves. Adding a
new record type never requires touching this file.
"""

import re
import unicodedata
from typing import Any, Dict, Optional

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


def strip_diacritics(text: Optional[str]) -> Optional[str]:
    """Mechanically strips diacritics/accents, keeping only plain ASCII letters/numbers/
    punctuation. Applies to any std_* field regardless of record type."""
    if text is None:
        return None
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c))


def parse_to_iso(reading: Optional[str]) -> Optional[str]:
    """Parses the LLM's best English-language date reading into YYYY-MM-DD (or a
    coarser YYYY-MM / YYYY if day/month aren't stated). Also passes through a date the
    LLM already gave in ISO form unchanged, since in practice a model asked for "event
    date" sometimes reaches for ISO formatting regardless of the prompt's wording.
    Returns None if the reading can't be confidently parsed, rather than guessing."""
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
    """Sets record_id (id_prefix + record_number) from the LLM's plain word event_type,
    looked up in the active type's event_types table. No-ops if event_type isn't
    recognized or record_number is missing, leaving whatever the LLM already set, if
    anything. Archivist derives its own event/family-bucket handling directly from
    event_type via the shared FactTypes.json (get_event_gedcom_tag/is_family_event) - this
    function no longer needs to compute a record_type_code for it, only record_id, which
    Archivist's generate_uid/generate_fam_uid still hash on for ID stability."""
    event_type = record.get("event_type")
    entry: Optional[Dict[str, str]] = event_types_table.get(event_type) if event_type else None
    if not entry:
        return

    record_number: Optional[str] = record.get("record_number")
    if record_number:
        record["record_id"] = f"{entry.get('id_prefix', '')}{record_number}"


def derive_role_numbers(record: Dict[str, Any], roles_table: Dict[str, Dict[str, Optional[str]]]) -> None:
    """Sets each participant's role_number from their plain-word role_name, looked up in
    the active type's roles table (case-insensitive match on the role's display name).
    The LLM only ever supplies role_name; it never needs to know numeric codes. Must run
    before derive_suffixes(), which depends on role_number already being set."""
    name_to_number = {(role.get("name") or "").strip().lower(): number for number, role in roles_table.items()}
    for participant in record.get("participants", []):
        if participant.get("role_number"):
            continue
        role_name = (participant.get("role_name") or "").strip().lower()
        role_number = name_to_number.get(role_name)
        if role_number is not None:
            participant["role_number"] = role_number


def derive_role_semantics(record: Dict[str, Any], roles_table: Dict[str, Dict[str, Optional[str]]]) -> None:
    """Sets each participant's role_semantic from their already-resolved role_number, looked
    up in the active type's roles table. This is the one piece of role meaning Archivist
    consumes directly - it never sees role_name text or role_number digits meaning anything
    on its own, only this small fixed vocabulary (primary/spouse/child/father/mother/
    father_in_law/mother_in_law), so a new record type's roles table only needs to tag the
    right entries with a semantic for family/association linking to work, no Archivist code
    changes required. A role with no semantic (Godparent, Officiant, Witness, Commissioner,
    ...) is left with none, which Archivist treats as an association, not a family link.
    Must run after derive_role_numbers(), which sets role_number in the first place."""
    for participant in record.get("participants", []):
        role_number = participant.get("role_number")
        role = roles_table.get(role_number) if role_number else None
        semantic = role.get("semantic") if role else None
        if semantic:
            participant["role_semantic"] = semantic


def _find_role_number(roles_table: Dict[str, Dict[str, Optional[str]]], semantic: str) -> Optional[str]:
    for role_number, role in roles_table.items():
        if role.get("semantic") == semantic:
            return role_number
    return None


def derive_suffixes(record: Dict[str, Any], roles_table: Dict[str, Dict[str, Optional[str]]]) -> None:
    """Sets 'Jr'/'Sr' on a primary participant and their father when their standardized
    names match exactly. No-ops entirely for a record type whose roles table has no
    'primary' or 'father' semantic entry, since there is nothing to compare."""
    primary_role = _find_role_number(roles_table, "primary")
    father_role = _find_role_number(roles_table, "father")
    if primary_role is None or father_role is None:
        return

    participants = record.get("participants", [])
    primary: Optional[Dict[str, Any]] = next(
        (p for p in participants if p.get("role_number") == primary_role), None)
    father: Optional[Dict[str, Any]] = next(
        (p for p in participants if p.get("role_number") == father_role), None)
    if not primary or not father:
        return

    if (primary.get("std_given") and primary.get("std_surname")
            and primary["std_given"] == father.get("std_given")
            and primary["std_surname"] == father.get("std_surname")):
        primary["suffix"] = "Jr"
        father["suffix"] = "Sr"


def apply_defaults(target: Dict[str, Any], defaults_table: Dict[str, str]) -> None:
    """Fills only null/empty fields on target from defaults_table, applied every time
    rather than possibly forgotten by the LLM. Callers pass the record-level or
    participant-level slice of a type's defaults table as appropriate."""
    for key, value in defaults_table.items():
        if not target.get(key):
            target[key] = value
