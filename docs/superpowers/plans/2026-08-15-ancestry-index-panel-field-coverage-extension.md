# Ancestry Index-Panel-Data Field Coverage Extension Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **This plan is written for a cheaper model (Gemini Flash) to execute with minimal prior context on this codebase.** Every task below is self-contained: exact file paths, exact code, exact real test data (captured live against all 12 US federal and all 10 Canadian census years this session — nothing here is invented).

**Prerequisite — read before starting:** This plan extends `docs/superpowers/plans/2026-08-15-ancestry-index-panel-extraction.md` (the original Ancestry index-panel-data plan, covering 1850/1860/1880/1920 only). **That plan's Tasks 1-4 must be executed FIRST**, in the same order, before starting this one — this plan's diffs are written against the file state that plan produces (the `ANCESTRY_INDEX_FIELD_TO_COLUMN` constant with its Task-1 entries, and `field_maps/ancestry_census.yaml` with its Task-4 additions: `"Marital Status"`, `"Birth Month"`, `"Months Not Employed"`, `"Home Ownership"`, `"Home Mortgaged"`, `"Native Tongue"`, `"Speaks English"`, `"Employment Field"`). If those Tasks have not yet run, run them first, then return here.

**Goal:** Extend the `ANCESTRY_INDEX_FIELD_TO_COLUMN` map (and, for two genuinely new but well-supported concepts, `field_maps/ancestry_census.yaml`) so that the real `fieldName` vocabulary confirmed live across all 22 researched census years (not just the original 4) resolves to the SAME existing, already-mapped targets wherever the underlying concept is already understood — instead of falling through to a raw label/fieldName and tripping the "unmapped column" review flag for a concept that isn't actually new.

**Explicitly NOT in scope for this plan — deliberately deferred, left unmapped/passthrough:** any concept that isn't already a target in the current `ancestry_census.yaml` and doesn't have a clean, unambiguous match in `Commissioner/FactTypes.json`. This includes: income/earnings (any form), radio ownership, class-of-worker, employer name, "usual" (as opposed to current) occupation/industry, 5-years-ago residence (1940's famous question — a genuinely new *structured* concept, not a simple alias), tribe/clan/Indian-blood/reservation-schedule fields (1900/1910/1930/1950/1891), homestead land-survey grid fields (1906/1921 Canada), livestock/agricultural-schedule fields (1861/1851 Canada), insurance costs (1911 Canada), class-of-house/construction-material/room-count (1921/1861/1851 Canada), marriage-age/current-marriage-number, weeks/hours worked, and every numbered-duplicate field pattern seen in 1851/1861/1911 Ancestry Canadian data (`Widowed`/`Widowed1`, `CannotRead`/`CannotRead1`, etc. — genuinely unclear whether these are the same question asked twice or two different sub-questions; do not guess). **These all remain visible in output via the existing passthrough behavior** (`ANCESTRY_INDEX_FIELD_TO_COLUMN[f.fieldName] || fieldLabelsByName[f.fieldName] || f.fieldName`, already built in the original plan's Task 1) and will surface as "unmapped" for the user's own joint mapping-review session — this plan must not silently invent GEDCOM targets for them.

**Architecture:** No new interfaces, no new files beyond one extended test file. Two changes only: (1) more entries in the existing `ANCESTRY_INDEX_FIELD_TO_COLUMN` object literal in `Voyageur.js`; (2) two new `participant_facts` entries in `field_maps/ancestry_census.yaml` (`"Religion"` and `"Nationality"`, both real, pre-existing fact types in `Commissioner/FactTypes.json` — confirmed present, not invented) to support the many Canadian years that carry these fields.

**Tech Stack:** JavaScript (Tampermonkey userscript, `Voyageur/Voyageur.js`), YAML (`Voyageur/field_maps/ancestry_census.yaml`), Node's built-in test runner (`node:test`), pytest.

**Spec:** `docs/superpowers/specs/2026-08-15-census-field-coverage-research.md` — the full real `fieldName` vocabulary per year/source this plan draws from. Also read `docs/superpowers/specs/2026-08-15-ancestry-index-panel-extraction-design.md` for the original architecture reasoning.

## Global Constraints

