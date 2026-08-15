# FamilySearch Image-Index Extraction (Image Browser path) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `Voyageur.js`'s FamilySearch gather to also cover records reached via Image Browser (township navigation), which renders the older "Image Index" page and never fires the orchestration API Tasks 1-3 of the prior plan already handle — instead firing `POST /search/filmdatainfo/image-data`.

**Architecture:** A second pure, DOM-free parser (`fsBuildRowsFromImageIndexResponse`) walks that endpoint's `records[].persons[]` response and produces the same row shape the orchestration-API parser does, routed through a new shared `fsColumnsFromCanonicalFields` builder both parsers use (the orchestration-API parser is refactored to route through it too, regression-gated by its own existing 22 tests). A second interceptor captures the response the same way Task 2 of the prior plan does, keyed by the response body's `arkId` since this endpoint's request URL is generic. `scrapeCurrentImage()` detects which page rendered (DOM: "Names" tab vs "Image Index" tab) and calls the matching wait+parse pair. Citation text for the Image-Index path is built entirely from this same JSON (never from `scrapeCitationAndCatalog()`'s UI read), matching `FS.py`'s existing `CITATION_RE`/`NARA_CITING_RE` prose format exactly so the Python side is untouched.

**Tech Stack:** Tampermonkey userscript (`Voyageur.js`), Node's built-in test runner (`node --test`) via the existing `Voyageur/tests/js/harness.js` pattern.

**Spec:** `docs/superpowers/specs/2026-08-14-fs-image-index-extraction-design.md`

## Global Constraints

- Single-file userscript, no build step — all new code lives in `Voyageur/Voyageur.js`, following its existing structure (top-level pure helpers exported via the `module.exports` guard at the bottom).
- New pure functions (no `document`/`window` DOM access) go at file top-level, alongside the existing `fs*` helpers, so they're unit-testable via `Voyageur/tests/js/harness.js`.
- Era boundary: fields absent from a given record's JSON (relationship/marital/occupation/race/parents'-birthplace on pre-1880 records) must be omitted from `columns` entirely — never set to `''`. No year-based branching code; field presence alone drives it.
- `columns` output shape stays exactly what `fsBuildRowsFromApiResponse` already produces today: `Given Name`, `Surname`, `Gender`, `Age`, `Family Number`, `Relationship to Head` (when present). The canonical field map captures marital status/occupation/race/parents'-birthplace/birthplace too, but they are deliberately NOT added to `columns` in this plan — matching the prior plan's own already-shipped scope, since the downstream schema (`FS.py`) has no slots for them yet. A natural follow-up, not this plan's job.
- `FS.py`'s `parse_citation()`, `parse_nara_citing_clause()`, `parse_census_browse_path()` are a deliberately untouched regression boundary — the new citation-text builder's only job is to produce a string those functions parse identically to a UI-scraped one.
- Bump `@version` in `Voyageur.js`'s header on every task that ships a real behavior change (current: `0.3.24` as of this plan — check the actual current value before each bump).
- Every JS change gets `node --check "Voyageur/Voyageur.js"` before commit.
- Task 6 (live verification) cannot be run by a coding subagent — no browser tool access, and per this project's own established constraint, must not be driven via Chrome automation either (the gather loop is timing-sensitive; a Claude-driven/background tab inflates `setTimeout` 20x+, giving a false read). Must be run by the user directly.

---

### Task 1: Shared canonical-field builder + orchestration-API parser refactor

