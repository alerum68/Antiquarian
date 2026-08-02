"""
Tests for Archivist's semantic-driven role/family-linking logic - the generalization
that replaced hardcoded role_number digit checks (role "2" is always "Father", role "4"
is always the marriage bride, ...) with a small fixed role_semantic vocabulary
(primary/spouse/child/father/mother/father_in_law/mother_in_law) read directly off each
participant, the same way for any record type.
"""

import pandas as pd

import Archivist as arc


def test_generate_uid_same_person_same_page_matches():
    """Baseline: identical record_id/role/page must always collide onto one UID."""
    rec = {"page": "page_001", "record_id": "SCRIP-5473", "participants": [{"role_number": "1"}]}
    part = rec["participants"][0]
    assert arc.generate_uid(rec, part, "1") == arc.generate_uid(dict(rec), part, "1")


def test_generate_uid_same_record_id_different_page_still_matches():
    """Regression: confirmed live, two JSON records for the same real person on different
    pages used to hash to different UIDs (page was part of the hash input) - two separate
    INDI blocks for one person. page must no longer affect the UID at all when record_id
    (or lac_pid) is the same."""
    part = {"role_number": "1"}
    rec_page_1 = {"page": "page_001", "record_id": "SCRIP-5473", "participants": [part]}
    rec_page_2 = {"page": "page_002", "record_id": "SCRIP-5473", "participants": [part]}

    assert arc.generate_uid(rec_page_1, part, "1") == arc.generate_uid(rec_page_2, part, "1")


def test_generate_uid_prefers_lac_pid_over_record_id():
    """Once Commissioner attaches lac_pid, it must take priority over record_id (LAC's own
    authoritative identifier vs. an OCR'd record_number) - proven here by two records with
    DIFFERENT record_ids but the SAME lac_pid still colliding onto one UID."""
    part = {"role_number": "1"}
    rec_a = {"page": "page_001", "record_id": "SCRIP-5473", "lac_pid": "1502188", "participants": [part]}
    rec_b = {"page": "page_002", "record_id": "SCRIP-9999", "lac_pid": "1502188", "participants": [part]}

    assert arc.generate_uid(rec_a, part, "1") == arc.generate_uid(rec_b, part, "1")


def test_get_dynamic_source_id_omits_prefix_for_scrip():
    """Per the user: LAC volume numbers are already globally unique on their own, unlike
    Parish which needs register_source_id to disambiguate two parishes sharing a volume
    number - "with Scrip it shouldn't have the @S1 just @S"."""
    original = arc.GENERAL_CONFIG.get('omit_source_id_prefix')
    try:
        arc.GENERAL_CONFIG['omit_source_id_prefix'] = True
        assert arc.get_dynamic_source_id("1324") == "@S1324@"
    finally:
        arc.GENERAL_CONFIG['omit_source_id_prefix'] = original


def test_get_dynamic_source_id_keeps_prefix_by_default_for_parish():
    """Unchanged existing behavior for every record type other than Scrip - the flag
    defaults to falsy/unset, so Parish's own register_source_id-based disambiguation
    keeps working exactly as before."""
    original = arc.GENERAL_CONFIG.get('omit_source_id_prefix')
    try:
        arc.GENERAL_CONFIG['omit_source_id_prefix'] = False
        assert arc.get_dynamic_source_id("1324") == "@S11324@"
    finally:
        arc.GENERAL_CONFIG['omit_source_id_prefix'] = original


def test_run_general_flavor_sets_omit_prefix_flag_from_record_type(monkeypatch, tmp_path):
    """run_general_flavor is the one place that decides the flag, from record_type_name -
    confirms it actually gets set (True for Scrip, False otherwise) before any GEDCOM is
    built, without needing to exercise the full file-writing path."""
    monkeypatch.setattr(arc, "resolve_gedcom_output_targets", lambda: [])
    arc.run_general_flavor({"record_type_name": "Scrip", "sheets": []})
    assert arc.GENERAL_CONFIG['omit_source_id_prefix'] is True

    arc.run_general_flavor({"record_type_name": "Parish", "sheets": []})
    assert arc.GENERAL_CONFIG['omit_source_id_prefix'] is False


def test_generate_uid_different_record_id_still_differs_without_lac_pid():
    """Sanity check the fix didn't accidentally collapse everything - genuinely different
    claims (no lac_pid on either) must still get different UIDs."""
    part = {"role_number": "1"}
    rec_a = {"page": "page_001", "record_id": "SCRIP-5473", "participants": [part]}
    rec_b = {"page": "page_001", "record_id": "SCRIP-9999", "participants": [part]}

    assert arc.generate_uid(rec_a, part, "1") != arc.generate_uid(rec_b, part, "1")


def test_generate_media_uid_for_path_deterministic_and_path_keyed():
    a = arc.generate_media_uid_for_path("C:/Media/Commissioner/1502188/e011355548.pdf")
    b = arc.generate_media_uid_for_path("C:/Media/Commissioner/1502188/e011355548.pdf")
    c = arc.generate_media_uid_for_path("C:/Media/Commissioner/1502188/e011355549.pdf")
    assert a == b
    assert a != c
    assert a.startswith("M")


def test_build_general_citation_page_line_uses_claim_affdt_when_present():
    """RootsMagic/FTM auto-name citations from this PAGE line - "Record EVEN-1964" (an
    internal id_prefix+number) made the Citations list unbrowsable in real testing. Use
    the claim's own real reference numbers instead when known."""
    rec = {"page": "3", "record_id": "EVEN-1964", "year": "1901",
           "type_specific_fields": {"claim_number": "1964", "affidavit_number": "850"},
           "original_transcription": "text", "english_translation": "text"}
    part = {"std_given": "Roger", "std_surname": "Letendre", "role_number": "1"}
    blocks = arc.build_general_citation(rec, part, "EVEN", "1", "M0000000001")
    assert "3 PAGE Claim 1964; Affdt 850, Page 3" in blocks[0]
    assert "Record EVEN-1964" not in blocks[0]


def test_build_general_citation_page_line_falls_back_without_claim_affdt():
    rec = {"page": "3", "record_id": "B-1", "year": "1876",
           "original_transcription": "text", "english_translation": "text"}
    part = {"std_given": "Jean", "std_surname": "Gagnon", "role_number": "1"}
    blocks = arc.build_general_citation(rec, part, "BIRT", "1", "M0000000001")
    assert "3 PAGE Page 3, Record B-1" in blocks[0]