- **Alias-only. No new GEDCOM targets except Religion/Nationality.** Every entry this plan adds to `ANCESTRY_INDEX_FIELD_TO_COLUMN` must point at a column-header string that is ALREADY a key somewhere in `field_maps/ancestry_census.yaml` (after the original plan's Task 4 has run) — verify this for every single entry before adding it. The only two exceptions are `"Religion"` and `"Nationality"`, which this plan itself adds as new `participant_facts` targets (Task 2).
- **Never touch the `else` branch or the DOM-table loop.** This plan only edits the `ANCESTRY_INDEX_FIELD_TO_COLUMN` constant and the YAML file — no changes to `extractCurrentPageData()`'s control flow, the interceptor, or `census_schema.py`.
- **`node --check Voyageur/Voyageur.js`** must pass after every JS change, before every commit.
- **`node --test Voyageur/tests/js/`** (from the `Voyageur/` directory) must show only passing tests after every JS test change.
- **`pytest`** (from the `Voyageur/` and `Archivist/` directories respectively) must show only passing tests after every Python change.

---

### Task 1: Extend `ANCESTRY_INDEX_FIELD_TO_COLUMN` with real cross-year aliases (US years)

**Files:**
- Modify: `Voyageur/Voyageur.js`
- Modify: `Voyageur/tests/js/test_ancestry_index_panel_parser.mjs`

**Interfaces:**
- Consumes: `ANCESTRY_INDEX_FIELD_TO_COLUMN` as left by the original plan's Task 1 (must already contain the ~42 entries listed in that plan — verify by opening the file and confirming `SelfMaritalStatus: 'Marital Status',` is present before starting).
- Produces: nothing new for other tasks — this is a data-only extension.

- [ ] **Step 1: Locate the constant**

Open `Voyageur/Voyageur.js`. Find `const ANCESTRY_INDEX_FIELD_TO_COLUMN = {` (search by that exact text). Find its closing `};`.

- [ ] **Step 2: Add these new entries immediately before the closing `};`**

Every target string on the right below is a column header that ALREADY exists as a key in `field_maps/ancestry_census.yaml` after the original plan's Task 4 (verify each one is present in that file before adding — if any target string below is NOT found in the current YAML, STOP and report it rather than adding the entry, since that would violate this plan's alias-only constraint):

```js
    // --- Extension: aliases confirmed live across the full 22-year US+Canadian
    // research pass (docs/superpowers/specs/2026-08-15-census-field-coverage-research.md).
    // Every target below already exists in field_maps/ancestry_census.yaml (as left by
    // the original plan's Task 4) - these are ONLY new fieldName spellings for concepts
    // this project already understands, never new GEDCOM targets.
    SelfOccupation: 'Occupation', // 1870/1871/1930's no-"Residence"-infix naming variant
    SelfIndustry: 'Industry', // 1930's naming variant of SelfResidenceIndustry
    SelfResidenceFatherForeignBirth: 'Father Foreign Born', // 1870 - boolean flag, not a place
    SelfResidenceMotherForeignBirth: 'Mother Foreign Born', // 1870
    SelfResidenceMaleCitizenOverTwentyone: 'Male Citizen Over 21', // 1870
    SelfResidenceDeniedVotingRights: 'Voting Rights Denied', // 1870
    SelfResidenceCanReadWrite: 'Cannot Read, Write', // 1930's single combined Can-Read-Write field
    SelfResidenceVeteran: 'Veteran Status', // 1900/1910/1920/1930/1940
    SelfResidenceWar: 'Which War', // 1930 - which war served in
    SelfResidenceMilitaryService: 'Military Service', // 1940
    SelfResidenceValueOfHome: 'Real Estate Value', // 1930/1940 - value-of-home aliased onto the existing Real Estate Value / Property fact
    SelfResidenceNativeLanguageCode: 'Native Tongue', // 1910's coded variant of SelfResidenceLanguageSpoken
    SelfResidenceMaritalStatus: 'Marital Status', // 1890's "Residence"-infixed naming variant of SelfMaritalStatus
    SelfResidence1HomeMortgaged: 'Home Mortgaged', // 1890's numbered-variant naming of SelfResidenceHomeMortgaged (this ONE numbered variant is a confirmed like-for-like alias, unlike the ambiguous numbered-duplicate PAIRS noted in this plan's scope-exclusion list - it's the only field of its kind in the 1890 collection, no sibling "HomeMortgaged" to be confused with)
    SelfResidenceGradeCompleted: 'Highest Grade Completed', // 1890
    SelfResidenceMonthsAtSchool: 'Attended School', // 1890/1901 - numeric months-attended aliased onto the existing boolean/text Attended School fact
```

