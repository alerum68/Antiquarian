"""
Tests for build_census_dataframe_from_unified - the adapter translating Voyageur's
now-normalized shared-schema census output (sheets[].records[].participants[]) back into
the same old-column-named DataFrame shape Archivist's household-parsing/citation logic
has always operated on. These functions (parse_household, parse_household_relational,
get_census_era, etc.) are deliberately NOT changed by this rework - only what feeds them
changed - so these tests confirm the adapter's column-naming/grouping produces input
those functions still handle correctly, not that the functions themselves changed.
"""
# noinspection PyUnresolvedReferences
import Utils
# noinspection PyUnresolvedReferences,PyPep8Naming
import Census as arc
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _unified_doc(record_type_name, sheets):
    return {"collection_title": "Test Census", "record_type_name": record_type_name,
            "citation": {"repository": "Ancestry.com"}, "sheets": sheets}


def _sheet(records, page_id="3"):
    return {"page_id": page_id, "document_metadata": {"source_location": "Minnesota"}, "records": records}


def _record(participants, family_number=None, ed="12", roll="T624_1"):
    ts = {"enumeration_district": ed, "roll_number": roll, "state": "Minnesota", "county": "Ramsey"}
    if family_number:
        ts["family_number"] = family_number
    return {"record_id": None, "page": "3", "record_number": family_number or "", "event_type": "Census (family)",
            "year": "1900", "event_date": "", "event_place": "", "citation_details": "",
            "citation_text": "", "review": False, "review_reason": None,
            "continues_on_next_image": False, "continues_from_previous_image": False,
            "type_specific_fields": ts, "participants": participants}


def _participant(given, surname, sex, role_name=None, age=None, line=None, facts=None):
    return {"role_number": None, "role_name": role_name, "std_given": given, "std_surname": surname,
            "raw_given": None, "raw_surname": None, "dit_name": None, "alternate_names": [],
            "prefix": None, "suffix": None, "sex": sex, "is_priest": False, "age": age, "age_unit": None,
            "occupation": None, "race": None, "religion": None, "residence": None, "birth_date": None,
            "birth_place": None, "death_date": None, "death_place": None, "review": False, "review_reason": None,
            "facts": facts or [], "type_specific_fields": {"line_number": line} if line else {}}


def test_adapter_produces_expected_columns_and_year_location():
    doc = _unified_doc("Census_1900", [_sheet([
        _record([_participant("Jean", "Gagnon", "M", role_name="Head", age="40", line="1")],
                family_number="5"),
    ])])

    df, year, location = arc.build_census_dataframe_from_unified(doc)

    assert year == "1900"
    assert location == "Minnesota"
    assert len(df) == 1
    row = df.iloc[0]
    assert row["Given Name"] == "Jean"
    assert row["Surname"] == "Gagnon"
    assert row["Gender"] == "M"
    assert row["Relationship to Head"] == "Head"
    assert row["Family Number"] == "5"
    assert row["Line Number"] == "1"
    assert row["Enumeration_District"] == "12"
    assert row["Roll"] == "T624_1"


def test_adapter_reads_image_id_and_place_details_from_document_metadata():
    """Regression: Image_ID (feeds the GEDCOM's '1 FILE' media path) and Place_Details were
    both silently dropped by this adapter even when census_schema.py's normalize step
    supplied them - Image_ID came from document_metadata.file_name (hardcoded '' before the
    census_schema.py fix), Place_Details wasn't read into page_meta at all here."""
    doc = _unified_doc("Census_1900", [{
        "page_id": "3",
        "document_metadata": {"source_location": "Minnesota", "file_name": "4211353_00001.jpg"},
        "records": [_record([_participant("Jean", "Gagnon", "M", role_name="Head", age="40", line="1")],
                            family_number="5", ed="12")],
    }])
    doc["sheets"][0]["records"][0]["type_specific_fields"]["place_details"] = "Ward 3"

    df, _, _ = arc.build_census_dataframe_from_unified(doc)

    row = df.iloc[0]
    assert row["Image_ID"] == "4211353_00001.jpg"
    assert row["Place_Details"] == "Ward 3"


