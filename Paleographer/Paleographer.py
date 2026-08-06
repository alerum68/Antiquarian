"""
Paleographer: General-Purpose Historical Document Extraction Script.

Uses the Gemini API to transcribe historical document images or PDFs of any
record type and extract structured records into a JSON master database,
following one universal schema. Which record type is active, and every
piece of type-specific vocabulary (event types, roles, defaults, schema
extensions), comes entirely from a single .pmt file in prompts/; this
script never changes when a new record type is added.

This file is self-contained: postprocess.py, engine.py, and agy_engine.py
are all folded in directly below so no sibling-file imports are required at
runtime. The original subfiles are kept in place for test-suite compatibility.
"""

import copy
import json
import math
import os
import re
import shutil
import sys
import tempfile
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from string import Template
from textwrap import dedent
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import pdfplumber
import yaml
from dotenv import load_dotenv
from google import genai
# noinspection unresolved-references
from google.genai import types
from PIL import Image
from titlecase import titlecase

# The Toolbox's own subprocess launcher sets PYTHONIOENCODING=utf-8, but this script also
# supports being run directly from the command line (its debug mode), where stdout would
# otherwise fall back to the system's default codepage and crash on emoji/checkmarks.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# PDFix and ScriptoriumMCP live in sibling tool folders, not installed packages - add the
# repo root to sys.path so they can be imported by absolute path.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from PDFix.PDFix import optimize_pdf, COMPRESSION_PARAMS  # noqa: E402
from ScriptoriumMCP import agy_client  # noqa: E402

try:
    from Voyageur import lac_client
    from Voyageur import LAC as voyageur_lac
except (ImportError, ValueError):
    try:
        from . import lac_client
        from . import LAC as voyageur_lac
    except (ImportError, ValueError):
        import lac_client
        import LAC as voyageur_lac

from Commissioner import normalization  # noqa: E402

# Global settings come from the project root's .env; this tool's own settings come from
# its own subfolder's .env, so Paleographer stays runnable standalone.
ROOT_ENV = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ROOT_ENV, override=True)
load_dotenv(Path(__file__).resolve().parent / ".env", override=True)


# ==============================================================================
# POSTPROCESS (folded from postprocess.py)
# ==============================================================================

def strip_diacritics(text: Optional[str]) -> Optional[str]:
    """Mechanically strips diacritics/accents, keeping only plain ASCII letters/numbers/
    punctuation. Applies to any std_* field regardless of record type."""
    if text is None:
        return None
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c))


def derive_role_numbers(record: Dict[str, Any], roles_table: Dict[str, Dict[str, Optional[str]]]) -> None:
    """Sets each participant's role_number from their plain-word role_name."""
    for participant in record.get("participants", []):
        raw_role_name = participant.get("role_name")
        if raw_role_name:
            participant["role_name"] = normalization.cap_case(raw_role_name)
        if participant.get("role_number"):
            continue
        role_number = normalization.derive_role_number(raw_role_name or "", roles_table)
        if role_number is not None:
            participant["role_number"] = role_number


def derive_role_semantics(record: Dict[str, Any], roles_table: Dict[str, Dict[str, Optional[str]]]) -> None:
    """Sets each participant's role_semantic from their already-resolved role_number."""
    for participant in record.get("participants", []):
        role_number = participant.get("role_number")
        semantic = normalization.derive_role_semantic(role_number, roles_table)
        if semantic:
            participant["role_semantic"] = semantic


def _find_role_number(roles_table: Dict[str, Dict[str, Optional[str]]], semantic: str) -> Optional[str]:
    for role_number, role in roles_table.items():
        if role.get("semantic") == semantic:
            return role_number
    return None


def derive_suffixes(record: Dict[str, Any], roles_table: Dict[str, Dict[str, Optional[str]]]) -> None:
    """Sets 'Jr'/'Sr' on a primary participant and their father when their standardized
    names match exactly."""
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
    return (
        (participant.get("std_given") or "").strip().lower(),
        (participant.get("std_surname") or "").strip().lower(),
    )


def _label_for(record: Dict[str, Any]) -> str:
    """Best available label for a record's own source document."""
    document_type = (record.get("type_specific_fields") or {}).get("document_type")
    if document_type:
        return normalization.cap_case(document_type)
    page = record.get("page")
    return f"Page {page}" if page else "Untitled section"


def _source_document_entry(record: Dict[str, Any]) -> Dict[str, Any]:
    """One record's own text, snapshotted as a source_documents list entry."""
    return {
        "document_type": _label_for(record),
        "page": record.get("page"),
        "citation_text": record.get("citation_text"),
        "citation_details": record.get("citation_details"),
    }


def _merge_record_into(base: Dict[str, Any], incoming: Dict[str, Any]) -> None:
    """Merges `incoming` into `base` in place."""
    source_documents = base.setdefault("source_documents", [])
    if not source_documents:
        source_documents.append(_source_document_entry(base))
    source_documents.append(_source_document_entry(incoming))

    base_fields = base.setdefault("type_specific_fields", {})
    for key, value in (incoming.get("type_specific_fields") or {}).items():
        if key == "document_type":
            continue
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
    """Merges records that share the same derived record_id within one extraction result's
    sheets into a single record."""
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
    """Fills only null/empty fields on target from defaults_table."""
    for key, value in defaults_table.items():
        if not target.get(key):
            target[key] = value


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


# ==============================================================================
# ENGINE (folded from engine.py)
# ==============================================================================

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
DEFAULT_TYPE = "Parish.pmt"
FACT_TYPES_PATH = Path(__file__).resolve().parent.parent / "FactTypes.json"

# A PDF with more pages than this routes through the Batch API instead of the
# synchronous path; a single-page image never crosses it.
BATCH_PAGE_THRESHOLD = 5

FRONT_MATTER_DELIM = "---"

UNIVERSAL_PROMPT_SUFFIX = dedent("""
    UNIVERSAL OUTPUT RULES (apply regardless of record type):
    - Output must match the provided JSON schema exactly. No extra fields. Use null when data isn't
      explicitly present.
    - raw_* fields preserve the exact original reading (diacritics, spelling, everything). std_* fields are
      your best linguistic standardization; formatting, diacritic-stripping, and code/ID derivation are
      handled downstream, not by you.
    - Set "review": true and give a short plain-English "review_reason" (under 15 words) whenever any part
      of a record or participant is uncertain, guessed, illegible, or otherwise needs a human to double-check
      it. Otherwise "review": false and "review_reason": null.
    - Illegible text: attempt reading at least 3 times. Use "[illegible]" if genuinely unreadable. NEVER
      guess silently.
    - Strikethroughs: insert "[struck through: <best reading>]" inline in the transcription.
    - PAGE CONTINUITY: each image is processed independently, with no memory of any other image -
      except when a "CONTINUATION FROM PREVIOUS IMAGE" context block is explicitly given to you below,
      which is the one case where you DO have information from the previous image. If your OWN last
      record on THIS image is cut off at the bottom of the page (no natural ending, mid-sentence, no
      closing/signature), set that record's "continues_on_next_image": true - do not guess how it
      would have ended. If you were given a "CONTINUATION FROM PREVIOUS IMAGE" block and the TOP of
      this image is what completes it, output ONE merged record combining the given content with what
      you read here (reusing its record_number/year), set "continues_from_previous_image": true on it,
      and do not also output a second, separate record for the same entry. If that context was given
      but nothing on this image continues it, ignore it entirely - do not force a merge.
""").strip()


class DailyQuotaExhausted(Exception):
    """Raised when Gemini reports the daily quota is exhausted. The whole run should stop, not retry."""


@dataclass
class TypeConfig:
    """A record type's resolved configuration."""
    name: str
    event_types: Dict[str, Dict[str, str]]
    roles: Dict[str, Dict[str, Optional[str]]]
    defaults: Dict[str, Dict[str, str]]
    extra_fields: Dict[str, List[Dict[str, str]]]
    metadata_fields: Dict[str, str]
    field_remap: Dict[str, str]
    batch_page_threshold: int
    role_validation: str
    prose: str


@dataclass
class CostConfig:
    cost_per_1m_in: float
    cost_per_1m_out: float
    cache_discount_multiplier: float


@dataclass
class CallCost:
    in_tokens: int
    out_tokens: int
    cached_tokens: int
    thoughts_tokens: int
    call_cost: float


# ==========================================
# TYPE CONFIG RESOLUTION
# ==========================================
def _substitute_env(value: Any) -> Any:
    """Recursively substitutes ${VAR_NAME} placeholders from the environment."""
    if isinstance(value, str):
        return Template(value).safe_substitute(os.environ)
    if isinstance(value, dict):
        return {k: _substitute_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_env(v) for v in value]
    return value


