"""
Tests for Archivist's semantic-driven role/family-linking logic - the generalization
that replaced hardcoded role_number digit checks (role "2" is always "Father", role "4"
is always the marriage bride, ...) with a small fixed role_semantic vocabulary
(primary/spouse/child/father/mother/father_in_law/mother_in_law) read directly off each
participant, the same way for any record type.
"""

import pandas as pd

import Archivist as arc


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


def test_build_individual_scrip_event_gets_type_line_and_generic_value_from_extra_fields():
    """Scrip's own event_type resolves to gedcom_tag 'EVEN' (a custom fact, not a standard
    GEDCOM tag) - it needs a '2 TYPE Scrip' line for RootsMagic to recognize which custom
    fact this is, and its extra_fields (scrip_number, scrip_amount, ...) have no standard
    slot of their own, so they render generically as the event's own value text - Archivist
    never hardcodes those field names, just formats whatever type_specific_fields exist."""
    rec = {"event_type": "Scrip", "page": "1", "record_id": "SC-1", "event_place": "Winnipeg",
           "type_specific_fields": {"scrip_number": "1234", "scrip_amount": "$160"},
           "participants": [make_participant("primary", given="Baptiste", surname="Ledoux")]}
    primary = rec["participants"][0]
    lines, _, _, _ = arc.build_individual("I1", rec, primary, "1", "M0000000001", "26 JUL 2026", False, "RM")
    joined = "\n".join(lines)
    assert "2 TYPE Scrip" in joined
    assert "Scrip Number: 1234" in joined and "Scrip Amount: $160" in joined
    assert "2 PLAC Winnipeg" in joined


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