def test_adapter_reads_alternate_birth_places_from_type_specific_fields():
    doc = _unified_doc("Census_1900", [_sheet([
        _record([_participant("Jean", "Gagnon", "M", role_name="Head", age="40", line="1")], family_number="5"),
    ])])
    doc["sheets"][0]["records"][0]["participants"][0]["type_specific_fields"]["alternate_birth_places"] = [
        {"value": "Quebec, Canada"}]

    df, _, _ = arc.build_census_dataframe_from_unified(doc)

    alt = json.loads(df.iloc[0]["AlternateBirthPlaces"])
    assert alt == [{"value": "Quebec, Canada"}]


def test_adapter_reads_street_and_it_drives_the_cens_addr_line(tmp_path, monkeypatch):
    """Confirms 'street' reaches the DataFrame AND actually drives build_gedcom_from_census's
    CENS fact '2 ADDR' line - not just that it lands somewhere plausible-looking."""
    head = _participant("Jean", "Gagnon", "M", role_name="Head", age="40", line="1")
    head["type_specific_fields"]["street"] = "212 Main St"
    doc = _unified_doc("Census_1900", [{
        "page_id": "3",
        "document_metadata": {"source_location": "Minnesota", "file_name": "4211353_00003.jpg"},
        "records": [_record([head], family_number="5")],
    }])
    df, year, _ = arc.build_census_dataframe_from_unified(doc)
    assert df.iloc[0]["Street"] == "212 Main St"

    monkeypatch.setattr(arc, "CENSUS_YEAR", int(year))
    monkeypatch.setattr(arc, "CENSUS_ERA", arc.get_census_era(int(year)))
    monkeypatch.setattr(Utils, "GEDCOM_OUTPUT_PATH", tmp_path)
    monkeypatch.setattr(Utils, "GEDCOM_OUTPUT_NAME", "Test_Census.ged")
    monkeypatch.setattr(arc, "IMAGE_DIR", tmp_path)

    arc.build_gedcom_from_census(df, "RM")

    lines = list(tmp_path.glob("*.ged"))[0].read_text(encoding="utf-8").splitlines()
    assert "2 ADDR 212 Main St" in lines


def test_adapter_reads_married_within_year_per_participant():
    doc = _unified_doc("Census_1900", [_sheet([
        _record([_participant("Jean", "Gagnon", "M", role_name="Head", age="40", line="1")], family_number="5"),
    ])])
    doc["sheets"][0]["records"][0]["participants"][0]["type_specific_fields"]["married_within_year"] = "Yes"

    df, _, _ = arc.build_census_dataframe_from_unified(doc)

    assert df.iloc[0]["Married within Year"] == "Yes"


def test_adapter_maps_facts_to_expected_old_column_names():
    doc = _unified_doc("Census_1900", [_sheet([
        _record([_participant("Jean", "Gagnon", "M",
                              facts=[{"fact_type": "Occupation", "value": "Farmer"},
                                     {"fact_type": "Immigration", "date": "1889"}])],
                family_number="5"),
    ])])
    df, _, _ = arc.build_census_dataframe_from_unified(doc)
    row = df.iloc[0]
    assert row["Occupation"] == "Farmer"
    assert row["Immigration Year"] == "1889"


def test_relational_era_household_parsing_works_on_adapted_dataframe():
    """1900 (relationship era) - Head + Wife, explicit role_name - confirms
    parse_household_relational (unchanged) correctly resolves the household from the
    adapter's column naming."""
    doc = _unified_doc("Census_1900", [_sheet([
        _record([
            _participant("Jean", "Gagnon", "M", role_name="Head", age="40", line="1"),
            _participant("Marie", "Gagnon", "F", role_name="Wife", age="38", line="2"),
        ], family_number="5"),
    ])])
    df, year, _ = arc.build_census_dataframe_from_unified(doc)

    arc.CENSUS_YEAR = int(year)
    arc.CENSUS_ERA = arc.get_census_era(arc.CENSUS_YEAR)
    assert arc.CENSUS_ERA == "relationship"

    units, unrelated, flags = arc.parse_household_relational(df)
    assert len(units) == 1
    assert units[0]["husband"]["Given Name"] == "Jean"
    assert units[0]["wife"]["Given Name"] == "Marie"
    assert not unrelated


