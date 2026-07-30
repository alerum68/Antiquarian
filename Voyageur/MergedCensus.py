"""
Voyageur/MergedCensus.py

Merges two already-gathered, already-normalized census documents - one from Ancestry.com
(Voyageur/A.py), one from FamilySearch (Voyageur/FS.py's census path) - covering the same
physical census page(s), into a single document in the shared record schema (see
census_schema.py). Both inputs are normalized at gather time before this ever runs, so this
merge step works entirely on the shared schema's field names, never on either source's own
raw column headers.

Which source is "primary" is configurable (MERGE_PRIMARY_PROVIDER, default Ancestry - see
Merged.py): per-field, the primary source's own reading wins on conflict, but the secondary
source's differing reading is never silently dropped - it's recorded as a review reason on
that participant instead. Every merged participant carries both sources' own identifiers/
links (Ancestry's pid, FamilySearch's fsftid/person_ark/familysearch_url) under
type_specific_fields regardless of which is primary, so Archivist's citation builder can
cite one holding while still linking back to both indexes.

The primary source's own household grouping (which record/family a person belongs to) is
treated as authoritative when both sides gathered the same sheet - matching happens at the
flattened participant level (by Line Number, the one locator both independently-built
indexes reliably carry), then merged participants are reattached to the primary source's
own record structure, not re-grouped from scratch.

Usage: python MergedCensus.py <primary.json> <secondary.json> [output.json]
"""
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def normalize_locator(value) -> str:
    """Collapses a locator value to bare alphanumerics, so two independently-built
    indexes' minor formatting differences ("T624 1" vs "T624_1") still line up."""
    return re.sub(r'[^a-z0-9]', '', str(value or '').lower())


def _sheet_locators(sheet: dict) -> Tuple[str, str, str]:
    """(enumeration_district, page_number, roll_number) - every record on one sheet
    shares the same page-level locators (see census_schema.py), so the first record is
    representative. A sheet with no records at all has nothing to key on."""
    records = sheet.get('records', [])
    ts = records[0].get('type_specific_fields', {}) if records else {}
    return (normalize_locator(ts.get('enumeration_district')),
            normalize_locator(sheet.get('page_id')),
            normalize_locator(ts.get('roll_number')))


def match_sheets(primary_sheets: List[dict], secondary_sheets: List[dict]
                 ) -> List[Tuple[Optional[dict], Optional[dict]]]:
    """Pairs sheets sharing an (ED, page_number) locator. Roll number is checked as a
    tie-breaker only when *both* sides actually have it (FamilySearch's census citation
    never exposes film_number, only roll_number - comparing the wrong pair of fields
    produced a false mismatch in the pre-normalization version of this merge). The primary
    source drives the pairing; an unmatched secondary sheet is appended afterward as its
    own (None, secondary_sheet) pair, never dropped."""
    secondary_by_core: Dict[Tuple[str, str], List[dict]] = {}
    for sec in secondary_sheets:
        ed, page_number, _ = _sheet_locators(sec)
        if ed or page_number:
            secondary_by_core.setdefault((ed, page_number), []).append(sec)

    matched_secondary_ids = set()
    pairs: List[Tuple[Optional[dict], Optional[dict]]] = []
    for p_sheet in primary_sheets:
        ed, page_number, p_roll = _sheet_locators(p_sheet)
        match = None
        for sec in secondary_by_core.get((ed, page_number), []):
            if id(sec) in matched_secondary_ids:
                continue
            _, _, sec_roll = _sheet_locators(sec)
            if p_roll and sec_roll and p_roll != sec_roll:
                continue
            match = sec
            break
        pairs.append((p_sheet, match))
        if match is not None:
            matched_secondary_ids.add(id(match))

    for sec in secondary_sheets:
        if id(sec) not in matched_secondary_ids:
            pairs.append((None, sec))

    return pairs


def _flatten_participants(sheet: dict) -> List[Tuple[dict, dict]]:
    """Every (record, participant) pair on a sheet, in order - the unit this merge
    actually matches on, since a household grouping (which record a person belongs to)
    isn't guaranteed to agree between two independently-gathered sources."""
    return [(record, p) for record in sheet.get('records', []) for p in record.get('participants', [])]


