"""Tests for FS.py's build_universal_json() document_metadata fix and Commissioner
validation wiring - see the Voyageur-Parish-Scrip-scaffold design spec."""
import FS


def test_sanitize_item_id_filename_replaces_unsafe_characters():
    assert FS.sanitize_item_id_filename("abc 123/def") == "abc_123_def.jpg"


def test_sanitize_item_id_filename_preserves_safe_characters():
    assert FS.sanitize_item_id_filename("abc-123_DEF") == "abc-123_DEF.jpg"


def test_build_universal_json_sets_real_document_metadata_from_item_id():
    raw = {"collection_title": "Test Parish Register"}
    items_raw = [{"item_id": "abc 123/def", "rows": [], "citation_text": ""}]
    result = FS.build_universal_json(raw, items_raw, {}, "church")

    metadata = result["sheets"][0]["document_metadata"]
    assert metadata["file_name"] == "abc_123_def.jpg"
    assert metadata["file_type"] == "jpg"


def test_build_universal_json_empty_item_id_yields_empty_file_name():
    raw = {"collection_title": "Test"}
    items_raw = [{"item_id": "", "rows": []}]
    result = FS.build_universal_json(raw, items_raw, {}, "church")

    assert result["sheets"][0]["document_metadata"]["file_name"] == ""


def test_validate_against_commissioner_accepts_valid_church_sheet(capsys):
    final_data = {
        "collection_title": "Test Parish",
        "sheets": [{
            "page_id": "abc123.jpg",
            "document_metadata": {"file_name": "abc123.jpg", "file_type": "jpg"},
            "records": [],
        }],
    }
    FS.validate_against_commissioner(final_data, "church", "Test Parish")
    assert "[WARN]" not in capsys.readouterr().out


def test_validate_against_commissioner_skipped_for_unmapped_family(capsys):
    FS.validate_against_commissioner({"sheets": []}, "wills", "Test")
    assert capsys.readouterr().out == ""


def test_validate_against_commissioner_warns_and_does_not_raise_on_bad_shape(capsys):
    bad_data = {"collection_title": "Bad", "sheets": [{"records": "not-a-list"}]}
    FS.validate_against_commissioner(bad_data, "church", "Bad Collection")
    captured = capsys.readouterr()
    assert "[WARN]" in captured.out
    assert "Bad Collection" in captured.out


def test_normalize_familysearch_census_gather_derives_record_type():
    raw_census = {
        "census_year": "1900",
        "pages": [{
            "page_number": 3, "state": "Ohio", "county": "Lucas", "city": "", "country": "USA",
            "repository": "FamilySearch",
            "people": [
                {"columns": {"Given Name": "Marie", "Surname": "Boucher", "Gender": "F",
                             "Age": "35", "Relationship to Head": "Head", "Family Number": "2"},
                 "pid": "p2"},
            ],
        }],
    }

    normalized = FS.normalize_familysearch_census_gather(raw_census, "1900 US Census - Ohio")

    assert normalized["record_type_name"] == "Census_1900"
    assert normalized["collection_title"] == "1900 US Census - Ohio"
    assert len(normalized["sheets"]) == 1


def test_build_census_json_accepts_household_view_row_shape():
    """Locks in this design's core claim: the household-view scraper (replacing the old
    Image Index table scraper) can produce rows in this exact shape with zero FS.py/Census.py
    changes - see docs/superpowers/specs/2026-08-07-familysearch-household-view-gather-design.md.
    Column keys and values mirror what a real View Name panel showed live (Joseph Rolette
    household, 1850 Minnesota census): Given Name/Surname split from Essential Information,
    Gender from "Sex: M", Relationship to Head from Household Details ("Spouse"/"Child"),
    Family Number synthesized per household section (not from FamilySearch, which has no
    such field)."""
    raw = {"collection_title": "Minnesota, 1850 federal census : population schedules"}
    items_raw = [{
        "item_id": "3:1:S3HY-67NL-ZP",
        "citation_text": '"Minnesota, 1850 federal census," database with images, FamilySearch '
        '(https://familysearch.org : 3 August 2026), Kittson > image 39; '
        "NARA microfilm publication.",
        "rows": [
            {"columns": {"Given Name": "Joseph", "Surname": "Rolette", "Gender": "M", "Age": "35",
                         "Relationship to Head": "Head", "Family Number": "1"},
             "person_ark": "MZ2Z-WM4", "attached_fsftid": "9CJG-851"},
            {"columns": {"Given Name": "Angelic", "Surname": "Rolette", "Gender": "F", "Age": "30",
                         "Relationship to Head": "Spouse", "Family Number": "1"},
             "person_ark": "MZ2Z-WM5", "attached_fsftid": ""},
            {"columns": {"Given Name": "Joseph", "Surname": "Rolette", "Gender": "M", "Age": "9",
                         "Relationship to Head": "Child", "Family Number": "1"},
             "person_ark": "MZ2Z-WM6", "attached_fsftid": ""},
            {"columns": {"Given Name": "George", "Surname": "Monison", "Gender": "M", "Age": "22",
                         "Relationship to Head": "No Relation", "Family Number": "1"},
             "person_ark": "MZ2Z-WM7", "attached_fsftid": ""},
            {"columns": {"Given Name": "J Baptiste", "Surname": "Cardinal", "Gender": "M", "Age": "40",
                         "Family Number": "2"},
             "person_ark": "MZ2Z-XX1", "attached_fsftid": ""},
        ],
    }]

    result = FS.build_census_json(raw, items_raw, {})

    people = result["pages"][0]["people"]
    assert len(people) == 5
    assert people[0]["pid"] == "MZ2Z-WM4"
    assert people[0]["person_ark"] == "MZ2Z-WM4"
    assert people[0]["fsftid"] == "9CJG-851"
    assert people[0]["familysearch_url"] == "https://www.familysearch.org/ark:/61903/1:1:MZ2Z-WM4"
    assert people[0]["columns"]["Relationship to Head"] == "Head"
    # J Baptiste Cardinal's household has no relationship data at all (the bare-"Primary"
    # case confirmed live) - the column must simply be absent, not fabricated as empty string.
    assert "Relationship to Head" not in people[4]["columns"]
