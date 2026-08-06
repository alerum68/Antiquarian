import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from Commissioner.models import (
    AlternateName,
    Collection,
    DocumentMetadata,
    FACT_DEFINITIONS,
    Fact,
    FactScope,
    Participant,
    Record,
    Sheet,
    get_fact_definition,
)


def test_fact_definitions_has_all_68_entries():
    assert len(FACT_DEFINITIONS) == 68


def test_known_person_fact_resolves():
    birth = get_fact_definition("Birth")
    assert birth.scope == FactScope.PERSON
    assert birth.gedcom_tag == "BIRT"
    assert birth.use_value is False
    assert birth.use_date is True
    assert birth.use_place is True
    assert birth.custom is False
    assert birth.code == "1"


def test_known_family_fact_resolves():
    marriage = get_fact_definition("Marriage")
    assert marriage.scope == FactScope.FAMILY
    assert marriage.gedcom_tag == "MARR"
    assert marriage.code == "300"


def test_custom_fact_resolves():
    scrip = get_fact_definition("Scrip")
    assert scrip.custom is True
    assert scrip.code == "10004"


def test_unknown_fact_name_raises():
    with pytest.raises(KeyError, match="Coordinator"):
        get_fact_definition("Coordinator")


SCHEMA_JSON_PATH = Path(__file__).resolve().parent.parent.parent / "Paleographer" / "schema.json"

EXPECTED_FIELDS = {
    "Collection": {"collection_title", "sheets"},
    "Sheet": {"page_id", "document_metadata", "records"},
    "DocumentMetadata": {"file_name", "file_type", "volume", "pages", "source_name", "source_location"},
    "Record": {
        "record_id", "page", "record_number", "event_type", "year", "event_date",
        "event_place", "english_translation", "original_transcription", "review",
        "review_reason", "continues_on_next_image", "continues_from_previous_image",
        "type_specific_fields", "participants",
    },
    "Participant": {
        "role_number", "role_name", "std_given", "std_surname", "raw_given",
        "raw_surname", "dit_name", "alternate_names", "prefix", "suffix", "sex",
        "is_priest", "age", "age_unit", "occupation", "race", "religion",
        "residence", "birth_date", "birth_place", "death_date", "death_place",
        "review", "review_reason", "facts", "type_specific_fields",
    },
    "AlternateName": {"value"},
    "Fact": {"fact_type", "value", "date", "place"},
}


def test_schema_json_file_exists_for_guardrail():
    assert SCHEMA_JSON_PATH.is_file()


def test_models_match_schema_json_field_names():
    """Guardrail: Paleographer still reads schema.json directly for its LLM calls.
    If models.py's fields ever drift from that file's shape, this must fail
    immediately rather than silently diverging."""
    full_schema = Collection.model_json_schema()
    defs = full_schema.get("$defs", {})

    assert set(full_schema["properties"].keys()) == EXPECTED_FIELDS["Collection"]

    for class_name, expected_fields in EXPECTED_FIELDS.items():
        if class_name == "Collection":
            continue
        assert class_name in defs, f"{class_name} missing from $defs"
        actual_fields = set(defs[class_name]["properties"].keys())
        assert actual_fields == expected_fields, (
            f"{class_name}: expected {expected_fields}, got {actual_fields}"
        )


def test_fact_rejects_unknown_fact_type():
    with pytest.raises(ValidationError, match="Coordinator"):
        Fact(fact_type="Coordinator")


def test_fact_accepts_known_fact_type():
    fact = Fact(fact_type="Birth", date="1850-01-01")
    assert fact.fact_type == "Birth"
    assert fact.value is None


def test_participant_requires_role_name_key_but_allows_null():
    participant = Participant(role_name=None, std_given="Jean", is_priest=False, sex="M")
    assert participant.role_name is None


def test_participant_requires_std_given_is_priest_sex():
    with pytest.raises(ValidationError):
        Participant(role_name="Other")


def test_full_collection_round_trips_minimal_payload():
    collection = Collection(
        collection_title="Test Collection",
        sheets=[
            Sheet(
                page_id="page_001",
                document_metadata=DocumentMetadata(source_location="Red River"),
                records=[
                    Record(
                        page="page_001",
                        record_number="1",
                        event_type="Baptism",
                        review=False,
                        continues_on_next_image=False,
                        continues_from_previous_image=False,
                        participants=[
                            Participant(
                                role_name="Primary",
                                std_given="Jean",
                                is_priest=False,
                                sex="M",
                                review=False,
                                facts=[Fact(fact_type="Birth", date="1850")],
                                alternate_names=[AlternateName(value="Jean-Baptiste")],
                            )
                        ],
                    )
                ],
            )
        ],
    )
    assert collection.sheets[0].records[0].participants[0].facts[0].fact_type == "Birth"
