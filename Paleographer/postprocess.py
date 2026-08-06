"""
Generic mechanical post-processing for Paleographer records.

Every function here is fully generic across record types: they take the
active type's parsed front-matter tables (event types, roles, defaults) as
plain arguments and never contain type-specific logic themselves. Adding a
new record type never requires touching this file.
"""

import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple, Set
from titlecase import titlecase

PRESERVED_ACRONYMS = {"HBC", "NWT", "USA", "NWMP", "RCMP", "UK", "US", "ED", "PID", "RM", "FTM"}


def _titlecase_callback(word: str, **kwargs) -> str | None:
    w_clean = re.sub(r'^[^\w]+|[^\w]+$', '', word)
    if w_clean.upper() in PRESERVED_ACRONYMS:
        return word.replace(w_clean, w_clean.upper())
    if "-" in word:
        parts = word.split("-")
        return "-".join(
            (p.upper() if re.sub(r'^[^\w]+|[^\w]+$', '', p).upper() in PRESERVED_ACRONYMS else titlecase(p, callback=_titlecase_callback).capitalize())
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
        raw_role_name = participant.get("role_name")
        if raw_role_name:
            participant["role_name"] = cap_case(raw_role_name)
        if participant.get("role_number"):
            continue
        role_name = (raw_role_name or "").strip().lower()
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


def _participant_key(participant: Dict[str, Any]) -> tuple:
    return ((participant.get("std_given") or "").strip().lower(),
           (participant.get("std_surname") or "").strip().lower())


def _label_for(record: Dict[str, Any]) -> str:
    """Best available label for a record's own source document, for use as a section
    header when its transcription gets merged into another record's. Prefers an explicit
    document_type (e.g. Scrip.pmt's extra field, "Witness Affidavit"/"Claimant's Own
    Affidavit") since that's a human-meaningful label a RootsMagic citation reader can
    actually use; falls back to the page number, which is always present, if no
    document_type was given (either the active record type doesn't define that field, or
    the LLM left it null)."""
    document_type = (record.get("type_specific_fields") or {}).get("document_type")
    if document_type:
        return cap_case(document_type)
    page = record.get("page")
    return f"Page {page}" if page else "Untitled section"


def _source_document_entry(record: Dict[str, Any]) -> Dict[str, Any]:
    """One record's own text, snapshotted as a source_documents list entry - see
    _merge_record_into. document_type/page identify WHICH physical document this text
    came from; Commissioner appends further entries to this same list later (certificate/
    grant downloads) using media_path instead of transcription text."""
    return {
        "document_type": _label_for(record),
        "page": record.get("page"),
        "citation_text": record.get("citation_text"),
        "citation_details": record.get("citation_details"),
    }


def _merge_record_into(base: Dict[str, Any], incoming: Dict[str, Any]) -> None:
    """Merges `incoming` into `base` in place - `base` is what survives, `incoming` is
    discarded by the caller afterward. See merge_same_claim_records for when this runs.

    base's own top-level citation_text/citation_details are left untouched
    (still just base's own text, unlabeled) - every document's text, including base's,
    instead lands in base["source_documents"], one entry per physical document. This
    keeps every other record type (anything that never goes through this merge step)
    completely unaffected, and lets Archivist emit one citation per source document
    instead of one flattened, labeled blob."""
    source_documents = base.setdefault("source_documents", [])
    if not source_documents:
        source_documents.append(_source_document_entry(base))
    source_documents.append(_source_document_entry(incoming))

    base_fields = base.setdefault("type_specific_fields", {})
    for key, value in (incoming.get("type_specific_fields") or {}).items():
        if key == "document_type":
            continue  # already consumed above as a section label, not a fact about the claim
        if value and not base_fields.get(key):
            base_fields[key] = value

    if incoming.get("review"):
        base["review"] = True
        reasons = [r for r in (base.get("review_reason"), incoming.get("review_reason")) if r]
        base["review_reason"] = "; ".join(reasons) if reasons else base.get("review_reason")

    base_participants = base.setdefault("participants", [])
    by_key = {_participant_key(p): p for p in base_participants if _participant_key(p) != ("", "")}
    for participant in incoming.get("participants", []):
        key = _participant_key(participant)
        existing = by_key.get(key) if key != ("", "") else None
        if existing is None:
            base_participants.append(participant)
            continue
        for field, value in participant.items():
            if field == "type_specific_fields":
                continue
            if value and not existing.get(field):
                existing[field] = value
        existing_fields = existing.setdefault("type_specific_fields", {})
        for tk, tv in (participant.get("type_specific_fields") or {}).items():
            if tv and not existing_fields.get(tk):
                existing_fields[tk] = tv


def merge_same_claim_records(sheets: List[Dict[str, Any]]) -> None:
    """Merges records that share the same derived record_id (event_type + record_number)
    within one extraction result's sheets into a single record - e.g. a witness affidavit
    and the claimant's own affidavit, sworn on different pages/images but supporting the
    same underlying claim (confirmed live: Scrip.pmt records for the same claim correctly
    share one record_number across documents; nothing previously merged them). Mutates
    `sheets` in place - a merged-away record is removed from its own sheet, its content
    folded into whichever same-record_id record was seen first, landing in the survivor's
    source_documents list (one entry per physical document - see _source_document_entry)
    rather than a single flattened, labeled text blob.

    Distinct from Paleographer.py's continues_on_next_image/continues_from_previous_image
    continuation mechanism, which is for ONE record's content literally cut off
    mid-sentence at a page/chunk boundary - this is for genuinely separate, complete
    documents that happen to support the same claim, identified purely by a shared
    record_id, with no continuation flags involved. Must run after derive_record_identity
    has set record_id on every record (records with no record_id - e.g. an unrecognized
    event_type - are left alone, never merged)."""
    seen: Dict[str, Dict[str, Any]] = {}
    for sheet in sheets:
        records = sheet.get("records", [])
        kept: List[Dict[str, Any]] = []
        for record in records:
            record_id = record.get("record_id")
            if record_id and record_id in seen:
                _merge_record_into(seen[record_id], record)
            else:
                if record_id:
                    seen[record_id] = record
                kept.append(record)
        sheet["records"] = kept


def apply_defaults(target: Dict[str, Any], defaults_table: Dict[str, str]) -> None:
    """Fills only null/empty fields on target from defaults_table, applied every time
    rather than possibly forgotten by the LLM. Callers pass the record-level or
    participant-level slice of a type's defaults table as appropriate."""
    for key, value in defaults_table.items():
        if not target.get(key):
            target[key] = value


# ==========================================
# SCRIP DATA CLEANING & REPAIR
# ==========================================
MONTHS_REGEX = (
    r'(?:january|february|march|april|may|june|july|august|september|october|november|december|'
    r'jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)'
)
DATE_PATTERN = re.compile(
    rf'\b(?:(?:\d{{1,2}}(?:st|nd|rd|th)?\s+)?{MONTHS_REGEX}\.?\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s*(?:17\d\d|18\d\d|19\d\d)?|'
    rf'\d{{1,2}}(?:st|nd|rd|th)?\s+{MONTHS_REGEX}\.?,?\s*(?:17\d\d|18\d\d|19\d\d)?|'
    rf'{MONTHS_REGEX}\.?,?\s*(?:17\d\d|18\d\d|19\d\d)|(?:17\d\d|18\d\d|19\d\d)(?:/(?:17\d\d|18\d\d|19\d\d))?)\b',
    re.I)
NARRATIVE_JUNK_REGEX = re.compile(
    r'\b(?:settler|settled|grandchild|descendant|resided|surviving|heir|entitled|deceased|father|mother|daughter|son|'
    r'brother|sister|wife|husband|married|leaving|claim|who\b|born\b|died\b)\b',
    re.I)

_MOJIBAKE_MAP = {
    'ã©': 'é', 'ã¨': 'è', 'ãª': 'ê', 'ã«': 'ë', 'ã ': 'à', 'ã¢': 'â',
    'ã®': 'î', 'ã¯': 'ï', 'ã´': 'ô', 'ã¹': 'ù', 'ã»': 'û', 'ã§': 'ç',
    'ã‰': 'É', 'ãˆ': 'È', 'ãŠ': 'Ê', 'ã‹': 'Ë', 'ã€': 'À', 'ã‚': 'Â',
    'ãŽ': 'Î', 'ã”': 'Ô', 'ã™': 'Ù', 'ã›': 'Û', 'ã‡': 'Ç',
    'â€™': "'", 'â€˜': "'", 'â€œ': '"', 'â€\x9d': '"', 'â€"': '—',
    'â€“': '–', 'ãfb': 'ï', 'ã\xaf': 'ï', 'ã\xad': 'í', 'ã\x89': 'É',
    'ã\x88': 'È', 'ã\x8a': 'ê', 'ã\x8b': 'ë', 'ã\x80': 'À', 'ã\x82': 'Â',
    'Ã©': 'é', 'Ã¨': 'è', 'Ãª': 'ê', 'Ã«': 'ë', 'Ã ': 'à', 'Ã¢': 'â',
    'Ã®': 'î', 'Ã¯': 'ï', 'Ã´': 'ô', 'Ã¹': 'ù', 'Ã»': 'û', 'Ã§': 'ç',
    'Ã‰': 'É', 'Ãˆ': 'È', 'ÃŠ': 'Ê', 'Ã‹': 'Ë', 'Ã€': 'À', 'Ã‚': 'Â',
    'ÃŽ': 'Î', 'Ã”': 'Ô', 'Ã™': 'Ù', 'Ã›': 'Û', 'Ã‡': 'Ç',
    '’': "'", '‘': "'", '“': '"', '”': '"', '—': '—', '–': '–',
}


def fix_mojibake(text: str) -> str:
    """Repairs UTF-8 strings that were decoded as CP1252 / ISO-8859-1 (mojibake)."""
    if not text:
        return ""
    fixed = re.sub(
        r"ã([\x80-\xbf\u00a0-\u00bf\u0080-\u009f\u2018-\u201d\u2022\u20ac])",
        lambda m: 'Ã' + m.group(1),
        str(text)
    )
    if any(ch in fixed for ch in ("Ã", "Â", "â", "ð")):
        try:
            fixed = fixed.encode("cp1252").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            try:
                fixed = fixed.encode("latin1").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
    for bad, good in _MOJIBAKE_MAP.items():
        if bad in fixed:
            fixed = fixed.replace(bad, good)
    return fixed


def clean_race(val: Any) -> str:
    if val is None:
        return ""
    text = str(val).strip()
    if not text:
        return ""
    cleaned = re.sub(r'^(?:the\s+)?(?:present\s+)?d(?:e)?pon(?:ent|end)\s*(?:and|&)?\s*', '', text, flags=re.I)
    cleaned = re.sub(r'[,;]?\s*(?:(?:and|&|an)\s+)?(?:the\s+)?(?:present\s+)?d(?:e)?pon(?:ent|end)\b.*$', '', cleaned, flags=re.I)
    cleaned = re.sub(r'[,;&\s]+$', '', cleaned).strip()
    cleaned = re.sub(r'^[,;&\s]+', '', cleaned).strip()
    if cleaned.lower() in ("deponent", "the deponent", "mother", "father", "wife", "husband", "widow", "as heir", ""):
        return ""
    if re.match(r'^(?:who|heir|file ref|was entitled|her brother)\b', cleaned, flags=re.I):
        return ""
    return cap_case(cleaned)


def clean_date_and_place(raw_date: str, raw_place: str) -> Tuple[str, str]:
    def strip_prefixes(s: str) -> str:
        if not s:
            return ""
        t = str(s).strip()
        t = re.sub(r'^(?:born|died|married|address)\s*,\s*', '', t, flags=re.I)
        t = re.sub(r'^(?:born|died|married|address)\s+', '', t, flags=re.I)
        t = re.sub(r'^(?:who\s+died|who\s+was\s+born|mother\s+married|father\s+married)\s*', '', t, flags=re.I)
        return re.sub(r'^[,\s\-:]+|[,\s\-:]+$', '', t).strip()

    d_clean = strip_prefixes(raw_date)
    p_clean = strip_prefixes(raw_place)
    found_date, candidate_place = "", ""
    d_match = DATE_PATTERN.search(d_clean)
    p_match = DATE_PATTERN.search(p_clean)

    if d_match:
        found_date = d_match.group(0).strip()
        d_rem = (d_clean[:d_match.start()] + " " + d_clean[d_match.end():]).strip()
        d_rem = re.sub(r'^[,\s\-:]+|[,\s\-:]+$', '', d_rem).strip()
        if d_rem and not NARRATIVE_JUNK_REGEX.search(d_rem):
            candidate_place = d_rem
    elif d_clean and not NARRATIVE_JUNK_REGEX.search(d_clean):
        candidate_place = d_clean

    if p_match:
        if not found_date:
            found_date = p_match.group(0).strip()
        p_rem = (p_clean[:p_match.start()] + " " + p_clean[p_match.end():]).strip()
        p_rem = re.sub(r'^[,\s\-:]+|[,\s\-:]+$', '', p_rem).strip()
        p_rem = re.sub(r'\s*\bor\s*$', '', p_rem, flags=re.I).strip()
        if p_rem and not candidate_place and not NARRATIVE_JUNK_REGEX.search(p_rem):
            candidate_place = p_rem
    elif p_clean and not candidate_place and not NARRATIVE_JUNK_REGEX.search(p_clean):
        candidate_place = p_clean

    candidate_place = re.sub(r'\s*\bor\s*$', '', candidate_place, flags=re.I).strip()
    return found_date, cap_case(candidate_place)


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
    cleaned = re.sub(r'^(?:dit|dite|alias)\s+', '', (dit_str or "").strip(), flags=re.I).strip()
    return " ".join(w.capitalize() for w in cleaned.split())


def parse_single_name(raw: str, expected_surname: str = "") -> Tuple[str, str, str]:
    """Parses a raw 'FIRSTNAME LASTNAME' string into (std_given, std_surname, dit_name)."""
    text = (raw or "").strip()
    if not text:
        return "", "", ""

    dit_name = ""
    m_dit = re.search(r'\s+\b(dit|dite)\b\s+(.+)$', text, flags=re.I)
    if m_dit:
        dit_name = clean_dit_name(m_dit.group(2))
        text = text[:m_dit.start()].strip()

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

    surname_idx = len(parts) - 1
    if len(parts) >= 3:
        two_word = f"{parts[-3]} {parts[-2]}".lower()
        if two_word in COMPOUND_SURNAME_PREFIXES_2:
            surname_idx = len(parts) - 3
        elif (parts[-2].lower().rstrip('.') in COMPOUND_SURNAME_PREFIXES_1
              or parts[-2].lower() in COMPOUND_SURNAME_PREFIXES_1):
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
    """Repairs participant's std_given and std_surname, moving compound prefixes properly."""
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
    """Repairs participant names across the entire record."""
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
    """Builds standard composite key: [Claim Number]-[Allotment Number]-[Scrip Number]."""
    claim = (tf.get("claim_number") or "").strip() or "0"
    allotment = (tf.get("allotment_number") or "").strip() or "0"
    scrip = (tf.get("scrip_number") or "").strip() or "0"
    return f"{claim}-{allotment}-{scrip}"


def resolve_maiden_name_for_record(record: Dict[str, Any], row_nee: str = "") -> bool:
    """Resolves maiden surname if married surname is currently in std_surname."""
    participants = record.get("participants", [])
    if not participants:
        return False

    primary = participants[0]
    father = next((p for p in participants
                   if p.get("role_semantic") == "father" or str(p.get("role_number")) == "6"), None)
    spouse = next((p for p in participants
                   if p.get("role_semantic") == "spouse" or str(p.get("role_number")) == "2"), None)

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
            if married_full and not any(
                (a.get("value") or "").strip().lower() == married_full.lower() for a in alt_names
            ):
                alt_names.append({"value": married_full})
            primary["std_surname"] = maiden_surname
            modified = True
        elif not c_surname:
            primary["std_surname"] = maiden_surname
            modified = True

    return modified


def resolve_dataset_maiden_names(data: Dict[str, Any]) -> int:
    """Resolves married/maiden surnames across an entire dataset."""
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


CITATION_PATTERNS = {
    "claim_number": re.compile(r"claim no\.?:?\s*([^;]+)", re.I),
    "affidavit_number": re.compile(r"aff(?:idavit|dt)?\.?\s*no\.?:?\s*([^;]+)", re.I),
    "allotment_number": re.compile(r"allotment\s*no\.?:?\s*([^;]+)", re.I),
    "scrip_number": re.compile(r"scrip no\.?:?\s*([^;]+)", re.I),
    "grant_number": re.compile(r"grant no\.?:?\s*([^;]+)", re.I),
    "patent_number": re.compile(r"patent no\.?:?\s*([^;]+)", re.I),
    "case_number": re.compile(r"case no\.?:?\s*([^;]+)", re.I),
    "scrip_amount": re.compile(r"amount:?\s*([^;]+)", re.I),
    "scrip_issue_date": re.compile(r"date of issue:?\s*([^;]+)", re.I),
    "issue_date": re.compile(r"date of issue:?\s*([^;]+)", re.I),
    "application_date": re.compile(r"date of application:?\s*([^;]+)", re.I),
}


def extract_citation_fields(citation: str) -> Dict[str, str]:
    """Extracts structured scrip fields from citation string."""
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