def resolve_prompt_path(requested_name: str) -> Path:
    """Finds the .pmt file for the requested record type, falling back to DEFAULT_TYPE."""
    requested = (requested_name or "").strip() or DEFAULT_TYPE
    if not requested.lower().endswith(".pmt"):
        requested += ".pmt"

    available = {p.name.lower(): p for p in PROMPTS_DIR.glob("*.pmt")} if PROMPTS_DIR.is_dir() else {}

    match = available.get(requested.lower())
    if match:
        return match

    fallback = available.get(DEFAULT_TYPE.lower())
    if fallback:
        return fallback

    raise FileNotFoundError(
        f"Could not find record type '{requested}' or fallback '{DEFAULT_TYPE}' in {PROMPTS_DIR}"
    )


def load_event_types() -> Dict[str, Dict[str, str]]:
    """Loads the toolbox-wide fact/event vocabulary from FactTypes.json."""
    data = json.loads(FACT_TYPES_PATH.read_text(encoding="utf-8"))
    merged: Dict[str, Dict[str, str]] = {}
    for bucket in ("person", "family"):
        for name, entry in data.get(bucket, {}).items():
            merged[name] = {"id_prefix": f"{entry['gedcom_tag']}-"}
    return merged


def parse_type_config(pmt_path: Path) -> TypeConfig:
    """Parses a .pmt file's YAML front matter and prose body."""
    raw = pmt_path.read_text(encoding="utf-8")
    stripped = raw.lstrip()

    front_matter: Dict[str, Any] = {}
    prose = raw

    if stripped.startswith(FRONT_MATTER_DELIM):
        parts = stripped.split(FRONT_MATTER_DELIM, 2)
        if len(parts) >= 3:
            front_matter = yaml.safe_load(parts[1]) or {}
            prose = parts[2]

    front_matter = _substitute_env(front_matter)

    return TypeConfig(
        name=pmt_path.stem,
        event_types=load_event_types(),
        roles=front_matter.get("roles", {}),
        defaults=front_matter.get("defaults", {}),
        extra_fields=front_matter.get("extra_fields", {}),
        metadata_fields=front_matter.get("metadata_fields", {}),
        field_remap=front_matter.get("field_remap", {}),
        batch_page_threshold=int(front_matter.get("batch_page_threshold", BATCH_PAGE_THRESHOLD)),
        role_validation=front_matter.get("role_validation", "closed"),
        prose=prose.strip(),
    )


# ==========================================
# SCHEMA MERGING
# ==========================================
def build_merged_schema(core_schema: Dict[str, Any],
                        extra_fields: Dict[str, List[Dict[str, str]]]) -> Dict[str, Any]:
    """Deep-copies the universal core schema and injects a record type's extra fields."""
    merged = copy.deepcopy(core_schema)

    def inject(container: Dict[str, Any], fields: List[Dict[str, str]]) -> None:
        properties = container.setdefault("properties", {})
        for f in fields:
            if f.get("type") == "enum":
                properties[f["name"]] = {"type": "string", "enum": f.get("choices", []), "nullable": True}
            elif f.get("type") == "dict":
                properties[f["name"]] = {"type": "object", "nullable": True}
            else:
                properties[f["name"]] = {"type": f.get("type", "string"), "nullable": True}

    record_props = merged["properties"]["sheets"]["items"]["properties"]["records"]["items"]["properties"]
    inject(record_props["type_specific_fields"], extra_fields.get("record", []))

    participant_props = record_props["participants"]["items"]["properties"]
    inject(participant_props["type_specific_fields"], extra_fields.get("participant", []))

    return merged


# ==========================================
# PROMPT BUILDING
# ==========================================
def optimize_image(image_path: str, max_dimension: int = 2048) -> Image.Image:
    """Downscale an image before sending it to the API, to cut token costs."""
    img = Image.open(image_path)
    img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
    return img


def build_vocabulary_summary(type_cfg: TypeConfig) -> str:
    """Auto-generates the valid event_type/role_name vocabulary lines."""
    event_type_names = ", ".join(sorted(type_cfg.event_types.keys()))

    role_context_by_name: Dict[str, Optional[str]] = {}
    for r in type_cfg.roles.values():
        name = r.get("name")
        if name and name not in role_context_by_name:
            role_context_by_name[name] = r.get("context")
    role_lines = [f"{name} ({context})" if context else name
                  for name, context in sorted(role_context_by_name.items())]
    role_names = ", ".join(role_lines)

    if type_cfg.role_validation == "open":
        # Census.pmt's open mode: the 9-name list is not exhaustive - a role outside it
        # (e.g. Boarder, Roomer) must be recorded verbatim as an association, never
        # coerced into one of the family roles (see the sub-project 2 design spec).
        role_name_line = dedent(f"""\
            - role_name: use one of these when it applies - {role_names} - and record the
              source's own relationship term verbatim when none of these fit (e.g. Boarder,
              Servant, Roomer, Grandson). Only the listed names carry a family relationship;
              anything else is recorded as-is and treated as an association, not a family link.""")
    else:
        role_name_line = dedent(f"""\
            - role_name (choose exactly one per participant - where a role's own meaning
              depends on the event type, that's noted in parentheses): {role_names}""")

    return dedent(f"""
        VALID VOCABULARY FOR THIS RECORD TYPE:
        - event_type (choose exactly one): {event_type_names}
    """).strip() + "\n" + role_name_line


def get_cached_system_instruction(type_cfg: TypeConfig) -> str:
    """The static system-instruction ruleset for this record type."""
    return f"{type_cfg.prose}\n\n{build_vocabulary_summary(type_cfg)}\n\n{UNIVERSAL_PROMPT_SUFFIX}"


def get_dynamic_prompt(type_cfg: TypeConfig, file_metadata: Dict[str, str]) -> str:
    """Per-file metadata block appended to the cached prompt."""
    combined = {**type_cfg.metadata_fields, **file_metadata}
    lines = "\n".join(f"{k}: {v}," for k, v in combined.items())
    return f"\nMetadata Context:\n{lines}\n"


def build_continuation_context(pending_record: Optional[Dict[str, Any]]) -> str:
    """Formats the previous image's cut-off last record as extra prompt context."""
    if not pending_record:
        return ""
    participants_summary = [
        {"role_name": p.get("role_name"), "std_given": p.get("std_given"), "std_surname": p.get("std_surname")}
        for p in pending_record.get("participants", [])
    ]
    return dedent(f"""

        CONTINUATION FROM PREVIOUS IMAGE:
        The record below was cut off at the bottom of the previous image and may continue
        at the top of THIS one. If it does, merge it into ONE complete record reusing its
        record_number/year, and set that record's continues_from_previous_image: true. If
        nothing on this image continues it, ignore this block entirely.

        record_number: {pending_record.get("record_number")}
        year: {pending_record.get("year")}
        event_type: {pending_record.get("event_type")}
        transcription so far: {pending_record.get("citation_text")}
        translation so far: {pending_record.get("citation_details")}
        participants captured so far: {json.dumps(participants_summary, ensure_ascii=False)}
    """)


# ==========================================
# CONTENT-TRANSPORT ROUTING
# ==========================================
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".tiff", ".tif")


def has_usable_text_layer(pdf_path: Union[str, Path], sample_pages: int = 3,
                          min_alpha_ratio: float = 0.5, min_chars: int = 40) -> bool:
    """Probes a PDF's first few pages for a genuine, non-garbage text layer."""
    # noinspection broad-exception
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            sampled = "".join((page.extract_text() or "") for page in pdf.pages[:sample_pages])
    except Exception:
        return False

    if len(sampled) < min_chars:
        return False

    alpha_count = sum(1 for c in sampled if c.isalpha())
    return (alpha_count / len(sampled)) >= min_alpha_ratio


def get_pdf_page_count(pdf_path: Union[str, Path]) -> int:
    with pdfplumber.open(str(pdf_path)) as pdf:
        return len(pdf.pages)


def optimize_pdf_for_upload(file_path: Path, compression_level: int = 2) -> Path:
    """Runs PDFix's lossless structural optimization against a throwaway temp copy."""
    tmp_fd, tmp_path_str = tempfile.mkstemp(suffix=".pdf", prefix="pdfix_upload_")
    os.close(tmp_fd)
    tmp_path = Path(tmp_path_str)
    try:
        shutil.copy2(file_path, tmp_path)
        params = COMPRESSION_PARAMS.get(compression_level, COMPRESSION_PARAMS[2])
        optimize_pdf(str(tmp_path), params)
        return tmp_path
    except Exception:
        tmp_path.unlink(missing_ok=True)
        return file_path


