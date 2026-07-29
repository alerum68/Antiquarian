"""
Structural validation of hand-written fixture documents against the merged
schema. Fixtures avoid null values throughout: Gemini's "nullable" extension
isn't consulted by the standard jsonschema library the way it is by the
live API, so a fixture testing that relaxation would need a custom
validator; this test is a structural smoke check, not a full contract test.
"""

import json
from pathlib import Path

import jsonschema

import engine

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema.json"


def load_core_schema():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_parish_fixture_validates_against_merged_schema():
    core = load_core_schema()
    merged = engine.build_merged_schema(core, extra_fields={})

    document = {
        "collection_title": "Baptisms, marriages and burials, 1848-1896",
        "sheets": [{
            "page_id": "1",
            "document_metadata": {"file_name": "4211353_00003.jpg", "file_type": "JPEG", "volume": "1",
                                  "pages": "3", "source_name": "Assumption Parish", "source_location": "Pembina"},
            "records": [{
                "record_id": "B-14", "page": "3", "record_number": "14",
                "event_type": "Baptism", "year": "1850", "event_date": "1850-12-12",
                "event_place": "Pembina", "english_translation": "On December 12, 1850...",
                "original_transcription": "Le 12 decembre 1850...", "review": False, "review_reason": "",
                "type_specific_fields": {},
                "participants": [
                    {"role_number": "1", "role_name": "Primary", "std_given": "Jean", "std_surname": "Gagnon",
                     "sex": "M", "is_priest": False, "type_specific_fields": {}},
                ]
            }]
        }]
    }

    jsonschema.validate(document, merged)


def test_scrip_fixture_validates_against_merged_schema():
    core = load_core_schema()
    extra_fields = {"record": [{"name": "scrip_number", "type": "string"}],
                    "participant": [{"name": "marital_status", "type": "string"}]}
    merged = engine.build_merged_schema(core, extra_fields)

    document = {
        "collection_title": "RG15 Scrip Records",
        "sheets": [{
            "page_id": "1",
            "document_metadata": {"file_name": "e011335187.pdf", "file_type": "PDF", "volume": "1", "pages": "38",
                                  "source_name": "Library and Archives Canada", "source_location": "Ottawa"},
            "records": [{
                "record_id": "SCRIP-1042", "page": "1", "record_number": "1042",
                "event_type": "Scrip Application", "year": "1876", "event_date": "1876-03-03",
                "event_place": "Manitoba", "english_translation": "Application of Baptiste Ledoux...",
                "original_transcription": "Application of Baptiste Ledoux...", "review": False,
                "review_reason": "", "type_specific_fields": {"scrip_number": "1042"},
                "participants": [
                    {"role_number": "1", "role_name": "Claimant", "std_given": "Baptiste", "std_surname": "Ledoux",
                     "sex": "M", "is_priest": False, "type_specific_fields": {"marital_status": "Married"}},
                ]
            }]
        }]
    }

    jsonschema.validate(document, merged)


def test_facts_and_age_unit_validate_against_merged_schema():
    core = load_core_schema()
    merged = engine.build_merged_schema(core, extra_fields={})

    document = {
        "collection_title": "1900 United States Federal Census",
        "sheets": [{
            "page_id": "1",
            "document_metadata": {"file_name": "", "file_type": "", "volume": "", "pages": "",
                                  "source_name": "", "source_location": ""},
            "records": [{
                "record_id": "CENS-1", "page": "1", "record_number": "1",
                "event_type": "Census (family)", "year": "1900", "event_date": "1900-06-01",
                "event_place": "", "english_translation": "", "original_transcription": "",
                "review": False, "review_reason": "",
                "type_specific_fields": {"family_number": "12"},
                "participants": [
                    {"role_number": "1", "role_name": "Head", "std_given": "Jean", "std_surname": "Gagnon",
                     "sex": "M", "is_priest": False, "age": "3", "age_unit": "months",
                     "facts": [{"fact_type": "Immigration", "date": "1889"}],
                     "type_specific_fields": {}},
                ]
            }]
        }]
    }

    jsonschema.validate(document, merged)


def test_household_tally_convention_validates_against_merged_schema():
    core = load_core_schema()
    merged = engine.build_merged_schema(core, extra_fields={})

    document = {
        "collection_title": "1800 United States Federal Census",
        "sheets": [{
            "page_id": "1",
            "document_metadata": {"file_name": "", "file_type": "", "volume": "", "pages": "",
                                  "source_name": "", "source_location": ""},
            "records": [{
                "record_id": "CENS-1", "page": "1", "record_number": "1",
                "event_type": "Census (family)", "year": "1800", "event_date": "1800-08-04",
                "event_place": "", "english_translation": "", "original_transcription": "",
                "review": False, "review_reason": "",
                "type_specific_fields": {
                    "household_tally": [{"category": "free_white_male_under_16", "count": 3}]
                },
                "participants": [
                    {"role_number": "1", "role_name": "Head", "std_given": "Jean", "std_surname": "Gagnon",
                     "sex": "M", "is_priest": False, "type_specific_fields": {}},
                ]
            }]
        }]
    }

    jsonschema.validate(document, merged)


def test_required_participant_fields_are_enforced():
    core = load_core_schema()
    merged = engine.build_merged_schema(core, extra_fields={})

    document = {
        "sheets": [{
            "records": [{
                "participants": [
                    {"std_given": "Jean"}  # missing required role_name and is_priest
                ]
            }]
        }]
    }

    try:
        jsonschema.validate(document, merged)
    except jsonschema.ValidationError:
        pass
    else:
        raise AssertionError("Expected a ValidationError for missing required participant fields")