def participant_line_number(participant: dict) -> str:
    return normalize_locator(participant.get('type_specific_fields', {}).get('line_number'))


def match_participants(primary_pairs: List[Tuple[dict, dict]], secondary_pairs: List[Tuple[dict, dict]]
                       ) -> List[Tuple[Optional[Tuple[dict, dict]], Optional[Tuple[dict, dict]]]]:
    """Matches participants within an already-paired sheet by Line Number - the one
    locator both sides reliably carry (real or synthesized - see ROADMAP.md), unlike
    name/date fields which two independent indexing efforts can transcribe differently."""
    secondary_by_line: Dict[str, Tuple[dict, dict]] = {}
    for sec_pair in secondary_pairs:
        line = participant_line_number(sec_pair[1])
        if line:
            secondary_by_line[line] = sec_pair

    matched_secondary_ids = set()
    pairs = []
    for p_pair in primary_pairs:
        line = participant_line_number(p_pair[1])
        sec_pair = secondary_by_line.get(line) if line else None
        pairs.append((p_pair, sec_pair))
        if sec_pair is not None:
            matched_secondary_ids.add(id(sec_pair[1]))

    for sec_pair in secondary_pairs:
        if id(sec_pair[1]) not in matched_secondary_ids:
            pairs.append((None, sec_pair))

    return pairs


# Flat participant fields where a secondary-only reading is worth adopting when the
# primary has nothing, and where a differing reading is worth flagging rather than
# silently keeping only the primary's - the identity/vital fields, not internal
# bookkeeping (role_number, type_specific_fields, facts - handled separately, not
# field-by-field here).
MERGE_FIELDS = ('std_given', 'std_surname', 'sex', 'age', 'birth_place', 'race',
                'occupation', 'residence', 'role_name')

# Every one of these is inherently source-specific (Ancestry only ever produces
# pid/extracted_url, FamilySearch only ever produces fsftid/person_ark/familysearch_url),
# so carrying all of them through from whichever side is secondary is always safe
# regardless of which real-world provider was chosen primary - a citation can always link
# back to both indexes no matter which one won on conflict.
IDENTIFIER_PASSTHROUGH_KEYS = ('pid', 'extracted_url', 'fsftid', 'person_ark', 'familysearch_url')


def merge_participant(primary: Optional[dict], secondary: Optional[dict],
                      primary_label: str, secondary_label: str) -> dict:
    if primary is not None and secondary is None:
        merged = dict(primary)
        merged.setdefault('type_specific_fields', {})
        merged['type_specific_fields'] = dict(merged['type_specific_fields'])
        merged['type_specific_fields']['merge_review_reason'] = f"No {secondary_label} match found for this person"
        merged['review'] = True
        return merged

    if primary is None:
        merged = dict(secondary)
        merged['type_specific_fields'] = dict(merged.get('type_specific_fields', {}))
        merged['type_specific_fields']['merge_review_reason'] = f"No {primary_label} match found for this person"
        merged['review'] = True
        return merged

    merged = dict(primary)
    merged['type_specific_fields'] = dict(primary.get('type_specific_fields', {}))
    conflicts: List[str] = []
    for field in MERGE_FIELDS:
        p_val = str(primary.get(field) or '').strip()
        s_val = str(secondary.get(field) or '').strip()
        if not s_val:
            continue
        if not p_val:
            merged[field] = secondary.get(field)
        elif p_val != s_val:
            conflicts.append(f'{field}: {primary_label}="{p_val}" vs {secondary_label}="{s_val}"')

    # Both sources' own identifiers/links are always carried through, not just on
    # conflict - Archivist's citation builder wants both regardless of field agreement.
    for key in IDENTIFIER_PASSTHROUGH_KEYS:
        if secondary.get('type_specific_fields', {}).get(key):
            merged['type_specific_fields'][key] = secondary['type_specific_fields'][key]

    if conflicts:
        merged['type_specific_fields']['merge_review_reason'] = "; ".join(f"Field conflict: {c}" for c in conflicts)
        merged['review'] = True

    return merged