**Files:**
- Modify: `Voyageur/Voyageur.js` — `fsBuildRowsFromApiResponse` (currently lines 268-298), delete now-dead `fsFamilyNumber` (currently lines 255-266), add `fsCanonicalFieldsFromApiPerson`/`fsColumnsFromCanonicalFields` nearby
- Modify: `Voyageur/tests/js/test_fs_api_parser.mjs` (existing file — its 22 tests are this task's regression contract; add new tests for the two new functions)
- Modify: `module.exports` guard (currently lines 2077-2083)

**Interfaces:**
- Consumes: nothing from this plan's other tasks (this is the foundation task, same role as Task 1 of the prior plan).
- Produces: `fsCanonicalFieldsFromApiPerson(byId, person) -> {givenName, surname, sex, age, birthplace, householdIdSource, householdIdFs, relationshipToHead, maritalStatus, occupation, race, fatherBirthplace, motherBirthplace}` (all strings, `''` when absent). `fsColumnsFromCanonicalFields(canonicalFields, sequenceFallback) -> {columns object}` — shared by this task and Task 2.

This is the one task that touches already-shipped, already-reviewed code. The regression contract is exact: `fsBuildRowsFromApiResponse`'s existing 22 tests must pass **unchanged** after this refactor — that's what proves behavior was preserved, not just "looks right."

- [ ] **Step 1: Write the failing tests for the two new functions**

Add to the end of `Voyageur/tests/js/test_fs_api_parser.mjs` (after its existing tests, before the closing of the file — the existing `makeApiResponse()` fixture and imports stay as-is; add `fsCanonicalFieldsFromApiPerson, fsColumnsFromCanonicalFields` to the destructured `require()` at the top of the file):

```js
test('fsCanonicalFieldsFromApiPerson: extracts every canonical field for an 1880-style person', () => {
    const data = makeApiResponse();
    const byId = buildFsElementIndex(data);
    const person = byId['1:1:PERSON-A'];
    const fields = fsCanonicalFieldsFromApiPerson(byId, person);
    assert.deepEqual(fields, {
        givenName: 'ELIZA M.', surname: 'FISK', sex: 'F', age: '38',
        birthplace: 'Maine, United States',
        householdIdSource: '90', householdIdFs: '',
        relationshipToHead: 'Head', maritalStatus: 'Married', occupation: 'Farmer',
        race: 'White', fatherBirthplace: 'Germany', motherBirthplace: 'Vermont, United States',
    });
});

test('fsCanonicalFieldsFromApiPerson: era-absent fields come back as empty strings, not thrown errors', () => {
    const data = makeApiResponse();
    const byId = buildFsElementIndex(data);
    const person = byId['1:1:PERSON-B'];
    const fields = fsCanonicalFieldsFromApiPerson(byId, person);
    assert.equal(fields.relationshipToHead, '');
    assert.equal(fields.maritalStatus, '');
    assert.equal(fields.occupation, '');
    assert.equal(fields.race, '');
    assert.equal(fields.fatherBirthplace, '');
    assert.equal(fields.motherBirthplace, '');
    assert.equal(fields.givenName, 'Bozil');
    assert.equal(fields.householdIdFs, '');
});

test('fsColumnsFromCanonicalFields: builds the exact existing columns shape, relationship present', () => {
    const columns = fsColumnsFromCanonicalFields({
        givenName: 'ELIZA M.', surname: 'FISK', sex: 'F', age: '38',
        householdIdSource: '90', householdIdFs: '', relationshipToHead: 'Head',
        maritalStatus: 'Married', occupation: 'Farmer', race: 'White',
        fatherBirthplace: 'Germany', motherBirthplace: 'Vermont, United States', birthplace: 'Maine',
    }, 1);
    assert.deepEqual(columns, {
        'Given Name': 'ELIZA M.', 'Surname': 'FISK', 'Gender': 'F', 'Age': '38',
        'Family Number': '90', 'Relationship to Head': 'Head',
    });
});

test('fsColumnsFromCanonicalFields: omits Relationship to Head entirely when absent, not blank', () => {
    const columns = fsColumnsFromCanonicalFields({
        givenName: 'Bozil', surname: 'Delmer', sex: 'M', age: '47',
        householdIdSource: '', householdIdFs: '', relationshipToHead: '',
        maritalStatus: '', occupation: '', race: '', fatherBirthplace: '', motherBirthplace: '', birthplace: '',
    }, 2);
    assert.deepEqual(columns, {
        'Given Name': 'Bozil', 'Surname': 'Delmer', 'Gender': 'M', 'Age': '47', 'Family Number': '2',
    });
    assert.ok(!('Relationship to Head' in columns));
});

test('fsColumnsFromCanonicalFields: Family Number precedence, householdIdSource wins over householdIdFs', () => {
    const columns = fsColumnsFromCanonicalFields({
        givenName: 'X', surname: 'Y', sex: '', age: '',
        householdIdSource: '90', householdIdFs: '999', relationshipToHead: '',
        maritalStatus: '', occupation: '', race: '', fatherBirthplace: '', motherBirthplace: '', birthplace: '',
    }, 5);
    assert.equal(columns['Family Number'], '90');
});

test('fsColumnsFromCanonicalFields: Family Number falls back to householdIdFs when householdIdSource absent', () => {
    const columns = fsColumnsFromCanonicalFields({
        givenName: 'X', surname: 'Y', sex: '', age: '',
        householdIdSource: '', householdIdFs: '999', relationshipToHead: '',
        maritalStatus: '', occupation: '', race: '', fatherBirthplace: '', motherBirthplace: '', birthplace: '',
    }, 5);
    assert.equal(columns['Family Number'], '999');
});

test('fsColumnsFromCanonicalFields: Family Number falls back to sequenceFallback when neither household id exists', () => {
    const columns = fsColumnsFromCanonicalFields({
        givenName: 'X', surname: 'Y', sex: '', age: '',
        householdIdSource: '', householdIdFs: '', relationshipToHead: '',
        maritalStatus: '', occupation: '', race: '', fatherBirthplace: '', motherBirthplace: '', birthplace: '',
    }, 3);
    assert.equal(columns['Family Number'], '3');
});
```

- [ ] **Step 2: Run the tests to verify the new ones fail**

Run: `node --test Voyageur/tests/js/test_fs_api_parser.mjs`
Expected: the 7 new tests FAIL (`fsCanonicalFieldsFromApiPerson`/`fsColumnsFromCanonicalFields` not exported yet); the original 22 still PASS (they don't touch the new functions).

- [ ] **Step 3: Implement the two new functions and refactor `fsBuildRowsFromApiResponse`**

In `Voyageur/Voyageur.js`, replace the block from `fsFamilyNumber` through the end of `fsBuildRowsFromApiResponse` (currently lines 255-298):

```js
    // Reduces one orchestration-API PERSON down to the canonical field map shared with the
    // Image-Index parser (fsCanonicalFieldsFromImageIndexPerson) - fsColumnsFromCanonicalFields
    // below builds the final `columns` object from either source's canonical map the same way.
    function fsCanonicalFieldsFromApiPerson(byId, person) {
        const {given, surname} = fsPersonName(byId, person);
        const sex = fsPersonFieldText(byId, person, 'SEX_CODE');
        return {
            givenName: given,
            surname: surname,
            sex: sex ? sex.toUpperCase() : '',
            age: fsWrappedFieldText(byId, person, 'AGE'),
            birthplace: fsPersonBirthPlace(byId, person),
            householdIdSource: fsPersonFieldText(byId, person, 'SOURCE_HOUSEHOLD_ID'),
            householdIdFs: fsPersonFieldText(byId, person, 'FS_HOUSEHOLD_ID'),
            relationshipToHead: fsPersonFieldText(byId, person, 'RELATIONSHIP_TO_HEAD'),
            maritalStatus: fsPersonFieldText(byId, person, 'MARITAL_STATUS'),
            occupation: fsPersonFieldText(byId, person, 'OCCUPATION'),
            race: fsPersonFieldText(byId, person, 'RACE_OR_COLOR'),
            fatherBirthplace: fsPersonFieldText(byId, person, 'FTHR_BIR_PLACE'),
            motherBirthplace: fsPersonFieldText(byId, person, 'MTHR_BIR_PLACE'),
        };
    }

    // Shared by both fsBuildRowsFromApiResponse (orchestration API) and
    // fsBuildRowsFromImageIndexResponse (filmdatainfo/image-data) - both sources reduce a
    // person down to the same canonical field shape above this function, so the household-ID
    // precedence and era-appropriate omission logic exists exactly once. householdIdSource
    // (SOURCE_HOUSEHOLD_ID) is the sheet-printed family number, preferred over
    // householdIdFs (FS_HOUSEHOLD_ID, FamilySearch's own system-generated id) - confirmed
    // live on the orchestration API these two are exact complements on a real image (35 + 7 =
    // 42 of 42 persons), and the same two-key relationship was independently confirmed live
    // again on the Image-Index endpoint (1860 sample used FS_HOUSEHOLD_ID, 1880 used
    // SOURCE_HOUSEHOLD_ID). Falls back to a sequential per-household counter only if neither
    // exists at all.
    function fsColumnsFromCanonicalFields(canonicalFields, sequenceFallback) {
        const columns = {
            'Given Name': canonicalFields.givenName || '',
            'Surname': canonicalFields.surname || '',
            'Gender': canonicalFields.sex || '',
            'Age': canonicalFields.age || '',
            'Family Number': canonicalFields.householdIdSource
                || canonicalFields.householdIdFs
                || String(sequenceFallback),
        };
        // Omitted entirely (not set to '') when absent - matches the old UI-scraper's own
        // "don't fabricate data" convention, and is how the pre-1880 era boundary is handled:
        // no special-case branching, just field-absence. maritalStatus/occupation/race/
        // fatherBirthplace/motherBirthplace/birthplace are captured in canonicalFields but
        // deliberately not added here - see this plan's Global Constraints.
        if (canonicalFields.relationshipToHead) columns['Relationship to Head'] = canonicalFields.relationshipToHead;
        return columns;
    }

    function fsBuildRowsFromApiResponse(apiResponse) {
        const byId = buildFsElementIndex(apiResponse);
        const rows = [];
        let householdIndex = 0;
        for (const household of fsHouseholds(apiResponse, byId)) {
            householdIndex++;
            for (const personId of household.personIds) {
                const person = byId[personId];
                if (!person) continue;

                const canonicalFields = fsCanonicalFieldsFromApiPerson(byId, person);
                const columns = fsColumnsFromCanonicalFields(canonicalFields, householdIndex);
                rows.push({columns, person_ark: person.id, attached_fsftid: ''});
            }
        }
        return rows;
    }

```

`fsFamilyNumber` is deleted, not kept alongside — its precedence logic now lives inside `fsColumnsFromCanonicalFields`, and it was never exported (confirm via Step 5's grep) so nothing outside this file could have depended on it.

- [ ] **Step 4: Update `module.exports`**

In `Voyageur/Voyageur.js`, update the export guard (currently lines 2077-2083):

```js
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = {
            placesMatch, saveReloadState, loadReloadState, clearReloadState,
            buildFsElementIndex, fsFieldText, fsPersonFieldText, fsWrappedFieldText,
            fsPersonName, fsPersonBirthPlace, fsHouseholds, fsBuildRowsFromApiResponse,
            fsCanonicalFieldsFromApiPerson, fsColumnsFromCanonicalFields,
        };
    }
```

- [ ] **Step 5: Confirm `fsFamilyNumber` has zero remaining references**

Run: `grep -n fsFamilyNumber Voyageur/Voyageur.js`
Expected: no matches (empty output). If any remain, something outside the block you replaced was still calling it — investigate before proceeding, don't just re-add it.

- [ ] **Step 6: Run the full test file to verify everything passes**

Run: `node --test Voyageur/tests/js/test_fs_api_parser.mjs`
Expected: PASS, all 29 tests (the original 22 unchanged, plus the 7 new ones from Step 1). If any of the original 22 fail, the refactor changed behavior — stop and fix before proceeding; do not edit the tests to match new output.

- [ ] **Step 7: Syntax-check the full file**

Run: `node --check Voyageur/Voyageur.js`
Expected: no output (clean exit).

- [ ] **Step 8: Commit**

```bash
git add Voyageur/Voyageur.js Voyageur/tests/js/test_fs_api_parser.mjs
git commit -m "refactor(voyageur): extract shared canonical-field/columns builder from FS API parser"
```

---

### Task 2: Image-Index person parser + row builder

**Files:**
- Modify: `Voyageur/Voyageur.js` (add new top-level functions after Task 1's additions)
- Test: `Voyageur/tests/js/test_fs_image_index_parser.mjs` (new file)
- Modify: `module.exports` guard

**Interfaces:**
- Consumes: `fsColumnsFromCanonicalFields` (Task 1).
- Produces: `fsImageIndexFieldText(fieldOrFact) -> string`, `fsImageIndexFindByType(list, type) -> object|null`, `fsCanonicalFieldsFromImageIndexPerson(person) -> {same canonical shape as Task 1}`, `fsBuildRowsFromImageIndexResponse(apiResponse) -> [{columns, person_ark, attached_fsftid}]` (same return shape as `fsBuildRowsFromApiResponse`).

This implements the confirmed live structure of `filmdatainfo/image-data`'s response, verified against two real captured records (not assumed): the response's top level is `{imageURL, arkId, dgsNum, collections[], records[], recordList[], meta}`. **`records[]` is one entry per household** (confirmed: an 1880 sample's `records[0]` held all 5 Gatchill household members; a later record on the same image held 11 people across a multi-family sheet). Each record is `{fields[] (record/citation-level admin data), persons[]}`. Each person is `{display, facts[], fields[], gender, names[], identifiers, links, principal}`:

- `person.facts[]` — each entry has both a convenience `.value` (the final resolved text) AND a nested `.fields[].values[]` (Original/Interpreted variants with `labelId`). Confirmed present as `facts[].type`: `http://gedcomx.org/Race`, `/Occupation`, `/MaritalStatus`, `/Census` (residence event, has `.place.fields[]`), `/Birth` (has `.place.fields[]` and `.date.fields[]`).
- `person.fields[]` — flat field objects, NO `.value` shortcut (must read `.values[]`, preferring `type: Interpreted` over `Original`). Confirmed present as `fields[].type`: `http://gedcomx.org/Age`, `http://gedcomx.org/RelationshipToHead`, `http://familysearch.org/types/fields/SourceHouseholdId` (⚡ confirmed distinct type URI from the one below), `http://familysearch.org/types/fields/HouseholdId` (backs `FS_HOUSEHOLD_ID` specifically — confirmed live on the 1860 sample, which had no `SourceHouseholdId` field at all), `.../FatherBirthPlace`, `.../MotherBirthPlace`.
- `person.gender` — `{type: "http://gedcomx.org/Male"|"http://gedcomx.org/Female", fields: [...]}` — the outer `.type` alone is enough, no need to read `fields[]`.
- `person.names[0].nameForms[0].parts[]` — each part has both a convenience `.value` and `.type` of `http://gedcomx.org/Surname` or `http://gedcomx.org/Given`.
- `person.identifiers['http://gedcomx.org/Persistent'][0]` — a full URL, e.g. `https://www.familysearch.org/ark:/61903/1:1:MF36-Z6D`; `person_ark` is the `1:1:XXXX-XXX` segment.
- **Confirmed real quirk to handle correctly:** the head-of-household's own `RelationshipToHead` field can carry conflicting `Interpreted` values in the SAME `values[]` array (confirmed live: `[{type: Original, text: "Self"}, {type: Interpreted, text: "Head"}, {type: Interpreted, text: "Self"}]`) — a correction trail, not random noise. Taking the FIRST `Interpreted` match (not the last) is confirmed correct against this real example (`Prince A. Gatchill`, the household's own first-listed/head person, correctly resolves to `"Head"`). `fsImageIndexFieldText` must implement "first Interpreted, else first Original" — not "last."
- `attached_fsftid` is not yet confirmed derivable from this response (no Family-Tree-attachment link was observed on either captured sample) — left as `''` for this task, same "don't fabricate" convention as everywhere else in this codebase. Flagged for Task 6's live verification, not blocking here.

- [ ] **Step 1: Write the failing tests using real captured data as fixtures**

Create `Voyageur/tests/js/test_fs_image_index_parser.mjs`:

```js
/* global globalThis */
import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const {
    fsImageIndexFieldText, fsImageIndexFindByType,
    fsCanonicalFieldsFromImageIndexPerson, fsBuildRowsFromImageIndexResponse,
} = require('./harness.js');

// Trimmed, structurally faithful fixture built from a real live capture (1880, Dakota
// Territory/Pembina, collection 1417683, ark 3:1:33S7-9YBZ-XVG) - not synthetic guesswork.
// Two people from the same real household: Prince A. Gatchill (head, has every rich 1880+
// field) and Hattie O. Gatchill (his wife, a clean single-value RelationshipToHead - proves
// the parser doesn't only work on the ambiguous multi-value case).
function makeImageIndex1880Response() {
    return {
        imageURL: 'https://www.familysearch.org/ark:/61903/3:1:33S7-9YBZ-XVG?cc=1417683',
        arkId: '3:1:33S7-9YBZ-XVG',
        collections: [{collections: [{title: 'United States, Census, 1880'}]}],
        records: [{
            fields: [
                {type: 'http://familysearch.org/types/fields/FilmNbr', values: [{text: '1254114', type: 'http://gedcomx.org/Interpreted'}]},
                {type: 'http://familysearch.org/types/fields/ExtPubNbr', values: [{text: 'T9', type: 'http://gedcomx.org/Original'}]},
            ],
            persons: [
                {
                    display: {name: 'Prince A. Gatchill'},
                    gender: {type: 'http://gedcomx.org/Male'},
                    names: [{nameForms: [{parts: [
                        {type: 'http://gedcomx.org/Surname', value: 'Gatchill'},
                        {type: 'http://gedcomx.org/Given', value: 'Prince A.'},
                    ]}]}],
                    facts: [
                        {type: 'http://gedcomx.org/Race', value: 'White'},
                        {type: 'http://gedcomx.org/Occupation', value: 'Editor'},
                        {type: 'http://gedcomx.org/MaritalStatus', value: 'Married'},
                        {type: 'http://gedcomx.org/Census', place: {fields: [
                            {type: 'http://gedcomx.org/State', values: [{text: 'Dakota Territory', type: 'http://gedcomx.org/Interpreted'}]},
                            {type: 'http://gedcomx.org/County', values: [{text: 'Pembina', type: 'http://gedcomx.org/Interpreted'}]},
                            {type: 'http://gedcomx.org/Township', values: [{text: 'Pembina', type: 'http://gedcomx.org/Interpreted'}]},
                            {type: 'http://gedcomx.org/District', values: [{text: 'ED 75', type: 'http://gedcomx.org/Original'}]},
                        ]}},
                        {type: 'http://gedcomx.org/Birth', place: {fields: [
                            {type: 'http://gedcomx.org/Place', values: [{text: 'Maine, United States', type: 'http://gedcomx.org/Interpreted'}]},
                        ]}},
                    ],
                    fields: [
                        {type: 'http://gedcomx.org/Age', values: [
                            {text: '38', type: 'http://gedcomx.org/Original'},
                            {text: '38 years', type: 'http://gedcomx.org/Interpreted'},
                        ]},
                        // Confirmed live quirk: two Interpreted values for the head person -
                        // first-Interpreted ("Head") is the correct one, not last ("Self").
                        {type: 'http://gedcomx.org/RelationshipToHead', values: [
                            {text: 'Self', type: 'http://gedcomx.org/Original'},
                            {text: 'Head', type: 'http://gedcomx.org/Interpreted'},
                            {text: 'Self', type: 'http://gedcomx.org/Interpreted'},
                        ]},
                        {type: 'http://familysearch.org/types/fields/SourceHouseholdId', values: [{text: '8735134', type: 'http://gedcomx.org/Original'}]},
                        {type: 'http://familysearch.org/types/fields/FatherBirthPlace', values: [{text: 'Maine, United States', type: 'http://gedcomx.org/Interpreted'}]},
                        {type: 'http://familysearch.org/types/fields/MotherBirthPlace', values: [{text: 'Maine, United States', type: 'http://gedcomx.org/Interpreted'}]},
                        {type: 'http://familysearch.org/types/fields/ExtRepositoryName', values: [{text: 'The U.S. National Archives and Records Administration (NARA)', type: 'http://gedcomx.org/Original'}]},
                    ],
                    identifiers: {'http://gedcomx.org/Persistent': ['https://www.familysearch.org/ark:/61903/1:1:MCVW-PYP']},
                },
                {
                    display: {name: 'Hattie O. Gatchill'},
                    gender: {type: 'http://gedcomx.org/Female'},
                    names: [{nameForms: [{parts: [
                        {type: 'http://gedcomx.org/Surname', value: 'Gatchill'},
                        {type: 'http://gedcomx.org/Given', value: 'Hattie O.'},
                    ]}]}],
                    facts: [
                        {type: 'http://gedcomx.org/Race', value: 'White'},
                        {type: 'http://gedcomx.org/MaritalStatus', value: 'Married'},
                    ],
                    fields: [
                        {type: 'http://gedcomx.org/Age', values: [{text: '32 years', type: 'http://gedcomx.org/Interpreted'}]},
                        {type: 'http://gedcomx.org/RelationshipToHead', values: [{text: 'Wife', type: 'http://gedcomx.org/Interpreted'}]},
                        {type: 'http://familysearch.org/types/fields/SourceHouseholdId', values: [{text: '8735134', type: 'http://gedcomx.org/Original'}]},
                    ],
                    identifiers: {'http://gedcomx.org/Persistent': ['https://www.familysearch.org/ark:/61903/1:1:MCVW-PY2']},
                },
            ],
        }],
    };
}

// Trimmed, structurally faithful fixture from a real live capture (1860, Dakota Territory,
// collection 1473181, ark 3:1:33S7-9YBJ-9PD7) - the era-boundary case: no relationship,
// marital, occupation, or parent-birthplace fields/facts at all, and household id via the
// FS_HOUSEHOLD_ID-backed type (not SourceHouseholdId) - confirmed live, distinct from the
// 1880 sample above.
function makeImageIndex1860Response() {
    return {
        imageURL: 'https://www.familysearch.org/ark:/61903/3:1:33S7-9YBJ-9PD7?cc=1473181',
        arkId: '3:1:33S7-9YBJ-9PD7',
        collections: [{collections: [{title: 'United States, Census, 1860'}]}],
        records: [{
            fields: [
                {type: 'http://familysearch.org/types/fields/ExtPubNbr', values: [{text: 'M653', type: 'http://gedcomx.org/Original'}]},
                {type: 'http://familysearch.org/types/fields/DigitalFilmNbr', values: [{text: '005165665', type: 'http://gedcomx.org/Interpreted'}]},
            ],
            persons: [{
                display: {name: 'Joseph Kosses'},
                gender: {type: 'http://gedcomx.org/Male'},
                names: [{nameForms: [{parts: [
                    {type: 'http://gedcomx.org/Surname', value: 'Kosses'},
                    {type: 'http://gedcomx.org/Given', value: 'Joseph'},
                ]}]}],
                facts: [
                    {type: 'http://gedcomx.org/Race', value: 'White'},
                    {type: 'http://gedcomx.org/Census', place: {fields: [
                        {type: 'http://gedcomx.org/State', values: [{text: 'Dakota Territory', type: 'http://gedcomx.org/Interpreted'}]},
                        {type: 'http://gedcomx.org/County', values: [{text: 'Unorganized Territory', type: 'http://gedcomx.org/Interpreted'}]},
                        // Confirmed live: the 1860 sample uses MinorCivilDivision where the
                        // 1880 sample used Township for the same third-level-locality concept.
                        {type: 'http://gedcomx.org/MinorCivilDivision', values: [{text: 'On the Red River', type: 'http://gedcomx.org/Interpreted'}]},
                    ]}},
                    {type: 'http://gedcomx.org/Birth', place: {fields: [
                        {type: 'http://gedcomx.org/Place', values: [{text: 'Hudson Bay Tery.', type: 'http://gedcomx.org/Original'}]},
                    ]}},
                ],
                fields: [
                    {type: 'http://gedcomx.org/Age', values: [
                        {text: '32', type: 'http://gedcomx.org/Original'},
                        {text: '32', type: 'http://gedcomx.org/Interpreted'},
                    ]},
                    {type: 'http://familysearch.org/types/fields/HouseholdId', values: [{text: '1', type: 'http://gedcomx.org/Interpreted'}]},
                ],
                identifiers: {'http://gedcomx.org/Persistent': ['https://www.familysearch.org/ark:/61903/1:1:MF36-Z6D']},
            }],
        }],
    };
}

test('fsImageIndexFieldText: prefers the direct .value shortcut when present (facts[])', () => {
    assert.equal(fsImageIndexFieldText({type: 'http://gedcomx.org/Race', value: 'White'}), 'White');
});

test('fsImageIndexFieldText: prefers Interpreted over Original when digging into values[]', () => {
    const field = {values: [{text: 'Raw', type: 'http://gedcomx.org/Original'}, {text: 'Clean', type: 'http://gedcomx.org/Interpreted'}]};
    assert.equal(fsImageIndexFieldText(field), 'Clean');
});

test('fsImageIndexFieldText: takes the FIRST Interpreted value when multiple exist, not the last', () => {
    const field = {values: [
        {text: 'Self', type: 'http://gedcomx.org/Original'},
        {text: 'Head', type: 'http://gedcomx.org/Interpreted'},
        {text: 'Self', type: 'http://gedcomx.org/Interpreted'},
    ]};
    assert.equal(fsImageIndexFieldText(field), 'Head');
});

test('fsImageIndexFieldText: falls back to Original when no Interpreted value exists', () => {
    const field = {values: [{text: 'Raw only', type: 'http://gedcomx.org/Original'}]};
    assert.equal(fsImageIndexFieldText(field), 'Raw only');
});

test('fsImageIndexFieldText: returns empty string for null/missing field', () => {
    assert.equal(fsImageIndexFieldText(null), '');
    assert.equal(fsImageIndexFieldText({values: []}), '');
});

test('fsCanonicalFieldsFromImageIndexPerson: 1880-style person gets every rich field, head resolves to "Head"', () => {
    const data = makeImageIndex1880Response();
    const fields = fsCanonicalFieldsFromImageIndexPerson(data.records[0].persons[0]);
    assert.deepEqual(fields, {
        givenName: 'Prince A.', surname: 'Gatchill', sex: 'M', age: '38 years',
        birthplace: 'Maine, United States',
        householdIdSource: '8735134', householdIdFs: '',
        relationshipToHead: 'Head', maritalStatus: 'Married', occupation: 'Editor',
        race: 'White', fatherBirthplace: 'Maine, United States', motherBirthplace: 'Maine, United States',
    });
});

test('fsCanonicalFieldsFromImageIndexPerson: spouse with a clean single relationshipToHead value', () => {
    const data = makeImageIndex1880Response();
    const fields = fsCanonicalFieldsFromImageIndexPerson(data.records[0].persons[1]);
    assert.equal(fields.relationshipToHead, 'Wife');
    assert.equal(fields.givenName, 'Hattie O.');
    assert.equal(fields.householdIdSource, '8735134');
});

test('fsCanonicalFieldsFromImageIndexPerson: 1860-style person omits era-absent fields as empty strings, uses HouseholdId type', () => {
    const data = makeImageIndex1860Response();
    const fields = fsCanonicalFieldsFromImageIndexPerson(data.records[0].persons[0]);
    assert.equal(fields.relationshipToHead, '');
    assert.equal(fields.maritalStatus, '');
    assert.equal(fields.occupation, '');
    assert.equal(fields.fatherBirthplace, '');
    assert.equal(fields.motherBirthplace, '');
    assert.equal(fields.householdIdSource, '');
    assert.equal(fields.householdIdFs, '1');
    assert.equal(fields.givenName, 'Joseph');
    assert.equal(fields.race, 'White');
});

test('fsBuildRowsFromImageIndexResponse: builds one row per person, per-household sequencing, same columns shape as the orchestration-API path', () => {
    const rows = fsBuildRowsFromImageIndexResponse(makeImageIndex1880Response());
    assert.equal(rows.length, 2);
    const prince = rows.find(r => r.person_ark === '1:1:MCVW-PYP');
    assert.deepEqual(prince.columns, {
        'Given Name': 'Prince A.', 'Surname': 'Gatchill', 'Gender': 'M', 'Age': '38 years',
        'Family Number': '8735134', 'Relationship to Head': 'Head',
    });
    assert.equal(prince.attached_fsftid, '');
    const hattie = rows.find(r => r.person_ark === '1:1:MCVW-PY2');
    assert.equal(hattie.columns['Relationship to Head'], 'Wife');
    assert.equal(hattie.columns['Family Number'], '8735134');
});

test('fsBuildRowsFromImageIndexResponse: 1860-style row omits Relationship to Head entirely', () => {
    const rows = fsBuildRowsFromImageIndexResponse(makeImageIndex1860Response());
    assert.equal(rows.length, 1);
    assert.deepEqual(rows[0].columns, {
        'Given Name': 'Joseph', 'Surname': 'Kosses', 'Gender': 'M', 'Age': '32', 'Family Number': '1',
    });
    assert.ok(!('Relationship to Head' in rows[0].columns));
    assert.equal(rows[0].person_ark, '1:1:MF36-Z6D');
});

test('fsBuildRowsFromImageIndexResponse: empty records array produces no rows, no throw', () => {
    assert.deepEqual(fsBuildRowsFromImageIndexResponse({records: []}), []);
    assert.deepEqual(fsBuildRowsFromImageIndexResponse({}), []);
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `node --test Voyageur/tests/js/test_fs_image_index_parser.mjs`
Expected: FAIL — none of the four functions exist in `harness.js` yet.

- [ ] **Step 3: Implement the parser functions**

In `Voyageur/Voyageur.js`, add after Task 1's `fsBuildRowsFromApiResponse` (which now ends the file's FS-orchestration-API section):

```js
    // filmdatainfo/image-data parsing (the "Image Index" page's own data source, reached via
    // Image Browser/township navigation - confirmed live to be a completely different
    // endpoint from the orchestration API, never firing on the same page as it). Confirmed
    // live against two real captures: records[] is one entry PER HOUSEHOLD, each holding
    // {fields[] (record/citation-level admin data), persons[]}. Each person mixes two shapes:
    // facts[] entries carry a convenience .value alongside their fuller .fields[].values[]
    // backing data; fields[] entries (relationship, household id, parents' birthplace) have
    // no .value shortcut and must be read via .values[], preferring Interpreted over Original.

    // Prefers the FIRST Interpreted value when multiple exist - confirmed live this is
    // correct, not an arbitrary choice: the head-of-household's own RelationshipToHead field
    // carries a correction trail (Original "Self", then two Interpreted entries "Head" then
    // "Self") where the first Interpreted entry is the right one.
    function fsImageIndexFieldText(fieldOrFact) {
        if (!fieldOrFact) return '';
        if (typeof fieldOrFact.value === 'string') return fieldOrFact.value;
        const values = fieldOrFact.values || [];
        const interpreted = values.find((v) => v.type === 'http://gedcomx.org/Interpreted');
        if (interpreted) return interpreted.text || '';
        const original = values.find((v) => v.type === 'http://gedcomx.org/Original');
        return original ? (original.text || '') : '';
    }

    function fsImageIndexFindByType(list, type) {
        return (list || []).find((item) => item.type === type) || null;
    }

    function fsCanonicalFieldsFromImageIndexPerson(person) {
        const facts = (person && person.facts) || [];
        const fields = (person && person.fields) || [];

        const nameForm = person && person.names && person.names[0] && person.names[0].nameForms && person.names[0].nameForms[0];
        const parts = (nameForm && nameForm.parts) || [];
        const surnamePart = fsImageIndexFindByType(parts, 'http://gedcomx.org/Surname');
        const givenPart = fsImageIndexFindByType(parts, 'http://gedcomx.org/Given');

        const genderType = person && person.gender && person.gender.type;
        const sex = genderType === 'http://gedcomx.org/Male' ? 'M'
            : genderType === 'http://gedcomx.org/Female' ? 'F' : '';

        const birthFact = fsImageIndexFindByType(facts, 'http://gedcomx.org/Birth');
        const birthPlaceField = birthFact && birthFact.place
            ? fsImageIndexFindByType(birthFact.place.fields, 'http://gedcomx.org/Place') : null;

        return {
            givenName: givenPart ? (givenPart.value || '') : '',
            surname: surnamePart ? (surnamePart.value || '') : '',
            sex,
            age: fsImageIndexFieldText(fsImageIndexFindByType(fields, 'http://gedcomx.org/Age')),
            birthplace: fsImageIndexFieldText(birthPlaceField),
            // SourceHouseholdId and HouseholdId are confirmed distinct type URIs backing
            // SOURCE_HOUSEHOLD_ID and FS_HOUSEHOLD_ID respectively - same precedence
            // relationship as the orchestration API (see fsColumnsFromCanonicalFields).
            householdIdSource: fsImageIndexFieldText(fsImageIndexFindByType(fields, 'http://familysearch.org/types/fields/SourceHouseholdId')),
            householdIdFs: fsImageIndexFieldText(fsImageIndexFindByType(fields, 'http://familysearch.org/types/fields/HouseholdId')),
            relationshipToHead: fsImageIndexFieldText(fsImageIndexFindByType(fields, 'http://gedcomx.org/RelationshipToHead')),
            maritalStatus: fsImageIndexFieldText(fsImageIndexFindByType(facts, 'http://gedcomx.org/MaritalStatus')),
            occupation: fsImageIndexFieldText(fsImageIndexFindByType(facts, 'http://gedcomx.org/Occupation')),
            race: fsImageIndexFieldText(fsImageIndexFindByType(facts, 'http://gedcomx.org/Race')),
            fatherBirthplace: fsImageIndexFieldText(fsImageIndexFindByType(fields, 'http://familysearch.org/types/fields/FatherBirthPlace')),
            motherBirthplace: fsImageIndexFieldText(fsImageIndexFindByType(fields, 'http://familysearch.org/types/fields/MotherBirthPlace')),
        };
    }

    function fsBuildRowsFromImageIndexResponse(apiResponse) {
        const rows = [];
        const records = (apiResponse && apiResponse.records) || [];
        records.forEach((record, recordIndex) => {
            (record.persons || []).forEach((person) => {
                const canonicalFields = fsCanonicalFieldsFromImageIndexPerson(person);
                const columns = fsColumnsFromCanonicalFields(canonicalFields, recordIndex + 1);

                // identifiers[...][0] is a full URL (.../ark:/61903/1:1:XXXX-XXX) - extract
                // just the "1:1:XXXX-XXX" segment to match the orchestration-API path's own
                // person_ark convention (a bare ark, not a full URL).
                const identifierUrl = (person.identifiers
                    && person.identifiers['http://gedcomx.org/Persistent']
                    && person.identifiers['http://gedcomx.org/Persistent'][0]) || '';
                const arkMatch = identifierUrl.match(/(1:1:[A-Z0-9-]+)/);

                // Tree-attachment link shape not yet confirmed against a real tree-attached
                // person (see this plan's Task 2 notes) - left empty rather than guessed,
                // same "don't fabricate" convention as everywhere else in this file.
                rows.push({columns, person_ark: arkMatch ? arkMatch[1] : '', attached_fsftid: ''});
            });
        });
        return rows;
    }

```

- [ ] **Step 4: Update `module.exports`**

```js
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = {
            placesMatch, saveReloadState, loadReloadState, clearReloadState,
            buildFsElementIndex, fsFieldText, fsPersonFieldText, fsWrappedFieldText,
            fsPersonName, fsPersonBirthPlace, fsHouseholds, fsBuildRowsFromApiResponse,
            fsCanonicalFieldsFromApiPerson, fsColumnsFromCanonicalFields,
            fsImageIndexFieldText, fsImageIndexFindByType,
            fsCanonicalFieldsFromImageIndexPerson, fsBuildRowsFromImageIndexResponse,
        };
    }
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `node --test Voyageur/tests/js/test_fs_image_index_parser.mjs`
Expected: PASS, all 13 tests.

- [ ] **Step 6: Run the full JS suite to confirm nothing broke**

Run: `node --test Voyageur/tests/js/test_stop_conditions.mjs Voyageur/tests/js/test_fs_api_parser.mjs Voyageur/tests/js/test_fs_image_index_parser.mjs`
Expected: PASS, all tests (23 + 29 + 13 = 65).

- [ ] **Step 7: Syntax-check**

Run: `node --check Voyageur/Voyageur.js`
Expected: no output.

- [ ] **Step 8: Commit**

```bash
git add Voyageur/Voyageur.js Voyageur/tests/js/test_fs_image_index_parser.mjs
git commit -m "feat(voyageur): add pure parser for FamilySearch filmdatainfo/image-data responses"
```

---

### Task 3: Citation-text builder from JSON

**Files:**
- Modify: `Voyageur/Voyageur.js` (add after Task 2's additions)
- Test: `Voyageur/tests/js/test_fs_citation_builder.mjs` (new file)
- Modify: `module.exports` guard

**Interfaces:**
- Consumes: nothing from Tasks 1-2 directly (a sibling pure function operating on the same `filmdatainfo/image-data` response shape Task 2 parses, but independently).
- Produces: `fsImageIndexBrowsePathSegments(censusFact) -> [string]`, `fsBuildCitationTextFromImageIndexResponse(apiResponse, {imageNumber, imageTotal}) -> string`.

Builds the exact same prose `citation_text` format `FS.py`'s `parse_citation()`/`parse_nara_citing_clause()` already regex-parse (see `Voyageur/tests/test_fs.py`'s own fixture strings), entirely from JSON fields — `FS.py` is not touched by this task or this plan.

**Confirmed real gotcha to handle:** `EXT_REPOSITORY_NAME`'s real value includes a parenthetical suffix (`"The U.S. National Archives and Records Administration (NARA)"`), which breaks `NARA_CITING_RE`'s `repo_name` group (`[^,()]+`, which excludes parentheses) if inserted verbatim. Strip the trailing parenthetical before using it.

- [ ] **Step 1: Write the failing tests, replicating `FS.py`'s actual regexes**

Create `Voyageur/tests/js/test_fs_citation_builder.mjs`:

```js
import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { fsImageIndexBrowsePathSegments, fsBuildCitationTextFromImageIndexResponse } = require('./harness.js');

// Mirrors Voyageur/FS.py's own CITATION_RE and NARA_CITING_RE exactly - this IS the
// regression contract for this task (FS.py itself is never touched or run from here). Keep
// these two patterns in sync with FS.py by hand if either changes.
const CITATION_RE = /^"(?<collection_name>.+?),"\s+database with images,\s+(?<repository>.+?)\s*\(.*?\),\s*(?<browse_path>.+?);\s*(?<publisher>.+?),\s*(?<pub_loc>[^,]+?)\.\s*$/;
const NARA_CITING_RE = /citing\s+NARA\s+microfilm\s+publication\s+(?<publication>\S+?)\s*\((?<repo_loc>[^:()]+):\s*(?<repo_name>[^,()]+),\s*n\.d\.\)/i;

function make1880Response() {
    return {
        imageURL: 'https://www.familysearch.org/ark:/61903/3:1:33S7-9YBZ-XVG?cc=1417683',
        collections: [{collections: [{title: 'United States, Census, 1880'}]}],
        records: [{
            fields: [
                {type: 'http://familysearch.org/types/fields/FilmNbr', values: [{text: '1254114', type: 'http://gedcomx.org/Interpreted'}]},
                {type: 'http://familysearch.org/types/fields/ExtPubNbr', values: [{text: 'T9', type: 'http://gedcomx.org/Original'}]},
            ],
            persons: [{
                facts: [{type: 'http://gedcomx.org/Census', place: {fields: [
                    {type: 'http://gedcomx.org/State', values: [{text: 'Dakota Territory', type: 'http://gedcomx.org/Interpreted'}]},
                    {type: 'http://gedcomx.org/County', values: [{text: 'Pembina', type: 'http://gedcomx.org/Interpreted'}]},
                    {type: 'http://gedcomx.org/Township', values: [{text: 'Pembina', type: 'http://gedcomx.org/Interpreted'}]},
                    {type: 'http://gedcomx.org/District', values: [{text: 'ED 75', type: 'http://gedcomx.org/Original'}]},
                ]}}],
                fields: [
                    {type: 'http://familysearch.org/types/fields/ExtRepositoryName', values: [
                        {text: 'The U.S. National Archives and Records Administration (NARA)', type: 'http://gedcomx.org/Original'},
                    ]},
                ],
            }],
        }],
    };
}

test('fsImageIndexBrowsePathSegments: State > County > Township, with ED appended', () => {
    const censusFact = make1880Response().records[0].persons[0].facts[0];
    assert.deepEqual(fsImageIndexBrowsePathSegments(censusFact), ['Dakota Territory', 'Pembina', 'Pembina', 'ED 75']);
});

test('fsImageIndexBrowsePathSegments: falls back to MinorCivilDivision when Township is absent (1860-style)', () => {
    const censusFact = {type: 'http://gedcomx.org/Census', place: {fields: [
        {type: 'http://gedcomx.org/State', values: [{text: 'Dakota Territory', type: 'http://gedcomx.org/Interpreted'}]},
        {type: 'http://gedcomx.org/County', values: [{text: 'Unorganized Territory', type: 'http://gedcomx.org/Interpreted'}]},
        {type: 'http://gedcomx.org/MinorCivilDivision', values: [{text: 'On the Red River', type: 'http://gedcomx.org/Interpreted'}]},
    ]}};
    assert.deepEqual(fsImageIndexBrowsePathSegments(censusFact), ['Dakota Territory', 'Unorganized Territory', 'On the Red River']);
});

test('fsImageIndexBrowsePathSegments: missing census fact returns empty array, no throw', () => {
    assert.deepEqual(fsImageIndexBrowsePathSegments(null), []);
});

test('fsBuildCitationTextFromImageIndexResponse: produced string round-trips through CITATION_RE exactly like FS.py parses it', () => {
    const text = fsBuildCitationTextFromImageIndexResponse(make1880Response(), {imageNumber: 1, imageTotal: 6});
    const m = CITATION_RE.exec(text);
    assert.ok(m, `citation text did not match CITATION_RE: ${text}`);
    assert.equal(m.groups.collection_name, 'United States, Census, 1880');
    assert.equal(m.groups.repository, 'FamilySearch');
    assert.match(m.groups.browse_path, /Dakota Territory > Pembina > Pembina > ED 75 > image 1 of 6/);
});

test('fsBuildCitationTextFromImageIndexResponse: NARA clause round-trips through NARA_CITING_RE, repository name parenthetical stripped', () => {
    const text = fsBuildCitationTextFromImageIndexResponse(make1880Response(), {imageNumber: 1, imageTotal: 6});
    const m = NARA_CITING_RE.exec(text);
    assert.ok(m, `citation text did not match NARA_CITING_RE: ${text}`);
    assert.equal(m.groups.publication, '1254114');
    assert.equal(m.groups.repo_name, 'The U.S. National Archives and Records Administration');
    assert.equal(m.groups.repo_loc, 'Washington D.C.');
});

test('fsBuildCitationTextFromImageIndexResponse: omits the image-position segment when imageTotal is not provided (no JSON source, UI fallback missing)', () => {
    const text = fsBuildCitationTextFromImageIndexResponse(make1880Response(), {});
    assert.ok(!/image \d+ of \d+/.test(text));
    const m = CITATION_RE.exec(text);
    assert.ok(m, `citation text without image position still did not match CITATION_RE: ${text}`);
});

test('fsBuildCitationTextFromImageIndexResponse: empty records array returns empty string, no throw', () => {
    assert.equal(fsBuildCitationTextFromImageIndexResponse({records: []}, {}), '');
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `node --test Voyageur/tests/js/test_fs_citation_builder.mjs`
Expected: FAIL — functions not exported yet.

- [ ] **Step 3: Implement the citation builder**

In `Voyageur/Voyageur.js`, add after Task 2's `fsBuildRowsFromImageIndexResponse`:

```js
    // Prefers Township (the more common modern label) but falls back to MinorCivilDivision -
    // confirmed live these are the same third-level-locality concept under two different type
    // URIs depending on era/collection (1880 sample used Township, 1860 sample used
    // MinorCivilDivision for an identically-shaped place). Matches FS.py's own
    // parse_census_browse_path(), which reads browse-path segments positionally, not by an
    // explicit state/county/township prefix - so segment ORDER here (state, county, township,
    // then "ED n" appended last) must stay exactly this order.
    function fsImageIndexBrowsePathSegments(censusFact) {
        const placeFields = (censusFact && censusFact.place && censusFact.place.fields) || [];
        const state = fsImageIndexFieldText(fsImageIndexFindByType(placeFields, 'http://gedcomx.org/State'));
        const county = fsImageIndexFieldText(fsImageIndexFindByType(placeFields, 'http://gedcomx.org/County'));
        const township = fsImageIndexFieldText(fsImageIndexFindByType(placeFields, 'http://gedcomx.org/Township'))
            || fsImageIndexFieldText(fsImageIndexFindByType(placeFields, 'http://gedcomx.org/MinorCivilDivision'));
        const district = fsImageIndexFieldText(fsImageIndexFindByType(placeFields, 'http://gedcomx.org/District'));
        const segments = [state, county, township].filter(Boolean);
        if (district) segments.push(`ED ${district}`);
        return segments;
    }

    // Builds the same prose citation_text string FS.py's parse_citation()/
    // parse_nara_citing_clause() already regex-parse (Voyageur/FS.py CITATION_RE/
    // NARA_CITING_RE) - entirely from JSON fields, so the Image-Index extraction path never
    // depends on scrapeCitationAndCatalog()'s UI read. imageNumber/imageTotal come from the
    // caller (the one remaining UI fallback in this whole plan - no JSON source for the total
    // image count was found in this endpoint's response).
    function fsBuildCitationTextFromImageIndexResponse(apiResponse, {imageNumber, imageTotal} = {}) {
        const record = ((apiResponse && apiResponse.records) || [])[0];
        if (!record) return '';
        const headPerson = (record.persons || [])[0];
        const recordFields = record.fields || [];
        const personFields = headPerson ? (headPerson.fields || []) : [];

        const collectionName = ((apiResponse.collections || [])[0]
            && apiResponse.collections[0].collections
            && apiResponse.collections[0].collections[0]
            && apiResponse.collections[0].collections[0].title) || '';
        const url = apiResponse.imageURL || '';
        const date = new Date().toLocaleDateString('en-US', {day: 'numeric', month: 'long', year: 'numeric'});

        const censusFact = headPerson ? fsImageIndexFindByType(headPerson.facts || [], 'http://gedcomx.org/Census') : null;
        const browsePath = fsImageIndexBrowsePathSegments(censusFact);
        if (imageNumber && imageTotal) browsePath.push(`image ${imageNumber} of ${imageTotal}`);

        const publication = fsImageIndexFieldText(fsImageIndexFindByType(recordFields, 'http://familysearch.org/types/fields/FilmNbr'))
            || fsImageIndexFieldText(fsImageIndexFindByType(recordFields, 'http://familysearch.org/types/fields/DigitalFilmNbr'));
        const rawRepoName = fsImageIndexFieldText(fsImageIndexFindByType(personFields, 'http://familysearch.org/types/fields/ExtRepositoryName'));
        // Confirmed live: the real value carries a trailing "(NARA)" that would otherwise
        // break NARA_CITING_RE's repo_name group ([^,()]+ - excludes parentheses).
        const repoName = rawRepoName.replace(/\s*\([^)]*\)\s*$/, '').trim();
        // NARA repository location - no matching JSON field found in either captured sample
        // (see design spec's "Not yet verified" list). Hardcoded: every US census NARA
        // microfilm citation this project has observed cites this same physical archive
        // location regardless of the specific record.
        const repoLoc = 'Washington D.C.';

        let text = `"${collectionName}," database with images, FamilySearch (${url} : ${date}), ${browsePath.join(' > ')}`;
        if (publication && repoName) {
            text += `; citing NARA microfilm publication ${publication} (${repoLoc}: ${repoName}, n.d.).`;
        } else {
            text += '.';
        }
        return text;
    }

```

- [ ] **Step 4: Update `module.exports`**

```js
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = {
            placesMatch, saveReloadState, loadReloadState, clearReloadState,
            buildFsElementIndex, fsFieldText, fsPersonFieldText, fsWrappedFieldText,
            fsPersonName, fsPersonBirthPlace, fsHouseholds, fsBuildRowsFromApiResponse,
            fsCanonicalFieldsFromApiPerson, fsColumnsFromCanonicalFields,
            fsImageIndexFieldText, fsImageIndexFindByType,
            fsCanonicalFieldsFromImageIndexPerson, fsBuildRowsFromImageIndexResponse,
            fsImageIndexBrowsePathSegments, fsBuildCitationTextFromImageIndexResponse,
        };
    }
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `node --test Voyageur/tests/js/test_fs_citation_builder.mjs`
Expected: PASS, all 7 tests.

- [ ] **Step 6: Run the full JS suite**

Run: `node --test Voyageur/tests/js/test_stop_conditions.mjs Voyageur/tests/js/test_fs_api_parser.mjs Voyageur/tests/js/test_fs_image_index_parser.mjs Voyageur/tests/js/test_fs_citation_builder.mjs`
Expected: PASS, all 72 tests.

- [ ] **Step 7: Syntax-check**

Run: `node --check Voyageur/Voyageur.js`
Expected: no output.

- [ ] **Step 8: Commit**

```bash
git add Voyageur/Voyageur.js Voyageur/tests/js/test_fs_citation_builder.mjs
git commit -m "feat(voyageur): build FS citation text from JSON instead of UI scraping"
```

---

### Task 4: Interceptor and response-wait glue

**Files:**
- Modify: `Voyageur/Voyageur.js` (inside `runFamilySearchGather()`, immediately after the existing orchestration-API interceptor block)

**Interfaces:**
- Consumes: nothing from Tasks 1-3 (the interceptor just stores raw parsed JSON, the same as the existing orchestration-API interceptor).
- Produces: `waitForFsImageIndexResponse(ark, {timeoutMs}) -> Promise<{result: object|null, timedOut: boolean, elapsedMs: number}>`.

Mirrors the existing orchestration-API interceptor's pattern exactly (double-install guard, per-ark waiter map, event-driven resolution — the corrected pattern from that interceptor's own fix round, not a polling `waitForCondition()` call). The one structural difference: `filmdatainfo/image-data`'s request URL is the same generic string for every image, so responses are keyed by the **response body's own `arkId` field**, not the request URL.

