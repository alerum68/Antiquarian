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
        "event_place", "citation_text", "citation_details", "review",
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

# Every field that carries LLM-facing guidance text in schema.json, verbatim. models.py
# must reproduce these exactly so Collection.model_json_schema() stays a drop-in
# replacement for schema.json - a missing or paraphrased description is a real regression
# that a field-names-only comparison cannot see.
EXPECTED_DESCRIPTIONS = {
    ('DocumentMetadata', 'source_name'): "The name of the institution this document is from, if this sheet states it (e.g. a parish/church's own printed heading or running title), read exactly as written. Null if this sheet never states it.",
    ('Participant', 'age_unit'): 'Unit for the age field. Infant baptism/burial ages are often given in months or days rather than years - set this explicitly whenever age is present; leave both null if no age is stated.',
    ('Participant', 'alternate_names'): "A later annotator's marginal note suggesting a different spelling of this person's name (not the priest's own original entry, and not a disagreement to resolve - both readings are kept). Leave empty/null if the margin has no such note. Do not use this for your own uncertainty about the body text's own reading - that's std_given/std_surname plus review/review_reason.",
    ('Participant', 'birth_date'): 'Your best English-language reading of the date exactly as it appears. Final ISO formatting is handled downstream, not by you.',
    ('Participant', 'death_date'): 'Your best English-language reading of the date exactly as it appears. Final ISO formatting is handled downstream, not by you.',
    ('Participant', 'facts'): "Any fact about this participant beyond the fields above, named from this record type's valid event vocabulary (the same vocabulary event_type is drawn from) - e.g. an immigration year, a naturalization status. Leave empty/null when nothing beyond the fields above applies; do not duplicate a fact already covered by a named field (occupation, birth_date, etc.) here.",
    ('Participant', 'review'): "True if THIS participant's own data (name reading, dates, role assignment, etc.) is uncertain, guessed, illegible, or otherwise needs a human to double-check it.",
    ('Participant', 'review_reason'): 'Short plain-English note (under 15 words) explaining why this participant needs review. Null if review is false.',
    ('Participant', 'role_name'): 'Choose exactly one value from this record type\'s valid role vocabulary, given in the system instructions. Null only when the source itself provides no relationship/role data at all for this person (e.g. a pre-1880 US census record) - never leave null merely because a role is unclear; use "Other" for that instead.',
    ('Participant', 'role_number'): 'Leave null. The numeric role code is derived downstream from role_name, not chosen by you.',
    ('Participant', 'sex'): 'Infer from role/given name if not explicitly stated. Use "U" only when genuinely indeterminate (e.g. an unfamiliar name with no role or contextual clue) - never leave this unset.',
    ('Participant', 'std_given'): 'Your best linguistic standardization of the given name, diacritics included. Diacritic stripping is handled downstream, not by you.',
    ('Participant', 'std_surname'): 'Your best linguistic standardization of the surname, diacritics included. Diacritic stripping is handled downstream, not by you.',
    ('Participant', 'type_specific_fields'): "Additional fields specific to this record type, defined by its .pmt file's front matter.",
    ('Record', 'continues_from_previous_image'): "True ONLY if a 'CONTINUATION FROM PREVIOUS IMAGE' context block was given to you AND this record's content is what completes it - in that case this must be the FIRST record you output, containing the FULL merged content (the given prior content plus what you read here), and record_number/year copied from the given context. False in every other case, including when no such context was given at all.",
    ('Record', 'continues_on_next_image'): 'True ONLY for the LAST record on this image, when its content appears to end abruptly at the very bottom of the visible page - cut off mid-sentence, no natural closing or signature - suggesting it continues onto content you cannot see. False for every other record, and false for the last record too if it has a normal, complete ending. See UNIVERSAL OUTPUT RULES for how this is used.',
    ('Record', 'event_date'): "Your best English-language reading of the date exactly as it appears (e.g. 'December 12, 1850'). Final ISO formatting is handled downstream, not by you.",
    ('Record', 'event_type'): "Choose exactly one value from this record type's valid event vocabulary, given in the system instructions.",
    ('Record', 'record_id'): 'Leave null. Derived downstream from event_type and record_number, not chosen by you.',
    ('Record', 'review'): 'True if any part of this record (dates, place, transcription, translation, or any participant) is uncertain, guessed, illegible, or otherwise needs a human to double-check it.',
    ('Record', 'review_reason'): 'Short plain-English note (under 15 words) explaining why this record needs review. Null if review is false.',
    ('Record', 'type_specific_fields'): "Additional fields specific to this record type, defined by its .pmt file's front matter. For a pre-1850 US census record with only a named head of household, this is also where an unnamed household_tally (age/sex/race bracket counts) belongs - not fabricated participant entries.",
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


def test_models_match_schema_json_field_descriptions():
    """Guardrail: field names alone can't catch a dropped description, and the
    descriptions ARE the LLM-facing guidance - losing one silently degrades extraction
    quality with no other symptom."""
    defs = Collection.model_json_schema().get("$defs", {})

    for (class_name, field_name), expected_description in EXPECTED_DESCRIPTIONS.items():
        assert class_name in defs, f"{class_name} missing from $defs"
        properties = defs[class_name]["properties"]
        assert field_name in properties, f"{class_name}.{field_name} missing from $defs"
        actual = properties[field_name].get("description")
        assert actual == expected_description, (
            f"{class_name}.{field_name}: description drifted from schema.json\n"
            f"  expected: {expected_description!r}\n"
            f"  actual:   {actual!r}"
        )


def _schema_json_descriptions():
    schema = json.loads(SCHEMA_JSON_PATH.read_text(encoding="utf-8"))
    sheet_props = schema["properties"]["sheets"]["items"]["properties"]
    record_props = sheet_props["records"]["items"]["properties"]
    participant_props = record_props["participants"]["items"]["properties"]
    found = {}
    for class_name, properties in (
        ("DocumentMetadata", sheet_props["document_metadata"]["properties"]),
        ("Record", record_props),
        ("Participant", participant_props),
    ):
        for field_name, spec in properties.items():
            if "description" in spec:
                found[(class_name, field_name)] = spec["description"]
    return found


def test_expected_descriptions_still_matches_real_schema_json():
    """The EXPECTED_DESCRIPTIONS literals above are the contract; this proves they are
    still a faithful copy of the real schema.json Paleographer ships, so the guardrail
    can't quietly pass against a stale expectation."""
    assert _schema_json_descriptions() == EXPECTED_DESCRIPTIONS


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


def test_only_participant_fields_are_required():
    """schema.json's only `required` list is on Participant's item schema; every other
    field is modeled as optional. Record/Sheet must not be stricter than the source of
    truth, or real extractions that omit e.g. page_id would fail validation."""
    defs = Collection.model_json_schema()["$defs"]

    assert set(defs["Participant"].get("required", [])) == {
        "role_name", "std_given", "is_priest", "sex",
    }
    for class_name in ("Record", "Sheet", "DocumentMetadata", "Collection"):
        source = defs[class_name] if class_name in defs else Collection.model_json_schema()
        assert not source.get("required"), (
            f"{class_name} declares required fields, but schema.json requires none of them: "
            f"{source.get('required')}"
        )

    # And the concrete case: a Record/Sheet with none of those four fields still validates.
    sheet = Sheet(records=[Record()])
    assert sheet.page_id is None
    assert sheet.records[0].page is None
    assert sheet.records[0].record_number is None
    assert sheet.records[0].event_type is None


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