def test_build_general_citation_single_block_without_source_documents():
    """Backward compatibility: every record type that never populates source_documents
    (everything except Parish/Scrip claims that went through the merge step) must get
    exactly the same single-block behavior as before."""
    rec = {"page": "1", "record_id": "B-1", "year": "1876",
           "original_transcription": "orig text", "english_translation": "eng text"}
    part = {"std_given": "Jean", "std_surname": "Gagnon", "role_number": "1"}
    blocks = arc.build_general_citation(rec, part, "BIRT", "1", "M0000000001")
    assert isinstance(blocks, list)
    assert len(blocks) == 1
    assert "orig text" in blocks[0]
    assert "eng text" in blocks[0]


def test_build_general_citation_collapses_identical_original_and_translation():
    """Per the user: most Scrip affidavits are already in English, so
    original_transcription and english_translation end up identical - showing both the
    "English Translation:"/"Original Transcription:" headers in that case just duplicates
    the same text twice. Only one plain text block, no header labels, when they match."""
    rec = {"page": "1", "record_id": "B-1", "year": "1876",
           "original_transcription": "I, Roger Letendre, do solemnly swear...",
           "english_translation": "I, Roger Letendre, do solemnly swear..."}
    part = {"std_given": "Roger", "std_surname": "Letendre", "role_number": "1"}
    blocks = arc.build_general_citation(rec, part, "EVEN", "1", "M0000000001")

    assert len(blocks) == 1
    assert blocks[0].count("I, Roger Letendre, do solemnly swear") == 1
    assert "English Translation:" not in blocks[0]
    assert "Original Transcription:" not in blocks[0]
    assert "4 TEXT I, Roger Letendre" in blocks[0]


def test_build_general_citation_normalization_is_whitespace_only_not_fuzzy():
    """Word order actually differing (the "1964" moved) is a genuine content difference,
    not just reflow - must NOT collapse, proving the normalization added for whitespace
    reflow doesn't also hide a real mismatch via fuzzy/reordering matching."""
    rec = {"page": "1", "record_id": "B-1", "year": "1876",
           "original_transcription": "1964\nForm A. (2).\nNORTH-WEST HALFBREED CLAIMS COMMISSION.",
           "english_translation": "Form A. (2). NORTH-WEST HALFBREED CLAIMS COMMISSION. 1964"}
    part = {"std_given": "Roger", "std_surname": "Letendre", "role_number": "1"}
    blocks = arc.build_general_citation(rec, part, "EVEN", "1", "M0000000001")

    assert len(blocks) == 1
    assert "English Translation:" in blocks[0]
    assert "Original Transcription:" in blocks[0]


def test_build_general_citation_collapses_whitespace_only_reflow():
    """The actual confirmed-live case: same words, same order, only newlines vs. spaces
    differ - this one must collapse."""
    rec = {"page": "1", "record_id": "B-1", "year": "1876",
           "original_transcription": "Form A. (2).\nNORTH-WEST HALFBREED CLAIMS COMMISSION.\nBefore me.",
           "english_translation": "Form A. (2). NORTH-WEST HALFBREED CLAIMS COMMISSION. Before me."}
    part = {"std_given": "Roger", "std_surname": "Letendre", "role_number": "1"}
    blocks = arc.build_general_citation(rec, part, "EVEN", "1", "M0000000001")

    assert len(blocks) == 1
    assert "English Translation:" not in blocks[0]
    assert "Original Transcription:" not in blocks[0]
    assert "NORTH-WEST HALFBREED CLAIMS COMMISSION" in blocks[0]


def test_build_general_citation_collapses_when_only_one_side_populated():
    rec = {"page": "1", "record_id": "B-1", "year": "1876",
           "original_transcription": "", "english_translation": "Only a translation exists here."}
    part = {"std_given": "Roger", "std_surname": "Letendre", "role_number": "1"}
    blocks = arc.build_general_citation(rec, part, "EVEN", "1", "M0000000001")

    assert len(blocks) == 1
    assert "Only a translation exists here." in blocks[0]
    assert "English Translation:" not in blocks[0]
    assert "Original Transcription:" not in blocks[0]


def test_build_general_citation_keeps_both_blocks_for_a_genuine_translation():
    """The other direction: a real French-original document with a distinct English
    translation must keep both labeled sections - nothing to collapse there."""
    rec = {"page": "1", "record_id": "B-1", "year": "1876",
           "original_transcription": "Je soussigné jure solennellement...",
           "english_translation": "I, the undersigned, do solemnly swear..."}
    part = {"std_given": "Roger", "std_surname": "Letendre", "role_number": "1"}
    blocks = arc.build_general_citation(rec, part, "EVEN", "1", "M0000000001")

    assert len(blocks) == 1
    assert "English Translation:" in blocks[0]
    assert "Original Transcription:" in blocks[0]
    assert "Je soussigné" in blocks[0]
    assert "I, the undersigned" in blocks[0]
    assert "-- " not in blocks[0]  # no document_type suffix when there's nothing to distinguish


def test_build_general_citation_one_block_per_source_document():
    rec = {"page": "1", "record_id": "SCRIP-5473", "year": "1880", "source_documents": [
        {"document_type": "Witness Affidavit", "page": "page_001",
         "original_transcription": "witness orig", "english_translation": "witness eng"},
        {"document_type": "Claimant's Own Affidavit", "page": "page_002",
         "original_transcription": "claimant orig", "english_translation": "claimant eng"},
    ]}
    part = {"std_given": "Roger", "std_surname": "Letendre", "role_number": "1"}
    blocks = arc.build_general_citation(rec, part, "EVEN", "1", "M0000000001")

    assert len(blocks) == 2
    assert "-- Witness Affidavit" in blocks[0]
    assert "Page page_001" in blocks[0]
    assert "witness orig" in blocks[0] and "witness eng" in blocks[0]
    assert "claimant orig" not in blocks[0]

    assert "-- Claimant's Own Affidavit" in blocks[1]
    assert "Page page_002" in blocks[1]
    assert "claimant orig" in blocks[1] and "claimant eng" in blocks[1]
    assert "witness orig" not in blocks[1]

    # record_id (shared across all merged documents) stays constant across both blocks
    assert "Record SCRIP-5473" in blocks[0]
    assert "Record SCRIP-5473" in blocks[1]


