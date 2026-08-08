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