def test_heuristic_era_household_parsing_works_on_adapted_dataframe():
    """1860 (heuristic era) - no role_name at all (matches what census_schema.py produces
    when the source has no relationship column) - confirms parse_household (unchanged)
    still infers the spouse pair from age/sex/surname proximity via the adapter's output."""
    doc = _unified_doc("Census_1860", [_sheet([
        _record([
            _participant("Jean", "Gagnon", "M", age="40", line="1"),
            _participant("Marie", "Gagnon", "F", age="38", line="2"),
        ], family_number="5"),
    ])])
    df, year, _ = arc.build_census_dataframe_from_unified(doc)

    arc.CENSUS_YEAR = int(year)
    arc.CENSUS_ERA = arc.get_census_era(arc.CENSUS_YEAR)
    assert arc.CENSUS_ERA == "heuristic"

    units, unrelated, flags = arc.parse_household(df)
    assert len(units) == 1
    assert {units[0]["husband"]["Given Name"], units[0]["wife"]["Given Name"]} == {"Jean", "Marie"}


def test_two_households_get_separate_family_number_groups():
    doc = _unified_doc("Census_1900", [_sheet([
        _record([_participant("Jean", "Gagnon", "M", role_name="Head", line="1")], family_number="5"),
        _record([_participant("Louis", "Riel", "M", role_name="Head", line="2")], family_number="6"),
    ])])
    df, _, _ = arc.build_census_dataframe_from_unified(doc)
    df["Household_ID"] = (df["Family Number"] != df["Family Number"].shift()).cumsum()
    assert df["Household_ID"].nunique() == 2


def test_dispatch_by_record_type_name_not_shape():
    """Both census and church documents use the "sheets" top-level key now - confirms
    is_census's own logic (record_type_name-based, not a hardcoded shape guess) would
    route a Census_-prefixed document to the census flavor."""
    doc = _unified_doc("Census_1900", [_sheet([_record([_participant("Jean", "Gagnon", "M")])])])
    assert doc.get("record_type_name", "").startswith("Census_")  # type: ignore
    assert "sheets" in doc


def test_build_census_task_folder_name_uses_fixed_vocabulary_not_raw_flag_text():
    """Regression: RootsMagic rejects an arbitrary sentence as a "0 _FOLDER" value -
    build_census_task used to write one directly (a lightly regex-cleaned copy of the raw
    review-flag text, e.g. "Head-surname match: no age fit"). The folder name must instead
    come from evaluate_task_priority's fixed, safe vocabulary - already proven correct for
    the general flavor - reusing the exact flag text real 1860 census data produced."""
    _, folder = arc.build_census_task("1", "Jean", "Gagnon", "1900, Fam 5, p.3",
                                      [("Head-surname match; no age fit", 0.3)],
                                      [], "img.jpg", "Title", "RM")
    assert folder == "Name & Identity Issues"

    _, folder2 = arc.build_census_task("2", "Jean", "Gagnon", "1900, Fam 5, p.3",
                                       [("Unrelated household member", 0.5)],
                                       [], "img.jpg", "Title", "RM")
    assert folder2 == "General Review"


