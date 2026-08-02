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


# ==========================================
# MERGE (source_documents shape)
# ==========================================
def test_label_for_prefers_document_type_over_page():
    record = {"page": "page_002", "type_specific_fields": {"document_type": "Witness Affidavit"}}
    assert postprocess._label_for(record) == "Witness Affidavit"


def test_label_for_falls_back_to_page():
    record = {"page": "page_002", "type_specific_fields": {}}
    assert postprocess._label_for(record) == "Page page_002"


def test_label_for_falls_back_to_untitled():
    record = {}
    assert postprocess._label_for(record) == "Untitled section"


def test_merge_record_into_builds_source_documents_from_scratch():
    base = {
        "page": "page_001",
        "original_transcription": "base original text",
        "english_translation": "base english text",
        "type_specific_fields": {"document_type": "Witness Affidavit", "scrip_number": "12751"},
        "participants": [],
    }
    incoming = {
        "page": "page_002",
        "original_transcription": "incoming original text",
        "english_translation": "incoming english text",
        "type_specific_fields": {"document_type": "Claimant's Own Affidavit", "claim_number": "3126"},
        "participants": [],
    }

    postprocess._merge_record_into(base, incoming)

    # base's own top-level transcription fields are untouched, not flattened/labeled
    assert base["original_transcription"] == "base original text"
    assert base["english_translation"] == "base english text"

    assert base["source_documents"] == [
        {"document_type": "Witness Affidavit", "page": "page_001",
         "original_transcription": "base original text", "english_translation": "base english text"},
        {"document_type": "Claimant's Own Affidavit", "page": "page_002",
         "original_transcription": "incoming original text", "english_translation": "incoming english text"},
    ]

    # incoming's own type_specific_fields fold into base without overwriting existing keys
    assert base["type_specific_fields"]["scrip_number"] == "12751"
    assert base["type_specific_fields"]["claim_number"] == "3126"
    assert "document_type" not in base["type_specific_fields"] or base["type_specific_fields"]["document_type"] == "Witness Affidavit"


def test_merge_record_into_appends_third_document_without_duplicating_base_entry():
    base = {"page": "page_001", "original_transcription": "base text", "english_translation": "",
            "type_specific_fields": {"document_type": "Witness Affidavit"}, "participants": []}
    second = {"page": "page_002", "original_transcription": "second text", "english_translation": "",
              "type_specific_fields": {"document_type": "Claimant's Own Affidavit"}, "participants": []}
    third = {"page": "page_003", "original_transcription": "third text", "english_translation": "",
             "type_specific_fields": {"document_type": "Commissioner's Certificate"}, "participants": []}

    postprocess._merge_record_into(base, second)
    postprocess._merge_record_into(base, third)

    assert len(base["source_documents"]) == 3
    assert [d["document_type"] for d in base["source_documents"]] == [
        "Witness Affidavit", "Claimant's Own Affidavit", "Commissioner's Certificate"]


def test_merge_record_into_merges_review_reasons():
    base = {"page": "page_001", "original_transcription": "", "english_translation": "",
            "type_specific_fields": {}, "participants": []}
    incoming = {"page": "page_002", "original_transcription": "", "english_translation": "",
                "type_specific_fields": {}, "participants": [], "review": True,
                "review_reason": "illegible witness name"}

    postprocess._merge_record_into(base, incoming)
    assert base["review"] is True
    assert base["review_reason"] == "illegible witness name"


def test_merge_record_into_merges_participants_by_name_filling_blank_fields_only():
    base = {"page": "page_001", "original_transcription": "", "english_translation": "",
            "type_specific_fields": {}, "participants": [
                {"std_given": "Roger", "std_surname": "Letendre", "role_name": "Claimant"},
            ]}
    incoming = {"page": "page_002", "original_transcription": "", "english_translation": "",
                "type_specific_fields": {}, "participants": [
                    {"std_given": "Roger", "std_surname": "Letendre", "marital_status": "Married"},
                    {"std_given": "Olivier", "std_surname": "Larocque", "role_name": "Witness"},
                ]}

    postprocess._merge_record_into(base, incoming)

    assert len(base["participants"]) == 2
    roger = next(p for p in base["participants"] if p["std_surname"] == "Letendre")
    assert roger["role_name"] == "Claimant"  # not overwritten
    assert roger["marital_status"] == "Married"  # filled in from incoming
    assert any(p["std_surname"] == "Larocque" for p in base["participants"])


def test_merge_same_claim_records_merges_matching_record_ids_across_one_sheet():
    witness_affidavit = {
        "record_id": "SCRIP-5473", "page": "page_001",
        "original_transcription": "witness text", "english_translation": "",
        "type_specific_fields": {"document_type": "Witness Affidavit"}, "participants": [],
    }
    claimant_affidavit = {
        "record_id": "SCRIP-5473", "page": "page_002",
        "original_transcription": "claimant text", "english_translation": "",
        "type_specific_fields": {"document_type": "Claimant's Own Affidavit"}, "participants": [],
    }
    unrelated = {
        "record_id": "SCRIP-9999", "page": "page_003",
        "original_transcription": "unrelated text", "english_translation": "",
        "type_specific_fields": {}, "participants": [],
    }
    sheets = [{"records": [witness_affidavit, claimant_affidavit, unrelated]}]

    postprocess.merge_same_claim_records(sheets)

    assert len(sheets[0]["records"]) == 2
    survivor = next(r for r in sheets[0]["records"] if r["record_id"] == "SCRIP-5473")
    assert len(survivor["source_documents"]) == 2
    assert survivor["original_transcription"] == "witness text"  # base's own text, untouched


def test_merge_same_claim_records_leaves_records_without_record_id_alone():
    no_id_a = {"page": "page_001", "original_transcription": "", "english_translation": "",
               "type_specific_fields": {}, "participants": []}
    no_id_b = {"page": "page_002", "original_transcription": "", "english_translation": "",
               "type_specific_fields": {}, "participants": []}
    sheets = [{"records": [no_id_a, no_id_b]}]

    postprocess.merge_same_claim_records(sheets)

    assert len(sheets[0]["records"]) == 2
    assert "source_documents" not in no_id_a
    assert "source_documents" not in no_id_b
