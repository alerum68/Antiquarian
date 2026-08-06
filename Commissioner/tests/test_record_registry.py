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