def build_content_part_for_file(client: genai.Client, file_path: Path) -> Tuple[str, Any]:
    """Classifies a source file and returns (mode, content_part)."""
    suffix = file_path.suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        return "image", optimize_image(str(file_path))

    if suffix == ".pdf":
        if has_usable_text_layer(file_path):
            with pdfplumber.open(str(file_path)) as pdf:
                text = "\n".join(page.extract_text() or "" for page in pdf.pages)
            return "pdf_text", text

        compression_level = int(os.getenv("PALEOGRAPHER_PDF_COMPRESSION_LEVEL", "2"))
        optimized_path = optimize_pdf_for_upload(file_path, compression_level)
        try:
            uploaded = client.files.upload(file=str(optimized_path))
        finally:
            if optimized_path != file_path:
                optimized_path.unlink(missing_ok=True)
        return "pdf_native", uploaded

    raise ValueError(f"Unsupported file type: {file_path}")


# ==========================================
# COST TRACKING
# ==========================================
def compute_call_cost(usage_metadata: Any, cost_cfg: CostConfig) -> CallCost:
    """Computes the dollar cost of one API call from its usage_metadata."""
    if usage_metadata is None:
        return CallCost(0, 0, 0, 0, 0.0)

    in_tokens = getattr(usage_metadata, "prompt_token_count", 0) or 0
    out_tokens = getattr(usage_metadata, "candidates_token_count", 0) or 0
    cached_tokens = getattr(usage_metadata, "cached_content_token_count", 0) or 0
    thoughts_tokens = getattr(usage_metadata, "thoughts_token_count", 0) or 0

    cache_rate = cost_cfg.cost_per_1m_in * cost_cfg.cache_discount_multiplier
    cost_cached = (cached_tokens / 1_000_000) * cache_rate
    cost_in = (in_tokens / 1_000_000) * cost_cfg.cost_per_1m_in
    cost_out = ((out_tokens + thoughts_tokens) / 1_000_000) * cost_cfg.cost_per_1m_out

    return CallCost(in_tokens, out_tokens, cached_tokens, thoughts_tokens, cost_cached + cost_in + cost_out)


# ==========================================
# SYNCHRONOUS RETRY LOOP
# ==========================================
def run_with_retries(call_fn: Callable[[], Any], max_retries: int = 10, max_json_retries: int = 3) -> Any:
    """Calls call_fn() until it succeeds, retrying on transient errors."""
    attempts = 0
    json_attempts = 0

    while attempts < max_retries:
        try:
            return call_fn()
        except json.JSONDecodeError as e:
            json_attempts += 1
            if json_attempts >= max_json_retries:
                raise RuntimeError(
                    f"Malformed JSON {max_json_retries}x in a row (likely a systemic issue, not transient): {e}"
                ) from e
            print(f"   [!] Malformed JSON generated. Retrying... ({e})", end="", flush=True)
            time.sleep(2)
            attempts += 1
        except genai.errors.ClientError as api_error:
            error_msg = str(api_error)
            if "PerDay" in error_msg:
                raise DailyQuotaExhausted(error_msg) from api_error
            if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg or agy_client.is_quota_or_rate_limit(error_msg):
                match = re.search(r"retry in (\d+\.?\d*)s", error_msg)
                if match:
                    wait_time = float(match.group(1)) + 1.5
                else:
                    wait_time = agy_client.parse_quota_reset_wait_seconds(error_msg)
                    if wait_time is None:
                        wait_time = 35.0 * float(2 ** attempts)
                agy_client.pause_for_quota_reset(wait_time, reason=f"Rate limit hit ({error_msg[:60]})")
                attempts += 1
            elif "500" in error_msg or "503" in error_msg or "504" in error_msg:
                print(f"   [!] Google Server Error ({error_msg[:30]}). Sleeping 5s...", end="", flush=True)
                time.sleep(5)
                attempts += 1
            else:
                raise

    raise RuntimeError(f"Exhausted all {max_retries} retries")


# ==========================================
# BATCH API (for large multi-page documents)
# ==========================================
def build_batch_request(model_id: str, contents: list, source_file: str,
                        gen_config_kwargs: Dict[str, Any]) -> types.InlinedRequest:
    """Builds one Gemini batch request."""
    return types.InlinedRequest(
        model=model_id, contents=contents, metadata={"source_file": source_file},
        config=genai.types.GenerateContentConfig(**gen_config_kwargs),
    )


def submit_batch_job(client: genai.Client, model_id: str, requests: List[types.InlinedRequest],
                     display_name: str = "paleographer-batch") -> str:
    """Submits a list of pre-built requests as one Gemini batch job."""
    job = client.batches.create(model=model_id, src=requests,
                                config=types.CreateBatchJobConfig(display_name=display_name))
    if not job.name:
        raise RuntimeError("Gemini created a batch job but returned no job name.")
    return job.name


def check_batch_jobs(client: genai.Client, pending: List[dict]) -> Tuple[List[dict], List[dict]]:
    """Checks every pending batch job entry against Gemini."""
    completed, still_pending = [], []
    for entry in pending:
        job = client.batches.get(name=entry["job_name"])
        if job.state == types.JobState.JOB_STATE_SUCCEEDED:
            completed.append(entry)
        elif job.state in (types.JobState.JOB_STATE_FAILED, types.JobState.JOB_STATE_CANCELLED,
                           types.JobState.JOB_STATE_EXPIRED):
            print(f"   [!] Batch job {entry['job_name']} ended in state {job.state}; "
                  "not retried automatically, resubmit manually if needed.")
        else:
            still_pending.append(entry)
    return completed, still_pending


def retrieve_batch_results(client: genai.Client, job_name: str) -> List[Tuple[str, Any]]:
    """Fetches a completed batch job's results."""
    job = client.batches.get(name=job_name)
    results: List[Tuple[str, Any]] = []
    dest = job.dest
    if dest is None or not dest.inlined_responses:
        return results
    for r in dest.inlined_responses:
        source_file = (r.metadata or {}).get("source_file", "")
        if r.error:
            print(f"   [!] Batch item for {source_file} failed: {r.error}")
            continue
        results.append((source_file, r.response))
    return results


# ==========================================
# CONTEXT CACHING
# ==========================================
def create_context_cache(client: genai.Client, model_id: str, system_instruction: str,
                         ttl_seconds: int = 86400) -> Optional[str]:
    """Uploads the system instruction as a Gemini Context Cache."""
    try:
        cache = client.caches.create(
            model=model_id,
            config=genai.types.CreateCachedContentConfig(system_instruction=system_instruction,
                                                         ttl=f"{ttl_seconds}s"),
        )
        return cache.name
    except Exception as e:
        print(f"Warning: Failed to create cache. Proceeding without it. Error: {e}")
        return None


def delete_context_cache(client: genai.Client, cache_name: str) -> None:
    try:
        client.caches.delete(name=cache_name)
    except Exception as e:
        print(f"Warning: Failed to delete cache {cache_name} (it will expire on its own via TTL). Error: {e}")


# ==========================================
# DEBUG MODE HELPERS
# ==========================================
def strip_markdown_fences(text: str) -> str:
    """Removes ```json ... ``` (or bare ```) code fences some models add."""
    backticks = "`" * 3
    if text.startswith(backticks):
        pattern = r"^" + backticks + r"(?:json)?\s*|\s*" + backticks + r"$"
        return re.sub(pattern, "", text.strip())
    return text


def debug_schema_suffix(schema: Dict[str, Any]) -> str:
    """Debug mode schema appended as text when thinking_config is active."""
    return ("\n\nOUTPUT FORMAT: Respond with ONLY raw JSON matching this schema, no markdown code "
            f"fences, no commentary before or after:\n{json.dumps(schema)}")


def build_debug_generation_config() -> Dict[str, Any]:
    return dict(thinking_config=genai.types.ThinkingConfig(include_thoughts=True))


# ==============================================================================
# AGY ENGINE (folded from agy_engine.py)
# ==============================================================================

# Paleographer's own default model for the agy backend.
DEFAULT_MODEL = "gemini-3.1-pro-high"

DEFAULT_MAX_RETRIES = 5
DEFAULT_BACKOFF_SECONDS = 5.0