- [ ] **Step 3: Run `node --check` to verify no syntax errors**

Run: `node --check Voyageur/Voyageur.js` (from repo root)
Expected: no output, exit code 0.

- [ ] **Step 4: Add tests proving the new aliases resolve correctly**

Open `Voyageur/tests/js/test_ancestry_index_panel_parser.mjs`. Add these tests at the end of the file (after the last existing `test(...)` block, still inside the same file, no new imports needed):

```js
test('ancestryColumnsFromIndexPanelRecord: 1870 real vitals-plus-voting-rights fields map onto existing targets', () => {
    // Real fieldName vocabulary confirmed live for 1870 (dbId 7163, imageId 4263342_00170).
    const record = {
        pid: 1, householdId: '1', fullName: 'Test Person',
        recordFields: [
            {fieldName: 'SelfOccupation', value: 'Farmer', correctedValue: null},
            {fieldName: 'SelfResidenceFatherForeignBirth', value: 'Y', correctedValue: null},
            {fieldName: 'SelfResidenceMotherForeignBirth', value: 'Y', correctedValue: null},
            {fieldName: 'SelfResidenceMaleCitizenOverTwentyone', value: 'Y', correctedValue: null},
            {fieldName: 'SelfResidenceDeniedVotingRights', value: 'N', correctedValue: null},
        ],
        citation: null, isUserCreated: false,
    };

    const columns = ancestryColumnsFromIndexPanelRecord(record, {});

    assert.equal(columns['Occupation'], 'Farmer');
    assert.equal(columns['Father Foreign Born'], 'Y');
    assert.equal(columns['Mother Foreign Born'], 'Y');
    assert.equal(columns['Male Citizen Over 21'], 'Y');
    assert.equal(columns['Voting Rights Denied'], 'N');
});

test('ancestryColumnsFromIndexPanelRecord: 1930 combined Can-Read-Write and value-of-home fields map onto existing targets', () => {
    // Real fieldName vocabulary confirmed live for 1930 (dbId 6224, imageId 4547413_00007).
    const record = {
        pid: 1, householdId: '1', fullName: 'Test Person',
        recordFields: [
            {fieldName: 'SelfResidenceCanReadWrite', value: 'Yes', correctedValue: null},
            {fieldName: 'SelfResidenceValueOfHome', value: '2500', correctedValue: null},
            {fieldName: 'SelfResidenceWar', value: 'WW', correctedValue: null},
            {fieldName: 'SelfIndustry', value: 'Retail', correctedValue: null},
        ],
        citation: null, isUserCreated: false,
    };

    const columns = ancestryColumnsFromIndexPanelRecord(record, {});

    assert.equal(columns['Cannot Read, Write'], 'Yes');
    assert.equal(columns['Real Estate Value'], '2500');
    assert.equal(columns['Which War'], 'WW');
    assert.equal(columns['Industry'], 'Retail');
});

test('ancestryColumnsFromIndexPanelRecord: 1890 fragment fields (numbered HomeMortgaged variant, grade, months-at-school) map onto existing targets', () => {
    // Real fieldName vocabulary confirmed live for 1890 Fragment (dbId 5445, imageId 4376858-00418).
    const record = {
        pid: 1, householdId: '1', fullName: 'Test Person',
        recordFields: [
            {fieldName: 'SelfResidenceMaritalStatus', value: 'Married', correctedValue: null},
            {fieldName: 'SelfResidence1HomeMortgaged', value: 'Y', correctedValue: null},
            {fieldName: 'SelfResidenceGradeCompleted', value: '6', correctedValue: null},
            {fieldName: 'SelfResidenceMonthsAtSchool', value: '4', correctedValue: null},
            {fieldName: 'SelfResidenceVeteran', value: 'Y', correctedValue: null},
            {fieldName: 'SelfResidenceMilitaryService', value: 'Union Army', correctedValue: null},
            {fieldName: 'SelfResidenceNativeLanguageCode', value: 'GER', correctedValue: null},
        ],
        citation: null, isUserCreated: false,
    };

    const columns = ancestryColumnsFromIndexPanelRecord(record, {});

    assert.equal(columns['Marital Status'], 'Married');
    assert.equal(columns['Home Mortgaged'], 'Y');
    assert.equal(columns['Highest Grade Completed'], '6');
    assert.equal(columns['Attended School'], '4');
    assert.equal(columns['Veteran Status'], 'Y');
    assert.equal(columns['Military Service'], 'Union Army');
    assert.equal(columns['Native Tongue'], 'GER');
});
```

