"""
Tests for build_census_dataframe_from_unified - the adapter translating Voyageur's
now-normalized shared-schema census output (sheets[].records[].participants[]) back into
the same old-column-named DataFrame shape Archivist's household-parsing/citation logic
has always operated on. These functions (parse_household, parse_household_relational,
get_census_era, etc.) are deliberately NOT changed by this rework - only what feeds them
changed - so these tests confirm the adapter's column-naming/grouping produces input
those functions still handle correctly, not that the functions themselves changed.
"""
import Utils
import Census as arc
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _unified_doc(record_type_name, sheets):
    return {"collection_title": "Test Census", "record_type_name": record_type_name,
            "citation": {"repository": "Ancestry.com"}, "sheets": sheets}


def _sheet(records, page_id="3"):
    return {"page_id": page_id, "document_metadata": {"source_location": "Minnesota"}, "records": records}


def _record(participants, family_number=None, ed="12", roll="T624_1"):
    ts = {"enumeration_district": ed, "roll_number": roll, "state": "Minnesota", "county": "Ramsey"}
    if family_number:
        ts["family_number"] = family_number
    return {"record_id": None, "page": "3", "record_number": family_number or "", "event_type": "Census (family)",
            "year": "1900", "event_date": "", "event_place": "", "citation_details": "",
            "citation_text": "", "review": False, "review_reason": None,
            "continues_on_next_image": False, "continues_from_previous_image": False,
            "type_specific_fields": ts, "participants": participants}


def _participant(given, surname, sex, role_name=None, age=None, line=None, facts=None):
    return {"role_number": None, "role_name": role_name, "std_given": given, "std_surname": surname,
            "raw_given": None, "raw_surname": None, "dit_name": None, "alternate_names": [],
            "prefix": None, "suffix": None, "sex": sex, "is_priest": False, "age": age, "age_unit": None,
            "occupation": None, "race": None, "religion": None, "residence": None, "birth_date": None,
            "birth_place": None, "death_date": None, "death_place": None, "review": False, "review_reason": None,
            "facts": facts or [], "type_specific_fields": {"line_number": line} if line else {}}


def test_adapter_produces_expected_columns_and_year_location():
    doc = _unified_doc("Census_1900", [_sheet([
        _record([_participant("Jean", "Gagnon", "M", role_name="Head", age="40", line="1")],
                family_number="5"),
    ])])

    df, year, location = arc.build_census_dataframe_from_unified(doc)

    assert year == "1900"
    assert location == "Minnesota"
    assert len(df) == 1
    row = df.iloc[0]
    assert row["Given Name"] == "Jean"
    assert row["Surname"] == "Gagnon"
    assert row["Gender"] == "M"
    assert row["Relationship to Head"] == "Head"
    assert row["Family Number"] == "5"
    assert row["Line Number"] == "1"
    assert row["Enumeration_District"] == "12"
    assert row["Roll"] == "T624_1"


def test_adapter_maps_facts_to_expected_old_column_names():
    doc = _unified_doc("Census_1900", [_sheet([
        _record([_participant("Jean", "Gagnon", "M",
                              facts=[{"fact_type": "Occupation", "value": "Farmer"},
                                     {"fact_type": "Immigration", "date": "1889"}])],
                family_number="5"),
    ])])
    df, _, _ = arc.build_census_dataframe_from_unified(doc)
    row = df.iloc[0]
    assert row["Occupation"] == "Farmer"
    assert row["Immigration Year"] == "1889"


def test_relational_era_household_parsing_works_on_adapted_dataframe():
    """1900 (relationship era) - Head + Wife, explicit role_name - confirms
    parse_household_relational (unchanged) correctly resolves the household from the
    adapter's column naming."""
    doc = _unified_doc("Census_1900", [_sheet([
        _record([
            _participant("Jean", "Gagnon", "M", role_name="Head", age="40", line="1"),
            _participant("Marie", "Gagnon", "F", role_name="Wife", age="38", line="2"),
        ], family_number="5"),
    ])])
    df, year, _ = arc.build_census_dataframe_from_unified(doc)

    arc.CENSUS_YEAR = int(year)
    arc.CENSUS_ERA = arc.get_census_era(arc.CENSUS_YEAR)
    assert arc.CENSUS_ERA == "relationship"

    units, unrelated, flags = arc.parse_household_relational(df)
    assert len(units) == 1
    assert units[0]["husband"]["Given Name"] == "Jean"
    assert units[0]["wife"]["Given Name"] == "Marie"
    assert not unrelated


def test_heuristic_era_household_parsing_works_on_adapted_dataframe():
    """1860 (heuristic era) - no role_name at all (matches what census_schema.py produces
    when the source has no relationship column) - confirms parse_household (unchanged)
    still infers the spouse pair from age/sex/surname proximity via the adapter's output."""
    doc = _unified_doc("Census_1860", [_sheet([
        _record([
            _participant("Jean", "Gagnon", "M", age="40", line="1"),
            _participant("Marie", "Gagnon", "F", age="38", line="2"),
        ], family_number="5"),
    ])])
    df, year, _ = arc.build_census_dataframe_from_unified(doc)

    arc.CENSUS_YEAR = int(year)
    arc.CENSUS_ERA = arc.get_census_era(arc.CENSUS_YEAR)
    assert arc.CENSUS_ERA == "heuristic"

    units, unrelated, flags = arc.parse_household(df)
    assert len(units) == 1
    assert {units[0]["husband"]["Given Name"], units[0]["wife"]["Given Name"]} == {"Jean", "Marie"}