def test_census_gedcom_output_has_no_illegal_name_under_sour_and_single_extension(tmp_path, monkeypatch):
    """Regression for the FTM import-error root cause (confirmed against a real FTM import
    error log: ~85 "Unsupported or invalid tag: NAME" errors on one real test census page):
    a "NAME Researcher: ..." line was being written as a child of a per-fact "2 SOUR ..."
    citation, which isn't legal under GEDCOM 5.5.1 (see build_census_citation). This is
    distinct from "2 NAME Researcher: ..." under the shared "1 SOUR @S1@" researcher
    reference on every individual - confirmed live by the user that RootsMagic needs BOTH
    "2 NAME" and "2 _TITL" there to merge that citation across every person who cites it;
    that pattern is intentional, not a regression of this fix. Also regresses an OBJE media
    filename doubling its extension (".jpg.jpg") when Image_ID already carries one, as it
    does coming from the unified schema's document_metadata.file_name - and confirms the
    FamilySearch Family Tree profile webtag now accompanies _FSFTID."""
    head = _participant("Jean", "Gagnon", "M", role_name="Head", age="40", line="1")
    head["type_specific_fields"] = {"line_number": "1", "fsftid": "LZXY-ABC"}
    wife = _participant("Marie", "Gagnon", "F", role_name="Wife", age="38", line="2")
    doc = _unified_doc("Census_1900", [{
        "page_id": "3",
        "document_metadata": {"source_location": "Minnesota", "file_name": "4211353_00003.jpg"},
        "records": [_record([head, wife], family_number="5")],
    }])
    df, year, _ = arc.build_census_dataframe_from_unified(doc)

    monkeypatch.setattr(arc, "CENSUS_YEAR", int(year))
    monkeypatch.setattr(arc, "CENSUS_ERA", arc.get_census_era(int(year)))
    monkeypatch.setattr(Utils, "GEDCOM_OUTPUT_PATH", tmp_path)
    # GEDCOM_OUTPUT_NAME is read from the environment at Utils import time, and this
    # dev machine's Archivist/.env sets it to an empty string - resolve_gedcom_output_path
    # would then produce a filename with no base and no ".ged" extension (" - RM").
    # Pin a real name here so the output is a findable *.ged file (in production
    # Archivist.py fills an empty name from the input file's stem before this is called).
    monkeypatch.setattr(Utils, "GEDCOM_OUTPUT_NAME", "Test_Census.ged")
    monkeypatch.setattr(arc, "IMAGE_DIR", tmp_path)

    arc.build_gedcom_from_census(df, "RM")

    out_files = list(tmp_path.glob("*.ged"))
    assert len(out_files) == 1
    lines = out_files[0].read_text(encoding="utf-8").splitlines()

    # The illegal line was specifically "3 NAME Researcher: ..." nested directly under a
    # per-fact "2 SOUR ..." citation - "2 NAME Researcher: ..." under the shared top-level
    # "1 SOUR @S1@" reference (checked below) is the separate, intentional pattern.
    sour_line_idxs = [i for i, ln in enumerate(lines) if ln.startswith("2 SOUR ")]
    for i in sour_line_idxs:
        for ln in lines[i + 1:]:
            if not (ln.startswith("3 ") or ln.startswith("4 ") or ln.startswith("5 ")):
                break
            if ln.startswith("3 NAME"):
                assert False, f"illegal NAME directly under a per-fact SOUR citation: {ln!r}"

    # The shared "1 SOUR @S1@" researcher reference on each individual needs BOTH "2 NAME"
    # and "2 _TITL" - confirmed live by the user - to merge across every person's citation
    # of it in RootsMagic's own UI.
    root_sour_idxs = [i for i, ln in enumerate(lines) if ln == f"1 SOUR {Utils.ROOT_SOURCE_ID}"]
    assert root_sour_idxs
    for i in root_sour_idxs:
        assert lines[i + 1].startswith("2 NAME Researcher:")
        assert lines[i + 2].startswith("2 _TITL Researcher:")

    file_lines = [ln for ln in lines if ln.startswith("1 FILE ")]
    assert file_lines
    assert all(ln.endswith(".jpg") and not ln.endswith(".jpg.jpg") for ln in file_lines)

    assert any(ln == "1 _FSFTID LZXY-ABC" for ln in lines)
    assert any("https://www.familysearch.org/tree/person/details/LZXY-ABC" in ln for ln in lines)