- [ ] **Step 5: Run the new tests to verify they pass**

Run: `node --test Voyageur/tests/js/test_ancestry_index_panel_parser.mjs` (from repo root)
Expected: all tests PASS (9 pre-existing + 3 new = 9 total from the original plan's file plus these 3, i.e. the file's total test count grows by exactly 3).

- [ ] **Step 6: Run the full existing JS suite to confirm no regressions**

Run: `node --test Voyageur/tests/js/` (from repo root)
Expected: all pre-existing tests still pass, plus the 3 new ones.

- [ ] **Step 7: Commit**

```bash
git add Voyageur/Voyageur.js Voyageur/tests/js/test_ancestry_index_panel_parser.mjs
git commit -m "feat(voyageur): alias 1870/1890/1930/1940 Ancestry index-panel fieldNames onto existing targets"
```

---

### Task 2: Add Religion/Nationality support (Canadian years) + their field aliases

**Files:**
- Modify: `Voyageur/field_maps/ancestry_census.yaml`
- Modify: `Voyageur/Voyageur.js`
- Modify: `Voyageur/tests/js/test_ancestry_index_panel_parser.mjs`
- Test: `Voyageur/tests/test_census_schema.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: nothing further downstream in this plan.

- [ ] **Step 1: Confirm `Religion` and `Nationality` are real fact types**

Run: `python -c "import json; d=json.load(open('Commissioner/FactTypes.json', encoding='utf-8')); print('Religion' in d['person'], 'Nationality' in d['person'])"` (from repo root)
Expected: `True True`. If either is `False`, STOP — do not proceed with this task, report the discrepancy instead (this plan was written against a live check of this exact file; a `False` result means something changed and the rest of this task's assumptions may not hold).

- [ ] **Step 2: Add the two new `participant_facts` entries to `ancestry_census.yaml`**

Open `Voyageur/field_maps/ancestry_census.yaml`. Find this exact line under `participant_facts:` (it's the last line of that block, right before the blank line and `record_fields:`):

```yaml
  "Voting Rights Denied": Miscellaneous
```

Replace it with (adds two new lines immediately after, keeps the existing line unchanged):

```yaml
  "Voting Rights Denied": Miscellaneous
  "Religion": Religion
  "Nationality": Nationality
```

- [ ] **Step 3: Add the corresponding fieldName aliases to `ANCESTRY_INDEX_FIELD_TO_COLUMN`**

In `Voyageur/Voyageur.js`, inside `ANCESTRY_INDEX_FIELD_TO_COLUMN` (same constant Task 1 extended), add these entries immediately before the closing `};` (after Task 1's additions):

```js
    // Religion/Nationality - confirmed real, pre-existing FactTypes.json fact types
    // (Commissioner/FactTypes.json), not invented for this plan. Present across most
    // Canadian census years (1861 onward) and absent from every US year checked.
    SelfReligion: 'Religion', // 1871/1881 naming variant (no "Residence" infix)
    SelfResidenceReligion: 'Religion', // 1861/1901/1861-per-province/1891 naming variant
    SelfNationality: 'Nationality', // 1871/1881/1901/1921
    SelfResidenceNationality: 'Nationality', // alternate naming variant, not yet observed but kept consistent with the SelfX/SelfResidenceX pairing pattern seen for every other duplicated field name across years - if this specific spelling is never actually emitted by any real collection, it is a harmless unused entry, not a risk
