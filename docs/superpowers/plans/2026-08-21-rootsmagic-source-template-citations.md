# RootsMagic Source Template Citation Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make RootsMagic recognize our custom Source Templates on import instead of
falling back to Free Form citations, by fixing the GEDCOM tag vocabulary and
citation-level template wiring — without touching template content, which stays as
currently defined in the `.rmst` files.

**Architecture:** Two independent, universal GEDCOM-format fixes (tag vocabulary
rewrite; citation-level `_TMPLT` wrapper) applied across four citation-building call
sites (`Census.py`, `Scrip.py`, `General.py`, `HBCA.py`), plus a naming consistency
pass (`*`→`!`) and small dict/field-list corrections, plus two independent Scrip
template-*selection* bugs unrelated to the GEDCOM structure itself.

**Tech Stack:** Python 3.12+, `lxml.etree` for `.rmst` XML parsing, `pytest` for tests,
hand-maintained GEDCOM string building (no GEDCOM library).

**Spec:** `docs/superpowers/specs/2026-08-21-rootsmagic-source-template-citations-design.md`

## Global Constraints

- `Metis Scrip.rmst`'s field content (6 master fields including `PrimaryCreator`/
  `Department`/`Date`/`SourceDescription`, plus `Accessed`/`RefNumber` detail fields)
  is authoritative — do NOT collapse it to `test.ged`'s simplified 3-field design.
  `test.ged` is evidence for GEDCOM *structure* only, never template *content*.
- Every template name gets `*` → `!` swapped, nothing else in the name text changes.
- Category text (`Simplified Citations for Genealogical Sources`) stays unchanged for
  every template, including the 5 Scrip ones.
- Census/Parish/Traditional/Master Template TIDs (`10008`/`10009`/`10010`/`10006`) are
  never renumbered. Scrip TIDs stay `20001`–`20005`. FindAGrave (`10001`) is deleted,
  not renumbered.
- Citation-level `_TMPLT` never carries a `TID` line — only the master `SOUR` record's
  `_TMPLT` does.
- Never re-run `capture_golden_gedcom.py` to make a failing test pass unless the diff
  is exactly the intentional structural change from this plan (per `AGENTS.md`'s
  golden-file discipline).
- Code comments stay short and answer *why*, never *what* — no restating what the next
  line already says, no reasoning trails ("I found this by...", "this turned out to
  be..."). One or two lines is enough; trim every comment in this plan's code blocks
  to that bar before committing it, not just the ones written fresh.

---

### Task 1: Tag-vocabulary rewrite in `Census.py`

**Files:**
- Modify: `Archivist/Census.py:141-197` (`_gedcom_text_lines`, `_rmst_element_to_gedcom`)
- Test: `Archivist/tests/test_archivist.py` (new tests, see below)

**Interfaces:**
- Produces: `_gedcom_wrapped_lines(level: int, tag: str, text: str, max_len: int = 200) -> List[str]` (replaces `_gedcom_text_lines`, same file)
- Produces: `_rmst_element_to_gedcom(elem) -> List[str]` (same signature, new tag vocabulary)

Current `_rmst_element_to_gedcom` emits `_SRCTEMPLATE`/`FOOT`/`BIBL`/`DISP`/`DETL`/
`LHNT` — tags RootsMagic's importer doesn't recognize. It must emit `_STMPLT` (name as
a separate `1 NAME` line, not inline), `FOOTNOTE`/`BIBLIO`/`DISPLAY`/`ISDETAIL`/
`LONGHINT`, with `TYPE` values upper-cased. The existing `_gedcom_text_lines` only
`CONT`-wraps on literal `\n` in the source text — it never enforces GEDCOM 5.5.1's
255-byte line limit within a paragraph, which real Footnote/Bibliography text can
exceed. Replace it with a helper that also `CONC`-wraps within a paragraph.

- [ ] **Step 1: Write the failing tests**

Add to `Archivist/tests/test_archivist.py`:

```python
def test_gedcom_wrapped_lines_cont_on_paragraph_break():
    lines = Census._gedcom_wrapped_lines(1, "DESC", "First paragraph.\n\nSecond paragraph.")
    assert lines[0] == "1 DESC First paragraph."
    assert lines[1] == "2 CONT "
    assert lines[2] == "2 CONT Second paragraph."


def test_gedcom_wrapped_lines_conc_on_long_line():
    long_text = "A" * 250
    lines = Census._gedcom_wrapped_lines(1, "FOOTNOTE", long_text, max_len=200)
    assert lines[0] == f"1 FOOTNOTE {'A' * 200}"
    assert lines[1] == f"2 CONC {'A' * 50}"


def test_rmst_element_to_gedcom_uses_stmplt_tag_vocabulary():
    import lxml.etree as etree
    xml = etree.fromstring("""
    <Template Id="99999">
      <Name>!Test Template</Name>
      <Description>A description.</Description>
      <Category>Test Category</Category>
      <Footnote>Footnote text.</Footnote>
      <ShortFootnote>Short text.</ShortFootnote>
      <Bibliography>Bibliography text.</Bibliography>
      <Field>
        <Type>Text</Type>
        <Name>TestField</Name>
        <Display>Test Field</Display>
        <Hint>a hint</Hint>
        <Detail>True</Detail>
        <LongHint>a long hint</LongHint>
      </Field>
    </Template>
    """)
    lines = Census._rmst_element_to_gedcom(xml)
    joined = "\n".join(lines)
    assert "0 _STMPLT" in joined
    assert "_SRCTEMPLATE" not in joined
    assert "1 TID 99999" in joined
    assert "1 NAME !Test Template" in joined
    assert "1 FOOTNOTE Footnote text." in joined
    assert "1 BIBLIO Bibliography text." in joined
    assert "2 DISPLAY Test Field" in joined
    assert "2 LONGHINT a long hint" in joined
    assert "2 TYPE TEXT" in joined
    assert "2 ISDETAIL Y" in joined
    assert "FOOT " not in joined
    assert "BIBL " not in joined
    assert "DISP " not in joined
    assert "DETL " not in joined
    assert "LHNT " not in joined
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd Archivist && python -m pytest tests/test_archivist.py -k "gedcom_wrapped_lines or rmst_element_to_gedcom" -v`
Expected: FAIL — `_gedcom_wrapped_lines` doesn't exist yet, `_rmst_element_to_gedcom` emits the old tags.

- [ ] **Step 3: Replace `_gedcom_text_lines` and rewrite `_rmst_element_to_gedcom`**

In `Archivist/Census.py`, replace lines 141-197 (`_gedcom_text_lines` through the end of
`_rmst_element_to_gedcom`) with:

```python
def _gedcom_wrapped_lines(level: int, tag: str, text: str, max_len: int = 200) -> List[str]:
    """CONT on each literal newline (paragraph break); CONC within a paragraph past
    max_len - GEDCOM 5.5.1 caps a physical line at 255 bytes."""
    lines: List[str] = []
    first = True
    for para in text.split("\n"):
        chunks = [para[i:i + max_len] for i in range(0, len(para), max_len)] or [""]
        for i, chunk in enumerate(chunks):
            if first:
                lines.append(f"{level} {tag} {chunk}")
                first = False
            elif i == 0:
                lines.append(f"{level + 1} CONT {chunk}")
            else:
                lines.append(f"{level + 1} CONC {chunk}")
    return lines


def _rmst_element_to_gedcom(elem: etree.Element) -> List[str]:
    """Emits _STMPLT/FOOTNOTE/BIBLIO/DISPLAY/ISDETAIL/LONGHINT - RM's real tag
    vocabulary, not the _SRCTEMPLATE/FOOT/BIBL/DISP/DETL/LHNT names RM doesn't
    recognize."""
    tid = elem.get("Id", "")
    name = (elem.findtext("Name") or "").strip()
    desc = (elem.findtext("Description") or "").strip()
    cat = (elem.findtext("Category") or "Simplified Citations for Genealogical Sources").strip()
    foot = (elem.findtext("Footnote") or "").strip()
    short = (elem.findtext("ShortFootnote") or "").strip()
    bibl = (elem.findtext("Bibliography") or "").strip()

    lines = ["0 _STMPLT", f"1 TID {tid}"]
    if name:
        lines.append(f"1 NAME {name}")
    if desc:
        lines.extend(_gedcom_wrapped_lines(1, "DESC", desc))
    if cat:
        lines.append(f"1 CAT {cat}")
    if foot:
        lines.extend(_gedcom_wrapped_lines(1, "FOOTNOTE", foot))
    if short:
        lines.extend(_gedcom_wrapped_lines(1, "SHORT", short))
    if bibl:
        lines.extend(_gedcom_wrapped_lines(1, "BIBLIO", bibl))

    for fld in elem.findall("Field"):
        f_type = (fld.findtext("Type") or "Text").strip().upper()
        f_name = (fld.findtext("Name") or "").strip()
        f_disp = (fld.findtext("Display") or "").strip()
        f_hint = (fld.findtext("Hint") or "").strip()
        f_detl = "Y" if (fld.findtext("Detail") or "False").strip().lower() in ("true", "1", "y") else "N"
        f_lhnt = (fld.findtext("LongHint") or "").strip()

        lines.append("1 FIELD")
        if f_name:
            lines.append(f"2 NAME {f_name}")
        if f_disp:
            lines.extend(_gedcom_wrapped_lines(2, "DISPLAY", f_disp))
        if f_hint:
            lines.extend(_gedcom_wrapped_lines(2, "HINT", f_hint))
        if f_lhnt:
            lines.extend(_gedcom_wrapped_lines(2, "LONGHINT", f_lhnt))
        lines.append(f"2 TYPE {f_type}")
        lines.append(f"2 ISDETAIL {f_detl}")
    return lines
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd Archivist && python -m pytest tests/test_archivist.py -k "gedcom_wrapped_lines or rmst_element_to_gedcom" -v`
Expected: PASS

- [ ] **Step 5: Run the full Census-related test suite to check for regressions**

Run: `cd Archivist && python -m pytest tests/ -k "census or Census" -v`
Expected: any failures referencing `_SRCTEMPLATE`/`FOOT`/`BIBL`/`DISP`/`DETL`/`LHNT`
text are expected — note them, they get fixed in Task 9's golden-file regen. Failures
unrelated to tag names indicate a real regression — investigate before continuing.

- [ ] **Step 6: Commit**

```bash
git add Archivist/Census.py Archivist/tests/test_archivist.py
git commit -m "fix(archivist): rewrite _rmst_element_to_gedcom to real RM tag vocabulary (Census.py)"
```

---

### Task 2: Tag-vocabulary rewrite in `General.py`

**Files:**
- Modify: `Archivist/General.py:456-497` (`_rmst_element_to_gedcom`; no existing
  `_gedcom_text_lines`/wrapping helper in this file at all today — General.py's copy
  never wrapped multi-line text, not even with `CONT`)
- Test: `Archivist/tests/test_general_smoke.py` (or `test_archivist.py` if that's where
  General-module tests already live — check which file imports `General` before adding)

**Interfaces:**
- Produces: `_gedcom_wrapped_lines(level: int, tag: str, text: str, max_len: int = 200) -> List[str]` (new to this file — same implementation as Task 1's, this file has no prior version at all)
- Produces: `_rmst_element_to_gedcom(elem) -> List[str]` (same signature as Task 1, mirrored fix)

This is the sibling copy of Task 1's function (the codebase intentionally duplicates
these across self-contained entrypoints — see `AI Assistant.md`/architecture notes on
"self-contained execution entrypoints" — so both copies get the identical fix, not a
shared import). General.py's current copy is worse than Census.py's: it has no
line-wrapping helper at all, so multi-line `Description` text with literal embedded
`\n` characters currently gets written as raw unescaped newlines inside a single GEDCOM
tag value — invalid GEDCOM on its own, independent of the tag-name bug.

- [ ] **Step 1: Write the failing test**

Add wherever General.py's existing tests live (check with
`grep -rn "import General" Archivist/tests/*.py` first):