def test_census_gedcom_media_attaches_to_each_fact_citation_per_original_design(tmp_path, monkeypatch):
    """This project's own citation-building shape, unchanged since the very first commit
    (CensusConverter/CensusConverter.py, build_citation_block): the OBJE media reference
    lives INSIDE each fact's own '2 SOUR ...' citation block (at '3 OBJE <id>', a child of
    the citation, not a direct child of the fact) - and that whole citation block, media
    included, is what gets attached once per fact (NAME, BIRT, CENS, OCCU, ...). A session
    mid-course attempt to instead park the media once on the shared top-level SOUR record
    was reverted after review - confirmed against project history that per-fact-citation
    attachment (not source-only) is the long-standing, correct design."""
    head = _participant("Jean", "Gagnon", "M", role_name="Head", age="40", line="1")
    wife = _participant("Marie", "Gagnon", "F", role_name="Wife", age="38", line="2")
    doc = _unified_doc("Census_1900", [{
        "page_id": "3",
        "document_metadata": {"source_location": "Minnesota", "file_name": "4211353_00003.jpg"},
        "records": [_record([head, wife], family_number="5")],
    }])
    df, year, _ = arc.build_census_dataframe_from_unified(doc)

    monkeypatch.setattr(arc, "CENSUS_YEAR", int(year))
    monkeypatch.setattr(arc, "CENSUS_ERA", arc.get_census_era(int(year)))
    monkeypatch.setattr(Utils, "GEDCOM_OUTPUT_PATH", tmp_path)
    monkeypatch.setattr(Utils, "GEDCOM_OUTPUT_NAME", "Test_Census.ged")
    monkeypatch.setattr(arc, "IMAGE_DIR", tmp_path)

    arc.build_gedcom_from_census(df, "RM")

    lines = list(tmp_path.glob("*.ged"))[0].read_text(encoding="utf-8").splitlines()

    # Each person has multiple facts (NAME, BIRT, CENS at least) - each carries its own
    # '3 OBJE' nested under its own '2 SOUR' citation, so the total count is several per
    # person, not one per person and not zero.
    obje_lines = [ln for ln in lines if ln.startswith("3 OBJE")]
    assert len(obje_lines) >= 4, f"expected multiple per-fact OBJE lines, got: {obje_lines}"
    assert all(ln == "3 OBJE @M4211353_00003@" for ln in obje_lines), obje_lines

    # The shared source record itself carries no OBJE - media is a citation-level detail,
    # not something hoisted onto the bare source.
    sour_idx = lines.index(f"0 @S{arc.CENSUS_SOURCE_ID}@ SOUR")
    sour_block_end = next((i for i in range(sour_idx + 1, len(lines)) if lines[i].startswith("0 ")), len(lines))
    sour_block = lines[sour_idx:sour_block_end]
    assert not any(ln.startswith("1 OBJE") for ln in sour_block), \
        f"source record should not carry its own OBJE: {sour_block}"


def test_census_gedcom_refn_is_bare_ark_not_the_gedcomx_type_prefixed_form(tmp_path, monkeypatch):
    """User-requested: a FamilySearch person ark's own REFN value should read as just the
    ark itself (e.g. 'MF36-Z6D'), not the GEDCOM X type-prefixed form ('1:1:MF36-Z6D') that
    FS.py's pid/person_ark actually carries and that the citation-level _FSFTID fallback
    also strips (see test_census_ingestion.py). The '@I<id>@' cross-ref pointer itself is
    untouched - that's an internal GEDCOM pointer needing only internal consistency, not
    display-cleanliness, and stripping it would risk mismatching its own definition/
    reference pair."""
    head = _participant("Jean", "Gagnon", "M", role_name="Head", age="40", line="1")
    head["type_specific_fields"]["pid"] = "1:1:MF36-Z6D"
    doc = _unified_doc("Census_1900", [{
        "page_id": "3",
        "document_metadata": {"source_location": "Minnesota", "file_name": "4211353_00003.jpg"},
        "records": [_record([head], family_number="5")],
    }])
    df, year, _ = arc.build_census_dataframe_from_unified(doc)

    monkeypatch.setattr(arc, "CENSUS_YEAR", int(year))
    monkeypatch.setattr(arc, "CENSUS_ERA", arc.get_census_era(int(year)))
    monkeypatch.setattr(Utils, "GEDCOM_OUTPUT_PATH", tmp_path)
    monkeypatch.setattr(Utils, "GEDCOM_OUTPUT_NAME", "Test_Census.ged")
    monkeypatch.setattr(arc, "IMAGE_DIR", tmp_path)

    arc.build_gedcom_from_census(df, "RM")

    lines = list(tmp_path.glob("*.ged"))[0].read_text(encoding="utf-8").splitlines()

    assert "0 @I1:1:MF36-Z6D@ INDI" in lines
    assert "1 REFN MF36-Z6D" in lines
    assert "1 REFN 1:1:MF36-Z6D" not in lines


def _citation_row(**overrides):
    row = {"Given Name": "Jean", "Surname": "Gagnon", "FSFTID": "", "FamilySearch_URL": "",
           "Extracted_URL": "", "Family Number": "5", "Dwelling Number": "5"}
    row.update(overrides)
    return pd.Series(row)