def merge_sheet(primary_sheet: Optional[dict], secondary_sheet: Optional[dict],
                primary_label: str, secondary_label: str) -> dict:
    if primary_sheet is not None and secondary_sheet is not None:
        primary_pairs = _flatten_participants(primary_sheet)
        secondary_pairs = _flatten_participants(secondary_sheet)
        matched = match_participants(primary_pairs, secondary_pairs)

        merged = dict(primary_sheet)
        merged_records = [dict(r) for r in primary_sheet.get('records', [])]
        record_index = {id(r): i for i, r in enumerate(primary_sheet.get('records', []))}
        for i in range(len(merged_records)):
            merged_records[i] = dict(merged_records[i])
            merged_records[i]['participants'] = []

        unmatched_secondary_only: List[dict] = []
        for p_pair, sec_pair in matched:
            if p_pair is not None:
                record, p_participant = p_pair
                sec_participant = sec_pair[1] if sec_pair else None
                merged_participant = merge_participant(p_participant, sec_participant,
                                                       primary_label, secondary_label)
                merged_records[record_index[id(record)]]['participants'].append(merged_participant)
            else:
                unmatched_secondary_only.append(
                    merge_participant(None, sec_pair[1], primary_label, secondary_label))

        if unmatched_secondary_only:
            # Secondary-only people with no primary-source counterpart at all on this
            # sheet - never dropped, attached as their own record so they still reach
            # Archivist.
            merged_records.append({
                "record_id": None, "page": primary_sheet.get("page_id", ""),
                "record_number": "", "event_type": "Census (family)", "year": "",
                "event_date": "", "event_place": "", "english_translation": "",
                "original_transcription": "", "review": True,
                "review_reason": f"{secondary_label}-only participants with no {primary_label} match on this sheet.",
                "continues_on_next_image": False, "continues_from_previous_image": False,
                "type_specific_fields": {}, "participants": unmatched_secondary_only,
            })

        merged['records'] = merged_records
        return merged

    if secondary_sheet is None:
        merged = dict(primary_sheet)
        merged['records'] = [
            dict(r, participants=[merge_participant(p, None, primary_label, secondary_label)
                                  for p in r.get('participants', [])])
            for r in primary_sheet.get('records', [])]
        return merged

    # primary_sheet is None: a secondary-only sheet, no primary-source counterpart
    # gathered at all.
    merged = dict(secondary_sheet)
    merged['records'] = [
        dict(r, participants=[merge_participant(None, p, primary_label, secondary_label)
                              for p in r.get('participants', [])])
        for r in secondary_sheet.get('records', [])]
    return merged


def merge_census(primary_doc: dict, secondary_doc: dict,
                 primary_label: str = "Ancestry", secondary_label: str = "FamilySearch") -> dict:
    """Merges two already-normalized census documents. primary_doc's own reading wins on
    field conflicts and its household grouping is treated as authoritative - which real
    document that is depends on MERGE_PRIMARY_PROVIDER (see Merged.py), not a fixed source."""
    sheet_pairs = match_sheets(primary_doc.get('sheets', []), secondary_doc.get('sheets', []))
    merged_sheets = [merge_sheet(p, sec, primary_label, secondary_label) for p, sec in sheet_pairs]

    return {
        'collection_title': primary_doc.get('collection_title') or secondary_doc.get('collection_title', ''),
        'record_type_name': primary_doc.get('record_type_name') or secondary_doc.get('record_type_name', ''),
        'citation': primary_doc.get('citation') or secondary_doc.get('citation', {}),
        'sheets': merged_sheets,
    }


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: python MergedCensus.py <primary.json> <secondary.json> [output.json] "
              "[primary_label] [secondary_label]")
        sys.exit(1)

    primary_path = Path(sys.argv[1])
    secondary_path = Path(sys.argv[2])
    output_path = Path(sys.argv[3]) if len(sys.argv) > 3 else \
        primary_path.with_name(primary_path.stem + "_merged.json")
    primary_label = sys.argv[4] if len(sys.argv) > 4 else "Ancestry"
    secondary_label = sys.argv[5] if len(sys.argv) > 5 else "FamilySearch"

    primary_data = json.loads(primary_path.read_text(encoding="utf-8"))
    secondary_data = json.loads(secondary_path.read_text(encoding="utf-8"))

    merged = merge_census(primary_data, secondary_data, primary_label, secondary_label)

    output_path.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[System] Merged census written to {output_path}")


if __name__ == "__main__":
    main()
