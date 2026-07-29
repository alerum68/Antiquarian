"""Tests for MergedCensus.py's merge logic on the normalized shared schema."""
import MergedCensus


def _doc(sheets, **overrides):
    doc = {"collection_title": "1900 US Census", "record_type_name": "Census_1900",
           "citation": {}, "sheets": sheets}
    doc.update(overrides)
    return doc


def _sheet(page_id, records, ed="12", roll="T624_1"):
    for r in records:
        r.setdefault("type_specific_fields", {})
        r["type_specific_fields"].setdefault("enumeration_district", ed)
        r["type_specific_fields"].setdefault("roll_number", roll)
    return {"page_id": page_id, "document_metadata": {}, "records": records}


def _record(participants, **overrides):
    record = {"record_id": None, "page": "3", "record_number": "5", "event_type": "Census (family)",
              "year": "1900", "event_date": "", "event_place": "", "english_translation": "",
              "original_transcription": "", "review": False, "review_reason": None,
              "continues_on_next_image": False, "continues_from_previous_image": False,
              "type_specific_fields": {}, "participants": participants}
    record.update(overrides)
    return record


def _participant(line, given, surname, **overrides):
    p = {"role_number": None, "role_name": "Head", "std_given": given, "std_surname": surname,
         "raw_given": None, "raw_surname": None, "dit_name": None, "alternate_names": [],
         "prefix": None, "suffix": None, "sex": "M", "is_priest": False, "age": None,
         "age_unit": None, "occupation": None, "race": None, "religion": None, "residence": None,
         "birth_date": None, "birth_place": None, "death_date": None, "death_place": None,
         "review": False, "review_reason": None, "facts": [],
         "type_specific_fields": {"line_number": line}}
    p.update(overrides)
    return p


def test_matched_sheet_merges_participants_by_line_number_ancestry_wins_conflict():
    ancestry = _doc([_sheet("3", [_record([_participant("1", "Jean", "Gagnon", sex="M")])])])
    fs = _doc([_sheet("3", [_record([_participant("1", "Jean", "Gagnon", sex="F")])])])
    # Attach an fsftid onto the FS participant directly - that's what merge_participant
    # actually reads (regardless of any field conflict, both sources' own IDs carry through).
    fs["sheets"][0]["records"][0]["participants"][0]["type_specific_fields"]["fsftid"] = "ABCD-1"

    merged = MergedCensus.merge_census(ancestry, fs)
    participants = merged["sheets"][0]["records"][0]["participants"]
    assert len(participants) == 1
    p = participants[0]
    # Ancestry's "M" wins over FS's "F" - a conflict, so flagged for review.
    assert p["sex"] == "M"
    assert p["review"] is True
    assert "sex" in p["type_specific_fields"]["merge_review_reason"]
    # FS's own identifier is still carried through regardless of the conflict.
    assert p["type_specific_fields"]["fsftid"] == "ABCD-1"


def test_fs_only_value_adopted_when_ancestry_blank():
    ancestry = _doc([_sheet("3", [_record([_participant("1", "Jean", "Gagnon", occupation=None)])])])
    fs = _doc([_sheet("3", [_record([_participant("1", "Jean", "Gagnon", occupation="Farmer")])])])

    merged = MergedCensus.merge_census(ancestry, fs)
    p = merged["sheets"][0]["records"][0]["participants"][0]
    assert p["occupation"] == "Farmer"
    assert p["review"] is False  # adopting a blank -> filled value is not a conflict


def test_ancestry_only_participant_flagged_no_fs_match():
    ancestry = _doc([_sheet("3", [_record([_participant("1", "Jean", "Gagnon")])])])
    fs = _doc([_sheet("3", [])])

    merged = MergedCensus.merge_census(ancestry, fs)
    p = merged["sheets"][0]["records"][0]["participants"][0]
    assert p["review"] is True
    assert "No FamilySearch match" in p["type_specific_fields"]["merge_review_reason"]


def test_fs_only_participant_on_matched_sheet_becomes_its_own_record():
    ancestry = _doc([_sheet("3", [_record([_participant("1", "Jean", "Gagnon")])])])
    fs = _doc([_sheet("3", [_record([_participant("2", "Marie", "Riel")])])])

    merged = MergedCensus.merge_census(ancestry, fs)
    records = merged["sheets"][0]["records"]
    assert len(records) == 2
    fs_only_record = next(r for r in records if r["participants"][0]["std_given"] == "Marie")
    assert fs_only_record["participants"][0]["review"] is True
    assert "No Ancestry match" in fs_only_record["participants"][0]["type_specific_fields"]["merge_review_reason"]


def test_unmatched_fs_only_sheet_is_appended_not_dropped():
    ancestry = _doc([_sheet("3", [_record([_participant("1", "Jean", "Gagnon")])], ed="12")])
    fs = _doc([_sheet("9", [_record([_participant("1", "Marie", "Riel")])], ed="99")])

    merged = MergedCensus.merge_census(ancestry, fs)
    assert len(merged["sheets"]) == 2
    fs_only_sheet = next(s for s in merged["sheets"] if s["page_id"] == "9")
    assert fs_only_sheet["records"][0]["participants"][0]["std_given"] == "Marie"