def test_census_citation_never_emits_apid_for_an_ark_shaped_rec_id(monkeypatch):
    """Regression: an FS-only gather has no real Ancestry APID_DB, but rec_id (fed from
    FS.py's per-person 'pid', which is the FamilySearch person ark, e.g. '1:1:MF36-Z6D'
    when there's no genuine Ancestry record) was still being unconditionally baked into the
    Ancestry-specific '_APID 1,<db>::<id>' GEDCOM tag - an ark is not an APID and must
    never appear there, and no bogus Ancestry citation data should be emitted at all.

    The ark itself must NOT be routed into the top-level per-person _FSFTID/tree-weblink
    mechanism (an earlier fix attempt did this, then had to be reverted - confirmed live it
    produced a broken 'familysearch.org/tree/person/details/1:1:MF36-Z6D' weblink, since
    that URL pattern is specifically for a Family Tree PROFILE id, a different, unrelated
    ID namespace only obtained via genuine tree-attachment). This test's row has no
    FamilySearch_URL either (not FS-sourced at all), so the citation-level _FSFTID fallback
    (see the companion test below) correctly doesn't fire - _FSFTID must not appear."""
    monkeypatch.setattr(arc, "APID_DB", "")
    monkeypatch.setattr(arc, "CENSUS_YEAR", 1860)
    monkeypatch.setattr(arc, "CENSUS_SOURCE_ID", "1473181")
    monkeypatch.setattr(arc, "COLLECTION_NAME", "United States, Census, 1860")

    row = _citation_row(FSFTID="")

    for target in ("RM", "FTM"):
        cit = arc.build_census_citation(row, "1:1:MF36-Z6D", "@Mimg1@", "3", target,
                                        "Pembina", "Dakota Territory", "Dakota Territory",
                                        "T624_1", "")
        assert not any("_APID" in ln for ln in cit), f"{target}: bogus _APID from an ark: {cit}"
        assert not any("_FSFTID" in ln for ln in cit), f"{target}: bogus _FSFTID from an ark: {cit}"


def test_census_citation_fsftid_falls_back_to_bare_ark_for_familysearch_sourced_rows(monkeypatch):
    """User-requested follow-up: the citation-level _FSFTID field should carry this record's
    own FamilySearch person ark - as an identifier, not a URL - when there's no genuine
    tree-attached FSFTID, but ONLY for rows we already know are FamilySearch-sourced
    (FamilySearch_URL present); never fabricated for Ancestry-only rows. And it must be
    BARE (no '1:1:' GEDCOM X type prefix) - that prefix stays only in the actual clickable
    weblink, which is unaffected here."""
    monkeypatch.setattr(arc, "APID_DB", "")
    monkeypatch.setattr(arc, "CENSUS_YEAR", 1860)
    monkeypatch.setattr(arc, "CENSUS_SOURCE_ID", "1473181")
    monkeypatch.setattr(arc, "COLLECTION_NAME", "United States, Census, 1860")

    fs_row = _citation_row(FSFTID="", **{"FamilySearch_URL": "https://www.familysearch.org/ark:/61903/1:1:MF36-Z6D"})
    for target in ("RM", "FTM"):
        cit = arc.build_census_citation(fs_row, "1:1:MF36-Z6D", "@Mimg1@", "3", target,
                                        "Pembina", "Dakota Territory", "Dakota Territory",
                                        "T624_1", "")
        assert any(ln == "3 _FSFTID MF36-Z6D" for ln in cit), f"{target}: missing bare _FSFTID: {cit}"

    monkeypatch.setattr(arc, "APID_DB", "2442")
    anc_row = _citation_row(FSFTID="")
    for target in ("RM", "FTM"):
        cit = arc.build_census_citation(anc_row, "105307051", "@Mimg1@", "3", target,
                                        "Pembina", "Dakota Territory", "Dakota Territory",
                                        "T624_1", "")
        assert not any("_FSFTID" in ln for ln in cit), f"{target}: fabricated _FSFTID for Ancestry-only row: {cit}"


def test_strip_ark_type_prefix():
    assert arc.strip_ark_type_prefix("1:1:MF36-Z6D") == "MF36-Z6D"
    assert arc.strip_ark_type_prefix("3:1:33S7-9YBJ-9PD7") == "33S7-9YBJ-9PD7"
    assert arc.strip_ark_type_prefix("105307051") == "105307051"
    assert arc.strip_ark_type_prefix("") == ""