def test_two_households_get_separate_family_number_groups():
    doc = _unified_doc("Census_1900", [_sheet([
        _record([_participant("Jean", "Gagnon", "M", role_name="Head", line="1")], family_number="5"),
        _record([_participant("Louis", "Riel", "M", role_name="Head", line="2")], family_number="6"),
    ])])
    df, _, _ = arc.build_census_dataframe_from_unified(doc)
    df["Household_ID"] = (df["Family Number"] != df["Family Number"].shift()).cumsum()
    assert df["Household_ID"].nunique() == 2


def test_dispatch_by_record_type_name_not_shape():
    """Both census and church documents use the "sheets" top-level key now - confirms
    is_census's own logic (record_type_name-based, not a hardcoded shape guess) would
    route a Census_-prefixed document to the census flavor."""
    doc = _unified_doc("Census_1900", [_sheet([_record([_participant("Jean", "Gagnon", "M")])])])
    assert doc.get("record_type_name", "").startswith("Census_")
    assert "sheets" in doc


def test_build_census_task_folder_name_uses_fixed_vocabulary_not_raw_flag_text():
    """Regression: RootsMagic rejects an arbitrary sentence as a "0 _FOLDER" value -
    build_census_task used to write one directly (a lightly regex-cleaned copy of the raw
    review-flag text, e.g. "Head-surname match: no age fit"). The folder name must instead
    come from evaluate_task_priority's fixed, safe vocabulary - already proven correct for
    the general flavor - reusing the exact flag text real 1860 census data produced."""
    _, folder = arc.build_census_task("1", "Jean", "Gagnon", "1900, Fam 5, p.3",
                                      [("Head-surname match; no age fit", 0.3)],
                                      [], "img.jpg", "Title", "RM")
    assert folder == "Name & Identity Issues"

    _, folder2 = arc.build_census_task("2", "Jean", "Gagnon", "1900, Fam 5, p.3",
                                       [("Unrelated household member", 0.5)],
                                       [], "img.jpg", "Title", "RM")
    assert folder2 == "General Review"


def test_census_gedcom_output_has_no_illegal_name_under_sour_and_single_extension(tmp_path, monkeypatch):
    """Regression for the FTM import-error root cause (confirmed against a real FTM import
    error log: ~85 "Unsupported or invalid tag: NAME" errors on one real test census page):
    a "NAME Researcher: ..." line was being written as a child of a per-fact "2 SOUR ..."
    citation, which isn't legal under GEDCOM 5.5.1 (see build_census_citation). This is
    distinct from "2 NAME Researcher: ..." under the shared "1 SOUR @S1@" researcher
    reference on every individual - confirmed live by the user that RootsMagic needs BOTH
    "2 NAME" and "2 _TITL" there to merge that citation across every person who cites it;
    that pattern is intentional, not a regression of this fix. Also regresses an OBJE media
    filename doubling its extension (".jpg.jpg") when Image_ID already carries one, as it
    does coming from the unified schema's document_metadata.file_name - and confirms the
    FamilySearch Family Tree profile webtag now accompanies _FSFTID."""
    head = _participant("Jean", "Gagnon", "M", role_name="Head", age="40", line="1")
    head["type_specific_fields"] = {"line_number": "1", "fsftid": "LZXY-ABC"}
    wife = _participant("Marie", "Gagnon", "F", role_name="Wife", age="38", line="2")
    doc = _unified_doc("Census_1900", [{
        "page_id": "3",
        "document_metadata": {"source_location": "Minnesota", "file_name": "4211353_00003.jpg"},
        "records": [_record([head, wife], family_number="5")],
    }])
    df, year, _ = arc.build_census_dataframe_from_unified(doc)

    monkeypatch.setattr(arc, "CENSUS_YEAR", int(year))
    monkeypatch.setattr(arc, "CENSUS_ERA", arc.get_census_era(int(year)))
    monkeypatch.setattr(Utils, "GEDCOM_OUTPUT_PATH", tmp_path)
    monkeypatch.setattr(arc, "IMAGE_DIR", tmp_path)

    arc.build_gedcom_from_census(df, "RM")

    out_files = list(tmp_path.glob("*.ged"))
    assert len(out_files) == 1
    lines = out_files[0].read_text(encoding="utf-8").splitlines()

    # The illegal line was specifically "3 NAME Researcher: ..." nested directly under a
    # per-fact "2 SOUR ..." citation - "2 NAME Researcher: ..." under the shared top-level
    # "1 SOUR @S1@" reference (checked below) is the separate, intentional pattern.
    sour_line_idxs = [i for i, ln in enumerate(lines) if ln.startswith("2 SOUR ")]
    for i in sour_line_idxs:
        for ln in lines[i + 1:]:
            if not (ln.startswith("3 ") or ln.startswith("4 ") or ln.startswith("5 ")):
                break
            if ln.startswith("3 NAME"):
                assert False, f"illegal NAME directly under a per-fact SOUR citation: {ln!r}"

    # The shared "1 SOUR @S1@" researcher reference on each individual needs BOTH "2 NAME"
    # and "2 _TITL" - confirmed live by the user - to merge across every person's citation
    # of it in RootsMagic's own UI.
    root_sour_idxs = [i for i, ln in enumerate(lines) if ln == f"1 SOUR {Utils.ROOT_SOURCE_ID}"]
    assert root_sour_idxs
    for i in root_sour_idxs:
        assert lines[i + 1].startswith("2 NAME Researcher:")
        assert lines[i + 2].startswith("2 _TITL Researcher:")

    file_lines = [ln for ln in lines if ln.startswith("1 FILE ")]
    assert file_lines
    assert all(ln.endswith(".jpg") and not ln.endswith(".jpg.jpg") for ln in file_lines)

    assert any(ln == "1 _FSFTID LZXY-ABC" for ln in lines)
    assert any("https://www.familysearch.org/tree/person/details/LZXY-ABC" in ln for ln in lines)