# ==========================================
# PDF RASTERIZATION
# ==========================================
def rasterize_pdf_to_images(pdf_path: Path, max_dimension: int = 2048,
                            resolution: int = 200) -> List[Image.Image]:
    """One PIL Image per page, via pdfplumber's page.to_image()."""
    images: List[Image.Image] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            page_image = page.to_image(resolution=resolution)
            img = page_image.original.convert("RGB")
            img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
            images.append(img)
    return images


# ==========================================
# EXTRACTION CALL
# ==========================================
def call_agy_extract(images: List[Image.Image], schema: Dict[str, Any], prompt_text: str,
                     model: str = DEFAULT_MODEL,
                     cli_bin: str = agy_client.DEFAULT_CLI_BIN,
                     timeout_seconds: int = agy_client.DEFAULT_TIMEOUT_SECONDS) -> agy_client.AgyStructuredResult:
    """Provisions a fresh scratch dir, saves images, calls agy_client.call_agy_structured."""
    if not images:
        raise ValueError("call_agy_extract requires at least one image")

    scratch_dir = Path(tempfile.mkdtemp(prefix="paleographer_agy_"))
    try:
        filenames = []
        for index, img in enumerate(images, start=1):
            filename = f"page_{index:03d}.jpg"
            img.convert("RGB").save(scratch_dir / filename, "JPEG", quality=90)
            filenames.append(filename)

        if len(filenames) == 1:
            file_instruction = f"The file to process is staged in your workspace directory as: {filenames[0]}."
        else:
            file_instruction = (
                f"The files to process are staged in your workspace directory, in page "
                f"order, as: {', '.join(filenames)}."
            )
        full_prompt = (
            f"{prompt_text}\n\n{file_instruction} Open/view "
            f"{'it' if len(filenames) == 1 else 'them, in order,'} and produce the JSON "
            f"output now, matching the schema exactly."
        )

        return agy_client.call_agy_structured(
            workspace_dir=scratch_dir, model=model, prompt=full_prompt, schema=schema,
            cli_bin=cli_bin, timeout_seconds=timeout_seconds,
        )
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)


# ==========================================
# CHUNKED EXTRACTION (large multi-page documents)
# ==========================================
DEFAULT_CHUNK_SIZE = 10