def test_build_general_citation_media_only_entry_uses_its_own_path_derived_uid():
    """A Commissioner-downloaded certificate has no transcription, only a media_path -
    its citation block must reference an OBJE built from generate_media_uid_for_path on
    THAT path, not the shared media_uid passed in for the sheet's own scanned image."""
    media_path = "C:/Media/Commissioner/1502999/e099999999.pdf"
    rec = {"page": "1", "record_id": "SCRIP-5473", "year": "1880", "source_documents": [
        {"document_type": "Scrip Certificate", "media_path": media_path},
    ]}
    part = {"std_given": "Roger", "std_surname": "Letendre", "role_number": "1"}
    blocks = arc.build_general_citation(rec, part, "EVEN", "1", "M_SHEET_UID")

    expected_uid = arc.generate_media_uid_for_path(media_path)
    assert f"3 OBJE @{expected_uid}@" in blocks[0]
    assert "M_SHEET_UID" not in blocks[0]
    assert "-- Scrip Certificate" in blocks[0]


def test_build_gedcom_from_general_creates_separate_objE_for_commissioner_media():
    media_path = "C:/Media/Commissioner/1502999/e099999999.pdf"
    data = {
        "collection_title": "Test Scrip Collection", "record_type_name": "Scrip",
        "sheets": [{
            "document_metadata": {"file_name": "BAC-LAC_fonandcol_1502188.pdf", "pages": "1", "file_type": "pdf"},
            "records": [{
                "event_type": "Scrip", "page": "1", "record_id": "SCRIP-5473", "year": "1880",
                "type_specific_fields": {}, "source_documents": [
                    {"document_type": "Scrip Certificate", "media_path": media_path},
                ],
                "participants": [make_participant("primary", given="Roger", surname="Letendre")],
            }],
        }],
    }
    ged = arc.build_gedcom_from_general(data, "RM")

    expected_uid = arc.generate_media_uid_for_path(media_path)
    assert f"0 @{expected_uid}@ OBJE" in ged
    assert f"1 FILE {media_path}" in ged
    assert "2 TITL Scrip Certificate" in ged
    assert f"3 OBJE @{expected_uid}@" in ged  # the citation references the same UID


def test_generate_media_uid_for_lac_asset_uses_the_e_number_directly():
    """Confirmed live in review: an opaque hashed media UID makes a real GEDCOM harder to
    cross-reference by hand against LAC - the e-number's digits are already a stable,
    unique identifier, so they should be used directly rather than hashed. The leading
    "e" is stripped (not kept) - per the user, FTM import breaks on a non-numeric media
    object ID, so everything after the fixed "M" prefix must stay digits-only."""
    assert arc.generate_media_uid_for_lac_asset("e011359206") == "M011359206"


def test_build_general_citation_prefers_lac_asset_id_over_hashed_path():
    """The realistic Commissioner shape: a source_documents entry always carries both
    media_path AND lac_asset_id - the e-number must win over hashing the path."""
    media_path = "C:/Media/Commissioner/1503710/e011359206.pdf"
    rec = {"page": "1", "record_id": "SCRIP-5473", "year": "1880", "source_documents": [
        {"document_type": "Scrip Certificate", "media_path": media_path, "lac_asset_id": "e011359206"},
    ]}
    part = {"std_given": "Margaret", "std_surname": "Sabiston", "role_number": "1"}
    blocks = arc.build_general_citation(rec, part, "EVEN", "1", "M_SHEET_UID")

    assert "3 OBJE @M011359206@" in blocks[0]
    hashed_uid = arc.generate_media_uid_for_path(media_path)
    assert f"@{hashed_uid}@" not in blocks[0]


def test_build_gedcom_from_general_uses_lac_asset_id_for_objE_when_present():
    media_path = "C:/Media/Commissioner/1503710/e011359206.pdf"
    data = {
        "collection_title": "Test Scrip Collection", "record_type_name": "Scrip",
        "sheets": [{
            "document_metadata": {"file_name": "e011359206.pdf", "pages": "1", "file_type": "pdf"},
            "records": [{
                "event_type": "Scrip", "page": "1", "record_id": "SCRIP-5473", "year": "1880",
                "type_specific_fields": {}, "source_documents": [
                    {"document_type": "Scrip Certificate", "media_path": media_path, "lac_asset_id": "e011359206"},
                ],
                "participants": [make_participant("primary", given="Margaret", surname="Sabiston")],
            }],
        }],
    }
    ged = arc.build_gedcom_from_general(data, "RM")

    assert "0 @M011359206@ OBJE" in ged
    assert f"1 FILE {media_path}" in ged
    assert "3 OBJE @M011359206@" in ged


def test_build_individual_scrip_desc_line_groups_claim_affidavit_scrip_together():
    original = arc.GENERAL_CONFIG.get('omit_source_id_prefix')
    try:
        arc.GENERAL_CONFIG['omit_source_id_prefix'] = True
        rec = {"event_type": "Scrip", "page": "1", "record_id": "SCRIP-5473", "event_place": "Winnipeg",
               "type_specific_fields": {
                   "claim_number": "3126", "affidavit_number": "5473",
                   "scrip_number": "12761", "scrip_amount": "$160", "claim_basis": "Half-breed Head",
               },
               "participants": [make_participant("primary", given="Roger", surname="Letendre")]}
        primary = rec["participants"][0]
        lines, _, _, _ = arc.build_individual("I1", rec, primary, "1", "M0000000001", "26 JUL 2026", False, "RM")
        joined = "\n".join(lines)

        assert "1 EVEN Claim: 3126; Affidavit #: 5473; Scrip #: 12761 ($160); Claim Basis: Half-breed Head" in joined
    finally:
        arc.GENERAL_CONFIG['omit_source_id_prefix'] = original