```

- [ ] **Step 4: Run `node --check` to verify no syntax errors**

Run: `node --check Voyageur/Voyageur.js`
Expected: no output, exit code 0.

- [ ] **Step 5: Add JS tests for the Religion/Nationality aliases**

Append to `Voyageur/tests/js/test_ancestry_index_panel_parser.mjs`:

```js
test('ancestryColumnsFromIndexPanelRecord: Canadian Religion/Nationality fieldName variants both map to their new targets', () => {
    // Real fieldName vocabulary confirmed live for 1871 Canada (dbId 1578, SelfReligion/
    // SelfNationality, no "Residence" infix) and 1861 Canada (dbId 1570,
    // SelfResidenceReligion, "Residence"-infixed).
    const record1871 = {
        pid: 1, householdId: '1', fullName: 'Donald MacDonald',
        recordFields: [
            {fieldName: 'SelfReligion', value: 'C Of Scotland', correctedValue: null},
            {fieldName: 'SelfNationality', value: 'Scotch', correctedValue: null},
        ],
        citation: null, isUserCreated: false,
    };
    const record1861 = {
        pid: 2, householdId: '2', fullName: 'Agnes MacDonald',
        recordFields: [
            {fieldName: 'SelfResidenceReligion', value: 'Presbyterian', correctedValue: null},
        ],
        citation: null, isUserCreated: false,
    };

    const columns1871 = ancestryColumnsFromIndexPanelRecord(record1871, {});
    const columns1861 = ancestryColumnsFromIndexPanelRecord(record1861, {});

    assert.equal(columns1871['Religion'], 'C Of Scotland');
    assert.equal(columns1871['Nationality'], 'Scotch');
    assert.equal(columns1861['Religion'], 'Presbyterian');
});
```

- [ ] **Step 6: Run the new test to verify it passes**

Run: `node --test Voyageur/tests/js/test_ancestry_index_panel_parser.mjs`
Expected: all tests PASS, including the new one.

- [ ] **Step 7: Write a Python test proving Religion/Nationality land in `participants[].facts`, not flagged as unmapped**

Open `Voyageur/tests/test_census_schema.py`. Find `def test_ancestry_birth_month_and_marital_status_are_mapped_not_unmapped():` (this test comes from the original plan's Task 4, Step 7 — it must already exist; if it doesn't, the original plan's Task 4 has not been run and you should stop and run it first). Insert this new test immediately after its closing (before the next `def`):

```python
def test_ancestry_religion_and_nationality_are_mapped_facts_not_unmapped():
    """Regression for this plan's Task 2 - Religion and Nationality are real,
    pre-existing FactTypes.json fact types (confirmed via Task 2 Step 1's live check),
    common on Canadian census years and previously absent from ancestry_census.yaml
    entirely. Confirms both land as facts, not flagged for manual review."""
    raw = {
        "census_year": "1871", "location": "Nova Scotia, Canada",
        "pages": [_page([
            {"columns": {"Given Name": "Donald", "Surname": "MacDonald", "Gender": "M",
                        "Age": "75", "Religion": "C Of Scotland", "Nationality": "Scotch"},
             "pid": "p1"},
        ])],
    }
    doc = census_schema.normalize_census_pages(raw, "ancestry_census", "1871 Canada Census", "Census_1871")

    participant = doc["sheets"][0]["records"][0]["participants"][0]
    fact_types = {f["fact_type"] for f in participant["facts"]}
    assert "Religion" in fact_types
    assert "Nationality" in fact_types
    assert not participant["review"], participant.get("review_reason")
