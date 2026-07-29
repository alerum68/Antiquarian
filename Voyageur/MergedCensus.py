"""
Voyageur/MergedCensus.py

Merges two already-gathered, already-normalized census documents - one from Ancestry.com
(Voyageur/A.py), one from FamilySearch (Voyageur/FS.py's census path) - covering the same
physical census page(s), into a single document in the shared record schema (see
census_schema.py). Both inputs are normalized at gather time before this ever runs, so this
merge step works entirely on the shared schema's field names, never on either source's own
raw column headers.

Per-field, Ancestry's own reading wins on conflict (its index is consistently the richer
of the two - see ROADMAP.md), but FamilySearch's differing reading is never silently
dropped: it's recorded as a review reason on that participant instead. Every merged
participant carries both sources' own identifiers/links (Ancestry's pid, FamilySearch's
fsftid/person_ark/familysearch_url) under type_specific_fields, so Archivist's citation
builder can cite one holding while still linking back to both indexes.

Ancestry's own household grouping (which record/family a person belongs to) is treated as
authoritative when both sides gathered the same sheet - matching happens at the flattened
participant level (by Line Number, the one locator both independently-built indexes
reliably carry), then merged participants are reattached to Ancestry's own record
structure, not re-grouped from scratch.

Usage: python MergedCensus.py <ancestry.json> <familysearch.json> [output.json]
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


def match_sheets(ancestry_sheets: List[dict], fs_sheets: List[dict]
                 ) -> List[Tuple[Optional[dict], Optional[dict]]]:
    """Pairs sheets sharing an (ED, page_number) locator. Roll number is checked as a
    tie-breaker only when *both* sides actually have it (FamilySearch's census citation
    never exposes film_number, only roll_number - comparing the wrong pair of fields
    produced a false mismatch in the pre-normalization version of this merge). Ancestry
    drives the pairing since it's the primary/richer source; an unmatched FamilySearch
    sheet is appended afterward as its own (None, fs_sheet) pair, never dropped."""
    fs_by_core: Dict[Tuple[str, str], List[dict]] = {}
    for fs in fs_sheets:
        ed, page_number, _ = _sheet_locators(fs)
        if ed or page_number:
            fs_by_core.setdefault((ed, page_number), []).append(fs)

    matched_fs_ids = set()
    pairs: List[Tuple[Optional[dict], Optional[dict]]] = []
    for a_sheet in ancestry_sheets:
        ed, page_number, a_roll = _sheet_locators(a_sheet)
        match = None
        for fs in fs_by_core.get((ed, page_number), []):
            if id(fs) in matched_fs_ids:
                continue
            _, _, fs_roll = _sheet_locators(fs)
            if a_roll and fs_roll and a_roll != fs_roll:
                continue
            match = fs
            break
        pairs.append((a_sheet, match))
        if match is not None:
            matched_fs_ids.add(id(match))

    for fs in fs_sheets:
        if id(fs) not in matched_fs_ids:
            pairs.append((None, fs))

    return pairs


def _flatten_participants(sheet: dict) -> List[Tuple[dict, dict]]:
    """Every (record, participant) pair on a sheet, in order - the unit this merge
    actually matches on, since a household grouping (which record a person belongs to)
    isn't guaranteed to agree between two independently-gathered sources."""
    return [(record, p) for record in sheet.get('records', []) for p in record.get('participants', [])]


def participant_line_number(participant: dict) -> str:
    return normalize_locator(participant.get('type_specific_fields', {}).get('line_number'))


def match_participants(a_pairs: List[Tuple[dict, dict]], fs_pairs: List[Tuple[dict, dict]]
                       ) -> List[Tuple[Optional[Tuple[dict, dict]], Optional[Tuple[dict, dict]]]]:
    """Matches participants within an already-paired sheet by Line Number - the one
    locator both sides reliably carry (real or synthesized - see ROADMAP.md), unlike
    name/date fields which two independent indexing efforts can transcribe differently."""
    fs_by_line: Dict[str, Tuple[dict, dict]] = {}
    for fs_pair in fs_pairs:
        line = participant_line_number(fs_pair[1])
        if line:
            fs_by_line[line] = fs_pair

    matched_fs_ids = set()
    pairs = []
    for a_pair in a_pairs:
        line = participant_line_number(a_pair[1])
        fs_pair = fs_by_line.get(line) if line else None
        pairs.append((a_pair, fs_pair))
        if fs_pair is not None:
            matched_fs_ids.add(id(fs_pair[1]))

    for fs_pair in fs_pairs:
        if id(fs_pair[1]) not in matched_fs_ids:
            pairs.append((None, fs_pair))

    return pairs


# Flat participant fields where an FS-only reading is worth adopting when Ancestry has
# nothing, and where a differing reading is worth flagging rather than silently keeping
# only Ancestry's - the identity/vital fields, not internal bookkeeping (role_number,
# type_specific_fields, facts - those are handled separately, not field-by-field here).
MERGE_FIELDS = ('std_given', 'std_surname', 'sex', 'age', 'birth_place', 'race',
                'occupation', 'residence', 'role_name')


