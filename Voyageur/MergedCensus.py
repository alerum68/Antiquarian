"""
Voyageur/MergedCensus.py

Merges two already-gathered census JSON files - one from Ancestry.com (Voyageur/A.py),
one from FamilySearch (Voyageur/FS.py's build_census_json path) - covering the same
physical census page(s), into a single JSON in the same {census_year, location, pages:
[...]} shape Archivist.py's census flavor already reads.

Per-field, Ancestry's own reading wins on conflict (its index is consistently the richer
of the two - see ROADMAP.md), but FamilySearch's differing reading is never silently
dropped: it's recorded as a review reason on that person instead. Every merged person
carries both source IDs (Ancestry's `pid`, FamilySearch's `fsftid`) and both web links
(`extracted_url`, `familysearch_url`), so Archivist's citation builder can cite one NARA
holding while still linking back to both indexes.

Usage: python MergedCensus.py <ancestry.json> <familysearch.json> [output.json]

This is the merge logic only - pasting both source URLs and running both live gathers
automatically is a deferred follow-up (see ROADMAP.md).
"""
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def normalize_locator(value) -> str:
    """Collapses a column name or locator value to bare alphanumerics, so "Birth Year" /
    "birth_year" / "BirthYear" (or "Roll 123" / "roll_123" / "123") all line up as the same
    field/value across two independently-built indexes. Coerces via str(value or '') so it's
    safe on both column names (always strings) and locator values (which may be None)."""
    return re.sub(r'[^a-z0-9]', '', str(value or '').lower())


def page_core_locator(page: dict) -> Tuple[str, str]:
    ed = normalize_locator(page.get('enumeration_district'))
    page_number = normalize_locator(page.get('page_number'))
    return ed, page_number


def page_roll_locator(page: dict) -> str:
    return normalize_locator(page.get('roll_number'))


def match_pages(ancestry_pages: List[dict], fs_pages: List[dict]
                ) -> List[Tuple[Optional[dict], Optional[dict]]]:
    """Pairs pages sharing an (ED, page_number) locator. Roll number is checked as a
    tie-breaker, only when *both* sides actually have it - FamilySearch's census citation
    never exposes film_number at all (see ROADMAP.md), only roll_number, so film_number
    isn't checked here at all (comparing Ancestry's film_number against FamilySearch's
    roll_number - two different identifiers - produced a false mismatch and split what
    should have been one merged page into two unmerged ones - confirmed live). Ancestry
    pages drive the pairing since Ancestry is the primary/richer source; any FamilySearch
    page with no match is appended afterward as its own (None, fs_page) pair so its data is
    never silently dropped."""
    fs_by_core: Dict[Tuple[str, str], List[dict]] = {}
    for fp in fs_pages:
        core = page_core_locator(fp)
        if any(core):
            fs_by_core.setdefault(core, []).append(fp)

    matched_fs_ids = set()
    pairs: List[Tuple[Optional[dict], Optional[dict]]] = []
    for ap in ancestry_pages:
        core = page_core_locator(ap)
        ap_roll = page_roll_locator(ap)
        match = None
        for fp in fs_by_core.get(core, []) if any(core) else []:
            if id(fp) in matched_fs_ids:
                continue
            fp_roll = page_roll_locator(fp)
            if ap_roll and fp_roll and ap_roll != fp_roll:
                continue
            match = fp
            break
        pairs.append((ap, match))
        if match is not None:
            matched_fs_ids.add(id(match))

    for fp in fs_pages:
        if id(fp) not in matched_fs_ids:
            pairs.append((None, fp))

    return pairs


def person_line_number(person: dict) -> str:
    columns = person.get('columns', {})
    for key, value in columns.items():
        if re.search(r'\bline\b', key, re.IGNORECASE):
            return normalize_locator(value)
    return ""


def match_people(ancestry_people: List[dict], fs_people: List[dict]
                 ) -> List[Tuple[Optional[dict], Optional[dict]]]:
    """Matches people within an already-paired page by Line Number - the one locator both
    sides reliably carry (real or synthesized, see ROADMAP.md), unlike name/date fields
    which two independent indexing efforts can transcribe differently."""
    fs_by_line: Dict[str, dict] = {}
    for fp in fs_people:
        line = person_line_number(fp)
        if line:
            fs_by_line[line] = fp

    matched_fs_ids = set()
    pairs: List[Tuple[Optional[dict], Optional[dict]]] = []
    for ap in ancestry_people:
        line = person_line_number(ap)
        fp = fs_by_line.get(line) if line else None
        pairs.append((ap, fp))
        if fp is not None:
            matched_fs_ids.add(id(fp))

    for fp in fs_people:
        if id(fp) not in matched_fs_ids:
            pairs.append((None, fp))

    return pairs