```python
def test_general_rmst_element_to_gedcom_uses_stmplt_tag_vocabulary():
    import lxml.etree as etree
    xml = etree.fromstring("""
    <Template Id="88888">
      <Name>!Test Template</Name>
      <Description>Paragraph one.

Paragraph two.</Description>
      <Category>Test Category</Category>
      <Footnote>Footnote text.</Footnote>
      <ShortFootnote>Short text.</ShortFootnote>
      <Bibliography>Bibliography text.</Bibliography>
      <Field>
        <Type>Name</Type>
        <Name>TestField</Name>
        <Display>Test Field</Display>
        <Hint>a hint</Hint>
        <Detail>False</Detail>
        <LongHint/>
      </Field>
    </Template>
    """)
    lines = General._rmst_element_to_gedcom(xml)
    joined = "\n".join(lines)
    assert "0 _STMPLT" in joined
    assert "_SRCTEMPLATE" not in joined
    assert "1 NAME !Test Template" in joined
    assert "1 DESC Paragraph one." in joined
    assert "2 CONT " in joined
    assert "2 CONT Paragraph two." in joined
    assert "1 FOOTNOTE Footnote text." in joined
    assert "1 BIBLIO Bibliography text." in joined
    assert "2 DISPLAY Test Field" in joined
    assert "2 TYPE NAME" in joined
    assert "2 ISDETAIL N" in joined
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd Archivist && python -m pytest tests/test_general_smoke.py -k "rmst_element_to_gedcom" -v`
(adjust file name to wherever you added it)
Expected: FAIL

- [ ] **Step 3: Add the wrapping helper and rewrite the function**

In `Archivist/General.py`, replace lines 456-497 (`_rmst_element_to_gedcom`) with:

```python
def _gedcom_wrapped_lines(level: int, tag: str, text: str, max_len: int = 200) -> List[str]:
    """CONT on each literal newline (paragraph break); CONC within a paragraph past
    max_len - GEDCOM 5.5.1 caps a physical line at 255 bytes."""
    lines: List[str] = []
    first = True
    for para in text.split("\n"):
        chunks = [para[i:i + max_len] for i in range(0, len(para), max_len)] or [""]
        for i, chunk in enumerate(chunks):
            if first:
                lines.append(f"{level} {tag} {chunk}")
                first = False
            elif i == 0:
                lines.append(f"{level + 1} CONT {chunk}")
            else:
                lines.append(f"{level + 1} CONC {chunk}")
    return lines


# noinspection DuplicatedCode
def _rmst_element_to_gedcom(elem: etree.Element) -> List[str]:
    """Emits _STMPLT/FOOTNOTE/BIBLIO/DISPLAY/ISDETAIL/LONGHINT - RM's real tag
    vocabulary, not the _SRCTEMPLATE/FOOT/BIBL/DISP/DETL/LHNT names RM doesn't
    recognize."""
    tid = elem.get("Id", "")
    name = (elem.findtext("Name") or "").strip()
    desc = (elem.findtext("Description") or "").strip()
    cat = (elem.findtext("Category") or "Simplified Citations for Genealogical Sources").strip()
    foot = (elem.findtext("Footnote") or "").strip()
    short = (elem.findtext("ShortFootnote") or "").strip()
    bibl = (elem.findtext("Bibliography") or "").strip()

    lines = ["0 _STMPLT", f"1 TID {tid}"]
    if name:
        lines.append(f"1 NAME {name}")
    if desc:
        lines.extend(_gedcom_wrapped_lines(1, "DESC", desc))
    if cat:
        lines.append(f"1 CAT {cat}")
    if foot:
        lines.extend(_gedcom_wrapped_lines(1, "FOOTNOTE", foot))
    if short:
        lines.extend(_gedcom_wrapped_lines(1, "SHORT", short))
    if bibl:
        lines.extend(_gedcom_wrapped_lines(1, "BIBLIO", bibl))

    for fld in elem.findall("Field"):
        f_type = (fld.findtext("Type") or "Text").strip().upper()
        f_name = (fld.findtext("Name") or "").strip()
        f_disp = (fld.findtext("Display") or "").strip()
        f_hint = (fld.findtext("Hint") or "").strip()
        f_detl = "Y" if (fld.findtext("Detail") or "False").strip().lower() in ("true", "1", "y") else "N"
        f_lhnt = (fld.findtext("LongHint") or "").strip()

        lines.append("1 FIELD")
        if f_name:
            lines.append(f"2 NAME {f_name}")
        if f_disp:
            lines.extend(_gedcom_wrapped_lines(2, "DISPLAY", f_disp))
        if f_hint:
            lines.extend(_gedcom_wrapped_lines(2, "HINT", f_hint))
        if f_lhnt:
            lines.extend(_gedcom_wrapped_lines(2, "LONGHINT", f_lhnt))
        lines.append(f"2 TYPE {f_type}")
        lines.append(f"2 ISDETAIL {f_detl}")
    return lines
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd Archivist && python -m pytest tests/test_general_smoke.py -k "rmst_element_to_gedcom" -v`
Expected: PASS

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `cd Archivist && python -m pytest tests/ -v`
Expected: failures referencing the old tag names are expected (fixed in Task 9's
golden-file regen); anything else is a real regression.

- [ ] **Step 6: Commit**

```bash
git add Archivist/General.py Archivist/tests/
git commit -m "fix(archivist): rewrite _rmst_element_to_gedcom to real RM tag vocabulary (General.py)"
```

---

### Task 3: Citation-level `_TMPLT` fix — `Census.py`

**Files:**
- Modify: `Archivist/Census.py:808-877` (`build_census_citation`)
- Test: `Archivist/tests/test_census_ingestion.py`

**Interfaces:**
- Consumes: none new
- Produces: `build_census_citation(...)` returns the same `List[str]` shape, with
  citation-level Detail fields now wrapped in `3 _TMPLT`/`4 FIELD`/`5 NAME`/`5 VALUE`
  (was bare `3 FIELD`/`4 NAME`/`4 VALUE`), placed after `PAGE`.

Real GEDCOM output (`Census-1950-USA-North Dakota-Pembina-Advance-34-1-FS-RM.ged`)
confirmed the current `3 FIELD` block is not wrapped in `_TMPLT` at all — RM doesn't
recognize orphaned `FIELD` tags as template data and falls back to Free Form.

- [ ] **Step 1: Update the existing detail-field test to expect the new nesting**

Find and update the existing test that checks `build_census_citation`'s FIELD output
(search `grep -n "4 VALUE" Archivist/tests/test_census_ingestion.py`). Update every
`"4 VALUE ..."` string assertion to `"5 VALUE ..."` and every `"4 NAME ..."` to
`"5 NAME ..."`, and add an assertion the wrapper exists:

```python
    assert any(ln == "3 _TMPLT" for ln in family_only), family_only
    assert any(ln == "5 VALUE 1" for ln in family_only), family_only
```