- [ ] **Step 1: Add the interceptor and wait function**

In `Voyageur/Voyageur.js`, inside `runFamilySearchGather()`, immediately after the closing `}` of the existing orchestration-API interceptor block (the one ending with `unsafeWindow.fetch = async function (...args) { ... };\n        }` — locate it by searching for `__voyageurFsApiWaiters` and finding the block's closing brace, do not trust literal line numbers, they will have shifted from Tasks 1-3 above):

```js
        // Same technique as the orchestration-API interceptor just above, targeting
        // filmdatainfo/image-data instead - confirmed live this endpoint's request URL is
        // identical for every image ("/search/filmdatainfo/image-data", no per-image query
        // param), so responses can't be keyed by URL the way the orchestration API's can.
        // Keyed by the response BODY's own arkId field instead.
        if (typeof unsafeWindow !== 'undefined' && !unsafeWindow.__voyageurFsImageIndexIntercepted) {
            unsafeWindow.__voyageurFsImageIndexIntercepted = true;
            unsafeWindow.__voyageurFsImageIndexResponses = {};
            unsafeWindow.__voyageurFsImageIndexWaiters = {};

            const FS_IMAGE_INDEX_TARGET = '/search/filmdatainfo/image-data';

            function storeFsImageIndexResponse(bodyText) {
                let parsed;
                try {
                    parsed = JSON.parse(bodyText);
                } catch (e) {
                    // Leave unset - waitForFsImageIndexResponse() below times out the same as
                    // "never arrived", the correct behavior for an unparseable response.
                    return;
                }
                const ark = parsed && parsed.arkId;
                if (!ark) return;
                unsafeWindow.__voyageurFsImageIndexResponses[ark] = parsed;
                const waiter = unsafeWindow.__voyageurFsImageIndexWaiters[ark];
                if (waiter) waiter(parsed);
            }

            const origImageIndexXhrOpen = unsafeWindow.XMLHttpRequest.prototype.open;
            unsafeWindow.XMLHttpRequest.prototype.open = function (method, url) {
                this.__voyageurFsImageIndexUrl = url;
                this.addEventListener('load', function () {
                    if (this.__voyageurFsImageIndexUrl && this.__voyageurFsImageIndexUrl.includes(FS_IMAGE_INDEX_TARGET)) {
                        storeFsImageIndexResponse(this.responseText);
                    }
                });
                return origImageIndexXhrOpen.apply(this, arguments);
            };

            const origImageIndexFetch = unsafeWindow.fetch;
            unsafeWindow.fetch = async function (...args) {
                const url = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url) || '';
                const resp = await origImageIndexFetch.apply(this, args);
                if (url.includes(FS_IMAGE_INDEX_TARGET)) {
                    resp.clone().text().then((t) => storeFsImageIndexResponse(t));
                }
                return resp;
            };
        }

        // Same event-driven-with-timeout-fallback shape as waitForFsApiResponse above.
        async function waitForFsImageIndexResponse(ark, {timeoutMs = 15000} = {}) {
            const startedAt = performance.now();
            const existing = (unsafeWindow.__voyageurFsImageIndexResponses || {})[ark];
            if (existing) {
                return {result: existing, elapsedMs: 0, timedOut: false};
            }
            return new Promise((resolve) => {
                let settled = false;
                const timer = setTimeout(() => {
                    if (settled) return;
                    settled = true;
                    delete unsafeWindow.__voyageurFsImageIndexWaiters[ark];
                    resolve({result: null, elapsedMs: Math.round(performance.now() - startedAt), timedOut: true});
                }, timeoutMs);
                unsafeWindow.__voyageurFsImageIndexWaiters[ark] = (result) => {
                    if (settled) return;
                    settled = true;
                    clearTimeout(timer);
                    delete unsafeWindow.__voyageurFsImageIndexWaiters[ark];
                    resolve({result, elapsedMs: Math.round(performance.now() - startedAt), timedOut: false});
                };
            });
        }
```

**Important note on chaining the two XHR/fetch patches:** because this interceptor is installed AFTER the orchestration-API one inside the same function, each patch wraps the previous patch's function (`origImageIndexXhrOpen`/`origImageIndexFetch` capture the orchestration-API interceptor's own already-patched `open`/`fetch`, not the browser's native ones) — this is correct and required, matching how the orchestration-API interceptor itself already wraps the file's Ancestry interceptor pattern. Do not "flatten" this into a single combined patch; the double-wrap is intentional and already proven safe by the existing code.

- [ ] **Step 2: Syntax-check**

Run: `node --check Voyageur/Voyageur.js`
Expected: no output.

- [ ] **Step 3: Run the full JS suite**

Run: `node --test Voyageur/tests/js/test_stop_conditions.mjs Voyageur/tests/js/test_fs_api_parser.mjs Voyageur/tests/js/test_fs_image_index_parser.mjs Voyageur/tests/js/test_fs_citation_builder.mjs`
Expected: PASS, all 72 tests (this task adds no new pure functions to test — same reasoning as the existing orchestration-API interceptor: `unsafeWindow`-dependent code doesn't execute under `require()`).

- [ ] **Step 4: Bump `@version`**

Check the current `// @version` value first (this plan was written against `0.3.24`; earlier tasks in this plan don't bump it, so it should still read `0.3.24` — but confirm) and increment the patch component.

- [ ] **Step 5: Commit**

```bash
git add Voyageur/Voyageur.js
git commit -m "feat(voyageur): intercept FamilySearch filmdatainfo/image-data responses"
```

---

### Task 5: Page-type detection and wire into `scrapeCurrentImage()`

**Files:**
- Modify: `Voyageur/Voyageur.js` — `scrapeCurrentImage()` (locate by function-name search, not literal line numbers — Tasks 1-4 will have shifted everything below their insertion points)

**Interfaces:**
- Consumes: `fsBuildRowsFromApiResponse`/`waitForFsApiResponse` (existing, unchanged), `fsBuildRowsFromImageIndexResponse`/`waitForFsImageIndexResponse` (Tasks 2 and 4), `fsBuildCitationTextFromImageIndexResponse` (Task 3), `findByExactText` (existing, unchanged).
- Produces: nothing new — this is the wiring task that makes Tasks 1-4 load-bearing.

This is the only task that changes actual gather behavior for the user. Everything before this task is inert (new functions exist but nothing calls them on the Image-Index path).

- [ ] **Step 1: Add the page-type detection helper**

In `Voyageur/Voyageur.js`, immediately before `scrapeCurrentImage()`:

```js
        // Runs once per image, before either data source is awaited. Names/Image Index tab
        // presence is the ground truth of which page actually rendered - confirmed live this
        // is a navigation-method split (Search -> Names panel, Image Browser -> Image Index),
        // not something inferable from the URL. Event-driven via the existing
        // waitForCondition convention, same as clickTab() above.
        async function detectFsPageType({timeoutMs = 15000} = {}) {
            const wait = await waitForCondition(() => {
                if (findByExactText('[role="tab"], button, a', 'Names')) return 'names';
                if (findByExactText('[role="tab"], button, a', 'Image Index')) return 'image-index';
                return null;
            }, {timeoutMs});
            return wait.result;
        }

```

- [ ] **Step 2: Replace `scrapeCurrentImage()`**

Locate the current `scrapeCurrentImage()` (search for `async function scrapeCurrentImage`). Current body:

```js
        async function scrapeCurrentImage() {
            const itemId = getItemId();
            if (!itemId || seenItemIds.has(itemId)) return;

            const apiWait = await waitForFsApiResponse(itemId);
            let rows = [];
            if (apiWait.result) {
                rows = fsBuildRowsFromApiResponse(apiWait.result);
            } else {
                debugLog(`No orchestration-API response arrived for item ${itemId} after `
                    + `${apiWait.elapsedMs}ms - continuing with no household data for this image.`);
                if (window.fsShowToast) {
                    window.fsShowToast('No index data received for this image - skipping.', 'error', 4000);
                }
            }

            const {citationText, catalogItems} = await scrapeCitationAndCatalog();
            // Awaited before moving on to the next image, same convention as Ancestry's
            // own per-page image download.
            await downloadFsImage(itemId);

            seenItemIds.add(itemId);
            accumulatedItems.push({item_id: itemId, citation_text: citationText, catalog_items: catalogItems, rows});

            debugLog(`Scraped item ${itemId}: ${rows.length} index rows.`);
        }
```

Replace with:

```js
        async function scrapeCurrentImage() {
            const itemId = getItemId();
            if (!itemId || seenItemIds.has(itemId)) return;

            const pageType = await detectFsPageType();
            let rows = [];
            let citationText = '';
            let catalogItems = [];

            if (pageType === 'image-index') {
                const apiWait = await waitForFsImageIndexResponse(itemId);
                if (apiWait.result) {
                    rows = fsBuildRowsFromImageIndexResponse(apiWait.result);
                    // The one UI read left in this whole plan: no JSON source for the total
                    // image count was found on this endpoint (see the design spec's "Not yet
                    // verified" list) - the page already renders it plainly ("Image 1 of 3").
                    const imageMatch = document.body.innerText.match(/Image\s+(\d+)\s+of\s+(\d+)/i);
                    citationText = fsBuildCitationTextFromImageIndexResponse(apiWait.result, {
                        imageNumber: imageMatch ? imageMatch[1] : undefined,
                        imageTotal: imageMatch ? imageMatch[2] : undefined,
                    });
                } else {
                    debugLog(`No Image-Index response arrived for item ${itemId} after `
                        + `${apiWait.elapsedMs}ms - continuing with no household data for this image.`);
                    if (window.fsShowToast) {
                        window.fsShowToast('No index data received for this image - skipping.', 'error', 4000);
                    }
                }
                // Still used for catalogItems (the Film/Digital Note table) - its own
                // citationText is discarded in favor of the JSON-built one above; both page
                // types share the same "Information" tab UI shell this function reads.
                const catalog = await scrapeCitationAndCatalog();
                catalogItems = catalog.catalogItems;
            } else if (pageType === 'names') {
                const apiWait = await waitForFsApiResponse(itemId);
                if (apiWait.result) {
                    rows = fsBuildRowsFromApiResponse(apiWait.result);
                } else {
                    debugLog(`No orchestration-API response arrived for item ${itemId} after `
                        + `${apiWait.elapsedMs}ms - continuing with no household data for this image.`);
                    if (window.fsShowToast) {
                        window.fsShowToast('No index data received for this image - skipping.', 'error', 4000);
                    }
                }
                const citation = await scrapeCitationAndCatalog();
                citationText = citation.citationText;
                catalogItems = citation.catalogItems;
            } else {
                debugLog(`Neither Names nor Image Index tab found for item ${itemId} - `
                    + 'unrecognized page shape, continuing with no data.');
                if (window.fsShowToast) {
                    window.fsShowToast('Unrecognized page - skipping.', 'error', 4000);
                }
            }

            // Awaited before moving on to the next image, same convention as Ancestry's
            // own per-page image download.
            await downloadFsImage(itemId);

            seenItemIds.add(itemId);
            accumulatedItems.push({item_id: itemId, citation_text: citationText, catalog_items: catalogItems, rows});

            debugLog(`Scraped item ${itemId}: ${rows.length} index rows.`);
        }
```

- [ ] **Step 3: Syntax-check**

Run: `node --check Voyageur/Voyageur.js`
Expected: no output.

- [ ] **Step 4: Run the full JS suite**

Run: `node --test Voyageur/tests/js/test_stop_conditions.mjs Voyageur/tests/js/test_fs_api_parser.mjs Voyageur/tests/js/test_fs_image_index_parser.mjs Voyageur/tests/js/test_fs_citation_builder.mjs`
Expected: PASS, all 72 tests (this task is wiring only, no new pure functions to test — a regression check, not new coverage).

- [ ] **Step 5: Bump `@version`**

Increment the patch component (this task ships a real, user-visible behavior change — the Image Browser path is now live).

- [ ] **Step 6: Commit**

```bash
git add Voyageur/Voyageur.js
git commit -m "feat(voyageur): wire Image-Index extraction into the FS gather loop"
```

---

### Task 6: Live verification (not delegable to a subagent, and not to be driven via Chrome automation)

**Files:** none (verification only, no code changes)

**Interfaces:** none.

This task cannot be executed by a coding subagent (requires an authenticated FamilySearch session and a real browser), and per this project's own established finding, must not be driven through Claude-controlled Chrome automation either — the gather loop is timing-sensitive (`MutationObserver`-based waits, XHR/fetch interception, real page navigation), and a Claude-driven or backgrounded tab inflates `setTimeout` timing 20x+, which would give a false read on exactly the kind of interceptor-timing behavior this task exists to verify. Run this task in a real, user-driven browser session.

- [ ] **Step 1: Verify on an 1880+ record reached via Image Browser**

Navigate to a known 1880+ census record via Image Browser (township navigation, not name search) — confirming the "Image Index" tab, not "Names", is what's showing. Trigger the gather via `?mgs_auto=1&mgs_run=<id>`, let it scrape at least one image, inspect the console log / downloaded JSON.

Expected: `rows` contains real names/ages, at least some rows include a `Relationship to Head` value, `citation_text` is a real, non-empty string in the same prose shape as an existing UI-scraped one (visually compare against a citation_text from a prior Names-panel gather).

- [ ] **Step 2: Verify on a pre-1880 record reached via Image Browser**

Same navigation method, a known 1850/1860/1870 record.

Expected: `rows` contains real names/ages, **no row has a `Relationship to Head` key at all** (genuinely absent, not blank).

- [ ] **Step 3: Verify the citation text actually parses correctly in `FS.py`**

Take one real `citation_text` string from Step 1 or 2's downloaded JSON and run it through `FS.py`'s actual `parse_citation()`/`parse_nara_citing_clause()` (e.g., a one-off Python REPL check: `from Voyageur.FS import parse_citation, parse_nara_citing_clause; parse_citation("<the real string>")`), confirming `repository`, `collection_name`, `browse_path` come out non-empty and sensible, and (if the record cites NARA) `parse_nara_citing_clause()` finds a real `publication`/`repository`/`repository_loc` — not just that the regex matched, but that the captured values are correct.

Expected: all fields populated correctly, no `NARA_CITING_RE` mismatch from the `EXT_REPOSITORY_NAME` parenthetical (Task 3's specific fix for this).

- [ ] **Step 4: Verify multi-image continuation still works on the Image Browser path**

Let the gather run across at least 3 images via Image Browser, confirming all 3 images' data survives into the final downloaded JSON.

Expected: downloaded JSON's `items` array has 3 entries, each with non-empty `rows`.

- [ ] **Step 5: Verify switching between Names panel and Image Index mid-run doesn't break anything**

If practical, run a gather that starts on a Names-panel record then advances into a collection/navigation that lands on an Image-Index page (or vice versa) — confirming `scrapeCurrentImage()`'s per-image page-type detection handles a mixed run correctly rather than assuming one page type for the whole batch.

Expected: both page types' rows appear correctly in the same downloaded JSON, no crash, no silently-empty rows on the page type that wasn't the first one encountered.

- [ ] **Step 6: If any step fails, do not close out this plan until root-caused**

Given this plan's whole premise came from discovering that untested assumptions about FamilySearch's page behavior don't generalize, a clean pass here is worth real scrutiny — but Tasks 1-5's unit tests already cover the parsing/building logic in isolation against real captured data, so this task exists specifically to confirm the *live wiring* (interceptor timing, page-type detection, real navigation), which unit tests structurally cannot cover.

---

## Self-Review Notes (from the plan author, not a task)

**Spec coverage:** Every numbered Architecture component in the spec (`docs/superpowers/specs/2026-08-14-fs-image-index-extraction-design.md`) maps to a task: canonical-field extraction + shared builder (Task 1), Image-Index person parser (Task 2), citation-text builder (Task 3), interceptor (Task 4), page-type detection + wiring (Task 5), live verification (Task 6). The spec's "Not yet verified" items (`attached_fsftid` derivation, orchestration-API standard-type-URI check, NARA repository location, total image count) are each explicitly carried into the relevant task as an honest gap, not silently resolved by guessing.

**Corrections made during planning that go beyond the spec's own stated structure** (the spec's Architecture section described the shape at a conceptual level; this plan's research nailed the precise real structure against two full real captures, not just the earlier scattered snippets the spec was written from): `filmdatainfo/image-data`'s actual top-level shape is `{records[] (one per household), recordList, collections, imageURL, arkId}`, not a flat `persons[]` array; each person mixes `facts[]` (has a `.value` shortcut) and a separate `fields[]` array (no shortcut, needs `.values[]`); household ID, `RelationshipToHead`, and parents'-birthplace live in `person.fields[]`, not `person.facts[]`; citation-relevant fields (`FilmNbr`, `ExtPubNbr`, `DigitalFilmNbr`) live in `record.fields[]` (household/citation level), not per-person; `EXT_REPOSITORY_NAME` is per-person only, read from the household's first-listed person. None of these contradict the spec's own claims — the spec was appropriately high-level; this plan is where implementation-precise structure belongs.

**Placeholder scan:** No TBD/TODO in any task step. Every code block is real, complete code verified against actual captured live data, not described-but-unwritten. The two genuinely unconfirmed values (NARA repository location, total image count) are implemented with an explicit, reasoned fallback (a documented constant; a UI read) rather than left as gaps.

**Type consistency:** `fsColumnsFromCanonicalFields` (Task 1) is called by both `fsBuildRowsFromApiResponse` (Task 1, refactored) and `fsBuildRowsFromImageIndexResponse` (Task 2) with the identical signature `(canonicalFields, sequenceFallback) -> columns`. `fsCanonicalFieldsFromApiPerson`/`fsCanonicalFieldsFromImageIndexPerson` both return the identical 12-key canonical shape. `waitForFsImageIndexResponse` (Task 4) matches `waitForFsApiResponse`'s exact return shape `{result, elapsedMs, timedOut}`. `fsBuildRowsFromImageIndexResponse` (Task 2) matches `fsBuildRowsFromApiResponse`'s exact return shape `[{columns, person_ark, attached_fsftid}]`, consumed identically by `scrapeCurrentImage()` (Task 5) regardless of which path produced it.