def _agy_pop_trailing_cutoff_record(sheets: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Same logic as pop_trailing_cutoff_record below, operating at chunk scope."""
    if not sheets:
        return None
    last_sheet = sheets[-1]
    records = last_sheet.get("records", [])
    if not records or not records[-1].get("continues_on_next_image"):
        return None
    record = records.pop()
    record["_pending_sheet_info"] = {"page_id": last_sheet.get("page_id"),
                                     "document_metadata": last_sheet.get("document_metadata")}
    return record


def _agy_consumed_leading_continuation(sheets: List[Dict[str, Any]]) -> bool:
    """Chunk-scoped equivalent of consumed_leading_continuation below."""
    if not sheets:
        return False
    first_records = sheets[0].get("records", [])
    return bool(first_records and first_records[0].get("continues_from_previous_image"))


def _agy_reattach_leftover_record(sheets: List[Dict[str, Any]], leftover: Dict[str, Any]) -> None:
    """Chunk-scoped equivalent of reattach_leftover_record below."""
    sheet_info = leftover.pop("_pending_sheet_info", {}) or {}
    sheets.insert(0, {"page_id": sheet_info.get("page_id", ""),
                      "document_metadata": sheet_info.get("document_metadata", {}), "records": [leftover]})


def _consolidate_chunked_result(all_sheets: List[Dict[str, Any]], collection_title: Optional[str],
                                schema: Dict[str, Any], model: str, cli_bin: str,
                                timeout_seconds: int) -> agy_client.AgyStructuredResult:
    """Final pass over the full concatenated result from every chunk."""
    scratch_dir = Path(tempfile.mkdtemp(prefix="paleographer_agy_consolidate_"))
    try:
        records_path = scratch_dir / "extracted_records.json"
        records_path.write_text(
            json.dumps({"collection_title": collection_title, "sheets": all_sheets}, ensure_ascii=False),
            encoding="utf-8",
        )
        prompt = (
            "The file extracted_records.json in your workspace directory contains records "
            "already extracted from a multi-page document, processed in sequential "
            "page-order sections due to its length. Read it, then review the FULL set for "
            "consistency:\n"
            "- If any two records actually describe the SAME application (e.g. duplicated "
            "across a section boundary), merge them into one record, keeping the most "
            "complete data from either.\n"
            "- Do not invent, drop, or renumber any distinct record that is genuinely "
            "separate - only merge genuine duplicates.\n"
            "- Preserve every field exactly as given except where merging duplicates "
            "requires combining two records' data.\n\n"
            "Output the final, reconciled JSON now, matching the schema exactly."
        )
        return agy_client.call_agy_structured(
            workspace_dir=scratch_dir, model=model, prompt=prompt, schema=schema,
            cli_bin=cli_bin, timeout_seconds=timeout_seconds,
        )
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)


def call_agy_extract_chunked(images: List[Image.Image], schema: Dict[str, Any], prompt_text: str,
                             model: str = DEFAULT_MODEL,
                             cli_bin: str = agy_client.DEFAULT_CLI_BIN,
                             timeout_seconds: int = agy_client.DEFAULT_TIMEOUT_SECONDS,
                             chunk_size: int = DEFAULT_CHUNK_SIZE) -> agy_client.AgyStructuredResult:
    """For documents with more pages than one agy call can reliably hold: splits images
    into chunk_size-page groups and processes sequentially with page continuity threaded
    between chunks, then runs one final consolidation pass."""
    if len(images) <= chunk_size:
        return call_agy_extract(images, schema, prompt_text, model=model, cli_bin=cli_bin,
                                timeout_seconds=timeout_seconds)

    chunks = [images[i:i + chunk_size] for i in range(0, len(images), chunk_size)]
    all_sheets: List[Dict[str, Any]] = []
    pending_continuation: Optional[Dict[str, Any]] = None
    collection_title: Optional[str] = None
    usage_totals = {"input_tokens": 0, "output_tokens": 0, "thinking_tokens": 0,
                    "cache_read_tokens": 0, "total_tokens": 0}

    def _add_usage(usage: agy_client.AgyUsage) -> None:
        usage_totals["input_tokens"] += usage.input_tokens
        usage_totals["output_tokens"] += usage.output_tokens
        usage_totals["thinking_tokens"] += usage.thinking_tokens
        usage_totals["cache_read_tokens"] += usage.cache_read_tokens
        usage_totals["total_tokens"] += usage.total_tokens

    for chunk_index, chunk_images in enumerate(chunks, start=1):
        print(f"   [agy] section {chunk_index}/{len(chunks)} ({len(chunk_images)} page(s))...",
              end="", flush=True)
        chunk_prompt = (
            f"{prompt_text}\n\nNOTE: This is section {chunk_index} of {len(chunks)} of a "
            f"longer multi-page document, processed in sequential page-order sections "
            f"due to its length. Apply the same PAGE CONTINUITY rules across this section "
            f"boundary as you would between any two consecutive images."
        )
        chunk_prompt += build_continuation_context(pending_continuation)

        def call_fn(imgs=chunk_images, prm=chunk_prompt) -> agy_client.AgyStructuredResult:
            return call_agy_extract(imgs, schema, prm, model=model, cli_bin=cli_bin,
                                    timeout_seconds=timeout_seconds)

        chunk_result = run_with_agy_retries(call_fn)
        print(" done.", flush=True)
        _add_usage(chunk_result.usage)
        if collection_title is None:
            collection_title = chunk_result.structured_output.get("collection_title")

        chunk_sheets = chunk_result.structured_output.get("sheets", [])
        if pending_continuation is not None and not _agy_consumed_leading_continuation(chunk_sheets):
            _agy_reattach_leftover_record(chunk_sheets, pending_continuation)
        pending_continuation = _agy_pop_trailing_cutoff_record(chunk_sheets)
        all_sheets.extend(chunk_sheets)

    if pending_continuation is not None:
        _agy_reattach_leftover_record(all_sheets, pending_continuation)

    unconsolidated_output = {"collection_title": collection_title, "sheets": all_sheets}

    print(f"   [agy] consolidating {len(chunks)} section(s)...", end="", flush=True)

    def consolidation_call_fn() -> agy_client.AgyStructuredResult:
        return _consolidate_chunked_result(all_sheets, collection_title, schema, model,
                                           cli_bin, timeout_seconds)

    try:
        final_result = run_with_agy_retries(consolidation_call_fn)
    except RuntimeError as e:
        print(f" FAILED ({e}) - using unconsolidated per-section result instead.", flush=True)
        return agy_client.AgyStructuredResult(
            structured_output=unconsolidated_output,
            usage=agy_client.AgyUsage(**usage_totals),
        )

    print(" done.", flush=True)
    _add_usage(final_result.usage)

    return agy_client.AgyStructuredResult(
        structured_output=final_result.structured_output,
        usage=agy_client.AgyUsage(**usage_totals),
    )


# ==========================================
# RETRY POLICY
# ==========================================
def run_with_agy_retries(call_fn: Callable[[], Any], max_retries: int = DEFAULT_MAX_RETRIES,
                         backoff_seconds: float = DEFAULT_BACKOFF_SECONDS) -> Any:
    """Retries agy_client.AgyCallError with linear backoff."""
    last_error: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        try:
            return call_fn()
        except agy_client.AgyBinaryNotFoundError as e:
            raise RuntimeError(str(e)) from e
        except agy_client.AgyCallError as e:
            last_error = e
            err_msg = str(e)
            if agy_client.is_quota_or_rate_limit(err_msg):
                wait_time = agy_client.parse_quota_reset_wait_seconds(err_msg)
                if wait_time is not None and wait_time > 0:
                    agy_client.pause_for_quota_reset(wait_time, reason=f"agy quota limit hit: {err_msg[:80]}")
                    continue
                else:
                    pause_wait = 30.0 * float(2 ** (attempt - 1))
                    agy_client.pause_for_quota_reset(pause_wait, reason=f"agy rate limit hit: {err_msg[:80]}")
                    continue

            if attempt < max_retries:
                wait = backoff_seconds * attempt
                print(f"   [!] agy call failed (attempt {attempt}/{max_retries}): {e} "
                      f"Retrying in {wait:.0f}s...", flush=True)
                time.sleep(wait)
    raise RuntimeError(f"agy call failed after {max_retries} attempts: {last_error}") from last_error


# ==========================================
# COST ADAPTATION
# ==========================================
def adapt_agy_usage_to_call_cost(usage: agy_client.AgyUsage) -> CallCost:
    """Maps agy's usage shape onto CallCost so record_cost/print_cost_line treat both
    engines uniformly. call_cost is always 0.0 (subscription-covered)."""
    return CallCost(
        in_tokens=usage.input_tokens,
        out_tokens=usage.output_tokens,
        cached_tokens=usage.cache_read_tokens,
        thoughts_tokens=usage.thinking_tokens,
        call_cost=0.0,
    )


# ==============================================================================
# PALEOGRAPHER CONFIGURATION
# ==============================================================================

# EXTRACTION_ENGINE picks which backend actually performs the AI extraction: "agy" (the
# default) shells out to the Antigravity CLI, subscription-covered rather than metered
# per-token; "api" uses the direct google-genai SDK against GEMINI_API_KEY. Read early
# since it decides whether a genai client is even constructed below.
EXTRACTION_ENGINE: str = (os.getenv("EXTRACTION_ENGINE", "agy") or "agy").strip().lower()
if EXTRACTION_ENGINE not in ("api", "agy"):
    raise RuntimeError(f"Unknown EXTRACTION_ENGINE '{EXTRACTION_ENGINE}' - expected 'api' or 'agy'.")

# Only constructed for the api engine - the agy engine never calls
# build_content_part_for_file at all (rasterization replaces it for both images and
# PDFs), so client is never touched/dereferenced on that path regardless of file type.
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY")) if EXTRACTION_ENGINE == "api" else None

# ==========================================
# CONFIGURATION
# ==========================================
RECORD_TYPE_NAME = os.getenv("PALEOGRAPHER_RECORD_TYPE", "")
COLLECTION_TITLE = os.getenv("VOLUME_TITLE")
VOLUME_NUM = os.getenv("VOLUME_NUM", "")

TYPE_CFG = parse_type_config(resolve_prompt_path(RECORD_TYPE_NAME))


def resolve_setting(generic_key: str, default: str = "") -> str:
    """Resolves a generic runtime setting via the active record type's own field_remap
    table, falling back to reading generic_key directly."""
    for prefixed_key, target in TYPE_CFG.field_remap.items():
        if target == generic_key:
            val = os.getenv(prefixed_key, "")
            if val:
                return val
    return os.getenv(generic_key, default)


API_BUDGET: float = float(os.getenv("API_BUDGET", "5.00"))
COST_CFG = CostConfig(
    cost_per_1m_in=float(os.getenv("COST_PER_1M_INPUT", "0.075")),
    cost_per_1m_out=float(os.getenv("COST_PER_1M_OUTPUT", "0.30")),
    cache_discount_multiplier=float(os.getenv("CACHE_DISCOUNT_MULTIPLIER", "0.10")),
)

PROGRAM_DIR: Path = Path(os.getenv("PROGRAM_DIR", ""))
_MASTER_DB_NAME = resolve_setting("MASTER_DB_NAME")
if not _MASTER_DB_NAME:
    raise RuntimeError(
        "MASTER_DB_NAME resolved to an empty value (check the active record type's own "
        "MASTER_DB_NAME setting, e.g. CHURCH_MASTER_DB_NAME for Parish.pmt) - without it "
        "MASTER_DB would just be the JSON folder itself, not a file inside it.")
MASTER_DB: str = str(PROGRAM_DIR / os.getenv("JSON_DIR", "") / _MASTER_DB_NAME)
SOURCE_DIR: str = str(PROGRAM_DIR / resolve_setting("IMAGE_DIR"))

MODEL_ID: str = os.getenv("MODEL_NAME") or ""
if not MODEL_ID:
    raise RuntimeError("MODEL_NAME is not set. Check your .env configuration.")
DEBUG_FILE: Union[str, None] = sys.argv[1] if (
    len(sys.argv) > 1
    and sys.argv[1] not in ("extract", "enrich", "crosscheck", "partition", "resolve-names")
    and not sys.argv[1].startswith("-")
) else None

# agy-engine-only settings. AGY_MODEL_ID is always passed explicitly to every agy call,
# never left to agy's own default.
AGY_MODEL_ID: str = os.getenv("AGY_MODEL_NAME") or DEFAULT_MODEL
AGY_CLI_BIN: str = os.getenv("AGY_CLI_BIN") or agy_client.DEFAULT_CLI_BIN
AGY_TIMEOUT_SECONDS: int = int(os.getenv("AGY_TIMEOUT_SECONDS", str(agy_client.DEFAULT_TIMEOUT_SECONDS)))

SOURCE_SUFFIXES = IMAGE_SUFFIXES + (".pdf",)

with open(Path(__file__).resolve().parent / "schema.json", "r", encoding="utf-8") as _schema_file:
    CORE_SCHEMA: Dict[str, Any] = json.load(_schema_file)

SCHEMA: Dict[str, Any] = build_merged_schema(CORE_SCHEMA, TYPE_CFG.extra_fields)


# ==============================================================================
# RECORD POST-PROCESSING
# ==============================================================================
def finalize_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Applies every generic mechanical post-processing step to one extracted record."""
    derive_role_numbers(record, TYPE_CFG.roles)
    derive_role_semantics(record, TYPE_CFG.roles)
    normalization.derive_record_identity(record, TYPE_CFG.event_types)
    derive_suffixes(record, TYPE_CFG.roles)
    apply_defaults(record, TYPE_CFG.defaults.get("record", {}))

    if record.get("event_date"):
        record["event_date"] = normalization.parse_to_iso(record["event_date"])

    for participant in record.get("participants", []):
        participant["std_given"] = strip_diacritics(participant.get("std_given"))
        participant["std_surname"] = strip_diacritics(participant.get("std_surname"))
        if participant.get("birth_date"):
            participant["birth_date"] = normalization.parse_to_iso(participant["birth_date"])
        if participant.get("death_date"):
            participant["death_date"] = normalization.parse_to_iso(participant["death_date"])
        apply_defaults(participant, TYPE_CFG.defaults.get("participant", {}))

    return record


def finalize_page_data(page_data: Dict[str, Any]) -> Dict[str, Any]:
    for sheet in page_data.get("sheets", []):
        for record in sheet.get("records", []):
            finalize_record(record)
    # After every record has its record_id set, fold together any that share one.
    merge_same_claim_records(page_data.get("sheets", []))
    return page_data


def tag_document_metadata(page_data: Dict[str, Any], file_name: str, file_ext: str) -> None:
    for sheet in page_data.get("sheets", []):
        metadata = sheet.setdefault("document_metadata", {})
        metadata["file_name"] = file_name
        metadata["file_type"] = file_ext
        metadata["volume"] = VOLUME_NUM


# ==============================================================================
# MASTER DB HELPERS
# ==============================================================================
def load_master_db() -> Dict[str, Any]:
    if os.path.exists(MASTER_DB):
        with open(MASTER_DB, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("record_type_name", TYPE_CFG.name)
        return data
    return {"collection_title": COLLECTION_TITLE, "record_type_name": TYPE_CFG.name, "sheets": [],
            "total_spent": 0.0, "total_pages_processed": 0, "pending_batch_jobs": []}


def save_master_db(master_data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(MASTER_DB), exist_ok=True)
    with open(MASTER_DB, "w", encoding="utf-8") as f:
        json.dump(master_data, f, indent=2, ensure_ascii=False)


def get_processed_files(master_data: Dict[str, Any]) -> set:
    processed = set()
    for sheet in master_data.get("sheets", []):
        metadata = sheet.get("document_metadata", {})
        if isinstance(metadata, dict) and "file_name" in metadata:
            processed.add(metadata["file_name"])
    return processed


def merge_sheets(master_data: Dict[str, Any], new_sheets: List[Dict[str, Any]]) -> None:
    master_sheets = master_data.get("sheets")
    if isinstance(master_sheets, list):
        master_sheets.extend(new_sheets)
    else:
        master_data["sheets"] = new_sheets


def record_cost(master_data: Dict[str, Any], usage_metadata: Any) -> CallCost:
    if isinstance(usage_metadata, agy_client.AgyUsage):
        cost = adapt_agy_usage_to_call_cost(usage_metadata)
    else:
        cost = compute_call_cost(usage_metadata, COST_CFG)
    master_data["total_spent"] = float(master_data.get("total_spent", 0.0)) + cost.call_cost
    master_data["total_pages_processed"] = int(master_data.get("total_pages_processed", 0)) + 1
    return cost


def print_cost_line(master_data: Dict[str, Any], cost: CallCost) -> None:
    total_tokens = cost.cached_tokens + cost.in_tokens + cost.out_tokens + cost.thoughts_tokens
    print(f" DONE! | Cost: ${cost.call_cost:.4f}")
    print(f"      Tokens -> Cached: {cost.cached_tokens} | Input: {cost.in_tokens} | "
          f"Output: {cost.out_tokens} | Thinking: {cost.thoughts_tokens} = Total: {total_tokens}")

    if EXTRACTION_ENGINE == "agy":
        print("      Budget -> N/A (subscription backend, no per-call cost)")
        return

    total_spent = master_data["total_spent"]
    total_pages = master_data["total_pages_processed"]
    avg_cost = total_spent / total_pages if total_pages else 0.0

    load_dotenv(ROOT_ENV, override=True)
    live_budget = float(os.getenv("API_BUDGET", str(API_BUDGET)))
    remaining_budget = max(0.0, live_budget - total_spent)
    estimated_pages_left = math.floor(remaining_budget / avg_cost) if avg_cost > 0 else 0
    print(f"      Budget -> Total Spent: ${total_spent:.4f} | Est Pages Left: ~{estimated_pages_left}")


# ==============================================================================
# FILE CLASSIFICATION
# ==============================================================================
def list_source_files() -> List[str]:
    return sorted(f for f in os.listdir(SOURCE_DIR) if f.lower().endswith(SOURCE_SUFFIXES))


def is_batch_eligible(file_path: Path) -> bool:
    """A PDF crosses the batch threshold if it has more pages than the active type's
    (or engine's default) threshold. Images are never batch-eligible."""
    if file_path.suffix.lower() != ".pdf":
        return False
    return get_pdf_page_count(file_path) > TYPE_CFG.batch_page_threshold


# ==============================================================================
# SYNCHRONOUS PROCESSING
# ==============================================================================
def build_gen_config_kwargs(active_cache_name: Optional[str]) -> Dict[str, Any]:
    if DEBUG_FILE:
        return build_debug_generation_config()
    kwargs: Dict[str, Any] = dict(response_mime_type="application/json", response_schema=SCHEMA)
    if active_cache_name:
        kwargs["cached_content"] = active_cache_name
    return kwargs


def process_one_file_sync(filename: str, active_cache_name: Optional[str],
                          pending_continuation: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Processes one file synchronously. Returns a dict with page_data/usage_metadata on
    success, or None on failure. Raises DailyQuotaExhausted, which the caller must handle
    by stopping the run."""
    file_path = Path(SOURCE_DIR) / filename
    file_base = file_path.stem
    file_ext = file_path.suffix.upper().replace(".", "")
    if file_ext == "JPG":
        file_ext = "JPEG"
    pages_str = file_base.split("_")[-1]

    file_metadata = {"File": file_base, "Pages": pages_str}
    dynamic_prompt = get_dynamic_prompt(TYPE_CFG, file_metadata)
    dynamic_prompt += build_continuation_context(pending_continuation)

    if EXTRACTION_ENGINE == "agy":
        images = (rasterize_pdf_to_images(file_path) if file_path.suffix.lower() == ".pdf"
                  else [optimize_image(str(file_path))])
        full_prompt = get_cached_system_instruction(TYPE_CFG) + "\n\n" + dynamic_prompt

        def call_fn() -> Any:
            result = call_agy_extract_chunked(images, SCHEMA, full_prompt, model=AGY_MODEL_ID,
                                              cli_bin=AGY_CLI_BIN, timeout_seconds=AGY_TIMEOUT_SECONDS)
            return result.structured_output, result.usage

        try:
            page_data, usage_metadata = run_with_agy_retries(call_fn)
        except RuntimeError as e:
            print(f"\n[FAILED] {filename}: {e}")
            return None
    else:
        _, content_part = build_content_part_for_file(client, file_path)

        if DEBUG_FILE:
            prompt = get_cached_system_instruction(TYPE_CFG) + "\n\n" + dynamic_prompt
            prompt += debug_schema_suffix(SCHEMA)
        else:
            prompt = dynamic_prompt

        contents = [prompt, content_part]

        def call_fn() -> Any:
            response = client.models.generate_content(
                model=MODEL_ID, contents=contents,
                config=genai.types.GenerateContentConfig(**build_gen_config_kwargs(active_cache_name)),
            )

            if DEBUG_FILE:
                parts = (response.candidates[0].content.parts or []) if response.candidates and \
                    response.candidates[0].content else []
                thought_parts = [p.text for p in parts if getattr(p, "thought", False) and p.text]
                if thought_parts:
                    print("\n\n--- MODEL THINKING ---")
                    print("\n".join(thought_parts))
                    print("--- END THINKING ---\n")

            raw_text = strip_markdown_fences((response.text or "").strip())
            return json.loads(raw_text), response.usage_metadata

        try:
            page_data, usage_metadata = run_with_retries(call_fn)
        except RuntimeError as e:
            print(f"\n[FAILED] {filename}: {e}")
            return None

    page_data = finalize_page_data(page_data)
    tag_document_metadata(page_data, filename, file_ext)

    return {"page_data": page_data, "usage_metadata": usage_metadata}


def pop_trailing_cutoff_record(sheets: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """If the last record of the last sheet is flagged continues_on_next_image, pops it
    out and returns it. None if there's nothing pending."""
    if not sheets:
        return None
    last_sheet = sheets[-1]
    records = last_sheet.get("records", [])
    if not records or not records[-1].get("continues_on_next_image"):
        return None
    record = records.pop()
    record["_pending_sheet_info"] = {"page_id": last_sheet.get("page_id"),
                                     "document_metadata": last_sheet.get("document_metadata")}
    return record


def consumed_leading_continuation(sheets: List[Dict[str, Any]]) -> bool:
    """True if the first record of the first sheet merged the pending continuation context."""
    if not sheets:
        return False
    first_records = sheets[0].get("records", [])
    return bool(first_records and first_records[0].get("continues_from_previous_image"))


def reattach_leftover_record(sheets: List[Dict[str, Any]], leftover: Dict[str, Any]) -> None:
    """Nothing on the new image continued the pending record - save it back as its own
    one-record sheet, ahead of this file's own sheets."""
    sheet_info = leftover.pop("_pending_sheet_info", {}) or {}
    sheets.insert(0, {"page_id": sheet_info.get("page_id", ""),
                      "document_metadata": sheet_info.get("document_metadata", {}), "records": [leftover]})


def run_synchronous_batch(files: List[str], master_data: Dict[str, Any]) -> None:
    total_files = len(files)
    active_cache_name = None
    pending_continuation: Optional[Dict[str, Any]] = None

    if not DEBUG_FILE and files:
        print(f"Found {total_files} file(s) to process synchronously.")
        if EXTRACTION_ENGINE == "api":
            print("Creating Context Cache for System Instructions to reduce costs...")
            active_cache_name = create_context_cache(
                client, MODEL_ID, get_cached_system_instruction(TYPE_CFG))
            if active_cache_name:
                print(f"Cache created successfully: {active_cache_name}\n")

    try:
        for index, filename in enumerate(files, start=1):
            print(f"[{index}/{total_files}] Processing {filename} with {MODEL_ID}...", end="", flush=True)
            try:
                result = process_one_file_sync(filename, active_cache_name, pending_continuation)
            except DailyQuotaExhausted:
                print("\n\n[FATAL ERROR] Daily Quota Exhausted.")
                print("Progress saved. Exiting script to prevent infinite crashing.")
                if not DEBUG_FILE and pending_continuation is not None:
                    reattach_leftover_record(master_data.setdefault("sheets", []), pending_continuation)
                    save_master_db(master_data)
                return
            except Exception as e:
                print(f" LOCAL ERROR! Details: {e}")
                continue

            if result is None:
                continue

            cost = record_cost(master_data, result["usage_metadata"])
            sheets = result["page_data"].get("sheets", [])

            if DEBUG_FILE:
                print("--- EXTRACTED JSON (not saved to master DB) ---")
                print(json.dumps(result["page_data"], indent=2, ensure_ascii=False))
                print_cost_line(master_data, cost)
            else:
                if pending_continuation is not None and not consumed_leading_continuation(sheets):
                    reattach_leftover_record(sheets, pending_continuation)
                pending_continuation = pop_trailing_cutoff_record(sheets)
                merge_sheets(master_data, sheets)
                save_master_db(master_data)
                print_cost_line(master_data, cost)

        if not DEBUG_FILE and pending_continuation is not None:
            reattach_leftover_record(master_data.setdefault("sheets", []), pending_continuation)
            save_master_db(master_data)
    finally:
        if active_cache_name:
            delete_context_cache(client, active_cache_name)
            print(f"\nDeleted context cache: {active_cache_name}")


# ==============================================================================
# BATCH PROCESSING (large multi-page documents)
# ==============================================================================
def run_batch_mode(files: List[str], master_data: Dict[str, Any]) -> None:
    """Batch-eligible files go through Gemini's Batch API instead of the synchronous
    loop. One run both retrieves any previously-submitted job and submits newly-pending
    files, then returns without blocking on Gemini."""
    pending_jobs = master_data.setdefault("pending_batch_jobs", [])

    if pending_jobs:
        completed, still_pending = check_batch_jobs(client, pending_jobs)
        master_data["pending_batch_jobs"] = still_pending

        for entry in completed:
            print(f"Retrieving results for completed batch job {entry['job_name']}...")
            for source_file, response in retrieve_batch_results(client, entry["job_name"]):
                try:
                    raw_text = strip_markdown_fences((response.text or "").strip())
                    page_data = json.loads(raw_text)
                except (json.JSONDecodeError, AttributeError) as e:
                    print(f"   [!] Could not parse batch result for {source_file}: {e}")
                    continue

                page_data = finalize_page_data(page_data)
                file_ext = Path(source_file).suffix.upper().replace(".", "")
                tag_document_metadata(page_data, source_file, file_ext)
                merge_sheets(master_data, page_data.get("sheets", []))
                cost = record_cost(master_data, response.usage_metadata)
                print(f"Merged {source_file}: cost ${cost.call_cost:.4f}")

            save_master_db(master_data)

    if not files:
        if not master_data.get("pending_batch_jobs"):
            print("No new or pending batch files.")
        return

    print(f"Submitting {len(files)} file(s) as a new batch job...")
    system_instruction = get_cached_system_instruction(TYPE_CFG)
    requests = []
    for filename in files:
        file_path = Path(SOURCE_DIR) / filename
        _, content_part = build_content_part_for_file(client, file_path)
        file_metadata = {"File": file_path.stem, "Pages": str(get_pdf_page_count(file_path))}
        prompt = system_instruction + "\n\n" + get_dynamic_prompt(TYPE_CFG, file_metadata)
        gen_config_kwargs: Dict[str, Any] = dict(response_mime_type="application/json", response_schema=SCHEMA)
        requests.append(build_batch_request(MODEL_ID, [prompt, content_part], filename,
                                            gen_config_kwargs))

    job_name = submit_batch_job(client, MODEL_ID, requests)
    master_data.setdefault("pending_batch_jobs", []).append(
        {"job_name": job_name, "submitted_at": time.strftime("%Y-%m-%d %H:%M:%S"), "file_names": files})
    save_master_db(master_data)
    print(f"Submitted batch job '{job_name}' for {len(files)} file(s). Check back later; "
          "re-run this same step to retrieve results once Gemini finishes.")


# ==============================================================================
# SCRIP ENRICHMENT & PARTITIONING (folded from Commissioner / DEV)
# ==============================================================================

def resolve_pid_from_filename(file_name: str) -> Optional[str]:
    """Returns the PID embedded in a locally-chosen filename, or None."""
    if not file_name:
        return None
    match = re.search(r"_(\d+)\.pdf$", file_name, re.IGNORECASE)
    return match.group(1) if match else None


def resolve_pid_for_sheet_or_record(sheet: Dict[str, Any], record: Dict[str, Any]) -> Optional[str]:
    """Resolves the PID for a record from record.lac_pid, document_metadata.pid, or file_name."""
    if record.get("lac_pid"):
        return str(record["lac_pid"]).strip()
    meta = sheet.get("document_metadata") or {}
    if meta.get("pid"):
        return str(meta["pid"]).strip()
    file_name = meta.get("file_name") or (record.get("document_metadata") or {}).get("file_name", "")
    return resolve_pid_from_filename(file_name)


UNKNOWN_COLLECTION_LABEL = "Unclassified (no rg_series_code or inferable volume yet)"


def classify_sheet_collection(sheet: Dict[str, Any]) -> Tuple[Optional[str], str, Optional[str], str]:
    """Determines collection for a sheet."""
    records = sheet.get("records", [])
    if records:
        record = records[0]
        series_code = (record.get("type_specific_fields") or {}).get("rg_series_code")
        res = voyageur_lac.collection_for_series_code(series_code)
        if res:
            return res

    meta = sheet.get("document_metadata", {})
    res = voyageur_lac.collection_for_volume(meta.get("volume"), meta.get("volume_range"))
    if res:
        return res

    return None, UNKNOWN_COLLECTION_LABEL, None, "unclassified"


def partition_json_by_collection(data: Dict[str, Any], output_dir: Path) -> Dict[str, Path]:
    """Partitions a master Scrip dataset into separate JSON files grouped by official LAC collection."""
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
    """Expands a range like '2234 to 2241' into individual numbers."""
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
    """Builds search queries to find a claim's related documents from LAC."""
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
    queries = build_claim_search_queries(record)
    return queries[0] if queries else None


def cross_check_claim_record(record: Dict[str, Any], cookies: Dict[str, str], media_dir: str
                             ) -> Dict[str, Any]:
    """Single-claim cross-check: resolves this Scrip record's own PID, searches for related documents,
    and downloads everything found into record['source_documents']."""
    file_name = (record.get("document_metadata") or {}).get("file_name", "")
    own_pid = resolve_pid_from_filename(file_name)

    if own_pid:
        record["lac_pid"] = own_pid
        try:
            own_bundle = voyageur_lac.download_pid_bundle(
                own_pid, media_dir, document_type_override=record.get("document_type")
            )
            record["lac_catalog_title"] = fix_mojibake(own_bundle["lac_catalog_title"])
            type_fields = record.setdefault("type_specific_fields", {})
            if own_bundle.get("reel_numbers"):
                type_fields["reel_numbers"] = ", ".join(own_bundle["reel_numbers"])
            if own_bundle.get("series_code"):
                type_fields["rg_series_code"] = own_bundle["series_code"]

            parsed = extract_citation_fields(record["lac_catalog_title"])
            for k, v in parsed.items():
                if not type_fields.get(k):
                    type_fields[k] = v
            resolve_maiden_name_for_record(record)
        except lac_client.LacCallError as e:
            record.setdefault("review_reason", []).append(f"Paleographer: failed to fetch own PID {own_pid}: {e}")

    queries = build_claim_search_queries(record)
    if not queries:
        record.setdefault("review_reason", []).append(
            "Paleographer: no claim_number/affidavit_number/scrip_number/e-number available to search LAC with")
        return record

    all_found_pids = set()
    for query in queries:
        try:
            all_found_pids.update(lac_client.search(query, cookies))
        except lac_client.LacSearchAuthError as e:
            record.setdefault("review_reason", []).append(f"Paleographer: search cookie expired/invalid: {e}")
            break
        except lac_client.LacCallError as e:
            record.setdefault("review_reason", []).append(f"Paleographer: search failed for {query!r}: {e}")

    related_pids = sorted(p for p in all_found_pids if p != own_pid)
    source_documents = record.setdefault("source_documents", [])
    for related_pid in related_pids:
        try:
            bundle = voyageur_lac.download_pid_bundle(related_pid, media_dir)
            source_documents.extend(bundle["source_documents"])
        except lac_client.LacCallError as e:
            record.setdefault("review_reason", []).append(
                f"Paleographer: failed to fetch related PID {related_pid}: {e}")

    return record


def enrich_record_from_lac_metadata(sheet: Dict[str, Any], record: Dict[str, Any],
                                    metadata: "lac_client.RecordMetadata") -> None:
    """Applies live LAC catalog metadata to a sheet and record."""
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

    parsed = extract_citation_fields(clean_title)
    for k, v in parsed.items():
        if not type_fields.get(k):
            type_fields[k] = v

    if not record.get("record_number") or record.get("record_number") == "0-0-0":
        record["record_number"] = build_composite_record_number(type_fields, record.get("lac_pid", ""))

    fix_all_participant_names_in_record(record)
    resolve_maiden_name_for_record(record)


def enrich_json_data(data: Dict[str, Any], checkpoint_path: Optional[str] = None,
                     delay_seconds: float = 0.4, limit: Optional[int] = None,
                     checkpoint_every: int = 50) -> Dict[str, Any]:
    """Iterates through all records in a JSON dataset, fetching live LAC metadata for each PID."""
    checkpoint = voyageur_lac.load_checkpoint(checkpoint_path) if checkpoint_path else {
        "done_pids": [], "failed_pids": {}
    }
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
                voyageur_lac.save_checkpoint(checkpoint_path, checkpoint)
                since_checkpoint = 0

            if delay_seconds > 0:
                time.sleep(delay_seconds)

    if checkpoint_path:
        checkpoint["done_pids"] = sorted(done)
        checkpoint["failed_pids"] = failed
        voyageur_lac.save_checkpoint(checkpoint_path, checkpoint)

    return data


def resolve_json_input(json_file: str, json_dir: str) -> Path:
    """Resolves the active JSON dataset path."""
    if os.path.isabs(json_file):
        return Path(json_file)
    p = Path(json_file)
    if p.is_file():
        return p
    return Path(json_dir) / json_file


# ==============================================================================
# MAIN EXECUTION
# ==============================================================================
def main() -> None:
    mode = "extract"
    if len(sys.argv) > 1 and sys.argv[1] in ("enrich", "crosscheck", "partition", "resolve-names"):
        mode = sys.argv[1]

    if mode != "extract":
        import argparse
        parser = argparse.ArgumentParser(description="Paleographer: AI-driven extraction & document enrichment.")
        parser.add_argument("mode", choices=["enrich", "crosscheck", "partition", "resolve-names"],
                            help="Operating mode")
        parser.add_argument("--json", dest="json_path", default=None,
                            help="Path to JSON dataset (for enrich, crosscheck, partition, resolve-names)")
        parser.add_argument("--delay", type=float, default=0.4, help="Delay in seconds between requests (for enrich)")
        parser.add_argument("--limit", type=int, default=None, help="Limit number of records to process (for enrich)")
        parser.add_argument("--output-dir", default=None, help="Output directory for partitioned datasets")
        parser.add_argument("--cookie-file", default=voyageur_lac.COOKIE_FILE,
                            help="Path to browser cookies file for LAC search (for crosscheck)")
        args, _ = parser.parse_known_args()

        if args.mode == "crosscheck":
            target = resolve_json_input(args.json_path or os.getenv("MASTER_DB", "master_database.json"),
                                        os.getenv("OUTPUT_DIR", str(Path(__file__).resolve().parent / "output")))
            print(f"Cross-checking claims in dataset: {target}...")
            try:
                cookies = voyageur_lac.load_cookies(args.cookie_file)
            except (FileNotFoundError, ValueError) as e:
                print(f"[FATAL ERROR] {e} Search LAC once in a real browser, then paste its Cookie header "
                      f"into that file.")
                return
            with open(target, "r", encoding="utf-8") as f:
                data = json.load(f)
            for sheet in data.get("sheets", []):
                for record in sheet.get("records", []):
                    cross_check_claim_record(record, cookies, voyageur_lac.MEDIA_DIR)
            with open(target, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"Cross-check complete: {target}")
            return

        if args.mode == "enrich":
            target = resolve_json_input(args.json_path or os.getenv("MASTER_DB", "master_database.json"),
                                        os.getenv("OUTPUT_DIR", str(Path(__file__).resolve().parent / "output")))
            print(f"Enriching dataset: {target}...")
            with open(target, "r", encoding="utf-8") as f:
                data = json.load(f)
            enrich_json_data(data, delay_seconds=args.delay, limit=args.limit)
            with open(target, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"Enrichment complete: {target}")
            return

        if args.mode == "partition":
            target = resolve_json_input(args.json_path or os.getenv("MASTER_DB", "master_database.json"),
                                        os.getenv("OUTPUT_DIR", str(Path(__file__).resolve().parent / "output")))
            out_dir = Path(args.output_dir) if args.output_dir else target.parent / "partitioned"
            print(f"Partitioning dataset {target} into {out_dir}...")
            with open(target, "r", encoding="utf-8") as f:
                data = json.load(f)
            written = partition_json_by_collection(data, out_dir)
            print(f"Partitioned into {len(written)} collections in {out_dir}")
            for k, p in written.items():
                print(f" - {k}: {p.name}")
            return

        if args.mode == "resolve-names":
            target = resolve_json_input(args.json_path or os.getenv("MASTER_DB", "master_database.json"),
                                        os.getenv("OUTPUT_DIR", str(Path(__file__).resolve().parent / "output")))
            print(f"Resolving names in dataset: {target}...")
            with open(target, "r", encoding="utf-8") as f:
                data = json.load(f)
            count = resolve_dataset_maiden_names(data)
            with open(target, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"Resolved maiden/dit names for {count} records in {target}")
            return

    # Standard extraction mode
    if EXTRACTION_ENGINE == "agy":
        print("Verifying Antigravity CLI authentication...")
        if not agy_client.check_or_prompt_auth(AGY_MODEL_ID, cli_bin=AGY_CLI_BIN):
            print("[FATAL ERROR] Could not authenticate with agy. Run the 'Test Agy "
                  "Connection' action in Scriptorium's Global Settings, or `agy` "
                  "directly, to sign in, then try again.")
            return
        print("Authenticated.\n")

    master_data = load_master_db()
    all_files = list_source_files()

    if DEBUG_FILE:
        if DEBUG_FILE not in all_files:
            print(f"[DEBUG MODE] '{DEBUG_FILE}' not found in {SOURCE_DIR}. Aborting.")
            return
        print(f"[DEBUG MODE] Processing ONLY '{DEBUG_FILE}' with thinking enabled. "
              f"Nothing will be saved to {MASTER_DB}.\n")
        run_synchronous_batch([DEBUG_FILE], master_data)
        return

    processed_files = get_processed_files(master_data)
    already_in_batch = {fn for entry in master_data.get("pending_batch_jobs", [])
                        for fn in entry.get("file_names", [])}
    pending_files = [f for f in all_files if f not in processed_files and f not in already_in_batch]

    if EXTRACTION_ENGINE == "agy":
        if pending_files:
            run_synchronous_batch(pending_files, master_data)
        else:
            print("No new files to process.")
        return

    sync_files: List[str] = []
    batch_files: List[str] = []
    for filename in pending_files:
        file_path = Path(SOURCE_DIR) / filename
        (batch_files if is_batch_eligible(file_path) else sync_files).append(filename)

    if batch_files or master_data.get("pending_batch_jobs"):
        run_batch_mode(batch_files, master_data)

    if sync_files:
        run_synchronous_batch(sync_files, master_data)
    elif not batch_files and not master_data.get("pending_batch_jobs"):
        print("No new files to process.")


if __name__ == "__main__":
    main()