def test_build_individual_scrip_desc_line_without_claim_or_affidavit_still_shows_scrip_number():
    """No claim_number/affidavit_number present (e.g. an older extraction) - the fact's own
    value line still shows whatever Scrip-specific fields it does have."""
    original = arc.GENERAL_CONFIG.get('omit_source_id_prefix')
    try:
        arc.GENERAL_CONFIG['omit_source_id_prefix'] = True
        rec = {"event_type": "Scrip", "page": "1", "record_id": "SCRIP-1", "event_place": "Winnipeg",
               "type_specific_fields": {"scrip_number": "12761", "scrip_amount": "$160"},
               "participants": [make_participant("primary", given="Roger", surname="Letendre")]}
        primary = rec["participants"][0]
        lines, _, _, _ = arc.build_individual("I1", rec, primary, "1", "M0000000001", "26 JUL 2026", False, "RM")
        joined = "\n".join(lines)

        assert "1 EVEN Scrip #: 12761 ($160)" in joined
        assert "Claim:" not in joined and "Affidavit #:" not in joined
    finally:
        arc.GENERAL_CONFIG['omit_source_id_prefix'] = original


def test_build_individual_scrip_desc_line_excludes_document_type_with_claim():
    """document_type labels ONE physical document (e.g. "Witness Affidavit"), not the
    whole merged claim - showing it in the fact's own value line was misleading (per the
    user, the note appeared to cite only the witness affidavit). Still available per
    citation via _TITL's own "-- {document_type}" suffix, just not here."""
    original = arc.GENERAL_CONFIG.get('omit_source_id_prefix')
    try:
        arc.GENERAL_CONFIG['omit_source_id_prefix'] = True
        rec = {"event_type": "Scrip", "page": "1", "record_id": "SCRIP-5473", "event_place": "Winnipeg",
               "type_specific_fields": {
                   "claim_number": "3126", "affidavit_number": "5473",
                   "scrip_number": "12761", "document_type": "Witness Affidavit",
               },
               "participants": [make_participant("primary", given="Roger", surname="Letendre")]}
        primary = rec["participants"][0]
        lines, _, _, _ = arc.build_individual("I1", rec, primary, "1", "M0000000001", "26 JUL 2026", False, "RM")
        joined = "\n".join(lines)

        assert "Document Type" not in joined
        even_line = next(line for line in lines if line.startswith("1 EVEN"))
        assert "Witness Affidavit" not in even_line
    finally:
        arc.GENERAL_CONFIG['omit_source_id_prefix'] = original


def test_build_individual_scrip_desc_line_excludes_document_type_without_claim():
    """Same exclusion in the no-claim/affidavit path."""
    original = arc.GENERAL_CONFIG.get('omit_source_id_prefix')
    try:
        arc.GENERAL_CONFIG['omit_source_id_prefix'] = True
        rec = {"event_type": "Scrip", "page": "1", "record_id": "SCRIP-1", "event_place": "Winnipeg",
               "type_specific_fields": {"scrip_number": "12761", "document_type": "Register Entry"},
               "participants": [make_participant("primary", given="Roger", surname="Letendre")]}
        primary = rec["participants"][0]
        lines, _, _, _ = arc.build_individual("I1", rec, primary, "1", "M0000000001", "26 JUL 2026", False, "RM")
        joined = "\n".join(lines)

        assert "Document Type" not in joined
        assert "Register Entry" not in joined
    finally:
        arc.GENERAL_CONFIG['omit_source_id_prefix'] = original


def test_parse_household_forms_second_family_unit_for_unrelated_boarder_household():
    """Regression: a family/dwelling-number group can legitimately contain two unrelated
    families (e.g. a boarder sharing a dwelling with an unrelated nuclear family) - real
    1860 census data ('Depar' family sharing a dwelling with boarder 'Hougton'). Previously,
    a plausible spouse pair (matching surname, opposite sex, valid age gap) that didn't
    also fit as a child of the group's first-listed unit was silently discarded instead of
    forming its own unit - every member of the second family fell through to 'unrelated'
    one at a time. parse_household must now recognize the second family as its own unit,
    with subsequent same-surname children correctly attaching to it."""
    rows = [
        {"Given Name": "Joseph", "Surname": "Hougton", "Gender": "Male", "Age": "45"},
        {"Given Name": "James", "Surname": "Depar", "Gender": "Male", "Age": "40"},
        {"Given Name": "Vide", "Surname": "Depar", "Gender": "Female", "Age": "34"},
        {"Given Name": "Lucretia", "Surname": "Depar", "Gender": "Female", "Age": "12"},
    ]
    group = pd.DataFrame(rows)
    units, unrelated, flags = arc.parse_household(group)

    assert len(unrelated) == 0
    assert len(units) == 2
    depar_unit = next(u for u in units
                      if (u["husband"] is not None and arc.clean_val(u["husband"].get("Surname")) == "Depar"))
    assert arc.clean_val(depar_unit["husband"].get("Given Name")) == "James"
    assert arc.clean_val(depar_unit["wife"].get("Given Name")) == "Vide"
    assert [arc.clean_val(c.get("Given Name")) for c in depar_unit["children"]] == ["Lucretia"]


def make_participant(role_semantic=None, role_name="", sex="M", given="Jean", surname="Gagnon",
                     is_priest=False, age=""):
    return {
        "role_semantic": role_semantic, "role_name": role_name, "role_number": "0",
        "sex": sex, "std_given": given, "std_surname": surname, "is_priest": is_priest, "age": age,
    }


def test_get_event_gedcom_tag_person_and_family_buckets():
    assert arc.get_event_gedcom_tag("Baptism") == "BAPM"
    assert arc.get_event_gedcom_tag("Christen") == "CHR"
    assert arc.get_event_gedcom_tag("Burial") == "BURI"
    assert arc.get_event_gedcom_tag("Marriage") == "MARR"


def test_get_event_gedcom_tag_unknown_falls_back_to_even():
    assert arc.get_event_gedcom_tag("Some Future Fact Type") == "EVEN"


def test_is_family_event_true_only_for_family_bucket():
    assert arc.is_family_event("Marriage") is True
    assert arc.is_family_event("Baptism") is False
    assert arc.is_family_event("Scrip") is False


def test_get_by_semantic_and_get_all_by_semantic():
    rec = {"participants": [
        make_participant("primary"), make_participant("father"), make_participant("mother"),
    ]}
    assert arc.get_by_semantic(rec, "primary") is rec["participants"][0]
    assert arc.get_by_semantic(rec, "spouse") is None
    assert arc.get_all_by_semantic(rec, ("father", "mother")) == rec["participants"][1:]


