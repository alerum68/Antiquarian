"""Tests for census_schema.py's field-map normalization across all three census eras."""
import census_schema


def _page(people, **overrides):
    page = {
        "page_number": 1, "image_id": "img1", "country": "USA", "state": "Minnesota",
        "county": "Ramsey", "city": "St. Paul", "place_details": "", "enumeration_district": "12",
        "film_number": "", "roll_number": "T624_1", "apid_db": "", "repository": "Ancestry.com",
        "repository_loc": "", "publisher": "", "pub_loc": "", "people": people,
    }
    page.update(overrides)
    return page


def test_relationship_era_groups_household_and_maps_role_name():
    raw = {
        "census_year": "1900",
        "location": "Minnesota",
        "pages": [_page([
            {"columns": {"Given Name": "Jean", "Surname": "Gagnon", "Gender": "M", "Age": "40",
                        "Relationship to Head": "Head", "Family Number": "5"}, "pid": "p1"},
            {"columns": {"Given Name": "Marie", "Surname": "Gagnon", "Gender": "F", "Age": "38",
                        "Relationship to Head": "Wife", "Family Number": "5"}, "pid": "p2"},
        ])],
    }
    doc = census_schema.normalize_census_pages(raw, "ancestry_census", "1900 US Census", "Census_1900")

    assert doc["record_type_name"] == "Census_1900"
    records = doc["sheets"][0]["records"]
    assert len(records) == 1
    record = records[0]
    assert record["event_type"] == "Census (family)"
    assert record["type_specific_fields"]["family_number"] == "5"
    assert len(record["participants"]) == 2

    head = next(p for p in record["participants"] if p["role_name"] == "Head")
    assert head["std_given"] == "Jean"
    assert head["std_surname"] == "Gagnon"
    assert head["sex"] == "M"
    assert head["age"] == "40"
    assert head["review"] is False

    wife = next(p for p in record["participants"] if p["role_name"] == "Wife")
    assert wife["std_given"] == "Marie"


def test_heuristic_era_groups_by_family_number_with_no_relationship_column():
    raw = {
        "census_year": "1860", "location": "Minnesota",
        "pages": [_page([
            {"columns": {"Given Name": "Jean", "Surname": "Gagnon", "Gender": "M", "Age": "40",
                        "Family Number": "5"}, "pid": "p1"},
            {"columns": {"Given Name": "Marie", "Surname": "Gagnon", "Gender": "F", "Age": "38",
                        "Family Number": "5"}, "pid": "p2"},
        ])],
    }
    doc = census_schema.normalize_census_pages(raw, "ancestry_census", "1860 US Census", "Census_1860")

    records = doc["sheets"][0]["records"]
    assert len(records) == 1
    assert len(records[0]["participants"]) == 2
    # No relationship column present at all this era - role_name stays unset, Archivist's
    # own heuristic parser resolves family position from age/sex/surname, not this step.
    assert all(p["role_name"] is None for p in records[0]["participants"])


def test_pre1850_era_has_no_family_number_and_no_grouping():
    raw = {
        "census_year": "1820", "location": "Minnesota",
        "pages": [_page([
            {"columns": {"Given Name": "Jean", "Surname": "Gagnon", "Gender": "M"}, "pid": "p1"},
        ])],
    }
    doc = census_schema.normalize_census_pages(raw, "ancestry_census", "1820 US Census", "Census_1820")

    records = doc["sheets"][0]["records"]
    assert len(records) == 1
    assert len(records[0]["participants"]) == 1
    assert "family_number" not in records[0]["type_specific_fields"]


def test_two_unrelated_households_on_one_page_stay_separate():
    raw = {
        "census_year": "1900", "location": "Minnesota",
        "pages": [_page([
            {"columns": {"Given Name": "Jean", "Surname": "Gagnon", "Gender": "M",
                        "Relationship to Head": "Head", "Family Number": "5"}, "pid": "p1"},
            {"columns": {"Given Name": "Louis", "Surname": "Riel", "Gender": "M",
                        "Relationship to Head": "Head", "Family Number": "6"}, "pid": "p2"},
        ])],
    }
    doc = census_schema.normalize_census_pages(raw, "ancestry_census", "1900 US Census", "Census_1900")
    records = doc["sheets"][0]["records"]
    assert len(records) == 2
    assert {r["type_specific_fields"]["family_number"] for r in records} == {"5", "6"}


def test_unmapped_column_is_preserved_and_flags_for_review():
    raw = {
        "census_year": "1900", "location": "Minnesota",
        "pages": [_page([
            {"columns": {"Given Name": "Jean", "Surname": "Gagnon", "Gender": "M",
                        "Relationship to Head": "Head", "Family Number": "5",
                        "Some Brand New Column Ancestry Just Added": "mystery value"}, "pid": "p1"},
        ])],
    }
    doc = census_schema.normalize_census_pages(raw, "ancestry_census", "1900 US Census", "Census_1900")
    participant = doc["sheets"][0]["records"][0]["participants"][0]

    assert participant["review"] is True
    assert "Some Brand New Column Ancestry Just Added" in participant["type_specific_fields"]["unmapped"]
    assert participant["type_specific_fields"]["unmapped"]["Some Brand New Column Ancestry Just Added"] == "mystery value"
    assert doc["sheets"][0]["records"][0]["review"] is True


def test_recognized_extra_columns_become_typed_facts_not_flagged_for_review():
    raw = {
        "census_year": "1900", "location": "Minnesota",
        "pages": [_page([
            {"columns": {"Given Name": "Jean", "Surname": "Gagnon", "Gender": "M",
                        "Relationship to Head": "Head", "Family Number": "5",
                        "Occupation": "Farmer", "Immigration Year": "1889"}, "pid": "p1"},
        ])],
    }
    doc = census_schema.normalize_census_pages(raw, "ancestry_census", "1900 US Census", "Census_1900")
    participant = doc["sheets"][0]["records"][0]["participants"][0]

    assert participant["review"] is False
    fact_types = {f["fact_type"] for f in participant["facts"]}
    assert fact_types == {"Occupation", "Immigration"}
    occupation_fact = next(f for f in participant["facts"] if f["fact_type"] == "Occupation")
    assert occupation_fact["value"] == "Farmer"


def test_familysearch_census_field_map_loads_and_normalizes():
    raw = {
        "census_year": "1900", "location": "Manitoba",
        "pages": [_page([
            {"columns": {"Given Name": "Jean", "Surname": "Gagnon", "Gender": "M",
                        "Relationship to Head": "Head", "Family Number": "5"}, "pid": "p1",
             "fsftid": "ABCD-123"},
        ])],
    }
    doc = census_schema.normalize_census_pages(raw, "familysearch_census", "1900 Canada Census", "Census_1900")
    participant = doc["sheets"][0]["records"][0]["participants"][0]
    assert participant["std_given"] == "Jean"
    assert participant["type_specific_fields"]["fsftid"] == "ABCD-123"