def merge_participant(a_participant: Optional[dict], fs_participant: Optional[dict]) -> dict:
    if a_participant is not None and fs_participant is None:
        merged = dict(a_participant)
        merged.setdefault('type_specific_fields', {})
        merged['type_specific_fields'] = dict(merged['type_specific_fields'])
        merged['type_specific_fields']['merge_review_reason'] = "No FamilySearch match found for this person"
        merged['review'] = True
        return merged

    if a_participant is None:
        merged = dict(fs_participant)
        merged['type_specific_fields'] = dict(merged.get('type_specific_fields', {}))
        merged['type_specific_fields']['merge_review_reason'] = "No Ancestry match found for this person"
        merged['review'] = True
        return merged

    merged = dict(a_participant)
    merged['type_specific_fields'] = dict(a_participant.get('type_specific_fields', {}))
    conflicts: List[str] = []
    for field in MERGE_FIELDS:
        a_val = str(a_participant.get(field) or '').strip()
        fs_val = str(fs_participant.get(field) or '').strip()
        if not fs_val:
            continue
        if not a_val:
            merged[field] = fs_participant.get(field)
        elif a_val != fs_val:
            conflicts.append(f'{field}: Ancestry="{a_val}" vs FamilySearch="{fs_val}"')

    # Both sources' own identifiers/links are always carried through, not just on
    # conflict - Archivist's citation builder wants both regardless of field agreement.
    for key in ('fsftid', 'person_ark', 'familysearch_url'):
        if fs_participant.get('type_specific_fields', {}).get(key):
            merged['type_specific_fields'][key] = fs_participant['type_specific_fields'][key]

    if conflicts:
        merged['type_specific_fields']['merge_review_reason'] = "; ".join(f"Field conflict: {c}" for c in conflicts)
        merged['review'] = True

    return merged


def merge_sheet(a_sheet: Optional[dict], fs_sheet: Optional[dict]) -> dict:
    if a_sheet is not None and fs_sheet is not None:
        a_pairs = _flatten_participants(a_sheet)
        fs_pairs = _flatten_participants(fs_sheet)
        matched = match_participants(a_pairs, fs_pairs)

        merged = dict(a_sheet)
        merged_records = [dict(r) for r in a_sheet.get('records', [])]
        record_index = {id(r): i for i, r in enumerate(a_sheet.get('records', []))}
        for i in range(len(merged_records)):
            merged_records[i] = dict(merged_records[i])
            merged_records[i]['participants'] = []

        unmatched_fs_only: List[dict] = []
        for a_pair, fs_pair in matched:
            if a_pair is not None:
                record, a_participant = a_pair
                fs_participant = fs_pair[1] if fs_pair else None
                merged_participant = merge_participant(a_participant, fs_participant)
                merged_records[record_index[id(record)]]['participants'].append(merged_participant)
            else:
                unmatched_fs_only.append(merge_participant(None, fs_pair[1]))

        if unmatched_fs_only:
            # FamilySearch-only people with no Ancestry counterpart at all on this sheet -
            # never dropped, attached as their own record so they still reach Archivist.
            merged_records.append({
                "record_id": None, "page": a_sheet.get("page_id", ""),
                "record_number": "", "event_type": "Census (family)", "year": "",
                "event_date": "", "event_place": "", "english_translation": "",
                "original_transcription": "", "review": True,
                "review_reason": "FamilySearch-only participants with no Ancestry match on this sheet.",
                "continues_on_next_image": False, "continues_from_previous_image": False,
                "type_specific_fields": {}, "participants": unmatched_fs_only,
            })

        merged['records'] = merged_records
        return merged

    if fs_sheet is None:
        merged = dict(a_sheet)
        merged['records'] = [dict(r, participants=[merge_participant(p, None) for p in r.get('participants', [])])
                             for r in a_sheet.get('records', [])]
        return merged

    # a_sheet is None: a FamilySearch-only sheet, no Ancestry counterpart gathered at all.
    merged = dict(fs_sheet)
    merged['records'] = [dict(r, participants=[merge_participant(None, p) for p in r.get('participants', [])])
                         for r in fs_sheet.get('records', [])]
    return merged


def merge_census(ancestry_doc: dict, fs_doc: dict) -> dict:
    sheet_pairs = match_sheets(ancestry_doc.get('sheets', []), fs_doc.get('sheets', []))
    merged_sheets = [merge_sheet(a, fs) for a, fs in sheet_pairs]

    return {
        'collection_title': ancestry_doc.get('collection_title') or fs_doc.get('collection_title', ''),
        'record_type_name': ancestry_doc.get('record_type_name') or fs_doc.get('record_type_name', ''),
        'citation': ancestry_doc.get('citation') or fs_doc.get('citation', {}),
        'sheets': merged_sheets,
    }


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: python MergedCensus.py <ancestry.json> <familysearch.json> [output.json]")
        sys.exit(1)

    ancestry_path = Path(sys.argv[1])
    fs_path = Path(sys.argv[2])
    output_path = Path(sys.argv[3]) if len(sys.argv) > 3 else \
        ancestry_path.with_name(ancestry_path.stem + "_merged.json")

    ancestry_data = json.loads(ancestry_path.read_text(encoding="utf-8"))
    fs_data = json.loads(fs_path.read_text(encoding="utf-8"))

    merged = merge_census(ancestry_data, fs_data)

    output_path.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[System] Merged census written to {output_path}")


if __name__ == "__main__":
    main()