def test_assign_spouses_by_sex():
    a = make_participant(sex="F")
    b = make_participant(sex="M")
    husb, wife = arc.assign_spouses_by_sex(a, b)
    assert husb is b and wife is a


def test_assign_spouses_by_sex_single_parent_defaults_by_own_sex():
    mother = make_participant(sex="F")
    husb, wife = arc.assign_spouses_by_sex(mother, None)
    assert husb is None and wife is mother


def test_resolve_family_links_baptism_shape_no_spouse_or_children():
    """Primary is purely a child in this record: their parents keep the unsuffixed FAM id,
    exactly as before child/spouse/in-law roles existed."""
    rec = {"participants": [make_participant("primary"), make_participant("father")]}
    links = arc.resolve_family_links(rec)
    assert links["primary_forms_own_family"] is False
    assert links["primary_parents_suffix"] == ""


def test_resolve_family_links_marriage_shape_with_spouse():
    rec = {"participants": [make_participant("primary"), make_participant("spouse")]}
    links = arc.resolve_family_links(rec)
    assert links["primary_forms_own_family"] is True
    assert links["main_suffix"] == ""
    assert links["primary_parents_suffix"] == "G"
    assert links["spouse_parents_suffix"] == "B"


def test_build_individual_primary_with_no_parents_still_gets_famc():
    """Regression: build_family always creates a FAM for a primary who is purely a child
    in this record, even with neither parent present (matching this record type's GEDCOM
    output from before family/child/in-law roles existed - see resolve_family_links).
    build_individual's own FAMC line has to point at that same FAM unconditionally too, not
    only when has_parents is true - caught by diffing against pre-refactor output on a
    burial with no parents recorded, where this FAMC line went missing entirely."""
    rec = {"event_type": "Burial", "page": "12", "record_id": "S-2", "participants": [
        make_participant("primary", given="Baptiste", surname="Ledoux"),
    ]}
    primary = rec["participants"][0]
    lines, _, _, _ = arc.build_individual("I1", rec, primary, "12", "M0000000001", "27 JUL 2026", False, "RM")
    joined = "\n".join(lines)
    assert "1 FAMC @F" in joined
    fams = arc.build_family(rec, "12", "M0000000001", "RM")
    assert len(fams) == 1
    famc_id = joined.split("1 FAMC @F")[1].split("@")[0]
    assert famc_id in fams[0]


def test_build_individual_fsftid_gets_companion_fs_tree_weblink():
    """Regression: only the record/citation-level FamilySearch ark URL was ever emitted -
    the person's own FS Tree profile page never had a link of its own, so it couldn't
    compete with the Ancestry link already present. _FSFTID must now be accompanied by a
    weblink to https://www.familysearch.org/tree/person/details/{fsftid}, RM/FTM-flavored
    the same way every other weblink already is (weblink_lines)."""
    rec = {"event_type": "Burial", "page": "12", "record_id": "S-2", "participants": [
        make_participant("primary", given="Baptiste", surname="Ledoux"),
    ]}
    primary = dict(rec["participants"][0], type_specific_fields={"fsftid": "LZXY-ABC"})
    rec["participants"][0] = primary

    rm_lines, _, _, _ = arc.build_individual("I1", rec, primary, "12", "M0000000001", "27 JUL 2026", False, "RM")
    joined_rm = "\n".join(rm_lines)
    assert "1 _FSFTID LZXY-ABC" in joined_rm
    assert "1 _WEBTAG" in joined_rm
    assert "2 URL https://www.familysearch.org/tree/person/details/LZXY-ABC" in joined_rm

    ftm_lines, _, _, _ = arc.build_individual("I1", rec, primary, "12", "M0000000001", "27 JUL 2026", False, "FTM")
    joined_ftm = "\n".join(ftm_lines)
    assert "1 _LINK https://www.familysearch.org/tree/person/details/LZXY-ABC" in joined_ftm


def test_build_family_baptism_shape_single_famc_no_suffix():
    rec = {"event_type": "Baptism", "page": "1", "record_id": "B-1", "participants": [
        make_participant("primary", given="Baptiste", surname="Ledoux"),
        make_participant("father", given="Pierre", surname="Ledoux"),
        make_participant("mother", given="Marie", surname="Roy"),
    ]}
    fams = arc.build_family(rec, "1", "M0000000001", "RM")
    assert len(fams) == 1
    assert "1 HUSB" in fams[0] and "1 WIFE" in fams[0] and "1 CHIL" in fams[0]
    assert "@F" in fams[0].splitlines()[0] and not fams[0].splitlines()[0].split("@")[1].endswith(("G", "B"))


def test_build_family_marriage_shape_three_families_with_suffixes():
    rec = {"event_type": "Marriage", "page": "5", "record_id": "M-1", "event_date": "1850-01-01",
           "participants": [
              make_participant("primary", given="Jean", surname="Gagnon"),
              make_participant("spouse", given="Marie", surname="Boucher", sex="F"),
              make_participant("father", given="Pierre", surname="Gagnon"),
              make_participant("mother", given="Anne", surname="Cyr", sex="F"),
              make_participant("father_in_law", given="Louis", surname="Boucher"),
              make_participant("mother_in_law", given="Rose", surname="Dubois", sex="F"),
           ]}
    fams = arc.build_family(rec, "5", "M0000000001", "RM")
    assert len(fams) == 3
    main, g_fam, b_fam = fams
    assert "1 MARR" in main
    assert g_fam.splitlines()[0].split("@")[1].endswith("G")
    assert b_fam.splitlines()[0].split("@")[1].endswith("B")


def test_build_family_burial_with_surviving_spouse_forms_fams_without_marr_event():
    """A burial naming the deceased's surviving spouse is real marriage evidence and should
    link as a real family - previously dropped entirely (role '4' outside a marriage record
    had no FAMC/FAMS handling at all). Burial is a person-level fact, so no MARR event is
    attached to this FAM - that event already lives on the deceased's own BURI record."""
    rec = {"event_type": "Burial", "page": "9", "record_id": "S-1", "participants": [
        make_participant("primary", given="Baptiste", surname="Ledoux"),
        make_participant("spouse", given="Marie", surname="Roy", sex="F"),
    ]}
    fams = arc.build_family(rec, "9", "M0000000001", "RM")
    assert len(fams) == 1
    assert "1 HUSB" in fams[0] and "1 WIFE" in fams[0]
    assert "MARR" not in fams[0]


