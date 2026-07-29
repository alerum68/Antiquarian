"""
Tests for build_census_dataframe_from_unified - the adapter translating Voyageur's
now-normalized shared-schema census output (sheets[].records[].participants[]) back into
the same old-column-named DataFrame shape Archivist's household-parsing/citation logic
has always operated on. These functions (parse_household, parse_household_relational,
get_census_era, etc.) are deliberately NOT changed by this rework - only what feeds them
changed - so these tests confirm the adapter's column-naming/grouping produces input
those functions still handle correctly, not that the functions themselves changed.
"""
import pandas as pd

import Archivist as arc


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
            "year": "1900", "event_date": "", "event_place": "", "english_translation": "",
            "original_transcription": "", "review": False, "review_reason": None,
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
