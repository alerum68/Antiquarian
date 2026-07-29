import postprocess

PARISH_ROLES = {
    "1": {"name": "Primary", "semantic": "primary"},
    "2": {"name": "Father", "semantic": "father"},
    "3": {"name": "Mother", "semantic": "mother"},
    "7": {"name": "Godfather/Witness 1"},
}

SCRIP_ROLES = {
    "1": {"name": "Claimant", "semantic": "primary"},
    "2": {"name": "Spouse", "semantic": "spouse"},
    "4": {"name": "Witness"},
}

PARISH_EVENT_TYPES = {
    "Baptism": {"code": "1", "id_prefix": "B-"},
    "Marriage": {"code": "2", "id_prefix": "M-"},
    "Burial": {"code": "3", "id_prefix": "S-"},
}


def test_strip_diacritics_removes_accents():
    assert postprocess.strip_diacritics("Gaïgnon") == "Gaignon"
    assert postprocess.strip_diacritics("Château") == "Chateau"


def test_strip_diacritics_passthrough_ascii_and_none():
    assert postprocess.strip_diacritics("Smith") == "Smith"
    assert postprocess.strip_diacritics(None) is None


def test_parse_to_iso_full_date():
    assert postprocess.parse_to_iso("December 12, 1850") == "1850-12-12"
    assert postprocess.parse_to_iso("12 December 1850") == "1850-12-12"


def test_parse_to_iso_month_year_only():
    assert postprocess.parse_to_iso("December 1850") == "1850-12"


def test_parse_to_iso_passes_through_already_iso_dates():
    """Regression: a live model run showed Gemini sometimes reaches for ISO formatting
    directly for 'event_date' regardless of the prompt asking for a plain reading. An
    earlier version of this function had no pattern for already-ISO input at all and
    silently returned None, erasing a perfectly good date."""
    assert postprocess.parse_to_iso("1849-01-11") == "1849-01-11"
    assert postprocess.parse_to_iso("1849-01") == "1849-01"


def test_parse_to_iso_bare_year():
    assert postprocess.parse_to_iso("1850") == "1850"


def test_parse_to_iso_unparseable_returns_none():
    assert postprocess.parse_to_iso("sometime last century") is None
    assert postprocess.parse_to_iso(None) is None
    assert postprocess.parse_to_iso("") is None


def test_derive_record_identity_sets_id():
    record = {"event_type": "Baptism", "record_number": "14"}
    postprocess.derive_record_identity(record, PARISH_EVENT_TYPES)
    assert record["record_id"] == "B-14"
    assert "record_type_code" not in record


def test_derive_record_identity_noops_on_unknown_event_type():
    record = {"event_type": "Something Unrecognized", "record_number": "14"}
    postprocess.derive_record_identity(record, PARISH_EVENT_TYPES)
    assert "record_id" not in record


def test_derive_record_identity_noops_without_record_number():
    record = {"event_type": "Baptism"}
    postprocess.derive_record_identity(record, PARISH_EVENT_TYPES)
    assert "record_id" not in record
    assert "record_id" not in record


def test_derive_role_numbers_matches_by_role_name():
    record = {"participants": [{"role_name": "Primary"}, {"role_name": "father"}]}
    postprocess.derive_role_numbers(record, PARISH_ROLES)
    assert record["participants"][0]["role_number"] == "1"
    assert record["participants"][1]["role_number"] == "2"


def test_derive_role_numbers_leaves_unmatched_role_blank():
    record = {"participants": [{"role_name": "Unknown Role"}]}
    postprocess.derive_role_numbers(record, PARISH_ROLES)
    assert "role_number" not in record["participants"][0]


def test_derive_role_numbers_does_not_overwrite_existing():
    record = {"participants": [{"role_name": "Primary", "role_number": "9"}]}
    postprocess.derive_role_numbers(record, PARISH_ROLES)
    assert record["participants"][0]["role_number"] == "9"


def test_derive_role_semantics_sets_semantic_from_role_number():
    record = {"participants": [{"role_number": "1"}, {"role_number": "2"}]}
    postprocess.derive_role_semantics(record, PARISH_ROLES)
    assert record["participants"][0]["role_semantic"] == "primary"
    assert record["participants"][1]["role_semantic"] == "father"


def test_derive_role_semantics_leaves_participant_without_semantic_untouched():
    record = {"participants": [{"role_number": "7"}, {"role_number": "9"}]}
    postprocess.derive_role_semantics(record, PARISH_ROLES)
    assert "role_semantic" not in record["participants"][0]
    assert "role_semantic" not in record["participants"][1]


def test_derive_role_semantics_noops_without_role_number():
    record = {"participants": [{"role_name": "Primary"}]}
    postprocess.derive_role_semantics(record, PARISH_ROLES)
    assert "role_semantic" not in record["participants"][0]


def test_derive_suffixes_sets_jr_sr_on_matching_names():
    record = {"participants": [
        {"role_number": "1", "std_given": "Jean", "std_surname": "Gagnon"},
        {"role_number": "2", "std_given": "Jean", "std_surname": "Gagnon"},
    ]}
    postprocess.derive_suffixes(record, PARISH_ROLES)
    assert record["participants"][0]["suffix"] == "Jr"
    assert record["participants"][1]["suffix"] == "Sr"


def test_derive_suffixes_noop_when_names_differ():
    record = {"participants": [
        {"role_number": "1", "std_given": "Jean", "std_surname": "Gagnon"},
        {"role_number": "2", "std_given": "Pierre", "std_surname": "Gagnon"},
    ]}
    postprocess.derive_suffixes(record, PARISH_ROLES)
    assert "suffix" not in record["participants"][0]
    assert "suffix" not in record["participants"][1]


def test_derive_suffixes_noop_when_role_table_has_no_father_semantic():
    """Scrip's roles table has no 'father' semantic entry at all: this must no-op
    cleanly rather than raise, proving the atomic-field design generalizes to record
    types with no comparable parent/child relationship."""
    record = {"participants": [
        {"role_number": "1", "std_given": "Baptiste", "std_surname": "Ledoux"},
        {"role_number": "2", "std_given": "Baptiste", "std_surname": "Ledoux"},
    ]}
    postprocess.derive_suffixes(record, SCRIP_ROLES)
    assert "suffix" not in record["participants"][0]
    assert "suffix" not in record["participants"][1]


def test_apply_defaults_fills_only_blank_fields():
    target = {"religion": "", "occupation": "Farmer"}
    postprocess.apply_defaults(target, {"religion": "Roman Catholic", "occupation": "Unknown"})
    assert target["religion"] == "Roman Catholic"
    assert target["occupation"] == "Farmer"


def test_apply_defaults_ignores_fields_not_in_table():
    target = {"given": "Jean"}
    postprocess.apply_defaults(target, {"religion": "Roman Catholic"})
    assert target == {"given": "Jean", "religion": "Roman Catholic"}