def test_build_family_scrip_shape_claimant_spouse_and_children_share_one_family():
    rec = {"event_type": "Scrip", "page": "2", "record_id": "SC-1", "participants": [
        make_participant("primary", given="Baptiste", surname="Ledoux"),
        make_participant("spouse", given="Marie", surname="Roy", sex="F"),
        make_participant("child", given="Louis", surname="Ledoux"),
        make_participant("child", given="Rose", surname="Ledoux", sex="F"),
    ]}
    fams = arc.build_family(rec, "2", "M0000000001", "RM")
    assert len(fams) == 1
    assert fams[0].count("1 CHIL") == 2


def test_build_individual_famc_and_fams_tags_use_semantic_not_digits():
    rec = {"event_type": "Marriage", "page": "5", "record_id": "M-1", "event_date": "1850-01-01",
           "participants": [
              make_participant("primary", given="Jean", surname="Gagnon"),
              make_participant("spouse", given="Marie", surname="Boucher", sex="F"),
              make_participant("father", given="Pierre", surname="Gagnon"),
           ]}
    primary = rec["participants"][0]
    lines, _, _, _ = arc.build_individual("I1", rec, primary, "5", "M0000000001", "26 JUL 2026", False, "RM")
    joined = "\n".join(lines)
    assert "1 FAMS @F" in joined
    assert "1 FAMC @F" in joined and joined.count("@F") >= 2


def test_build_custom_fact_lines_renders_even_type_and_citation():
    rec = {"page": "1", "record_id": "B-1"}
    part = make_participant("primary")
    lines = arc.build_custom_fact_lines("Race", "Metis", rec, part, "1", "M0000000001", "RM")
    assert lines[0] == "1 EVEN Metis"
    assert lines[1] == "2 TYPE Race"
    assert "2 SOUR" in "\n".join(lines)


def test_build_custom_fact_lines_empty_value_returns_nothing():
    rec = {"page": "1", "record_id": "B-1"}
    part = make_participant("primary")
    assert arc.build_custom_fact_lines("Race", "", rec, part, "1", "M0000000001", "RM") == []


def test_build_individual_race_uses_generic_custom_fact_not_bare_race_tag():
    rec = {"event_type": "Baptism", "page": "1", "record_id": "B-1", "participants": [
        make_participant("primary", given="Baptiste", surname="Ledoux"),
    ]}
    primary = rec["participants"][0]
    primary["race"] = "Metis"
    lines, _, _, _ = arc.build_individual("I1", rec, primary, "1", "M0000000001", "26 JUL 2026", False, "RM")
    joined = "\n".join(lines)
    assert "_RACE" not in joined
    assert "1 EVEN Metis" in joined and "2 TYPE Race" in joined


def test_build_individual_scrip_event_gets_type_line_and_value_from_extra_fields():
    """Scrip's own event_type resolves to gedcom_tag 'EVEN' - it's built as a dedicated
    "Scrip" custom fact (FactTypes.json code 10004), needing a '2 TYPE Scrip' line for
    RootsMagic to recognize it, with its own Date/Place/Desc all filled in."""
    original = arc.GENERAL_CONFIG.get('omit_source_id_prefix')
    try:
        arc.GENERAL_CONFIG['omit_source_id_prefix'] = True
        rec = {"event_type": "Scrip", "page": "1", "record_id": "SC-1", "event_place": "Winnipeg",
               "type_specific_fields": {"scrip_number": "1234", "scrip_amount": "$160"},
               "participants": [make_participant("primary", given="Baptiste", surname="Ledoux")]}
        primary = rec["participants"][0]
        lines, _, _, _ = arc.build_individual("I1", rec, primary, "1", "M0000000001", "26 JUL 2026", False, "RM")
        joined = "\n".join(lines)
        assert "2 TYPE Scrip" in joined
        assert "1 EVEN Scrip #: 1234 ($160)" in joined
        assert "2 PLAC Winnipeg" in joined
    finally:
        arc.GENERAL_CONFIG['omit_source_id_prefix'] = original


def test_build_individual_scrip_fact_gets_document_year_as_date_and_media_attached():
    original = arc.GENERAL_CONFIG.get('omit_source_id_prefix')
    try:
        arc.GENERAL_CONFIG['omit_source_id_prefix'] = True
        rec = {"event_type": "Scrip", "page": "1", "record_id": "SC-1", "year": "1901",
               "type_specific_fields": {"scrip_number": "1234"},
               "participants": [make_participant("primary", given="Baptiste", surname="Ledoux")]}
        primary = rec["participants"][0]
        lines, _, _, _ = arc.build_individual("I1", rec, primary, "1", "M0000000001", "26 JUL 2026", False, "RM")
        joined = "\n".join(lines)
        assert "2 DATE 1901" in joined
        assert "3 OBJE @M0000000001@" in joined
    finally:
        arc.GENERAL_CONFIG['omit_source_id_prefix'] = original


def test_build_individual_scrip_race_fact_gets_no_document_year_date():
    """Per the user: everything but Race should carry the document year as its DATE -
    Race describes an ongoing characteristic, not something dated to one document."""
    original = arc.GENERAL_CONFIG.get('omit_source_id_prefix')
    try:
        arc.GENERAL_CONFIG['omit_source_id_prefix'] = True
        rec = {"event_type": "Scrip", "page": "1", "record_id": "SC-1", "year": "1901",
               "type_specific_fields": {}, "participants": [make_participant("primary")]}
        primary = rec["participants"][0]
        primary["race"] = "Metis"
        lines, _, _, _ = arc.build_individual("I1", rec, primary, "1", "M0000000001", "26 JUL 2026", False, "RM")
        joined = "\n".join(lines)
        race_block = joined.split("2 TYPE Race")[1].split("2 SOUR")[0]
        assert "2 DATE" not in race_block
    finally:
        arc.GENERAL_CONFIG['omit_source_id_prefix'] = original