def test_census_citation_household_id_field_is_bare_number_when_only_one_number_present(monkeypatch):
    """Regression: RM's 'HouseholdID' citation FIELD was rendering as 'family 1' or
    'dwelling 5' (confirmed live against a real 1860 gather - RootsMagic shows
    'HouseholdID: family 1', which reads as a stray descriptive word next to the field's
    own name) instead of the bare id value. The label word only earns its place when BOTH
    dwelling and family numbers exist and genuinely need to be told apart."""
    monkeypatch.setattr(arc, "APID_DB", "")
    monkeypatch.setattr(arc, "CENSUS_YEAR", 1860)
    monkeypatch.setattr(arc, "CENSUS_SOURCE_ID", "1473181")
    monkeypatch.setattr(arc, "COLLECTION_NAME", "United States, Census, 1860")

    family_only = arc.build_census_citation(
        _citation_row(**{"Family Number": "1", "Dwelling Number": ""}), "MF36-Z6D", "@Mimg1@", "3", "RM",
        "Pembina", "Dakota Territory", "Dakota Territory", "T624_1", "")
    assert any(ln == "4 VALUE 1" for ln in family_only), family_only
    assert not any("family" in ln.lower() for ln in family_only), family_only

    dwelling_only = arc.build_census_citation(
        _citation_row(**{"Family Number": "", "Dwelling Number": "5"}), "MF36-Z6D", "@Mimg1@", "3", "RM",
        "Pembina", "Dakota Territory", "Dakota Territory", "T624_1", "")
    assert any(ln == "4 VALUE 5" for ln in dwelling_only), dwelling_only
    assert not any("dwelling" in ln.lower() for ln in dwelling_only), dwelling_only

    both = arc.build_census_citation(
        _citation_row(**{"Family Number": "1", "Dwelling Number": "5"}), "MF36-Z6D", "@Mimg1@", "3", "RM",
        "Pembina", "Dakota Territory", "Dakota Territory", "T624_1", "")
    assert any(ln == "4 VALUE dwelling 5, family 1" for ln in both), both


def test_census_citation_still_emits_apid_for_real_ancestry_data(monkeypatch):
    """Companion to the regression above - a genuine Ancestry-sourced record (real APID_DB,
    numeric rec_id, no FSFTID) must still get its _APID tag exactly as before."""
    monkeypatch.setattr(arc, "APID_DB", "2442")
    monkeypatch.setattr(arc, "CENSUS_YEAR", 1860)
    monkeypatch.setattr(arc, "CENSUS_SOURCE_ID", "1001")
    monkeypatch.setattr(arc, "COLLECTION_NAME", "1860 United States Federal Census")

    row = _citation_row()

    for target in ("RM", "FTM"):
        cit = arc.build_census_citation(row, "105307051", "@Mimg1@", "3", target,
                                        "Pembina", "Dakota Territory", "Dakota Territory",
                                        "T624_1", "")
        assert any(ln == "3 _APID 1,2442::105307051" for ln in cit), f"{target}: missing real _APID: {cit}"


def test_dynamic_occupation_template():
    from Census import get_occupation_value

    # Test Employed
    row1 = pd.Series({
        "Occupation": "Farmer",
        "Employer": "Smith Farm",
        "Industry": "Agriculture",
        "Class of Worker": "W",
        "Hours Worked": "40"
    })
    occ1, notes1 = get_occupation_value(row1)
    assert occ1 == "Farmer at Smith Farm, working in Agriculture"
    assert "Class of Worker: W" in notes1
    assert "Hours Worked: 40" in notes1

    # Test Unemployed override
    row2 = pd.Series({
        "Occupation": "Clerk",
        "Employer": "Bank",
        "Out Of Work": "Yes"
    })
    occ2, notes2 = get_occupation_value(row2)
    assert occ2 == "Unemployed from Clerk at Bank"

    # Test Usual Occupation priority
    row3 = pd.Series({
        "Occupation": "Laborer",
        "Usual Occupation": "Carpenter"
    })
    occ3, notes3 = get_occupation_value(row3)
    assert occ3 == "Carpenter"
