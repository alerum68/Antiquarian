# Ancestry Index-Panel-Data Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **This plan is written for a cheaper model (Gemini Flash) to execute with minimal prior context on this codebase.** Every task below is self-contained: exact file paths, exact code, exact real test data (captured live against 4 real Ancestry census years this session — nothing here is invented). Read a task's own text before starting it; do not assume context from other tasks beyond what's stated in its own "Interfaces" block.

**Goal:** Add a second, API-based data source for Ancestry's per-image person-index data (`imageviewer/api/record/index-panel-data`) in `Voyageur.js`, running as a fallback pair alongside the existing DOM-table scraper — never replacing it.

**Architecture:** Extend the existing Ancestry `XMLHttpRequest`/`fetch` interceptor already installed in `Voyageur.js` (currently used only for `extractPidsFromText`) to also capture `index-panel-data` responses. A new pure parser converts the API's `records[].recordFields[]` shape into the exact same `columns`/`pid` row shape the DOM-table scraper already produces, so `census_schema.py` and `field_maps/ancestry_census.yaml` need no changes beyond a handful of new header mappings for genuinely new fields this API exposes. The per-page gather loop tries the API path first (with a bounded wait); if it times out or returns nothing, the existing DOM-table-scraping code runs completely unchanged.

**Tech Stack:** JavaScript (Tampermonkey userscript, `Voyageur/Voyageur.js`), Python (`Voyageur/census_schema.py`), YAML (`Voyageur/field_maps/ancestry_census.yaml`), Node's built-in test runner (`node:test`), pytest.

**Spec:** `docs/superpowers/specs/2026-08-15-ancestry-index-panel-extraction-design.md` — read this first for the full real-data field tables across 1850/1860/1880/1920; this plan's code embeds the values needed per task, but the spec has the full picture and the reasoning behind each mapping decision.

## Global Constraints