def test_build_individual_scrip_witness_associations_exclude_nuclear_family():
    """Only true witnesses (no family-position role_semantic) become witness
    Associations - spouse/parent/child participants must not appear here even though the
    old filter (just excluding 'primary') used to sweep them in too. Uses FTM output,
    where witnesses render as plain names in a NOTE line - RM's own _SHAR form only ever
    carries a UID + role text, not a name, so it can't distinguish this directly."""
    original = arc.GENERAL_CONFIG.get('omit_source_id_prefix')
    try:
        arc.GENERAL_CONFIG['omit_source_id_prefix'] = True
        rec = {"event_type": "Scrip", "page": "1", "record_id": "SC-1",
               "type_specific_fields": {"scrip_number": "1"},
               "participants": [
                   make_participant("primary", given="Baptiste", surname="Ledoux"),
                   make_participant("spouse", given="Marie", surname="Ledoux"),
                   make_participant("child", given="Jean", surname="Ledoux"),
                   make_participant(None, role_name="Witness", given="Louis", surname="Riel"),
               ]}
        primary = rec["participants"][0]
        lines, _, _, _ = arc.build_individual("I1", rec, primary, "1", "M0000000001", "26 JUL 2026", False, "FTM")
        joined = "\n".join(lines)
        witness_note = next(line for line in lines if line.startswith("2 NOTE Witnesses:"))
        assert "Louis" in witness_note and "Riel" in witness_note
        assert "Marie" not in witness_note
        assert "Jean" not in witness_note
    finally:
        arc.GENERAL_CONFIG['omit_source_id_prefix'] = original


def test_build_individual_baptism_event_gets_no_type_line():
    """A standard GEDCOM-tagged event (Baptism -> BAPM) must not gain a '2 TYPE' line or
    any value text on its '1 BAPM' line - that's exclusively for the 'EVEN' fallback case."""
    rec = {"event_type": "Baptism", "page": "1", "record_id": "B-1", "participants": [
        make_participant("primary", given="Baptiste", surname="Ledoux"),
    ]}
    primary = rec["participants"][0]
    lines, _, _, _ = arc.build_individual("I1", rec, primary, "1", "M0000000001", "26 JUL 2026", False, "RM")
    joined = "\n".join(lines)
    assert "1 BAPM" in joined
    assert "2 TYPE Baptism" not in joined


def test_build_individual_alternate_name_renders_as_proposed_name_fact_with_event_note():
    """A margin note offering a different spelling (a later annotator's aid, not the
    priest's own entry - see Parish.pmt's MARGIN ANNOTATIONS rule) becomes its own
    'proposed' NAME fact, same convention as census's crowdsourced alternate readings,
    plus a NOTE on the primary's own event so it's visible right where the event is."""
    rec = {"event_type": "Baptism", "page": "1", "record_id": "B-1", "participants": [
        make_participant("primary", given="Baptiste", surname="Ledoux"),
    ]}
    primary = rec["participants"][0]
    primary["alternate_names"] = [{"value": "Baptiste Ladoux"}]
    lines, _, _, _ = arc.build_individual("I1", rec, primary, "1", "M0000000001", "26 JUL 2026", False, "RM")
    joined = "\n".join(lines)
    assert "1 NAME Baptiste /Ladoux/" in joined
    assert "2 _PROOF proposed" in joined
    assert "2 NOTE Margin note suggests alternate spelling: Baptiste Ladoux" in joined


# ==========================================
# Scrip custom RootsMagic source templates (Metis Scrip.rmst, Ids 20001-20005)
# ==========================================
def test_select_scrip_template_id_manitoba_from_commission_reference():
    assert arc.select_scrip_template_id("Affidavit under Manitoba Act, 33 Vic. Cap 3", "Witness Affidavit") == 20001


def test_select_scrip_template_id_north_west_from_commission_reference():
    ref = "Form A - North-West Half-Breed Claims Commission under Order in Council of 30th March, 1885"
    assert arc.select_scrip_template_id(ref, "Claimant's Own Affidavit") == 20002


def test_select_scrip_template_id_treaty_8_from_commission_reference():
    assert arc.select_scrip_template_id("Form C - Treaty No. 8", "Witness Affidavit") == 20003


def test_select_scrip_template_id_certificate_from_document_type_regardless_of_commission():
    """document_type wins over commission_reference - a Certificate is a structurally
    different document from an affidavit no matter which commission issued it."""
    assert arc.select_scrip_template_id("Manitoba Act, 33 Vic. Cap 3", "Scrip Certificate") == 20004


def test_select_scrip_template_id_prefers_series_code_over_commission_reference_text():
    """series_code is LAC's own catalog classification (Commissioner-fetched) - more
    authoritative than the printed commission_reference text, so it wins when present,
    even when commission_reference text alone would have matched a different template."""
    assert arc.select_scrip_template_id("some unrelated header text", "Witness Affidavit",
                                        series_code="RG15-D-II-8-c") == 20002


def test_select_scrip_template_id_returns_none_when_unrecognized():
    """No guessing - an unresolved record must fall back to the plain freeform source,
    not get mis-templated."""
    assert arc.select_scrip_template_id("", "") is None
    assert arc.select_scrip_template_id("some unrelated header text", "Register Entry") is None


def test_scrip_template_field_value_microfilm_from_commissioner_reel_numbers():
    rec = {"type_specific_fields": {"reel_numbers": "C-14929, C-14930"}}
    part = {}
    assert arc._scrip_template_field_value("Microfilm", rec, part, "1320") == "C-14929, C-14930"


def test_scrip_template_field_value_issue_date_prefers_dedicated_field_over_application_date():
    rec = {"type_specific_fields": {"issue_date": "5 May 1886", "application_date": "1 Jan 1886"}}
    assert arc._scrip_template_field_value("IssueDate", rec, {}, "1320") == "5 May 1886"


def test_scrip_template_field_value_issue_date_falls_back_to_application_date():
    rec = {"type_specific_fields": {"application_date": "1 Jan 1886"}}
    assert arc._scrip_template_field_value("IssueDate", rec, {}, "1320") == "1 Jan 1886"


def test_scrip_template_field_value_treaty_8_delivery_fields():
    rec = {"type_specific_fields": {"delivery_date": "3 Aug 1900", "delivery_place": "Fort Vermilion"}}
    assert arc._scrip_template_field_value("DeliveryDate", rec, {}, "1") == "3 Aug 1900"
    assert arc._scrip_template_field_value("DeliveryPlace", rec, {}, "1") == "Fort Vermilion"


