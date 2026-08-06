import pytest

from Commissioner.record_registry import (
    InvalidRoleError,
    UnknownDocumentTypeError,
    UnknownFieldTypeError,
    _build_registry,
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


def test_undeclared_extra_field_key_is_rejected_not_ignored():
    """extra='forbid': since the validated model is never written back over the caller's
    dict, an undeclared key must fail loudly rather than be silently ignored."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="not_a_real_field"):
        validate_record_extra_fields("Scrip", {"not_a_real_field": "x"})

    with pytest.raises(ValidationError, match="not_a_real_field"):
        validate_participant_extra_fields("Scrip", {"not_a_real_field": "x"})


UNKNOWN_TYPE_PMT = """---
roles:
  "1": {name: "Claimant"}
extra_fields:
  record:
    - {name: bogus_field, type: nonsense}
---
Fixture prompt body.
"""


def test_unknown_field_type_token_raises_at_load_time(tmp_path):
    (tmp_path / "Fixture.pmt").write_text(UNKNOWN_TYPE_PMT, encoding="utf-8")
    with pytest.raises(UnknownFieldTypeError, match="nonsense"):
        _build_registry(tmp_path)


def test_build_registry_accepts_a_valid_fixture_dir(tmp_path):
    """Control for the test above: same fixture with a supported type token loads fine,
    so the failure there is the type token and not the fixture format."""
    (tmp_path / "Fixture.pmt").write_text(
        UNKNOWN_TYPE_PMT.replace("type: nonsense", "type: string"), encoding="utf-8"
    )
    registry = _build_registry(tmp_path)
    assert set(registry) == {"Fixture"}
    assert registry["Fixture"].valid_roles == frozenset({"Claimant"})


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


def test_parse_collection_leaves_type_specific_fields_exactly_as_given():
    """parse_collection validates type_specific_fields; it must never rewrite them.
    Overwriting with the validation model's dump would inject None for every
    declared-but-absent field - silent data corruption of the caller's payload."""
    payload = {
        **SAMPLE_SCRIP_PAYLOAD,
        "sheets": [
            {
                **SAMPLE_SCRIP_PAYLOAD["sheets"][0],
                "records": [
                    {
                        **SAMPLE_SCRIP_PAYLOAD["sheets"][0]["records"][0],
                        # Only 2 of Scrip's 16 declared record extra fields.
                        "type_specific_fields": {"claim_number": "5473", "scrip_type": "Land"},
                        "participants": [
                            {
                                **SAMPLE_SCRIP_PAYLOAD["sheets"][0]["records"][0]["participants"][0],
                                "type_specific_fields": {"treaty_band": "St. Peter's"},
                            }
                        ],
                    }
                ],
            }
        ],
    }
    collection = parse_collection(payload, document_type="Scrip")
    record = collection.sheets[0].records[0]
    assert record.type_specific_fields == {"claim_number": "5473", "scrip_type": "Land"}
    assert record.participants[0].type_specific_fields == {"treaty_band": "St. Peter's"}


def test_parse_collection_preserves_empty_type_specific_fields_for_parish():
    """Parish.pmt declares zero extra_fields, so an overwrite-with-dump would have been
    invisible here - but every Parish record's dict must still survive untouched."""
    payload = {
        "collection_title": "Test Parish Collection",
        "sheets": [
            {
                "page_id": "page_001",
                "records": [
                    {
                        "page": "page_001",
                        "record_number": "1",
                        "event_type": "Baptism",
                        "type_specific_fields": {},
                        "participants": [
                            {
                                "role_name": "Primary",
                                "std_given": "Jean",
                                "is_priest": False,
                                "sex": "M",
                                "type_specific_fields": {},
                            }
                        ],
                    }
                ],
            }
        ],
    }
    collection = parse_collection(payload, document_type="Parish")
    record = collection.sheets[0].records[0]
    assert record.type_specific_fields == {}
    assert record.participants[0].type_specific_fields == {}


def test_parse_collection_rejects_undeclared_type_specific_field_key():
    payload = {
        **SAMPLE_SCRIP_PAYLOAD,
        "sheets": [
            {
                **SAMPLE_SCRIP_PAYLOAD["sheets"][0],
                "records": [
                    {
                        **SAMPLE_SCRIP_PAYLOAD["sheets"][0]["records"][0],
                        "type_specific_fields": {"claim_number": "5473", "undeclared_key": "x"},
                    }
                ],
            }
        ],
    }
    with pytest.raises(ValidationError, match="undeclared_key"):
        parse_collection(payload, document_type="Scrip")


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