- **Fallback pair, not replacement.** The existing DOM-table-scraping code inside `extractCurrentPageData()` (the `for (const row of rows) { ... }` loop, `Voyageur/Voyageur.js`) must end this plan byte-for-byte identical to how it starts — every task that touches this function must wrap new code AROUND that loop, never edit inside it.
- **Extend the existing interceptor, do not add a second one.** `Voyageur.js` already has exactly one Ancestry `XMLHttpRequest.prototype.open`/`fetch` override, guarded by `unsafeWindow.__mgs_intercepted`. Add to that same guarded block.
- **Waiter-map pattern, not `waitForCondition()`.** Use a plain object mapping a key to a resolver callback (see FS's `waitForFsApiResponse`/`__voyageurFsApiWaiters` in this same file for the exact pattern to mirror) — `waitForCondition()` only re-checks on DOM `MutationObserver` events and will never fire for a response stored as a plain object property. This exact mistake was made and reverted once already this session for a different feature; do not repeat it.
- **Bump `Voyageur.js`'s `@version`** (currently `0.3.26`, line 4) by one patch level (`0.3.27`) on the task that first changes its runtime behavior (Task 3), not on tasks that only add new, not-yet-wired-in functions (Tasks 1-2 don't need a version bump; Task 3 does, since that's the first task where gather behavior actually changes).
- **`node --check Voyageur/Voyageur.js`** must pass after every JS change, before every commit.
- **`node --test Voyageur/tests/js/`** (from the `Voyageur/` directory) must show only passing tests after every JS test change.
- **`pytest`** (from the `Voyageur/` and `Archivist/` directories respectively) must show only passing tests after every Python change.
- **No live-network code in Node tests.** Every JS unit test in this plan uses a plain JS object literal as a fixture (the same shape `JSON.parse()` would produce from the real API) — never a live `fetch`.

---

### Task 1: Field map + pure parser functions (`Voyageur.js`)

**Files:**
- Modify: `Voyageur/Voyageur.js` (add new code; do not touch any existing function bodies in this task)
- Test: `Voyageur/tests/js/test_ancestry_index_panel_parser.mjs` (new file)

**Interfaces:**
- Produces: `ANCESTRY_INDEX_FIELD_TO_COLUMN` (object constant), `ancestryColumnsFromIndexPanelRecord(record, fieldLabelsByName)` (function, returns object), `ancestryRowsFromIndexPanelResponse(apiResponse)` (function, returns array of `{columns, pid, household_id, extracted_url, alternate_names, alternate_birth_places}` objects) — all three must be added to `module.exports` at the bottom of `Voyageur.js` (see Step 5).
- Consumes: nothing from other tasks.

- [x] **Step 1: Locate the insertion point**

Open `Voyageur/Voyageur.js`. Find the function `async function extractCurrentPageData(rows) {` (search for that exact text — do not rely on a line number, other tasks in this plan may shift line numbers before you get to this file). Note the line number just ABOVE that function declaration — you will insert the new code from this task immediately before it, so it's defined before it's used.

- [x] **Step 2: Add the field-name-to-column mapping constant**

Insert this constant immediately before `async function extractCurrentPageData(rows) {`:

```js
// Ancestry's imageviewer/api/record/index-panel-data endpoint uses a stable, self-
// describing fieldName vocabulary that does NOT change across census years (only which
// fields are present varies) - confirmed live against real 1850, 1860, 1880, and 1920
// Ancestry census data (Pembina, ND / Minnesota Territory / Dakota Territory), see
// docs/superpowers/specs/2026-08-15-ancestry-index-panel-extraction-design.md for the
// full real field tables this was built from. Maps each known fieldName to the SAME
// column header text the existing DOM-table scraper already produces (e.g. "Given
// Name", "Surname") so field_maps/ancestry_census.yaml needs no changes for any field
// already listed here - this is a drop-in second producer of the exact same `columns`
// shape, not a new schema.
const ANCESTRY_INDEX_FIELD_TO_COLUMN = {
    LineNumber: 'Line Number',
    SourceDwellingNumber: 'Dwelling Number',
    HouseNumber: 'Dwelling Number', // 1920's fieldName for the same concept as SourceDwellingNumber - confirmed the two never co-occur on the same collection/year
    Famnum: 'Family Number',
    SelfGivenName: 'Given Name',
    SelfSurname: 'Surname',
    SelfResidenceAge: 'Age',
    SelfBirthYear: 'Birth Year',
    SelfBirthMonth: 'Birth Month',
    SelfGender: 'Gender',
    SelfRace: 'Race',
    SelfResidenceOccupation: 'Occupation',
    SelfResidenceIndustry: 'Industry',
    SelfResidenceRealEstateValue: 'Real Estate Value',
    SelfResidencePersonalEstateValue: 'Personal Estate Value',
    SelfBirthPlace: 'Birth Place',
    SelfResidenceMarriedWithinYear: 'Married within Year',
    SelfResidenceAttendedSchool: 'Attended School',
    SelfResidenceCannotRead: 'Cannot Read, Write',
    SelfResidenceCannotWrite: 'Cannot Read, Write',
    SelfResidenceCanRead: 'Cannot Read, Write',
    SelfResidenceCanWrite: 'Cannot Read, Write',
    SelfResidenceDisabilityCondition: 'Disability Condition',
    SelfResidenceIsMaimed: 'Disability Condition',
    SelfResidenceIsSick: 'Disability Condition',
    SelfResidenceIsBlind: 'Disability Condition',
    SelfResidenceIsDeafDumb: 'Deaf Dumb Blind Insane',
    SelfResidenceIsInsane: 'Deaf Dumb Blind Insane',
    SelfResidenceIsIdiotic: 'Idiotic Pauper Convict',
    SelfResidenceStreetAddress: 'Street',
    SelfRelationToHead: 'Relationship to Head',
    SelfMaritalStatus: 'Marital Status',
    FatherBirthPlace: 'Father Foreign Born',
    MotherBirthPlace: 'Mother Foreign Born',
    SelfResidenceMonthsUnEmployedPastYear: 'Months Not Employed',
    SelfResidenceHomeOwnership: 'Home Ownership',
    SelfResidenceHomeMortgaged: 'Home Mortgaged',
    SelfArrivalYear: 'Immigration Year',
    SelfResidenceNaturalizationStatus: 'Naturalization Status',
    SelfNaturalizationYear: 'Year of Naturalization',
    SelfResidenceLanguageSpoken: 'Native Tongue',
    SelfResidenceAbleToSpeakEnglish: 'Speaks English',
    SelfResidenceIsEmployed: 'Employment Field',
};
```

- [x] **Step 3: Add the two pure parser functions**

Insert immediately after the constant from Step 2 (still before `extractCurrentPageData`):

```js
// Converts one index-panel-data record (one person) into the same {columnHeader:
// value} shape the DOM-table scraper produces. Empty-string values are skipped
// entirely (never fabricate a blank column, matching how downstream unmapped-column
// detection already treats blank values as absent). When two different API fieldNames
// map to the SAME target column (e.g. 1880's SelfResidenceIsSick and
// SelfResidenceIsBlind both feed "Disability Condition"), their values are combined
// with "; " rather than the second silently overwriting the first - confirmed live
// this collision is real (1880 exposes 6 separate boolean disability flags, this
// project's existing schema only has one combined "Disability Condition" column). An
// unrecognized fieldName (a field this map hasn't been extended to cover yet) is
// passed through under its own human-readable label (from fieldLabelsByName) when
// available, or its raw fieldName otherwise - never dropped. This exact case (a new,
// not-yet-mapped fieldName) is expected to happen on census years beyond the 4
// confirmed here; downstream census_schema.py already flags any unrecognized column
// as "unmapped" for manual review - no new review-flagging logic is needed in this
// function, it just needs to not lose the data.
function ancestryColumnsFromIndexPanelRecord(record, fieldLabelsByName) {
    const columns = {};
    (record.recordFields || []).forEach((f) => {
        const value = (f.value == null ? '' : String(f.value)).trim();
        if (!value) return;
        const target = ANCESTRY_INDEX_FIELD_TO_COLUMN[f.fieldName] || fieldLabelsByName[f.fieldName] || f.fieldName;
        columns[target] = columns[target] ? `${columns[target]}; ${value}` : value;
    });
    return columns;
}

// Converts a full index-panel-data API response into the same row-array shape
// extractCurrentPageData()'s DOM-table loop already produces for pageEntry.people:
// [{columns, pid, extracted_url, alternate_names, alternate_birth_places}], plus a new
// household_id field census_schema.py's _group_household() will prefer when present
// (see Task 4). record.pid is Ancestry's own real, stable numeric person ID -
// confirmed live this is the exact same identifier this project's DOM-scraper already
// extracts from an <a href="...records/{pid}"> link, just delivered directly instead
// of scraped. Synthesizes "Line Number" from array position (1-based) when the API
// response doesn't expose that field at all - confirmed live 1860 exposes no
// LineNumber field, matching the DOM-scraper's own existing "not every census year's
// index exposes a Line Number column" fallback for the same reason.
function ancestryRowsFromIndexPanelResponse(apiResponse) {
    const fieldLabelsByName = {};
    (apiResponse.fieldLabels || []).forEach((fl) => {
        fieldLabelsByName[fl.fieldName] = fl.labelText;
    });
    return (apiResponse.records || []).map((record, idx) => {
        const columns = ancestryColumnsFromIndexPanelRecord(record, fieldLabelsByName);
        if (!columns['Line Number']) {
            columns['Line Number'] = String(idx + 1);
        }
        return {
            columns: columns,
            pid: record.pid != null ? String(record.pid) : '',
            household_id: record.householdId ? String(record.householdId) : '',
            extracted_url: '',
            alternate_names: [],
            alternate_birth_places: [],
        };
    });
}
```

- [x] **Step 4: Run `node --check` to verify no syntax errors**

Run: `node --check Voyageur/Voyageur.js` (from the repo root, i.e. `Scriptorium/`)
Expected: no output, exit code 0.

- [x] **Step 5: Export the two new functions**

Find `module.exports = {` near the bottom of the file (inside the `if (typeof module !== 'undefined' && module.exports) {` block). Add the two new function names to the existing list (do not remove or reorder any existing entries):

```js
        module.exports = {
            placesMatch, saveReloadState, loadReloadState, clearReloadState,
            buildFsElementIndex, fsFieldText, fsPersonFieldText, fsWrappedFieldText,
            fsPersonName, fsPersonBirthPlace, fsHouseholds, fsBuildRowsFromApiResponse,
            fsCanonicalFieldsFromApiPerson, fsColumnsFromCanonicalFields,
            fsImageIndexFieldText, fsImageIndexFindByType,
            fsCanonicalFieldsFromImageIndexPerson, fsBuildRowsFromImageIndexResponse,
            fsImageIndexBrowsePathSegments, fsBuildCitationTextFromImageIndexResponse,
            ancestryColumnsFromIndexPanelRecord, ancestryRowsFromIndexPanelResponse,
        };
```

- [x] **Step 6: Write the test file with real fixture data from all 4 confirmed census years**

Create `Voyageur/tests/js/test_ancestry_index_panel_parser.mjs`:

```js
/* global globalThis */
import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const {
    ancestryColumnsFromIndexPanelRecord, ancestryRowsFromIndexPanelResponse,
} = require('./harness.js');

// Real captured 1850 fieldLabels (dbId 8054, Pembina, Minnesota Territory) - 17 fields,
// no LineNumber-less collision, includes "Industry" (an existing ancestry_census.yaml
// Occupation-fact alias, confirmed no YAML change needed for this field).
const FIELD_LABELS_1850 = [
    {fieldName: 'LineNumber', labelText: 'Line Number'},
    {fieldName: 'SourceDwellingNumber', labelText: 'Dwelling Number'},
    {fieldName: 'Famnum', labelText: 'Family Number'},
    {fieldName: 'SelfGivenName', labelText: 'Given Name'},
    {fieldName: 'SelfSurname', labelText: 'Surname'},
    {fieldName: 'SelfResidenceAge', labelText: 'Residence Age'},
    {fieldName: 'SelfBirthYear', labelText: 'Birth Date'},
    {fieldName: 'SelfGender', labelText: 'Gender'},
    {fieldName: 'SelfRace', labelText: 'Race'},
    {fieldName: 'SelfResidenceOccupation', labelText: 'Occupation'},
    {fieldName: 'SelfResidenceIndustry', labelText: 'Industry'},
    {fieldName: 'SelfResidenceRealEstateValue', labelText: 'Real Estate'},
    {fieldName: 'SelfBirthPlace', labelText: 'Birth Place'},
    {fieldName: 'SelfResidenceMarriedWithinYear', labelText: 'Married within the Year'},
    {fieldName: 'SelfResidenceAttendedSchool', labelText: 'Attended School'},
    {fieldName: 'SelfResidenceCannotRead', labelText: 'Cannot Read, Write'},
    {fieldName: 'SelfResidenceDisabilityCondition', labelText: 'Condition'},
];

function fieldLabelsByNameFrom(labels) {
    const byName = {};
    labels.forEach((l) => { byName[l.fieldName] = l.labelText; });
    return byName;
}

test('ancestryColumnsFromIndexPanelRecord: 1850 real Joseph Rolette record maps to expected columns', () => {
    // Real captured values, dbId 8054, imageId 4195937-00039, Pembina, Minnesota Territory
    const record = {
        pid: 3325109, householdId: '3325109', fullName: 'Joseph Rolette',
        recordFields: [
            {fieldName: 'LineNumber', value: '1', correctedValue: null},
            {fieldName: 'SourceDwellingNumber', value: '1', correctedValue: null},
            {fieldName: 'Famnum', value: '1', correctedValue: null},
            {fieldName: 'SelfGivenName', value: 'Joseph', correctedValue: null},
            {fieldName: 'SelfSurname', value: 'Rolette', correctedValue: null},
            {fieldName: 'SelfResidenceAge', value: '28', correctedValue: null},
            {fieldName: 'SelfBirthYear', value: '1822', correctedValue: null},
            {fieldName: 'SelfGender', value: 'Male', correctedValue: null},
            {fieldName: 'SelfRace', value: 'White', correctedValue: null},
            {fieldName: 'SelfResidenceOccupation', value: 'Clerk', correctedValue: null},
            {fieldName: 'SelfResidenceIndustry', value: 'Not Specified Retail Trade', correctedValue: null},
            {fieldName: 'SelfResidenceRealEstateValue', value: '', correctedValue: null},
            {fieldName: 'SelfBirthPlace', value: 'Michigan', correctedValue: null},
            {fieldName: 'SelfResidenceMarriedWithinYear', value: '', correctedValue: null},
            {fieldName: 'SelfResidenceAttendedSchool', value: '', correctedValue: null},
            {fieldName: 'SelfResidenceCannotRead', value: '', correctedValue: null},
            {fieldName: 'SelfResidenceDisabilityCondition', value: '', correctedValue: null},
        ],
        citation: null, isUserCreated: false,
    };

    const columns = ancestryColumnsFromIndexPanelRecord(record, fieldLabelsByNameFrom(FIELD_LABELS_1850));

    assert.equal(columns['Line Number'], '1');
    assert.equal(columns['Dwelling Number'], '1');
    assert.equal(columns['Family Number'], '1');
    assert.equal(columns['Given Name'], 'Joseph');
    assert.equal(columns['Surname'], 'Rolette');
    assert.equal(columns['Age'], '28');
    assert.equal(columns['Birth Year'], '1822');
    assert.equal(columns['Gender'], 'Male');
    assert.equal(columns['Race'], 'White');
    assert.equal(columns['Occupation'], 'Clerk');
    assert.equal(columns['Industry'], 'Not Specified Retail Trade');
    assert.equal(columns['Birth Place'], 'Michigan');
    // Empty-string fields must never appear as keys at all.
    assert.equal('Real Estate Value' in columns, false);
    assert.equal('Married within Year' in columns, false);
    assert.equal('Attended School' in columns, false);
    assert.equal('Cannot Read, Write' in columns, false);
    assert.equal('Disability Condition' in columns, false);
});

test('ancestryColumnsFromIndexPanelRecord: 1880 disability sub-flags combine into one column, not overwrite', () => {
    // Real fieldName vocabulary from 1880 (dbId 6742) - synthetic combination of two
    // simultaneously-true disability flags to prove the combine-not-overwrite behavior;
    // Sick and Blind are both real 1880 fieldNames mapping to the same "Disability
    // Condition" target column.
    const record = {
        pid: 1, householdId: '1', fullName: 'Test Person',
        recordFields: [
            {fieldName: 'SelfResidenceIsSick', value: 'X', correctedValue: null},
            {fieldName: 'SelfResidenceIsBlind', value: 'X', correctedValue: null},
        ],
        citation: null, isUserCreated: false,
    };

    const columns = ancestryColumnsFromIndexPanelRecord(record, {});

    assert.equal(columns['Disability Condition'], 'X; X');
});

test('ancestryColumnsFromIndexPanelRecord: unrecognized fieldName passes through under its label, never dropped', () => {
    const record = {
        pid: 1, householdId: '1', fullName: 'Test Person',
        recordFields: [
            {fieldName: 'SomeFutureCensusYearField', value: 'a real value', correctedValue: null},
        ],
        citation: null, isUserCreated: false,
    };

    const withLabel = ancestryColumnsFromIndexPanelRecord(
        record, {SomeFutureCensusYearField: 'Some Future Label'});
    assert.equal(withLabel['Some Future Label'], 'a real value');

    const withoutLabel = ancestryColumnsFromIndexPanelRecord(record, {});
    assert.equal(withoutLabel['SomeFutureCensusYearField'], 'a real value');
});

test('ancestryRowsFromIndexPanelResponse: 1860 real response (no LineNumber field at all) synthesizes Line Number from position', () => {
    // Real captured shape, dbId 7667, imageId 4211353_00001 - 1860 genuinely has no
    // LineNumber fieldLabel at all (confirmed live, unlike 1850/1880/1920).
    const apiResponse = {
        records: [
            {
                pid: 17613762, householdId: '17613762', fullName: 'Joseph Kosses',
                recordFields: [
                    {fieldName: 'SourceDwellingNumber', value: '1', correctedValue: null},
                    {fieldName: 'Famnum', value: '1', correctedValue: null},
                    {fieldName: 'SelfGivenName', value: 'Joseph', correctedValue: null},
                    {fieldName: 'SelfSurname', value: 'Kosses', correctedValue: null},
                ],
                citation: null, isUserCreated: false,
            },
            {
                pid: 17613763, householdId: '17613762', fullName: 'Mary Kosses',
                recordFields: [
                    {fieldName: 'SourceDwellingNumber', value: '1', correctedValue: null},
                    {fieldName: 'Famnum', value: '1', correctedValue: null},
                    {fieldName: 'SelfGivenName', value: 'Mary', correctedValue: null},
                    {fieldName: 'SelfSurname', value: 'Kosses', correctedValue: null},
                ],
                citation: null, isUserCreated: false,
            },
        ],
        fieldLabels: [
            {fieldName: 'SourceDwellingNumber', labelText: 'Dwelling Number'},
            {fieldName: 'Famnum', labelText: 'Family Number'},
            {fieldName: 'SelfGivenName', labelText: 'Given Name'},
            {fieldName: 'SelfSurname', labelText: 'Surname'},
        ],
    };

    const rows = ancestryRowsFromIndexPanelResponse(apiResponse);

    assert.equal(rows.length, 2);
    assert.equal(rows[0].pid, '17613762');
    assert.equal(rows[0].household_id, '17613762');
    assert.equal(rows[0].columns['Given Name'], 'Joseph');
    assert.equal(rows[0].columns['Line Number'], '1');
    assert.equal(rows[1].pid, '17613763');
    assert.equal(rows[1].columns['Line Number'], '2');
});

test('ancestryRowsFromIndexPanelResponse: 1920 real fields (HouseNumber, no SourceDwellingNumber) map to the same Dwelling Number column', () => {
    // Real captured shape, dbId 6061, imageId 4383784_00215, Mary J Darylus, Pembina ND.
    const apiResponse = {
        records: [{
            pid: 79215820, householdId: '79215820', fullName: 'Mary J Darylus',
            recordFields: [
                {fieldName: 'LineNumber', value: '1', correctedValue: null},
                {fieldName: 'HouseNumber', value: 'Farm', correctedValue: null},
                {fieldName: 'Famnum', value: '1', correctedValue: null},
                {fieldName: 'SelfSurname', value: 'Darylus', correctedValue: null},
                {fieldName: 'SelfGivenName', value: 'Mary J', correctedValue: null},
                {fieldName: 'SelfRelationToHead', value: 'Head', correctedValue: null},
                {fieldName: 'SelfMaritalStatus', value: 'Widowed', correctedValue: null},
                {fieldName: 'SelfArrivalYear', value: '1882', correctedValue: null},
                {fieldName: 'SelfResidenceNaturalizationStatus', value: 'Naturalized', correctedValue: null},
                {fieldName: 'SelfBirthPlace', value: 'Canada', correctedValue: null},
                {fieldName: 'SelfResidenceLanguageSpoken', value: 'English', correctedValue: null},
                {fieldName: 'FatherBirthPlace', value: 'Ireland', correctedValue: null},
                {fieldName: 'MotherBirthPlace', value: 'Ireland', correctedValue: null},
                {fieldName: 'SelfResidenceAbleToSpeakEnglish', value: 'Yes', correctedValue: null},
            ],
            citation: null, isUserCreated: false,
        }],
        fieldLabels: [],
    };

    const rows = ancestryRowsFromIndexPanelResponse(apiResponse);

    assert.equal(rows[0].columns['Dwelling Number'], 'Farm');
    assert.equal(rows[0].columns['Relationship to Head'], 'Head');
    assert.equal(rows[0].columns['Marital Status'], 'Widowed');
    assert.equal(rows[0].columns['Immigration Year'], '1882');
    assert.equal(rows[0].columns['Naturalization Status'], 'Naturalized');
    assert.equal(rows[0].columns['Native Tongue'], 'English');
    assert.equal(rows[0].columns['Father Foreign Born'], 'Ireland');
    assert.equal(rows[0].columns['Mother Foreign Born'], 'Ireland');
    assert.equal(rows[0].columns['Speaks English'], 'Yes');
    assert.equal(rows[0].household_id, '79215820');
});
```

- [x] **Step 7: Run the new tests to verify they pass**

Run: `node --test Voyageur/tests/js/test_ancestry_index_panel_parser.mjs` (from repo root)
Expected: all tests PASS (6 tests total).

- [x] **Step 8: Run the full existing JS suite to confirm no regressions**

Run: `node --test Voyageur/tests/js/` (from repo root)
Expected: all pre-existing tests still pass, plus the 6 new ones.

- [x] **Step 9: Commit**

```bash
git add Voyageur/Voyageur.js Voyageur/tests/js/test_ancestry_index_panel_parser.mjs
git commit -m "feat(voyageur): add Ancestry index-panel-data field map and parser functions"
```

---

### Task 2: Interceptor + `waitForAncestryIndexPanelResponse` (`Voyageur.js`)

**Files:**
- Modify: `Voyageur/Voyageur.js`

**Interfaces:**
- Consumes: nothing from Task 1 directly (this task is independent JS in a different part of the file).
- Produces: `waitForAncestryIndexPanelResponse(dbId, imageId, {timeoutMs})` (async function, resolves to `{result, elapsedMs, timedOut}`) — Task 3 calls this.

- [x] **Step 1: Locate the existing Ancestry interceptor block**

In `Voyageur/Voyageur.js`, find this exact block (search for `__mgs_intercepted`):

```js
        if (typeof unsafeWindow !== 'undefined' && !unsafeWindow.__mgs_intercepted) {
            unsafeWindow.__mgs_intercepted = true;
            unsafeWindow.__mgs_pids = [];

            function extractPidsFromText(text) {
                try {
                    let parsed;
                    try {
                        parsed = JSON.parse(text);
                    } catch (e) {
                        parsed = null;
                    }

                    if (parsed && Array.isArray(parsed.RecordRectangles) && parsed.RecordRectangles.length > 0) {
                        const ids = parsed.RecordRectangles
                            .map(r => (r && r.RecordId != null) ? String(r.RecordId) : null)
                            .filter(id => id !== null);
                        if (ids.length > 0) {
                            unsafeWindow.__mgs_pids = ids;
                            return;
                        }
                    }

                    const matches = [...text.matchAll(/"(?:recordId|pId|clientRecordId)"\s*:\s*"?(\d{5,15})"?/gi)];
                    if (matches.length > 2) {
                        unsafeWindow.__mgs_pids = matches.map(m => m[1]);
                    }
                } catch (e) {
                }
            }

            const origFetch = unsafeWindow.fetch;
            unsafeWindow.fetch = async function (...args) {
                const response = await origFetch.apply(this, args);
                try {
                    const clone = response.clone();
                    clone.text().then(text => extractPidsFromText(text)).catch(() => {
                    });
                } catch (e) {
                }
                return response;
            };

            const origOpen = unsafeWindow.XMLHttpRequest.prototype.open;
            unsafeWindow.XMLHttpRequest.prototype.open = function (method, url) {
                this.addEventListener('load', function () {
                    extractPidsFromText(this.responseText);
                });
                origOpen.apply(this, arguments);
            };
        }
```

- [x] **Step 2: Replace that exact block with this extended version**

This is the SAME block with three additions: (a) two new `unsafeWindow` state objects, (b) a URL-key helper and a store function for `index-panel-data`, (c) both the `fetch` and `XMLHttpRequest.open` overrides now also check for and store `index-panel-data` responses. `extractPidsFromText` itself is untouched.

```js
        if (typeof unsafeWindow !== 'undefined' && !unsafeWindow.__mgs_intercepted) {
            unsafeWindow.__mgs_intercepted = true;
            unsafeWindow.__mgs_pids = [];
            // State for the index-panel-data interceptor below - separate from __mgs_pids
            // since this captures the FULL per-person field response, not just a PID list.
            unsafeWindow.__voyageurAncestryIndexPanelResponses = {};
            // Per-"dbId:imageId" resolver callbacks for waitForAncestryIndexPanelResponse()
            // below - same waiter-map pattern as FS's __voyageurFsApiWaiters elsewhere in
            // this file. Storing a response sets a plain object property, not a DOM node -
            // waitForCondition()'s MutationObserver would never see it, so waiters are
            // notified directly here instead.
            unsafeWindow.__voyageurAncestryIndexPanelWaiters = {};

            const ANCESTRY_INDEX_PANEL_TARGET = '/imageviewer/api/record/index-panel-data';

            function ancestryIndexPanelKeyFromUrl(url) {
                const dbMatch = url.match(/[?&]dbId=([^&]+)/);
                const imgMatch = url.match(/[?&]imageId=([^&]+)/);
                if (!dbMatch || !imgMatch) return null;
                return `${decodeURIComponent(dbMatch[1])}:${decodeURIComponent(imgMatch[1])}`;
            }

            function storeAncestryIndexPanelResponse(url, bodyText) {
                const key = ancestryIndexPanelKeyFromUrl(url);
                if (!key) return;
                try {
                    const parsed = JSON.parse(bodyText);
                    unsafeWindow.__voyageurAncestryIndexPanelResponses[key] = parsed;
                    const waiter = unsafeWindow.__voyageurAncestryIndexPanelWaiters[key];
                    if (waiter) waiter(parsed);
                } catch (e) {
                    // Leave unset - waitForAncestryIndexPanelResponse() below times out the
                    // same as "never arrived", the correct behavior for an unparseable body.
                }
            }

            function extractPidsFromText(text) {
                try {
                    let parsed;
                    try {
                        parsed = JSON.parse(text);
                    } catch (e) {
                        parsed = null;
                    }

                    if (parsed && Array.isArray(parsed.RecordRectangles) && parsed.RecordRectangles.length > 0) {
                        const ids = parsed.RecordRectangles
                            .map(r => (r && r.RecordId != null) ? String(r.RecordId) : null)
                            .filter(id => id !== null);
                        if (ids.length > 0) {
                            unsafeWindow.__mgs_pids = ids;
                            return;
                        }
                    }

                    const matches = [...text.matchAll(/"(?:recordId|pId|clientRecordId)"\s*:\s*"?(\d{5,15})"?/gi)];
                    if (matches.length > 2) {
                        unsafeWindow.__mgs_pids = matches.map(m => m[1]);
                    }
                } catch (e) {
                }
            }

            const origFetch = unsafeWindow.fetch;
            unsafeWindow.fetch = async function (...args) {
                const url = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url) || '';
                const response = await origFetch.apply(this, args);
                try {
                    const clone = response.clone();
                    clone.text().then(text => {
                        extractPidsFromText(text);
                        if (url.includes(ANCESTRY_INDEX_PANEL_TARGET)) {
                            storeAncestryIndexPanelResponse(url, text);
                        }
                    }).catch(() => {
                    });
                } catch (e) {
                }
                return response;
            };

            const origOpen = unsafeWindow.XMLHttpRequest.prototype.open;
            unsafeWindow.XMLHttpRequest.prototype.open = function (method, url) {
                this.addEventListener('load', function () {
                    extractPidsFromText(this.responseText);
                    if (url && url.includes(ANCESTRY_INDEX_PANEL_TARGET)) {
                        storeAncestryIndexPanelResponse(url, this.responseText);
                    }
                });
                origOpen.apply(this, arguments);
            };
        }

        // Instant resolution if the response already arrived before this was called (the
        // API call fires on page load, same as the DOM table's own data source - by the
        // time extractCurrentPageData's caller has already confirmed the DOM table
        // populated, this response has almost always already arrived too). Falls back to a
        // bounded timer only when the API genuinely never fires for this collection/page.
        async function waitForAncestryIndexPanelResponse(dbId, imageId, {timeoutMs = 8000} = {}) {
            const key = `${dbId}:${imageId}`;
            const startedAt = performance.now();
            const existing = (unsafeWindow.__voyageurAncestryIndexPanelResponses || {})[key];
            if (existing) {
                return {result: existing, elapsedMs: 0, timedOut: false};
            }
            return new Promise((resolve) => {
                let settled = false;
                const timer = setTimeout(() => {
                    if (settled) return;
                    settled = true;
                    delete unsafeWindow.__voyageurAncestryIndexPanelWaiters[key];
                    resolve({result: null, elapsedMs: Math.round(performance.now() - startedAt), timedOut: true});
                }, timeoutMs);
                unsafeWindow.__voyageurAncestryIndexPanelWaiters[key] = (result) => {
                    if (settled) return;
                    settled = true;
                    clearTimeout(timer);
                    delete unsafeWindow.__voyageurAncestryIndexPanelWaiters[key];
                    resolve({result, elapsedMs: Math.round(performance.now() - startedAt), timedOut: false});
                };
            });
        }
```

- [x] **Step 3: Run `node --check` to verify no syntax errors**

Run: `node --check Voyageur/Voyageur.js`
Expected: no output, exit code 0.

- [x] **Step 4: Run the full JS test suite to confirm no regressions**

Run: `node --test Voyageur/tests/js/` (from repo root)
Expected: all tests still pass (this task adds no new tests of its own - `waitForAncestryIndexPanelResponse` is network/timer-driven and not practically unit-testable in the Node harness the same way the pure Task 1 functions are; it gets exercised by Task 5's live verification instead).

- [x] **Step 5: Commit**

```bash
git add Voyageur/Voyageur.js
git commit -m "feat(voyageur): intercept Ancestry index-panel-data responses"
```

---

### Task 3: Wire the API path into `extractCurrentPageData()` as a fallback pair

**Files:**
- Modify: `Voyageur/Voyageur.js`

**Interfaces:**
- Consumes: `ancestryRowsFromIndexPanelResponse` (Task 1), `waitForAncestryIndexPanelResponse` (Task 2).
- Produces: nothing new for later tasks - this is the final wiring point for Voyageur.js in this plan.

- [x] **Step 1: Locate the exact insertion point inside `extractCurrentPageData`**

Find `async function extractCurrentPageData(rows) {` again (line numbers have shifted since Tasks 1-2 added code above it - search by name, not line number). Inside it, find this exact line:

```js
            let columnNames = [];
```

Immediately followed by:

```js
            for (const row of rows) {
```

- [x] **Step 2: Insert the API-first branch between those two lines**

The line `let columnNames = [];` stays exactly where it is. Immediately after it, and immediately BEFORE `for (const row of rows) {`, insert:

```js

            // Try the index-panel-data API first (Task 1/2) - if it already fired for this
            // exact image (the common case: it's the same page load that populated the DOM
            // table extractCurrentPageData's caller already confirmed), this resolves
            // instantly. Only pays the bounded timeout when the API genuinely never fires
            // for this collection/page, in which case the DOM-table loop below (completely
            // unmodified) is the fallback. dbid/imageId were both already computed above in
            // this same function.
            const dbIdForApi = (dbid && dbid !== "0") ? dbid : null;
            let apiSourcedPeople = null;
            if (dbIdForApi && imageId) {
                const apiWait = await waitForAncestryIndexPanelResponse(dbIdForApi, imageId, {timeoutMs: 8000});
                if (!apiWait.timedOut && apiWait.result && Array.isArray(apiWait.result.records) && apiWait.result.records.length > 0) {
                    apiSourcedPeople = ancestryRowsFromIndexPanelResponse(apiWait.result).filter((p) => {
                        if (p.pid && seenPids.has(p.pid)) return false;
                        if (p.pid) seenPids.add(p.pid);
                        return true;
                    });
                    debugLog(`Ancestry index-panel-data API: ${apiSourcedPeople.length} people (of ${apiWait.result.records.length} total, ${apiWait.elapsedMs}ms) - using API data, skipping DOM table scrape for this page.`);
                } else {
                    debugLog(`Ancestry index-panel-data API ${apiWait.timedOut ? 'timed out' : 'returned no records'} after ${apiWait.elapsedMs}ms - falling back to DOM table scrape.`);
                }
            }

            if (apiSourcedPeople) {
                pageEntry.people.push(...apiSourcedPeople);
            } else {
```

- [x] **Step 3: Close the new `else` branch after the existing loop**

Find the existing loop's closing brace - it's the `}` that immediately follows the line `pageEntry.people.push({... alternate_names: alternateNames, alternate_birth_places: alternateBirthPlaces});` and precedes the blank line before `const thisPlace = {`. That closing `}` currently closes the `for` loop. Add ONE more closing brace right after it, to close the new `else` block from Step 2:

Before (existing code, do not change the loop body itself):
```js
                pageEntry.people.push({
                    columns: columns, pid: rowPid, extracted_url: rowUrl,
                    alternate_names: alternateNames, alternate_birth_places: alternateBirthPlaces
                });
            }

            const thisPlace = {
```

After:
```js
                pageEntry.people.push({
                    columns: columns, pid: rowPid, extracted_url: rowUrl,
                    alternate_names: alternateNames, alternate_birth_places: alternateBirthPlaces
                });
            }
            }

            const thisPlace = {
```

(The DOM-table loop body between `for (const row of rows) {` and this closing brace is UNCHANGED - do not edit anything inside it. Only the brace structure around it changed: one new `if (apiSourcedPeople) { ... } else {` wraps the whole thing, needing one extra closing `}`.)

- [x] **Step 4: Bump the version number**

Find `// @version      0.3.26` near the top of the file (line 4) and change it to:

```
// @version      0.3.27
```

- [x] **Step 5: Run `node --check` to verify no syntax errors**

Run: `node --check Voyageur/Voyageur.js`
Expected: no output, exit code 0. If this fails with a brace-mismatch error, re-check Step 3 carefully - it's the step most likely to introduce an unbalanced brace.

- [x] **Step 6: Run the full JS test suite to confirm no regressions**

Run: `node --test Voyageur/tests/js/` (from repo root)
Expected: all tests still pass. This step doesn't add new tests (this wiring is only exercisable live, in a real browser with a real network response - Task 5 covers that).

- [x] **Step 7: Commit**

```bash
git add Voyageur/Voyageur.js
git commit -m "feat(voyageur): wire Ancestry index-panel-data as a fallback pair with DOM-table scraping"
```

---

### Task 4: `census_schema.py` household_id preference + `ancestry_census.yaml` new field mappings

**Files:**
- Modify: `Voyageur/census_schema.py`
- Modify: `Voyageur/field_maps/ancestry_census.yaml`
- Test: `Voyageur/tests/test_census_schema.py`

**Interfaces:**
- Consumes: the `household_id` key Task 1's `ancestryRowsFromIndexPanelResponse` sets on each person row (already documented above - this task's Python tests construct that key directly in fixtures, no need to run any JS).
- Produces: nothing further downstream in this plan.

- [x] **Step 1: Write the failing test for household_id preference**

Open `Voyageur/tests/test_census_schema.py`. Find the `def test_relationship_era_groups_household_and_maps_role_name():` function (search by name). Insert this new test immediately before it:

```python
def test_group_household_prefers_household_id_over_column_based_key():
    """Ancestry's index-panel-data API supplies a real, stable household_id per person
    (Task 1/2/3 of docs/superpowers/plans/2026-08-15-ancestry-index-panel-extraction.md) -
    when present, it must win over the existing Family/Dwelling Number column-based
    inference, since it's a direct signal from Ancestry itself rather than a guess from
    column text that can vary or be absent by census year. Two people share a
    household_id but have DIFFERENT Family Number column values (simulating a data
    inconsistency) to prove household_id, not the column, decides the grouping."""
    raw = {
        "census_year": "1920", "location": "North Dakota",
        "pages": [_page([
            {"columns": {"Given Name": "Mary", "Surname": "Darylus", "Gender": "F", "Age": "67",
                        "Family Number": "1"}, "pid": "p1", "household_id": "79215820"},
            {"columns": {"Given Name": "Helen", "Surname": "Darylus", "Gender": "F", "Age": "42",
                        "Family Number": "2"}, "pid": "p2", "household_id": "79215820"},
        ])],
    }
    doc = census_schema.normalize_census_pages(raw, "ancestry_census", "1920 US Census", "Census_1920")

    records = doc["sheets"][0]["records"]
    assert len(records) == 1, f"expected both people grouped into one household by household_id, got: {records}"
    assert len(records[0]["participants"]) == 2


def test_group_household_falls_back_to_column_based_key_when_household_id_absent():
    """The DOM-table-scraping fallback path (Task 3) never sets household_id - confirms
    the existing column-based grouping still works completely unchanged when it's
    absent, matching every pre-existing test in this file."""
    raw = {
        "census_year": "1900", "location": "Minnesota",
        "pages": [_page([
            {"columns": {"Given Name": "Jean", "Surname": "Gagnon", "Gender": "M", "Age": "40",
                        "Family Number": "5"}, "pid": "p1"},
            {"columns": {"Given Name": "Marie", "Surname": "Gagnon", "Gender": "F", "Age": "38",
                        "Family Number": "5"}, "pid": "p2"},
        ])],
    }
    doc = census_schema.normalize_census_pages(raw, "ancestry_census", "1900 US Census", "Census_1900")

    records = doc["sheets"][0]["records"]
    assert len(records) == 1
    assert records[0]["record_number"] == "5"
```

- [x] **Step 2: Run the new tests to verify they fail**

Run: `cd Voyageur && python -m pytest tests/test_census_schema.py -k "household_id" -v` (adjust the `python` command to `python3`/`py -3` if that's what this machine uses - check with `python --version` first if unsure)
Expected: `test_group_household_prefers_household_id_over_column_based_key` FAILS (grouping not yet implemented), `test_group_household_falls_back_to_column_based_key_when_household_id_absent` PASSES (this behavior already exists, this test just documents/locks it in before the change).

- [x] **Step 3: Implement `household_id` preference in `_group_household`**

Open `Voyageur/census_schema.py`. Find this exact function (search for `def _group_household`):

```python
def _group_household(people: List[dict], field_map: Dict[str, Dict[str, str]]
                     ) -> List[Tuple[Optional[str], List[dict]]]:
    """Groups people sharing the same family/dwelling number (or, failing that, the same
    page-number fallback - see _household_key) into one household. A person with neither
    at all becomes their own single-person group - there's genuinely nothing to group them
    with."""
    groups: Dict[Optional[str], List[dict]] = {}
    order: List[Optional[str]] = []
    fallback_counter = 0
    for person in people:
        columns = person.get("columns", {}) or {}
        key = _household_key(columns, field_map)
        if key is None:
```

Replace it with:

```python
def _group_household(people: List[dict], field_map: Dict[str, Dict[str, str]]
                     ) -> List[Tuple[Optional[str], List[dict]]]:
    """Groups people sharing the same household_id (a real, stable identifier some
    sources supply directly - e.g. Ancestry's index-panel-data API, see
    docs/superpowers/specs/2026-08-15-ancestry-index-panel-extraction-design.md) when
    present, or the same family/dwelling number (or, failing that, the same page-number
    fallback - see _household_key) otherwise. A person with neither at all becomes their
    own single-person group - there's genuinely nothing to group them with."""
    groups: Dict[Optional[str], List[dict]] = {}
    order: List[Optional[str]] = []
    fallback_counter = 0
    for person in people:
        columns = person.get("columns", {}) or {}
        key = person.get("household_id") or _household_key(columns, field_map)
        if key is None:
```

(Everything below this point in the function - the `fallback_counter` handling, the `groups`/`order` bookkeeping, the `return` statement - is unchanged. Only the `key = ...` line itself changes, from `key = _household_key(columns, field_map)` to `key = person.get("household_id") or _household_key(columns, field_map)`.)

- [x] **Step 4: Run the tests again to verify they pass**

Run: `cd Voyageur && python -m pytest tests/test_census_schema.py -k "household_id" -v`
Expected: both tests PASS.

- [x] **Step 5: Run the full `census_schema.py` test suite to confirm no regressions**

Run: `cd Voyageur && python -m pytest tests/test_census_schema.py -v`
Expected: all tests pass (should be 22 total: 20 pre-existing + 2 new from this task).

- [x] **Step 6: Add the new field-map entries to `ancestry_census.yaml`**

Open `Voyageur/field_maps/ancestry_census.yaml`. Find this exact block under `participant_fields:`:

```yaml
  "Street": type_specific_fields.street
  "Street Address": type_specific_fields.street
  "Address": type_specific_fields.street
  "Married within Year": type_specific_fields.married_within_year
  "Married Within Year": type_specific_fields.married_within_year
```

Replace it with (adds two new entries, keeps the existing four unchanged):

```yaml
  "Street": type_specific_fields.street
  "Street Address": type_specific_fields.street
  "Address": type_specific_fields.street
  "Married within Year": type_specific_fields.married_within_year
  "Married Within Year": type_specific_fields.married_within_year
  "Birth Month": type_specific_fields.birth_month
  "Marital Status": type_specific_fields.marital_status
```

Then find this exact block under `participant_facts:`:

```yaml
  "Male Citizen Over 21": Miscellaneous
  "Voting Rights Denied": Miscellaneous
```

Replace it with (adds six new entries, keeps the existing two unchanged):

```yaml
  "Male Citizen Over 21": Miscellaneous
  "Voting Rights Denied": Miscellaneous
  "Months Not Employed": Miscellaneous
  "Home Ownership": Miscellaneous
  "Home Mortgaged": Miscellaneous
  "Native Tongue": Miscellaneous
  "Speaks English": Miscellaneous
  "Employment Field": Miscellaneous
```

Do NOT add an "Industry" entry anywhere in this file - it already exists (`"Industry": Occupation` under `participant_facts`, confirmed present before this task). Do NOT add a "House Number" entry under `participant_fields` - it's deliberately absent there (already exists under `record_fields` as a `dwelling_number` alias; the existing comment in the file explains why it must not also appear under `participant_fields`).

- [x] **Step 7: Write a test proving the two new `participant_fields` mappings work**

In `Voyageur/tests/test_census_schema.py`, find `def test_married_within_year_is_a_per_participant_field_not_dropped_as_a_record_field():` (search by name) and insert this new test immediately after its closing (before the next `def`):

```python
def test_ancestry_birth_month_and_marital_status_are_mapped_not_unmapped():
    """Regression for the two new participant_fields entries this session's Ancestry
    index-panel-data investigation surfaced (1880's SelfBirthMonth, 1880/1920's
    SelfMaritalStatus) - confirms they land in type_specific_fields and do NOT trigger
    the unmapped-column review flag."""
    raw = {
        "census_year": "1880", "location": "Dakota Territory",
        "pages": [_page([
            {"columns": {"Given Name": "Jean", "Surname": "Gagnon", "Gender": "M", "Age": "40",
                        "Birth Month": "March", "Marital Status": "Married"}, "pid": "p1"},
        ])],
    }
    doc = census_schema.normalize_census_pages(raw, "ancestry_census", "1880 US Census", "Census_1880")

    participant = doc["sheets"][0]["records"][0]["participants"][0]
    assert participant["type_specific_fields"]["birth_month"] == "March"
    assert participant["type_specific_fields"]["marital_status"] == "Married"
    assert not participant["review"], participant.get("review_reason")
```

- [x] **Step 8: Run the new test to verify it passes**

Run: `cd Voyageur && python -m pytest tests/test_census_schema.py -k "birth_month_and_marital_status" -v`
Expected: PASS.

- [x] **Step 9: Run the full Voyageur and Archivist Python test suites**

Run: `cd Voyageur && python -m pytest tests/ -v`
Expected: all tests pass.

Run: `cd Archivist && python -m pytest tests/ -v`
Expected: all tests pass (this task doesn't touch Archivist, this is a pure regression check).

- [x] **Step 10: Commit**

```bash
git add Voyageur/census_schema.py Voyageur/field_maps/ancestry_census.yaml Voyageur/tests/test_census_schema.py
git commit -m "feat(voyageur): prefer household_id for grouping, map new Ancestry index-panel fields"
```

---

### Task 5: Live verification (NOT subagent-delegable - requires a real Ancestry gather in the user's own logged-in browser)

**Files:** none - this task runs the already-built code, no new code.

**Interfaces:** N/A.

- [x] **Step 1: Run a real 3-page Ancestry gather**

Using the same isolated-output-directory technique already established this session (env var overrides `JSON_DIR`/`MEDIA_DIR`/`GENEALOGY_DIR`, never touching the user's real `.env`-configured output paths), run `python Voyageur/A.py` against one of the four already-confirmed test URLs from the design spec (1850 `dbId=8054`/`imageId=4195937-00039`, 1860 `dbId=7667`/`imageId=4211353_00001`, 1880 `dbId=6742`/`imageId=4240106-00102`, or 1920 `dbId=6061`/`imageId=4383784_00215` - any one is a valid live test; the 1860 one is this project's own long-standing default test record, referenced throughout this repo's own prior session history).

- [x] **Step 2: Confirm the API path actually fired, not just the DOM fallback**

Inspect the resulting JSON output's `citation` block and per-person `type_specific_fields` for a `pid` value shaped like Ancestry's real numeric person IDs (confirmed live examples: `17613762`, `79215820`, `3325109`), and for a `household_id` field being present (only the API path sets this - the DOM-table fallback never does). If `household_id` is absent on every person, the API path did not fire for this run - re-check the interceptor is actually installed and firing (Tampermonkey's own console log, `DEBUG_MODE` toggled on in `Voyageur.js`, should show either "using API data" or "falling back to DOM table scrape" per page - see Task 3 Step 2's `debugLog` calls).

- [x] **Step 3: Generate the GEDCOM and confirm households grouped correctly**

Run `Archivist.py` against the isolated JSON output (same isolated-output-directory technique). Open the resulting `.ged` file and spot-check that people confirmed live to share a household (e.g., for the 1860 test record: Joseph Kosses/Mary Kosses/Julia Kosses, household 1; John May/Nena May, household 2 - see this session's own earlier live-verification report for the full household list) are grouped into the same `0 @F...@ FAM` record.

- [x] **Step 4: Confirm the DOM-table fallback still works**

This is harder to force live (the API path will usually succeed when it's genuinely available), but at minimum confirm via code review that Task 3's `else` branch is reachable and its body is byte-for-byte identical to the pre-Task-3 DOM-scraping loop (diff `git show <Task-3-commit>^:Voyageur/Voyageur.js` against the current file's DOM-loop section, or just re-read Task 3 Step 3 above and confirm the wrapped loop body wasn't edited).

- [x] **Step 5: Report results**

Document in this plan's own SDD ledger (or directly to the user, if not running under SDD) what was confirmed: real `pid`/`household_id` values seen, household grouping correctness, GEDCOM output sanity. If the API path did NOT fire during this live test, that's a genuine finding worth reporting honestly - do not claim success without having actually observed `household_id` populated in real output.

---

## Self-Review Notes (for whoever executes this plan)

- **Spec coverage:** Task 1 covers the field-map/parser (spec's Architecture items 2-3). Task 2 covers the interceptor (spec's Architecture item 1). Task 3 covers the fallback wiring (spec's Architecture item 4). Task 4 covers household_id preference (spec's Architecture item 5) and the field-map YAML changes (spec's "Field-map changes required" section). Task 5 covers the spec's "Not yet verified" items 1 (household grouping via household_id in practice).
- **Not covered by this plan, intentionally** (per the spec's own Scope Decisions): `collections/collection-text` interception, `correctedValue` handling, State/Canadian/other-census-year coverage - all tracked under GitHub issue #24.
- **Waiter-map key collision risk** (spec's "Not yet verified" item 2): not addressed by this plan's tests - genuinely requires live, rapid-navigation testing beyond what Task 5 covers. If it becomes a real problem in production use, that's a fast-follow bug fix, not a blocker for this plan.

## Status: COMPLETE (2026-08-15)

All 5 tasks done, Task 5 live-verified against the 1860 Dakota Territory test record (dbId `7667`/imageId `4211353_00001`): real Ancestry `pid`s and `household_id`-driven grouping confirmed in the API path's output, correct household grouping in the generated GEDCOM (Kosses, May), DOM-table fallback branch confirmed byte-for-byte unchanged.

Tasks 1-3 (`Voyageur.js`) had been implemented and tested but never committed - committed post-hoc (`fbcc2b5`). One post-verification fix: `SelfGender` returns the full word ("Male"/"Female"), unlike the DOM table's single-letter form, which tripped Commissioner's soft schema validation - `ancestryColumnsFromIndexPanelRecord()` now normalizes it to M/F/U via `ancestryNormalizeGender()`, matching every other sex-bearing field in this codebase.

Follow-on tracked separately: [issue #25](https://github.com/alerum68/Scriptorium/issues/25) (eliminate the remaining FS Information-tab dependency, found during this plan's live verification but out of this plan's own scope).