def test_scrip_template_field_value_land_grant_fields_are_a_known_gap():
    """No claimant affidavit states these - they belong to a later, separately-cataloged
    Dominion Lands Office patent record Commissioner doesn't fetch yet."""
    rec = {"type_specific_fields": {}}
    for field in ("OriginalClaimant", "LandDescription", "Liber", "Folio"):
        assert arc._scrip_template_field_value(field, rec, {}, "1") == ""


def test_get_scrip_citation_fields_skips_empty_values():
    rec = {"type_specific_fields": {"affidavit_number": "5473"}, "lac_pid": ""}
    part = make_participant("primary", given="Roger", surname="Letendre")
    lines = arc.get_scrip_citation_fields(20001, rec, part, "1320")
    joined = "\n".join(lines)
    assert "4 NAME AffidavitNumber" in joined and "4 VALUE 5473" in joined
    assert "4 NAME ClaimantName" in joined and "4 VALUE Roger Letendre" in joined
    # Microfilm/Parish/URL were never set on this record - must not appear at all.
    assert "Microfilm" not in joined
    assert "URL" not in joined


def test_build_general_citation_scrip_cites_the_matching_template_source_with_field_block():
    original = arc.GENERAL_CONFIG.get('omit_source_id_prefix')
    try:
        arc.GENERAL_CONFIG['omit_source_id_prefix'] = True
        rec = {"page": "1", "record_id": "SC-1", "record_number": "5473", "lac_pid": "1506170",
               "type_specific_fields": {"commission_reference": "Affidavit under Manitoba Act, 33 Vic. Cap 3",
                                        "affidavit_number": "5473"}}
        part = make_participant("primary", given="William", surname="Anderson")
        blocks = arc.build_general_citation(rec, part, "CENS", "1324", "M0000000001", target_software="RM")
        joined = blocks[0]
        assert "2 SOUR @S20001@" in joined
        assert "4 NAME AffidavitNumber" in joined and "4 VALUE 5473" in joined
        assert "LAC Digital Record" in joined
        assert "https://recherche-collection-search.bac-lac.gc.ca/eng/Home/Record?app=fonandcol&IdNumber=1506170" in joined
    finally:
        arc.GENERAL_CONFIG['omit_source_id_prefix'] = original


def test_build_general_citation_scrip_forces_proven_even_when_date_is_estimated():
    """Every Scrip fact is read straight off a sworn primary source - get_proof_status'
    generic BEF/ABT/EST downgrade (still correct for Parish/Census) must not apply here."""
    original = arc.GENERAL_CONFIG.get('omit_source_id_prefix')
    try:
        arc.GENERAL_CONFIG['omit_source_id_prefix'] = True
        rec = {"page": "1", "record_id": "SC-1", "type_specific_fields": {}}
        part = make_participant("primary")
        blocks = arc.build_general_citation(rec, part, "BIRT", "1324", "M0000000001",
                                            proof_status="proposed", target_software="RM")
        assert "2 _PROOF proven" in blocks[0]
    finally:
        arc.GENERAL_CONFIG['omit_source_id_prefix'] = original


def test_build_general_citation_scrip_falls_back_to_freeform_when_template_unresolved():
    """An unrecognized commission_reference must not get mis-templated - it cites the
    existing per-volume freeform source instead, same @S{vol}@ id as before this change."""
    original = arc.GENERAL_CONFIG.get('omit_source_id_prefix')
    try:
        arc.GENERAL_CONFIG['omit_source_id_prefix'] = True
        rec = {"page": "1", "record_id": "SC-1", "type_specific_fields": {}}
        part = make_participant("primary")
        blocks = arc.build_general_citation(rec, part, "CENS", "1324", "M0000000001", target_software="RM")
        assert "2 SOUR @S1324@" in blocks[0]
    finally:
        arc.GENERAL_CONFIG['omit_source_id_prefix'] = original


def test_get_volume_sources_omits_church_template_for_scrip():
    original = arc.GENERAL_CONFIG.get('omit_source_id_prefix')
    try:
        arc.GENERAL_CONFIG['omit_source_id_prefix'] = True
        arc.GENERAL_CONFIG['parish_name'] = "Library and Archives Canada"
        arc.GENERAL_CONFIG['register_name'] = "Scrip Records"
        arc.GENERAL_CONFIG['volume_title'] = "Scrip Records"
        arc.GENERAL_CONFIG['parish_location'] = "Ottawa, ON"
        lines = arc.get_volume_sources({"1324"}, "RM")
        joined = "\n".join(lines)
        assert "TID 355" not in joined
        assert "Church_Author" not in joined
    finally:
        arc.GENERAL_CONFIG['omit_source_id_prefix'] = original


def test_get_volume_sources_keeps_church_template_for_parish():
    original = arc.GENERAL_CONFIG.get('omit_source_id_prefix')
    try:
        arc.GENERAL_CONFIG['omit_source_id_prefix'] = False
        arc.GENERAL_CONFIG['parish_name'] = "St. Boniface"
        arc.GENERAL_CONFIG['register_name'] = "Baptisms"
        arc.GENERAL_CONFIG['volume_title'] = "Baptisms"
        arc.GENERAL_CONFIG['parish_location'] = "Manitoba"
        lines = arc.get_volume_sources({"1"}, "RM")
        joined = "\n".join(lines)
        assert "TID 355" in joined
    finally:
        arc.GENERAL_CONFIG['omit_source_id_prefix'] = original


def test_build_individual_researcher_citation_has_both_name_and_titl():
    """RootsMagic needs both '2 NAME' and '2 _TITL' under the shared @S1@ researcher
    citation to merge it across multiple people's citations in its own UI - confirmed
    live by the user; _TITL alone displays but doesn't merge."""
    rec = {"event_type": "Baptism", "page": "1", "record_id": "B-1",
          "participants": [make_participant("primary", given="Baptiste", surname="Ledoux")]}
    primary = rec["participants"][0]
    lines, _, _, _ = arc.build_individual("I1", rec, primary, "1", "M0000000001", "26 JUL 2026", False, "RM")
    joined = "\n".join(lines)
    assert "2 NAME Researcher:" in joined
    assert "2 _TITL Researcher:" in joined
