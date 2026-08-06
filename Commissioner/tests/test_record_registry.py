import pytest

from Commissioner.record_registry import (
    InvalidRoleError,
    UnknownDocumentTypeError,
    get_document_types,
    get_valid_roles,
    validate_participant_extra_fields,
    validate_record_extra_fields,
    validate_role_name,
)


def test_discovers_both_real_pmt_files():
    doc_types = get_document_types()
    assert "Parish" in doc_types
    assert "Scrip" in doc_types


def test_parish_has_no_extra_fields():
    record_extra = validate_record_extra_fields("Parish", {})
    assert record_extra.model_dump() == {}
    participant_extra = validate_participant_extra_fields("Parish", {})
    assert participant_extra.model_dump() == {}


def test_scrip_record_extra_fields_validate_and_coerce_types():
    extra = validate_record_extra_fields(
        "Scrip",
        {
            "claim_number": "5473",
            "scrip_amount": "160",
            "scrip_type": "Cash",
        },
    )
    assert extra.claim_number == "5473"
    assert extra.scrip_amount == "160"
    assert extra.scrip_type == "Cash"


def test_scrip_record_extra_rejects_invalid_enum_choice():
    from pydantic import ValidationError
    with pytest.raises(ValidationError, match="Land"):
        validate_record_extra_fields("Scrip", {"scrip_type": "Currency"})


def test_scrip_participant_extra_fields():
    extra = validate_participant_extra_fields(
        "Scrip", {"marital_status": "Married", "race_or_origin": "Metis"}
    )
    assert extra.marital_status == "Married"
    assert extra.race_or_origin == "Metis"


def test_unknown_document_type_raises():
    with pytest.raises(UnknownDocumentTypeError, match="Census"):
        validate_record_extra_fields("Census", {})


def test_valid_roles_differ_by_document_type():
    parish_roles = get_valid_roles("Parish")
    scrip_roles = get_valid_roles("Scrip")
    assert "Officiant" in parish_roles
    assert "Claimant" in scrip_roles
    assert "Claimant" not in parish_roles


def test_validate_role_name_accepts_known_role():
    validate_role_name("Scrip", "Claimant")
    validate_role_name("Scrip", None)


def test_validate_role_name_rejects_unknown_role():
    with pytest.raises(InvalidRoleError, match="Coordinator"):
        validate_role_name("Scrip", "Coordinator")


import pytest
from pydantic import ValidationError

from Commissioner.record_registry import InvalidRoleError, parse_collection


SAMPLE_SCRIP_PAYLOAD = {
    "collection_title": "Test Scrip Collection",
    "sheets": [
        {
            "page_id": "page_001",
            "document_metadata": {"source_location": "Manitoba"},
            "records": [
                {
                    "page": "page_001",
                    "record_number": "5473-0-0",
                    "event_type": "Scrip",
                    "review": False,
                    "continues_on_next_image": False,
                    "continues_from_previous_image": False,
                    "type_specific_fields": {
                        "claim_number": "5473",
                        "scrip_amount": "160",
                        "scrip_type": "Cash",
                    },
                    "participants": [
                        {
                            "role_name": "Claimant",
                            "std_given": "Jean",
                            "std_surname": "Gagnon",
                            "is_priest": False,
                            "sex": "M",
                            "review": False,
                            "type_specific_fields": {
                                "marital_status": "Married",
                                "race_or_origin": "Metis",
                            },
                        }
                    ],
                }
            ],
        }
    ],
}


def test_parse_collection_validates_scrip_payload_end_to_end():
    collection = parse_collection(SAMPLE_SCRIP_PAYLOAD, document_type="Scrip")
    record = collection.sheets[0].records[0]
    assert record.type_specific_fields["scrip_type"] == "Cash"
    participant = record.participants[0]
    assert participant.type_specific_fields["race_or_origin"] == "Metis"


def test_parse_collection_rejects_bad_extra_field_type():
    bad_payload = {
        **SAMPLE_SCRIP_PAYLOAD,
        "sheets": [
            {
                **SAMPLE_SCRIP_PAYLOAD["sheets"][0],
                "records": [
                    {
                        **SAMPLE_SCRIP_PAYLOAD["sheets"][0]["records"][0],
                        "type_specific_fields": {"scrip_type": "Currency"},
                    }
                ],
            }
        ],
    }
    with pytest.raises(ValidationError, match="Land"):
        parse_collection(bad_payload, document_type="Scrip")


def test_parse_collection_rejects_invalid_role_for_document_type():
    bad_payload = {
        **SAMPLE_SCRIP_PAYLOAD,
        "sheets": [
            {
                **SAMPLE_SCRIP_PAYLOAD["sheets"][0],
                "records": [
                    {
                        **SAMPLE_SCRIP_PAYLOAD["sheets"][0]["records"][0],
                        "participants": [
                            {
                                **SAMPLE_SCRIP_PAYLOAD["sheets"][0]["records"][0]["participants"][0],
                                "role_name": "Coordinator",
                            }
                        ],
                    }
                ],
            }
        ],
    }
    with pytest.raises(InvalidRoleError, match="Coordinator"):
        parse_collection(bad_payload, document_type="Scrip")