(There are three such assertions in the existing household-ID test — for family-only,
dwelling-only, and both — update all three the same way.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd Archivist && python -m pytest tests/test_census_ingestion.py -k household_id_field -v`
Expected: FAIL — current code emits `3 FIELD`/`4 NAME`/`4 VALUE`, not `3 _TMPLT`/`4 FIELD`/`5 NAME`/`5 VALUE`.

- [ ] **Step 3: Fix `build_census_citation`**

In `Archivist/Census.py`, replace the body from `if target_software == "RM":` through
`cit.append("3 DATA")` (lines 830-854) with:

```python
    if target_software == "RM":
        page_parts = [row_roll, f"{row_town}{ed_suffix}", real_page]
        if caps["household"]:
            page_parts.append(fam_num)
        page_parts.append(person_str)

        collection_title = COLLECTION_NAME or DEFAULT_COLLECTION_NAME

        detail_fields = [
            ("Page", f"p. {real_page}" if real_page else ""),
            ("SourceDetailPerson", person_str),
            ("Location", row_loc),
            ("CensusED", row_ed),
            ("HouseholdID", f"dwelling {dwell_num}, family {fam_num}" if (dwell_num and fam_num)
             else (fam_num or dwell_num)),
            ("Repository", "Ancestry.com" if not fs_url else "FamilySearch"),
            ("URL", ancestry_url),
            ("RefNumber", f"APID 1,{APID_DB}::{rec_id}" if (APID_DB and rec_id) else ""),
        ]
        cit.append(f"3 PAGE {'; '.join(filter(None, page_parts))}")
        # Bare FIELD tags render Free Form; RM needs them under _TMPLT. No TID here -
        # that's on the master SOUR record only.
        cit.append("3 _TMPLT")
        for f_name, f_val in detail_fields:
            if f_val:
                cit.extend(["4 FIELD", f"5 NAME {f_name}", f"5 VALUE {f_val}"])

        cit.append("3 DATA")
```

(Everything from `if APID_DB and rec_id:` onward stays unchanged.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd Archivist && python -m pytest tests/test_census_ingestion.py -k household_id_field -v`
Expected: PASS

- [ ] **Step 5: Run the full Census test module**

Run: `cd Archivist && python -m pytest tests/test_census_ingestion.py -v`
Expected: all pass (this file has no golden-file dependency).

- [ ] **Step 6: Commit**

```bash
git add Archivist/Census.py Archivist/tests/test_census_ingestion.py
git commit -m "fix(archivist): wrap census citation Detail fields in _TMPLT block"
```

---

### Task 4: Citation-level `_TMPLT` fix — `General.py` (Parish/Non-traditional)

**Files:**
- Modify: `Archivist/General.py:165-197` (`GeneralProfile.citation_detail_fields`)
- Test: `Archivist/tests/test_archivist.py`

**Interfaces:**
- Produces: `GeneralProfile.citation_detail_fields(rec, part, page, vol, target_software) -> List[str]` returns `["3 _TMPLT", "4 FIELD", "5 NAME ...", "5 VALUE ...", ...]` instead of bare `3 FIELD` lines (or `[]` if no detail values present).

`General.py`'s `_build_citation_block` (lines 560-587) already places
`citation_detail_fields()`'s output *after* `titl`/`page_line` — no reordering needed
there, only the profile method's own FIELD wrapping.

- [ ] **Step 1: Write the failing test**

Add to `Archivist/tests/test_archivist.py`:

```python
def test_general_profile_citation_detail_fields_wraps_in_tmplt():
    rec = {"record_id": "REC-1", "type_specific_fields": {}}
    part = {"std_given": "Marie", "std_surname": "Gagnon"}
    General.GENERAL_CONFIG["parish_location"] = "St. Boniface, Manitoba"
    lines = General.GeneralProfile.citation_detail_fields(rec, part, "12", "3", "RM")
    assert lines[0] == "3 _TMPLT"
    assert "4 FIELD" in lines
    assert any(ln == "5 NAME SourceDetailPerson" for ln in lines)
    assert any(ln == "5 VALUE Marie Gagnon" for ln in lines)
    assert not any(ln.startswith("4 TID") for ln in lines)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd Archivist && python -m pytest tests/test_archivist.py -k citation_detail_fields_wraps -v`
Expected: FAIL

- [ ] **Step 3: Fix `citation_detail_fields`**

In `Archivist/General.py`, replace lines 193-197 (the `lines = []` loop through
`return lines`) with:

```python
        # Bare FIELD tags render Free Form; RM needs them under _TMPLT. No TID here -
        # that's on the master SOUR record only.
        field_lines = []
        for f_name, f_val in parish_detail_fields:
            if f_val:
                field_lines.extend(["4 FIELD", f"5 NAME {f_name}", f"5 VALUE {f_val}"])
        if not field_lines:
            return []
        return ["3 _TMPLT"] + field_lines
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd Archivist && python -m pytest tests/test_archivist.py -k citation_detail_fields_wraps -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add Archivist/General.py Archivist/tests/test_archivist.py
git commit -m "fix(archivist): wrap parish citation Detail fields in _TMPLT block"
```

---

### Task 5: Citation-level `_TMPLT` fix — `Scrip.py`

**Files:**
- Modify: `Archivist/Scrip.py:249-256` (`get_scrip_citation_fields`)
- Test: `Archivist/tests/test_archivist.py`

**Interfaces:**
- Produces: `get_scrip_citation_fields(template_id, rec, part, vol) -> List[str]` returns `["3 _TMPLT", "4 FIELD", "5 NAME ...", "5 VALUE ...", ...]` (or `[]` if no detail values present).

- [ ] **Step 1: Update the existing test to expect the new nesting**

Find `test_get_scrip_citation_fields_skips_empty_values` in
`Archivist/tests/test_archivist.py` and update:

```python
def test_get_scrip_citation_fields_skips_empty_values():
    rec = {"type_specific_fields": {"affidavit_number": "5473"}, "lac_pid": ""}
    part = make_participant("primary", given="Roger", surname="Letendre")
    lines = Scrip.get_scrip_citation_fields(20001, rec, part, "1320")
    joined = "\n".join(lines)
    assert "3 _TMPLT" in joined
    assert "5 NAME AffidavitNumber" in joined and "5 VALUE 5473" in joined
    assert "5 NAME ClaimantName" in joined and "5 VALUE Roger Letendre" in joined
    # Microfilm/Parish/URL were never set on this record - must not appear at all.
    assert "Microfilm" not in joined
    assert "URL" not in joined
```

Also find `test_build_general_citation_scrip_cites_the_matching_template_source_with_field_block`
in the same file and update:

```python
        joined = blocks[0]
        assert "2 SOUR @S20001@" in joined
        assert "3 _TMPLT" in joined
        assert "5 NAME AffidavitNumber" in joined and "5 VALUE 5473" in joined
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd Archivist && python -m pytest tests/test_archivist.py -k "get_scrip_citation_fields or scrip_cites_the_matching" -v`
Expected: FAIL

- [ ] **Step 3: Fix `get_scrip_citation_fields`**

In `Archivist/Scrip.py`, replace lines 249-256 with:

```python
def get_scrip_citation_fields(template_id: int, rec: dict, part: dict, vol: str) -> List[str]:
    """Bare FIELD tags render Free Form; RM needs them under _TMPLT. No TID here -
    that's on the master SOUR record only."""
    lines = []
    for field_name in _SCRIP_TEMPLATES[template_id]['detail_fields']:
        value = _scrip_template_field_value(field_name, rec, part, vol)
        if value:
            lines.extend(["4 FIELD", f"5 NAME {field_name}", f"5 VALUE {value}"])
    if not lines:
        return []
    return ["3 _TMPLT"] + lines
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd Archivist && python -m pytest tests/test_archivist.py -k "get_scrip_citation_fields or scrip_cites_the_matching" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add Archivist/Scrip.py Archivist/tests/test_archivist.py
git commit -m "fix(archivist): wrap scrip citation Detail fields in _TMPLT block"
```

---

### Task 6: Citation-level `_TMPLT` fix — `HBCA.py`

**Files:**
- Modify: `Archivist/HBCA.py:109-189` (`citation_detail_fields`)
- Test: `Archivist/tests/test_hbca_profile.py`

**Interfaces:**
- Produces: `citation_detail_fields(rec, part, page, vol, target_software) -> List[str]` returns `["3 _TMPLT", "4 FIELD", "5 NAME ...", "5 VALUE ...", ...]` (or `[]`).

- [ ] **Step 1: Write the failing test**

Add to the existing HBCA test file:

```python
def test_hbca_citation_detail_fields_wraps_in_tmplt():
    rec = {"event_place": "Red River", "type_specific_fields": {
        "employee_name": "John Smith", "hbca_references": ["A.32/1"],
    }}
    part = {"std_given": "John", "std_surname": "Smith"}
    lines = HBCA.HBCAProfile.citation_detail_fields(rec, part, "1", "1", "RM")
    assert lines[0] == "3 _TMPLT"
    assert "4 FIELD" in lines
    assert any(ln == "5 NAME SourceDetailPerson" for ln in lines)
    assert not any(ln.startswith("4 TID") for ln in lines)
```

(Check the actual profile class name in `HBCA.py` with
`grep -n "class.*Profile" Archivist/HBCA.py` — adjust `HBCAProfile` if it differs.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd Archivist && python -m pytest tests/test_hbca_profile.py -k tmplt -v`
Expected: FAIL

- [ ] **Step 3: Fix `citation_detail_fields`**

In `Archivist/HBCA.py`, replace lines 185-189 (the `lines = []` loop through
`return lines`) with:

```python
        # Bare FIELD tags render Free Form; RM needs them under _TMPLT. No TID here -
        # that's on the master SOUR record only.
        field_lines = []
        for f_name, f_val in detail_fields:
            if f_val:
                field_lines.extend(["4 FIELD", f"5 NAME {f_name}", f"5 VALUE {f_val}"])
        if not field_lines:
            return []
        return ["3 _TMPLT"] + field_lines
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd Archivist && python -m pytest tests/test_hbca_profile.py -k tmplt -v`
Expected: PASS

- [ ] **Step 5: Run full HBCA test module**

Run: `cd Archivist && python -m pytest tests/test_hbca_profile.py -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add Archivist/HBCA.py Archivist/tests/
git commit -m "fix(archivist): wrap HBCA citation Detail fields in _TMPLT block"
```

---

### Task 7: Naming (`*`→`!`) and field-list reconciliation across all templates

**Files:**
- Modify: `Archivist/Scrip.py:9-136` (`_SIMPLIFIED_CITATION_TEMPLATES` dict)
- Modify: `Archivist/Source Templates/Metis Scrip.rmst` (5 `<Name>` elements)
- Modify: `Archivist/Source Templates/Simplified Citations - Census.rmst` (1 `<Name>`)
- Modify: `Archivist/Source Templates/Simplified Citations - Non-traditional.rmst` (1 `<Name>`)
- Modify: `Archivist/Source Templates/Simplified Citations - Traditional.rmst` (1 `<Name>`)
- Modify: `Archivist/Source Templates/Simplified Citations - Master Template.rmst` (1 `<Name>`)
- Test: `Archivist/tests/test_archivist.py`

**Interfaces:**
- Consumes: none new
- Produces: `_SIMPLIFIED_CITATION_TEMPLATES[tid]['name']` now starts with `!` for every
  entry except the removed `10001`.

This task does three things together since they're all trivial, same-file dict edits:
(a) swap `*`→`!` in every template name, in both the `.rmst` files and the Python dict
(minimal swap only — do not alter any other part of the name text or the `Category`
text, per the Global Constraints); (b) remove the dead `10001` FindAGrave entry
(colliding with the real North-West Scrip TID in the user's live database, unused
anywhere else in the codebase — verified via
`grep -rn "10001" Archivist/*.py`); (c) reconcile the four non-Scrip dict entries'
field lists against their own `.rmst` files, which is real drift found during
diagnosis, independent of the naming swap:

- **Census (`10008`)**: `.rmst` defines a `PersonalID` detail field missing from the
  dict's `detail_fields`. Add it — safe to leave unpopulated (our data model has no
  such value; the existing `if f_val:` skip-when-empty pattern in `build_census_citation`
  already handles that, since it's never referenced in the Footnote/Bibliography text).
- **Non-traditional (`10009`)**: dict's `master_fields` wrongly includes `Publisher`
  and `PublishLocation` — not present in the real `.rmst` at all. Remove them. Also
  missing `PersonalID` from `detail_fields`.
- **Traditional (`10010`)**: dict is missing `Title` from `master_fields` and
  `PersonalID` from `detail_fields`.
- **Master Template (`10006`)**: dict is missing `Author`, `Role`, `BookTitle`,
  `Subtitle`, `Title` from `master_fields`, and `PersonalID` from `detail_fields`.

(`10006` and `10010` are confirmed unused by any `citation_template_id`/
`resolve_source_templates` call today — this is hygiene with zero behavioral impact
right now, but low-cost since the file is already being edited.)

- [ ] **Step 1: Write the failing tests**

Add to `Archivist/tests/test_archivist.py`:

```python
def test_all_template_names_start_with_bang():
    for tid, tpl in Scrip._SIMPLIFIED_CITATION_TEMPLATES.items():
        assert tpl['name'].startswith('!'), f"TID {tid} name {tpl['name']!r} missing ! prefix"


def test_findagrave_entry_removed():
    assert 10001 not in Scrip._SIMPLIFIED_CITATION_TEMPLATES


def test_non_traditional_master_fields_match_rmst():
    tpl = Scrip._SIMPLIFIED_CITATION_TEMPLATES[10009]
    assert 'Publisher' not in tpl['master_fields']
    assert 'PublishLocation' not in tpl['master_fields']
    assert 'PersonalID' in tpl['detail_fields']


def test_census_detail_fields_include_personal_id():
    assert 'PersonalID' in Scrip._SIMPLIFIED_CITATION_TEMPLATES[10008]['detail_fields']


def test_traditional_master_fields_include_title():
    tpl = Scrip._SIMPLIFIED_CITATION_TEMPLATES[10010]
    assert 'Title' in tpl['master_fields']
    assert 'PersonalID' in tpl['detail_fields']


def test_master_template_fields_match_rmst():
    tpl = Scrip._SIMPLIFIED_CITATION_TEMPLATES[10006]
    for f in ('Author', 'Role', 'BookTitle', 'Subtitle', 'Title'):
        assert f in tpl['master_fields'], f"missing {f}"
    assert 'PersonalID' in tpl['detail_fields']
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd Archivist && python -m pytest tests/test_archivist.py -k "bang or findagrave_entry_removed or master_fields_match_rmst or detail_fields_include_personal_id or master_fields_include_title" -v`
Expected: FAIL

- [ ] **Step 3: Edit `_SIMPLIFIED_CITATION_TEMPLATES` in `Scrip.py`**

Replace lines 9-136 (the whole dict) with:

```python
_SIMPLIFIED_CITATION_TEMPLATES: Dict[int, Dict[str, object]] = {
    10006: {
        'name': "!Simplified Citations Master Template",
        'category': "Simplified Citations for Genealogical Sources",
        'label': "Master Template",
        'source_description': "Master Citation Template",
        'master_fields': ['PrimaryCreator', 'Department', 'Author', 'Role', 'Date',
                          'BookTitle', 'Subtitle', 'Title', 'SourceDescription',
                          'Person', 'Publisher', 'PublishLocation'],
        'detail_fields': ['Page', 'SourceDetailPerson', 'Location', 'CensusED',
                          'HouseholdID', 'Repository', 'URL', 'Accessed', 'RefNumber',
                          'PersonalID'],
    },
    10008: {
        'name': "!Simple Citations: Census Records",
        'category': "Simplified Citations for Genealogical Sources",
        'label': "Census Records",
        'source_description': "Census Records and Population Schedules",
        'master_fields': ['PrimaryCreator', 'Department', 'Date', 'SourceDescription',
                          'Person', 'Publisher', 'PublishLocation'],
        'detail_fields': ['Page', 'SourceDetailPerson', 'Location', 'CensusED',
                          'HouseholdID', 'Repository', 'URL', 'Accessed', 'RefNumber',
                          'PersonalID'],
    },
    10009: {
        'name': "!Simple Citations: Non-traditional",
        'category': "Simplified Citations for Genealogical Sources",
        'label': "Non-traditional (Church / Parish / Vital / Cemetery)",
        'source_description': "Church Registers, Vital Records, and Archives",
        'master_fields': ['PrimaryCreator', 'Department', 'Date', 'SourceDescription', 'Person'],
        'detail_fields': ['Page', 'SourceDetailPerson', 'Location', 'Repository',
                          'URL', 'Accessed', 'RefNumber', 'PersonalID'],
    },
    10010: {
        'name': "!Simple Citations: Traditional",
        'category': "Simplified Citations for Genealogical Sources",
        'label': "Traditional (Books / Newspapers / Periodicals)",
        'source_description': "Published Books, Articles, and Periodicals",
        'master_fields': ['Author', 'Role', 'Date', 'BookTitle', 'Subtitle', 'Title',
                          'Publisher', 'PublishLocation'],
        'detail_fields': ['Page', 'SourceDetailPerson', 'Location', 'Repository',
                          'URL', 'Accessed', 'RefNumber', 'PersonalID'],
    },
    20001: {
        'name': "!Simple Citations: Métis Scrip (Manitoba, 1870–1876)",
        'category': "Simplified Citations for Genealogical Sources",
        'label': "Métis Scrip: Manitoba (1870–1876)",
        'source_description': "Manitoba Métis Scrip Applications",
        'website_collection': "Manitoba Métis scrip applications",
        'primary_creator': "Department of the Interior",
        'department': "Manitoba Scrip Commission",
        'commission': "Manitoba Scrip Commission",
        'collection': "Department of the Interior fonds, RG 15, Series D-II-8-a",
        'date_range': [(1870, 1876)],
        'date_range_str': "1870–1876",
        'master_fields': ['PrimaryCreator', 'Department', 'Date', 'SourceDescription', 'Collection', 'Repository'],
        'detail_fields': ['ClaimantName', 'AffidavitNumber', 'Parish', 'ScripType',
                          'Volume', 'Microfilm', 'URL', 'Accessed', 'RefNumber'],
    },
    20002: {
        'name': "!Simple Citations: Métis Scrip (North-West, 1885 & 1900-1901)",
        'category': "Simplified Citations for Genealogical Sources",
        'label': "Métis Scrip: North-West (1885 & 1900-1901)",
        'source_description': "North-West Territories Métis Scrip Applications",
        'website_collection': "North-West Territories Métis scrip applications",
        'primary_creator': "Department of the Interior",
        'department': "North-West Half-Breed Claims Commission",
        'commission': "North-West Half-Breed Claims Commission",
        'collection': "Department of the Interior fonds, RG 15, Series D-II-8-c",
        'date_range': [(1885, 1885), (1900, 1901)],
        'date_range_str': "1885 & 1900-1901",
        'master_fields': ['PrimaryCreator', 'Department', 'Date', 'SourceDescription', 'Collection', 'Repository'],
        'detail_fields': ['ClaimantName', 'ClaimNumber', 'ScripNumber', 'IssueDate',
                          'Location', 'Volume', 'Microfilm', 'URL', 'Accessed', 'RefNumber'],
    },
    20003: {
        'name': "!Simple Citations: Métis Scrip (Treaty 8, 1899-1908)",
        'category': "Simplified Citations for Genealogical Sources",
        'label': "Métis Scrip: Treaty 8 (1899-1908)",
        'source_description': "Treaty No. 8 Métis Scrip Applications",
        'website_collection': "Treaty No. 8 Métis scrip applications",
        'primary_creator': "Department of the Interior",
        'department': "Treaty No. 8 Scrip Commission",
        'commission': "Treaty No. 8 Scrip Commission",
        'collection': "Department of the Interior fonds, RG 15, Series D-II-8-i",
        'date_range': [(1899, 1908)],
        'date_range_str': "1899–1908",
        'master_fields': ['PrimaryCreator', 'Department', 'Date', 'SourceDescription', 'Collection', 'Repository'],
        'detail_fields': ['ClaimantName', 'ClaimNumber', 'ScripAmount', 'ScripNoteNumber',
                          'DeliveryDate', 'DeliveryPlace', 'Volume', 'URL', 'Accessed', 'RefNumber'],
    },
    20004: {
        'name': "!Simple Citations: Métis Scrip (Certificates & Payments)",
        'category': "Simplified Citations for Genealogical Sources",
        'label': "Métis Scrip: Certificate",
        'source_description': "Métis Scrip Certificates and Payments",
        'website_collection': "Métis scrip certificates and payments",
        'primary_creator': "Department of the Interior",
        'department': "Scrip Commission",
        'commission': "Scrip Commission",
        'collection': "Department of the Interior fonds, RG 15, Series D-II-8-e/f/j",
        'date_range': [(1870, 1906)],
        'date_range_str': "1870–1906",
        'master_fields': ['PrimaryCreator', 'Department', 'Date', 'SourceDescription', 'Collection', 'Repository'],
        'detail_fields': ['ClaimantName', 'ScripType', 'CertificateNumber', 'Amount',
                          'IssueDate', 'Volume', 'Microfilm', 'URL', 'Accessed', 'RefNumber'],
    },
    20005: {
        'name': "!Simple Citations: Dominion Land Grants & Patents",
        'category': "Simplified Citations for Genealogical Sources",
        'label': "Land Records: Dominion Land Grant Patent",
        'source_description': "Dominion Lands Patents",
        'website_collection': "Dominion Lands patents",
        'primary_creator': "Department of the Interior",
        'department': "Dominion Lands Branch",
        'commission': "",
        'collection': "Dominion Land Grants, RG 15",
        'date_range': [(1870, 1930)],
        'date_range_str': "1870–1930",
        'master_fields': ['PrimaryCreator', 'Department', 'Date', 'SourceDescription', 'Collection', 'Repository'],
        'detail_fields': ['GranteeName', 'OriginalClaimant', 'LandDescription', 'IssueDate',
                          'Liber', 'Folio', 'Microfilm', 'URL', 'Accessed', 'RefNumber'],
    },
}
```

(Note: `20004`/`20005`'s `date_range` is populated here rather than left empty — that's
Task 10's fix, folded in here since it's the same dict edit. `10009`'s `master_fields`
also drops `Publisher`/`PublishLocation` here per the reconciliation above.)

- [ ] **Step 4: Edit the five `<Name>` elements in `Metis Scrip.rmst`**

In `Archivist/Source Templates/Metis Scrip.rmst`, change each of the 5 `<Name>*
Simple Citations: ...</Name>` elements to `<Name>!Simple Citations: ...</Name>`
(swap only the leading character, e.g.
`<Name>* Simple Citations: Métis Scrip (Manitoba, 1870–1876)</Name>` becomes
`<Name>!Simple Citations: Métis Scrip (Manitoba, 1870–1876)</Name>`). Use
`grep -n "<Name>\* Simple" "Archivist/Source Templates/Metis Scrip.rmst"` to find all 5.

- [ ] **Step 5: Edit the `<Name>` element in each of the other four `.rmst` files**

Same swap (`*` → `!`, nothing else changes) in:
- `Archivist/Source Templates/Simplified Citations - Census.rmst`
- `Archivist/Source Templates/Simplified Citations - Non-traditional.rmst`
- `Archivist/Source Templates/Simplified Citations - Traditional.rmst`
- `Archivist/Source Templates/Simplified Citations - Master Template.rmst`

(The Master Template file's name has trailing whitespace —
`<Name>* Simplified Citations Master Template   </Name>` — preserve the trailing
spaces, only swap the leading `*` for `!`.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd Archivist && python -m pytest tests/test_archivist.py -k "bang or findagrave_entry_removed or master_fields_match_rmst or detail_fields_include_personal_id or master_fields_include_title" -v`
Expected: PASS

- [ ] **Step 7: Run full test suite**

Run: `cd Archivist && python -m pytest tests/ -v`
Expected: any failures should now only be golden-file diffs (fixed in Task 9).

- [ ] **Step 8: Commit**

```bash
git add Archivist/Scrip.py "Archivist/Source Templates/"*.rmst Archivist/tests/test_archivist.py
git commit -m "fix(archivist): ! name prefix on all templates, reconcile field lists with .rmst, drop dead FindAGrave entry"
```

---

### Task 8: Scrip template-selection bug — `document_type` field path

**Files:**
- Modify: `Archivist/Scrip.py:190-195` (`resolve_scrip_template_id`)
- Test: `Archivist/tests/test_archivist.py`

**Interfaces:**
- Produces: `resolve_scrip_template_id(rec: dict) -> Optional[int]` now also checks
  `rec['source_documents'][*]['document_type']`, in addition to
  `rec['type_specific_fields']['document_type']`.

Confirmed via `grep -n "'document_type'" Voyageur/LAC.py` and
`Paleographer/ScripTools.py` that real Scrip records carry `document_type` under
`source_documents[].document_type`, not `type_specific_fields.document_type` — so the
"certificate"/"receipt" shortcut in `select_scrip_template_id` never fires today.

- [ ] **Step 1: Write the failing test**

Add to `Archivist/tests/test_archivist.py`:

```python
def test_resolve_scrip_template_id_checks_source_documents_document_type():
    rec = {
        "type_specific_fields": {},
        "source_documents": [{"document_type": "Scrip Certificate"}],
    }
    assert Scrip.resolve_scrip_template_id(rec) == 20004
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd Archivist && python -m pytest tests/test_archivist.py -k source_documents_document_type -v`
Expected: FAIL — `resolve_scrip_template_id` returns `None` (falls through every check,
including the year fallback, since this fixture has no year either).

- [ ] **Step 3: Fix `resolve_scrip_template_id`**

In `Archivist/Scrip.py`, replace lines 190-195 with:

```python
def resolve_scrip_template_id(rec: dict) -> Optional[int]:
    """Resolves the template ID for a single Scrip record."""
    tf = rec.get('type_specific_fields') or {}
    doc_type = tf.get('document_type')
    if not doc_type:
        for doc in rec.get('source_documents') or []:
            doc_type = doc.get('document_type')
            if doc_type:
                break
    return select_scrip_template_id(
        tf.get('commission_reference'), doc_type, tf.get('rg_series_code'), _scrip_record_year(rec)
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd Archivist && python -m pytest tests/test_archivist.py -k source_documents_document_type -v`
Expected: PASS

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `cd Archivist && python -m pytest tests/ -v`
Expected: no new failures introduced by this change (existing tests that already pass
`document_type` via `type_specific_fields` are unaffected — that path is checked
first, unchanged).

- [ ] **Step 6: Commit**

```bash
git add Archivist/Scrip.py Archivist/tests/test_archivist.py
git commit -m "fix(archivist): resolve_scrip_template_id checks source_documents document_type too"
```

---

### Task 9: Regenerate golden files and verify full suite

**Files:**
- Modify: `Archivist/tests/golden/*.ged` (regenerated, only where diffs are the
  intentional structural change from Tasks 1-8)
- No new tests — this task is verification-only.

- [ ] **Step 1: Run the full test suite and record failures**

Run: `cd Archivist && python -m pytest tests/ -v 2>&1 | tail -60`

Expected failures at this point are golden-file mismatches
(`test_parish_rm_matches_golden`, `test_scrip_rm_matches_golden` if it exists, etc.) —
every failure diff should be explainable entirely by Tasks 1-8's changes (tag
vocabulary, `_TMPLT` wrapper placement, `!` prefix). If any failure's diff includes
something NOT explained by this plan, STOP and investigate before regenerating — do
not paper over an unrelated regression.

- [ ] **Step 2: Regenerate golden files**

Run: `cd Archivist && python tests/golden/capture_golden_gedcom.py`

- [ ] **Step 3: Review the full diff before committing**

Run: `git diff Archivist/tests/golden/`

Confirm every changed line traces back to: `_SRCTEMPLATE`→`_STMPLT`+`NAME`,
`FOOT`→`FOOTNOTE`, `BIBL`→`BIBLIO`, `DISP`→`DISPLAY`, `DETL`→`ISDETAIL`,
`LHNT`→`LONGHINT`, `TYPE` value upper-casing, bare `FIELD`→`_TMPLT`-wrapped `FIELD`
(one level deeper), or `*`→`!` in a template name. If the golden Scrip fixture in
`capture_golden_gedcom.py` never resolves a template ID (per the existing known gap —
check whether `SCRIP_FIXTURE`'s `type_specific_fields`/`source_documents` now
resolves one after Task 8's fix; if it still doesn't, the `scrip_rm.ged`/`scrip_ftm.ged`
golden files won't show any `_TMPLT`-related diff at all, which is expected and NOT a
sign anything is broken).

- [ ] **Step 4: Run full suite again to confirm green**

Run: `cd Archivist && python -m pytest tests/ -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add Archivist/tests/golden/
git commit -m "test(archivist): regenerate golden GEDCOM files for _STMPLT/_TMPLT structure fix"
```

---

### Task 10: Hand-trace Footnote verification

**Files:** none modified — this is a verification-only task, results recorded in the
task's own commit message (no code changes to commit alongside it; skip the commit
step if nothing changed).

Manually evaluate RM's template mini-language against representative real field values
for at least the Manitoba Scrip template (`20001`), to confirm the resulting citation
sentence reads correctly once RM can actually see it (which it couldn't before this
plan, due to Tasks 1-2's tag-vocabulary bug).

- [ ] **Step 1: Decode the Manitoba Scrip Footnote template**

From `Archivist/Source Templates/Metis Scrip.rmst`, the `Footnote` for TID `20001`
(HTML-entity-decoded, `&lt;`→`<`, `&gt;`→`>`):

```
<[PrimaryCreator]<,  [Department]>>< ([Date])>. <?[SourceDescription]|[SourceDescription].|><?[Collection]| [Collection].> ||< [ClaimantName]>>< , affidavit no. [AffidavitNumber]>< , [Parish]>< , [ScripType] scrip>< ; vol. [Volume]>< , microfilm [Microfilm]>< . [Repository:Caps]>< ?[Repository]|< ([URL]>< ? [URL]|< : accessed [Accessed]>>< ?[URL]|)>.>>< [RefNumber:Caps].>
```

RM template syntax: `<...>` is an optional clause that renders (including its own
literal punctuation) only if every `[Field]` placeholder directly inside it is
non-empty; `<?[Field]|A>` renders `A` only if `Field` is non-empty, otherwise nothing;
`[Field:Caps]` upper-cases the value, `[Field:Surname]` extracts a surname-only form.

- [ ] **Step 2: Trace it against a realistic record**

Sample values (matching `_scrip_template_field_value`'s real computation): master
fields `PrimaryCreator` = "Department of the Interior", `Department` = "Manitoba Scrip
Commission", `Date` = "1870–1876", `SourceDescription` = "Manitoba Métis Scrip
Applications", `Collection` = "Department of the Interior fonds, RG 15, Series
D-II-8-a"; detail fields for claimant Roger Letendre: `ClaimantName` = "Roger
Letendre", `AffidavitNumber` = "5473", `Parish` = "" (empty — no residence/birthplace
on this record), `ScripType` = "Half-breed Head", `Volume` = "1320", `Microfilm` = ""
(empty), `Repository` = "Library and Archives Canada, Ottawa, Ontario", `URL` =
"https://recherche-collection-search.bac-lac.gc.ca/eng/Home/Record?app=fonandcol&IdNumber=1502188",
`Accessed` = "" (empty), `RefNumber` = "Item ID 1502188".

Trace, clause by clause:
- `<[PrimaryCreator]<,  [Department]>>` → "Department of the Interior,  Manitoba Scrip Commission"
- `< ([Date])>` → " (1870–1876)"
- `. ` → ". "
- `<?[SourceDescription]|[SourceDescription].|>` → "Manitoba Métis Scrip Applications."
- `<?[Collection]| [Collection].>` → " Department of the Interior fonds, RG 15, Series D-II-8-a."
- `< [ClaimantName]>` → " Roger Letendre"
- `< , affidavit no. [AffidavitNumber]>` → ", affidavit no. 5473"
- `< , [Parish]>` → omitted (`Parish` empty)
- `< , [ScripType] scrip>` → ", Half-breed Head scrip"
- `< ; vol. [Volume]>` → "; vol. 1320"
- `< , microfilm [Microfilm]>` → omitted (`Microfilm` empty)
- `< . [Repository:Caps]>` → ". LIBRARY AND ARCHIVES CANADA, OTTAWA, ONTARIO"
- `<?[Repository]|< ([URL]>< ? [URL]|< : accessed [Accessed]>>< ?[URL]|)>.>` →
  `Repository` present → inner renders: `URL` present → " (https://...IdNumber=1502188" then
  `<? [URL]|...>` (URL present, so the "no URL" branch is skipped and the accessed-clause
  evaluates) → `<: accessed [Accessed]>` omitted (`Accessed` empty) → then `)` and `.` →
  " (https://recherche-collection-search.bac-lac.gc.ca/eng/Home/Record?app=fonandcol&IdNumber=1502188)."
- `< [RefNumber:Caps].>` → " ITEM ID 1502188."

Assembled (the `||` token is a visual separator in RM's own renderer between the
master-field portion and the detail-field portion — it does not add literal
characters):

> Department of the Interior,  Manitoba Scrip Commission (1870–1876). Manitoba Métis
> Scrip Applications. Department of the Interior fonds, RG 15, Series D-II-8-a. Roger
> Letendre, affidavit no. 5473, Half-breed Head scrip; vol. 1320. LIBRARY AND ARCHIVES
> CANADA, OTTAWA, ONTARIO (https://recherche-collection-search.bac-lac.gc.ca/eng/Home/Record?app=fonandcol&IdNumber=1502188). ITEM ID 1502188.

This reads as a correct, grammatical citation with no dangling punctuation from the
omitted `Parish`/`Microfilm`/`Accessed` fields — each optional clause cleanly dropped
its own leading punctuation along with the empty field. Record this trace (or an
updated one if any assumption above turns out wrong once checked against a real RM
render) as confirmation; if it does NOT read correctly, that's a bug in the `.rmst`
Footnote text itself — file a follow-up, since fixing citation *wording* is out of
this plan's scope (which fixes *wiring*, not content).

- [ ] **Step 3: Spot-check one more template**

Repeat a lighter version of Step 2 for TID `20005` (Land Records: Dominion Land Grant
Patent) or `10008` (Census) using an existing test fixture's field values (e.g. the
`PARISH_FIXTURE`/`SCRIP_FIXTURE` in `Archivist/tests/golden/capture_golden_gedcom.py`
or the household-ID test fixtures in `test_census_ingestion.py`) — confirm no
dangling punctuation or double periods.

- [ ] **Step 4: No commit needed**

This task produces no file changes — its output is the verification record above (and
any follow-up bug filed if a trace revealed a real content problem, which is separate
from this plan).

---

### Task 11: Regenerate and inspect real output

**Files:** none modified in the repo — this exercises the real pipeline against
whatever real gathered JSON is available, writing to the user's configured
`GEDCOM_OUTPUT_PATH` (outside the repo).

- [ ] **Step 1: Identify a real JSON source to regenerate from**

Check `.env`'s `JSON_DIR` for a previously-gathered census or Scrip JSON matching the
real output file referenced during diagnosis
(`Census-1950-USA-North Dakota-Pembina-Advance-34-1-FS.json` or similar). If none is
available, use `Archivist/tests/golden/capture_golden_gedcom.py`'s fixtures instead —
regenerate `parish_rm.ged`/`scrip_rm.ged` (already done in Task 9) and inspect those.

- [ ] **Step 2: Run the real pipeline (if real JSON is available)**

Run: `cd Archivist && python Archivist.py` (or the appropriate entrypoint/flags for
regenerating from an existing JSON — check `Archivist/Archivist.py`'s CLI args if
unsure) targeting the same collection used for the original diagnostic file.

- [ ] **Step 3: Inspect the regenerated `.ged` for the corrected structure**

Search the output for a citation block and confirm:
- `2 SOUR @S<id>@` is immediately followed by `3 _TMPLT` then `4 FIELD`/`5 NAME`/`5 VALUE` pairs, then `3 _TITL`/`3 PAGE`.
- No `3 _TMPLT`/`4 TID` (citation level should have no TID).
- The master `0 @S<id>@ SOUR` record still has `1 _TMPLT`/`2 TID <id>`/`2 FIELD`/`3 NAME`/`3 VALUE`.
- Near the end of the file, `0 _STMPLT` blocks exist (not `0 _SRCTEMPLATE`), each with
  `1 NAME !...`, `1 FOOTNOTE`, `1 BIBLIO`, and field-level `2 DISPLAY`/`2 ISDETAIL`/`2 LONGHINT`.

- [ ] **Step 4: Report to the user**

This step is on the user, not the implementer — actual RootsMagic import verification
requires a real RM instance, which isn't available in this environment. Report the
regenerated file's path and the structural spot-check results from Step 3, and ask
the user to re-import it into RootsMagic to confirm the templates are now recognized
before considering this plan fully done.

---

## Self-Review Notes

- **Spec coverage:** Section 1 (tag vocabulary) → Tasks 1-2. Section 2 (citation
  `_TMPLT`) → Tasks 3-6. Section 3 (naming, `.rmst` authoritative) → Task 7. Section 4
  (Census/Parish/Traditional/Master field-list reconciliation) → Task 7. Section 5
  (selection bugs) → Tasks 7 (date_range, folded into the dict rewrite) and 8
  (document_type path). Section 6 (verification) → Tasks 9-11.
- **Placeholder scan:** no TBD/TODO; every code step has real, complete code; Task 11's
  Step 2 command is conditional on real JSON availability with a documented fallback.
- **Type consistency:** `_gedcom_wrapped_lines` signature identical across Tasks 1 and
  2 (both files get the same helper, independently, matching the codebase's existing
  duplication pattern for self-contained entrypoints). All `_TMPLT`-wrapping call sites
  (Tasks 3-6) produce the same `3 _TMPLT`/`4 FIELD`/`5 NAME`/`5 VALUE` shape.