def merge_columns(a_columns: dict, fs_columns: dict) -> Tuple[dict, List[str]]:
    """Union merge of two per-person column dicts, keyed by normalized field name. Ancestry
    wins when both sides disagree; FamilySearch's differing reading is never dropped, just
    reported back as a conflict description for the caller to flag."""
    a_by_norm = {normalize_locator(k): (k, v) for k, v in a_columns.items()}
    fs_by_norm = {normalize_locator(k): (k, v) for k, v in fs_columns.items()}

    merged: dict = dict(a_columns)
    conflicts: List[str] = []

    for norm_key, (fs_orig_key, fs_val) in fs_by_norm.items():
        fs_val_clean = str(fs_val).strip() if fs_val is not None else ""
        if not fs_val_clean:
            continue

        if norm_key in a_by_norm:
            a_orig_key, a_val = a_by_norm[norm_key]
            a_val_clean = str(a_val).strip() if a_val is not None else ""
            if not a_val_clean:
                merged[a_orig_key] = fs_val
            elif a_val_clean != fs_val_clean:
                conflicts.append(f'{a_orig_key}: Ancestry="{a_val_clean}" vs FamilySearch="{fs_val_clean}"')
        else:
            merged[fs_orig_key] = fs_val

    return merged, conflicts


def merge_person(a_person: Optional[dict], fs_person: Optional[dict]) -> dict:
    if a_person is not None and fs_person is not None:
        merged_columns, conflicts = merge_columns(a_person.get('columns', {}), fs_person.get('columns', {}))
        merged = dict(a_person)
        merged['columns'] = merged_columns
        merged['fsftid'] = fs_person.get('fsftid', '')
        person_ark = fs_person.get('person_ark', '')
        merged['familysearch_url'] = f"https://www.familysearch.org/ark:/61903/1:1:{person_ark}" if person_ark else ''
        if conflicts:
            merged['columns']['_MergeReviewReason'] = "; ".join(f"Field conflict: {c}" for c in conflicts)
        return merged

    if fs_person is None:
        merged = dict(a_person)
        merged['columns'] = dict(a_person.get('columns', {}))
        merged['fsftid'] = ''
        merged['familysearch_url'] = ''
        merged['columns']['_MergeReviewReason'] = "No FamilySearch match found for this person"
        return merged

    # a_person is None: a FamilySearch-only row, no Ancestry counterpart at this line number.
    # dict(fs_person) above already copies its own 'pid' through as-is - no need to re-set it.
    merged = dict(fs_person)
    merged['columns'] = dict(fs_person.get('columns', {}))
    merged['extracted_url'] = ''
    person_ark = fs_person.get('person_ark', '')
    merged['familysearch_url'] = f"https://www.familysearch.org/ark:/61903/1:1:{person_ark}" if person_ark else ''
    merged['columns']['_MergeReviewReason'] = "No Ancestry match found for this person"
    return merged


def merge_page(a_page: Optional[dict], fs_page: Optional[dict]) -> dict:
    if a_page is not None and fs_page is not None:
        merged = dict(a_page)
        pairs = match_people(a_page.get('people', []), fs_page.get('people', []))
        merged['people'] = [merge_person(ap, fp) for ap, fp in pairs]
        return merged

    if fs_page is None:
        merged = dict(a_page)
        merged['people'] = [merge_person(p, None) for p in a_page.get('people', [])]
        return merged

    # a_page is None: a FamilySearch-only page, no Ancestry counterpart gathered at all.
    merged = dict(fs_page)
    merged['people'] = [merge_person(None, p) for p in fs_page.get('people', [])]
    return merged


def merge_census(ancestry_data: dict, fs_data: dict) -> dict:
    page_pairs = match_pages(ancestry_data.get('pages', []), fs_data.get('pages', []))
    merged_pages = [merge_page(ap, fp) for ap, fp in page_pairs]

    return {
        'census_year': ancestry_data.get('census_year') or fs_data.get('census_year', ''),
        'location': ancestry_data.get('location') or fs_data.get('location', ''),
        'pages': merged_pages,
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
