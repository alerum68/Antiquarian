from Commissioner.models import FACT_DEFINITIONS, FactScope, get_fact_definition


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
    import pytest
    with pytest.raises(KeyError, match="Coordinator"):
        get_fact_definition("Coordinator")