```

- [ ] **Step 8: Run the new test to verify it passes**

Run: `cd Voyageur && python -m pytest tests/test_census_schema.py -k "religion_and_nationality" -v`
Expected: PASS.

- [ ] **Step 9: Run the full Voyageur and Archivist Python test suites**

Run: `cd Voyageur && python -m pytest tests/ -v`
Expected: all tests pass.

Run: `cd Archivist && python -m pytest tests/ -v`
Expected: all tests pass (this task doesn't touch Archivist, this is a pure regression check).

- [ ] **Step 10: Commit**

```bash
git add Voyageur/field_maps/ancestry_census.yaml Voyageur/Voyageur.js Voyageur/tests/js/test_ancestry_index_panel_parser.mjs Voyageur/tests/test_census_schema.py
git commit -m "feat(voyageur): map Religion/Nationality to real FactTypes.json facts for Canadian census years"
```

---

### Task 3: Live verification on a real Canadian record (NOT subagent-delegable)

**Files:** none - this task runs the already-built code, no new code.

**Interfaces:** N/A.

**Why this task exists separately from the original plan's Task 5:** that task only verified against US `dbId`s (1850/1860/1880/1920) — no Canadian collection has ever been live-verified end-to-end through this code path. Canada is where this plan's only new GEDCOM targets (Religion/Nationality) actually get exercised.

- [ ] **Step 1: Run a real gather against a confirmed-live Canadian record**

Using the same isolated-output-directory technique already established this session, run `python Voyageur/A.py` against the 1871 Canada test record confirmed live this session: `dbId=1578`, `imageId=4396761_00576` (Donald MacDonald / Pictou, Nova Scotia — from `docs/superpowers/specs/2026-08-15-census-field-coverage-research.md`'s Canadian research table).

- [ ] **Step 2: Confirm Religion/Nationality actually appear in the output**

Inspect the resulting JSON output's per-person `facts` array (or `type_specific_fields`, depending on where `normalize_census_pages` places them) for `Religion` and `Nationality` entries with real values ("C Of Scotland" / "Scotch" for this specific test record, or whatever real values this collection's actual current data shows — Ancestry collections are occasionally re-indexed, so an exact-value mismatch against this plan's numbers is not itself a failure, only a genuinely EMPTY or MISSING field is).

- [ ] **Step 3: Confirm no new "unmapped column" review flags appeared for Religion/Nationality specifically**

Check the output for any `review`/`review_reason` flag mentioning "Religion" or "Nationality" as an unmapped column. Their presence would mean Task 2 didn't take effect — re-check the YAML and JS constant changes actually saved and the running code picked them up (a stale Tampermonkey cache is the most likely cause; force-reload the userscript).

- [ ] **Step 4: Generate the GEDCOM and spot-check**

Run `Archivist.py` against the isolated JSON output (same isolated-output-directory technique). Confirm the resulting `.ged` file has `2 RELI` (or whatever tag `Religion` maps to in this project's fact-to-GEDCOM-tag table — check `Archivist/Census.py` or the shared fact-mapping code if unsure of the exact tag) and a nationality-bearing note/fact line for Donald MacDonald.

- [ ] **Step 5: Report results**

Document what was confirmed: real Religion/Nationality values seen in JSON and GEDCOM output, no spurious review flags. If anything didn't work as expected, that's a genuine finding worth reporting honestly — do not claim success without having actually observed the real output.

---

## Self-Review Notes (for whoever executes this plan)

- **Spec coverage:** Task 1 covers the safe cross-year field aliases identified from the full research pass (US years). Task 2 covers the two new Canadian-specific fact types this session confirmed are real and pre-existing. Task 3 covers live verification specifically on Canadian data, which no prior plan touched.
- **Deliberately NOT covered by this plan** (see the top-level scope-exclusion list): income/earnings, radio ownership, class-of-worker, employer name, usual-occupation, 1940's 5-years-ago-residence structure, tribe/clan/reservation-schedule fields, homestead land-survey grid fields, livestock/agricultural-schedule fields, insurance costs, home construction/room-count details, marriage-age, weeks/hours-worked, and the ambiguous numbered-duplicate field pairs (`Widowed`/`Widowed1` etc.) seen in 1851/1861/1911 Ancestry Canadian data. All of these remain visible via the existing passthrough-to-raw-label behavior and are exactly the "unknown fields" the user's own planned joint mapping-review session will go through — this plan must not preempt that session's decisions.
- **1916 Canada and Ancestry's 1881 index-only collection are out of scope for this plan entirely** — 1916 has no Ancestry index-panel-data at all (confirmed, `isIndexPanelVisible: false`), so there is nothing for this JS-side plan to extend for that year; 1881's Ancestry collection is genuinely thin (9 fields, already fully covered by the original plan's generic passthrough) with no new aliasable concepts. Both years are FamilySearch-primary per the research doc — that's a different code path (`Voyageur.js`'s FS orchestration-API extraction, already implemented, self-describing, not year-branched) with no equivalent plan needed.
- **FamilySearch side needs no equivalent plan.** Per the research doc's confirmed finding, FS's orchestration-API parser is self-describing (reads whatever `fieldTypes` the API returns dynamically, no per-year `fieldName`-to-column hardcoding like Ancestry's DOM-table-legacy schema requires) — there is no FS-side equivalent of this plan's Task 1/2 to write.
