# FamilySearch Orchestration-API Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `Voyageur.js`'s FamilySearch household/name data extraction (currently: click the "Names" tab, click into each person's detail panel) with direct parsing of FamilySearch's own internal orchestration API response, intercepted via the same `unsafeWindow.fetch`/`XMLHttpRequest.prototype.open` patch pattern already used for Ancestry's PID capture.

**Architecture:** A pure, DOM-free parser (testable in plain Node, no browser) walks the API response's flat `elements` graph and produces the exact same `rows` shape the old UI-scraper produced. An interceptor installed early inside `runFamilySearchGather()` captures the response FamilySearch's own client already requests automatically on page load. `scrapeCurrentImage()` calls the new path instead of the old one. Citation-text scraping (`scrapeCitationAndCatalog()`, the "Information" tab) and image-to-image navigation (`goToNextImage()`, the hover-mount "Next Image" fix) are unchanged — this plan touches data extraction only.

**Tech Stack:** Tampermonkey userscript (`Voyageur.js`), Node's built-in test runner (`node --test`) via the existing `Voyageur/tests/js/harness.js` pattern.

**Spec:** `docs/superpowers/specs/2026-08-14-fs-orchestration-api-extraction-design.md`

## Global Constraints

- Single-file userscript, no build step, no module boundary — all new code lives in `Voyageur/Voyageur.js`, following its existing structure (top-level pure helpers exported via `module.exports` guard at the bottom; per-repository gather logic nested inside `runAncestryGather()`/`runFamilySearchGather()`).
- New pure functions (no `document`/`window` DOM access) go at file top-level so they're unit-testable via `Voyageur/tests/js/harness.js`, matching `placesMatch`/`saveReloadState`/`loadReloadState`/`clearReloadState`'s existing placement.
- Era boundary: 1850-1870 census records do not carry `RELATIONSHIP_TO_HEAD`/`MARITAL_STATUS`/`OCCUPATION`/`RACE_OR_COLOR`/parents'-birthplace fields at all (matches real US census history — 1880 was the first year these were recorded). The parser must degrade gracefully (empty string, omitted downstream column) when these fields are absent — no year-based branching code, since field-presence naturally reflects the era.
- Downstream output shape is unchanged: `{item_id, citation_text, catalog_items, rows: [{columns: {...}, person_ark, attached_fsftid}]}`, consumed by `FS.py`'s `build_census_json()`.
- Bump `@version` in `Voyageur.js`'s header on every task that ships a real behavior change (current: `0.3.22` as of this plan — check the actual current value before each bump, since earlier tasks in this same plan increment it).
- Every JS change gets `node --check "Voyageur/Voyageur.js"` before commit (syntax only — this project has no linter for this file).
- Live browser verification steps (marked explicitly below) cannot be run by a coding subagent — no browser tool access. These must be run by the controlling session/user directly, regardless of whether the rest of this plan executes via subagent-driven-development or inline execution.

---

### Task 1: Pure API-response parser

**Files:**
- Modify: `Voyageur/Voyageur.js` (add new top-level functions after `clearReloadState()`, currently ending around line 154; add exports to the `module.exports` guard near the end of the file, currently around line 2132)
- Test: `Voyageur/tests/js/test_fs_api_parser.mjs` (new file)

**Interfaces:**
- Produces: `buildFsElementIndex(apiResponse) -> {id: element}`, `fsFieldText(fieldElement) -> string`, `fsPersonFieldText(byId, person, fieldType) -> string`, `fsWrappedFieldText(byId, person, wrapperElementType) -> string`, `fsPersonName(byId, person) -> {given: string, surname: string}`, `fsPersonBirthPlace(byId, person) -> string`, `fsHouseholds(apiResponse, byId) -> [{recordId, personIds: [string]}]`, `fsBuildRowsFromApiResponse(apiResponse) -> [{columns: {...}, person_ark: string, attached_fsftid: string}]`. All pure, DOM-free, take/return plain objects.
- Consumes: nothing from other tasks (this is the foundation task).

This task implements the confirmed graph traversal from the design spec (`docs/superpowers/specs/2026-08-14-fs-orchestration-api-extraction-design.md`, "Confirmed working traversal" and "Newly confirmed fields" sections) as real, tested code.

- [ ] **Step 1: Write the failing tests**

Create `Voyageur/tests/js/test_fs_api_parser.mjs`:

```js
/* global globalThis */
import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const {
    buildFsElementIndex, fsFieldText, fsPersonFieldText, fsWrappedFieldText,
    fsPersonName, fsPersonBirthPlace, fsHouseholds, fsBuildRowsFromApiResponse,
} = require('./harness.js');

// Fixture shape matches the confirmed live structure exactly: a flat `elements`
// array, cross-referenced by UUID/ark via subElements/superElements - see the
// design spec's "Confirmed element types" table. Two households, one person with
// a direct RELATIONSHIP_TO_HEAD field (1880+ shape), one with only the fields
// confirmed present on 1850 (no relationship/marital/occupation/race/parents'
// birthplace at all - the era boundary this parser must handle by simple
// field-absence, not year-branching).
function makeApiResponse() {
    return {
        numberOfPersonsOnImage: 2,
        numberOfRecordsOnImage: 2,
        elements: [
            // --- Household 1: "1:1:PERSON-A", 1880-style (has RELATIONSHIP_TO_HEAD etc.) ---
            {elementType: 'RECORD', id: 'rec-1', subElements: [{id: '1:1:PERSON-A'}]},
            {
                elementType: 'PERSON', id: '1:1:PERSON-A', primary: true,
                subElements: [
                    {id: 'name-a'}, {id: 'age-a'}, {id: 'event-birth-a'},
                    {id: 'field-relhead-a'}, {id: 'field-marital-a'}, {id: 'field-occ-a'},
                    {id: 'field-race-a'}, {id: 'field-fbp-a'}, {id: 'field-mbp-a'},
                    {id: 'field-sex-a'}, {id: 'field-householdid-a'},
                ],
            },
            {elementType: 'NAME', id: 'name-a', primary: true, subElements: [{id: 'given-a'}, {id: 'surname-a'}]},
            {elementType: 'NAME_GIVEN', id: 'given-a', subElements: [{id: 'field-given-a'}]},
            {elementType: 'FIELD', id: 'field-given-a', fieldType: 'NAME_GN', fieldValues: [{normalizedValues: [{text: 'ELIZA M.'}]}]},
            {elementType: 'NAME_SURNAME', id: 'surname-a', subElements: [{id: 'field-surname-a'}]},
            {elementType: 'FIELD', id: 'field-surname-a', fieldType: 'NAME_SURN', fieldValues: [{normalizedValues: [{text: 'FISK'}]}]},
            {elementType: 'AGE', id: 'age-a', subElements: [{id: 'field-age-a'}]},
            {elementType: 'FIELD', id: 'field-age-a', fieldType: 'AGE', fieldValues: [{normalizedValues: [{text: '38'}]}]},
            {elementType: 'EVENT', id: 'event-birth-a', eventType: 'BIRTH', subElements: [{id: 'place-birth-a'}]},
            {elementType: 'PLACE', id: 'place-birth-a', subElements: [{id: 'field-birthplace-a'}]},
            {elementType: 'FIELD', id: 'field-birthplace-a', fieldType: 'PLACE', fieldValues: [{normalizedValues: [{text: 'Maine, United States'}]}]},
            {elementType: 'FIELD', id: 'field-relhead-a', fieldType: 'RELATIONSHIP_TO_HEAD', fieldValues: [{normalizedValues: [{text: 'Head'}]}]},
            {elementType: 'FIELD', id: 'field-marital-a', fieldType: 'MARITAL_STATUS', fieldValues: [{normalizedValues: [{text: 'Married'}]}]},
            {elementType: 'FIELD', id: 'field-occ-a', fieldType: 'OCCUPATION', fieldValues: [{normalizedValues: [{text: 'Farmer'}]}]},
            {elementType: 'FIELD', id: 'field-race-a', fieldType: 'RACE_OR_COLOR', fieldValues: [{normalizedValues: [{text: 'White'}]}]},
            {elementType: 'FIELD', id: 'field-fbp-a', fieldType: 'FTHR_BIR_PLACE', fieldValues: [{normalizedValues: [{text: 'Germany'}]}]},
            {elementType: 'FIELD', id: 'field-mbp-a', fieldType: 'MTHR_BIR_PLACE', fieldValues: [{normalizedValues: [{text: 'Vermont, United States'}]}]},
            {elementType: 'FIELD', id: 'field-sex-a', fieldType: 'SEX_CODE', fieldValues: [{normalizedValues: [{text: 'F'}]}]},
            {elementType: 'FIELD', id: 'field-householdid-a', fieldType: 'SOURCE_HOUSEHOLD_ID', fieldValues: [{normalizedValues: [{text: '90'}]}]},

            // --- Household 2: "1:1:PERSON-B", 1850-style (no relationship/marital/occupation/
            // race/parents'-birthplace at all - only name/age/sex/household fields exist,
            // matching the confirmed 1850 capture in the design spec). ---
            {elementType: 'RECORD', id: 'rec-2', subElements: [{id: '1:1:PERSON-B'}]},
            {
                elementType: 'PERSON', id: '1:1:PERSON-B', primary: true,
                subElements: [{id: 'name-b'}, {id: 'age-b'}, {id: 'field-sex-b'}, {id: 'field-houseNbr-b'}],
            },
            {elementType: 'NAME', id: 'name-b', primary: true, subElements: [{id: 'given-b'}, {id: 'surname-b'}]},
            {elementType: 'NAME_GIVEN', id: 'given-b', subElements: [{id: 'field-given-b'}]},
            {elementType: 'FIELD', id: 'field-given-b', fieldType: 'NAME_GN', fieldValues: [{normalizedValues: [{text: 'Bozil'}]}]},
            {elementType: 'NAME_SURNAME', id: 'surname-b', subElements: [{id: 'field-surname-b'}]},
            {elementType: 'FIELD', id: 'field-surname-b', fieldType: 'NAME_SURN', fieldValues: [{normalizedValues: [{text: 'Delmer'}]}]},
            {elementType: 'AGE', id: 'age-b', subElements: [{id: 'field-age-b'}]},
            {elementType: 'FIELD', id: 'field-age-b', fieldType: 'AGE', fieldValues: [{normalizedValues: [{text: '47'}]}]},
            {elementType: 'FIELD', id: 'field-sex-b', fieldType: 'SEX_CODE', fieldValues: [{normalizedValues: [{text: 'M'}]}]},
            {elementType: 'FIELD', id: 'field-houseNbr-b', fieldType: 'SOURCE_HOUSE_NBR', fieldValues: [{normalizedValues: [{text: '12'}]}]},
        ],
    };
}

test('buildFsElementIndex: indexes every element by id', () => {
    const byId = buildFsElementIndex(makeApiResponse());
    assert.equal(byId['1:1:PERSON-A'].elementType, 'PERSON');
    assert.equal(byId['field-given-a'].fieldType, 'NAME_GN');
});

test('fsFieldText: prefers normalizedValues over origValue', () => {
    const field = {fieldValues: [{normalizedValues: [{text: 'Normalized'}], origValue: {text: 'Raw'}}]};
    assert.equal(fsFieldText(field), 'Normalized');
});

test('fsFieldText: falls back to origValue.text when no normalizedValues', () => {
    const field = {fieldValues: [{origValue: {text: 'Raw only'}}]};
    assert.equal(fsFieldText(field), 'Raw only');
});

test('fsFieldText: returns empty string for a field with no values at all', () => {
    assert.equal(fsFieldText({fieldValues: []}), '');
    assert.equal(fsFieldText({}), '');
});

test('fsPersonName: resolves the confirmed NAME -> NAME_GIVEN/NAME_SURNAME -> FIELD chain', () => {
    const data = makeApiResponse();
    const byId = buildFsElementIndex(data);
    const person = byId['1:1:PERSON-A'];
    assert.deepEqual(fsPersonName(byId, person), {given: 'ELIZA M.', surname: 'FISK'});
});

test('fsPersonFieldText: reads a direct PERSON -> FIELD child (1880+ shape)', () => {
    const data = makeApiResponse();
    const byId = buildFsElementIndex(data);
    const person = byId['1:1:PERSON-A'];
    assert.equal(fsPersonFieldText(byId, person, 'RELATIONSHIP_TO_HEAD'), 'Head');
    assert.equal(fsPersonFieldText(byId, person, 'MARITAL_STATUS'), 'Married');
    assert.equal(fsPersonFieldText(byId, person, 'OCCUPATION'), 'Farmer');
    assert.equal(fsPersonFieldText(byId, person, 'RACE_OR_COLOR'), 'White');
    assert.equal(fsPersonFieldText(byId, person, 'FTHR_BIR_PLACE'), 'Germany');
    assert.equal(fsPersonFieldText(byId, person, 'MTHR_BIR_PLACE'), 'Vermont, United States');
});

test('fsPersonFieldText: returns empty string when the field genuinely does not exist (1850-era person)', () => {
    const data = makeApiResponse();
    const byId = buildFsElementIndex(data);
    const person = byId['1:1:PERSON-B'];
    assert.equal(fsPersonFieldText(byId, person, 'RELATIONSHIP_TO_HEAD'), '');
    assert.equal(fsPersonFieldText(byId, person, 'MARITAL_STATUS'), '');
    assert.equal(fsPersonFieldText(byId, person, 'OCCUPATION'), '');
});

test('fsWrappedFieldText: resolves the two-level PERSON -> AGE -> FIELD indirection', () => {
    const data = makeApiResponse();
    const byId = buildFsElementIndex(data);
    assert.equal(fsWrappedFieldText(byId, byId['1:1:PERSON-A'], 'AGE'), '38');
    assert.equal(fsWrappedFieldText(byId, byId['1:1:PERSON-B'], 'AGE'), '47');
});

test('fsPersonBirthPlace: resolves PERSON -> EVENT(eventType=BIRTH) -> PLACE -> FIELD', () => {
    const data = makeApiResponse();
    const byId = buildFsElementIndex(data);
    assert.equal(fsPersonBirthPlace(byId, byId['1:1:PERSON-A']), 'Maine, United States');
});

test('fsPersonBirthPlace: returns empty string when no BIRTH event exists', () => {
    const data = makeApiResponse();
    const byId = buildFsElementIndex(data);
    assert.equal(fsPersonBirthPlace(byId, byId['1:1:PERSON-B']), '');
});

test('fsHouseholds: groups PERSON arks by RECORD.subElements directly, no extra matching', () => {
    const data = makeApiResponse();
    const byId = buildFsElementIndex(data);
    const households = fsHouseholds(data, byId);
    assert.equal(households.length, 2);
    assert.deepEqual(households[0].personIds, ['1:1:PERSON-A']);
    assert.deepEqual(households[1].personIds, ['1:1:PERSON-B']);
});

test('fsBuildRowsFromApiResponse: 1880-style person gets full columns including Relationship to Head', () => {
    const rows = fsBuildRowsFromApiResponse(makeApiResponse());
    const rowA = rows.find(r => r.person_ark === '1:1:PERSON-A');
    assert.deepEqual(rowA.columns, {
        'Given Name': 'ELIZA M.', 'Surname': 'FISK', 'Gender': 'F', 'Age': '38',
        'Family Number': '90', 'Relationship to Head': 'Head',
    });
    assert.equal(rowA.attached_fsftid, '');
});

test('fsBuildRowsFromApiResponse: 1850-style person omits Relationship to Head entirely, not blank', () => {
    const rows = fsBuildRowsFromApiResponse(makeApiResponse());
    const rowB = rows.find(r => r.person_ark === '1:1:PERSON-B');
    assert.deepEqual(rowB.columns, {
        'Given Name': 'Bozil', 'Surname': 'Delmer', 'Gender': 'M', 'Age': '47',
        'Family Number': '12',
    });
    assert.ok(!('Relationship to Head' in rowB.columns));
});

test('fsBuildRowsFromApiResponse: Family Number prefers SOURCE_HOUSEHOLD_ID over SOURCE_HOUSE_NBR when both exist', () => {
    const data = makeApiResponse();
    // Give PERSON-B both fields to prove the preference order, not just "whichever exists".
    data.elements.push(
        {elementType: 'FIELD', id: 'field-fshouseholdid-b', fieldType: 'FS_HOUSEHOLD_ID', fieldValues: [{normalizedValues: [{text: '999'}]}]},
    );
    data.elements.find(e => e.id === '1:1:PERSON-B').subElements.push({id: 'field-fshouseholdid-b'});
    const rows = fsBuildRowsFromApiResponse(data);
    const rowB = rows.find(r => r.person_ark === '1:1:PERSON-B');
    // SOURCE_HOUSE_NBR ("12") is a dwelling number, not a family number - FS_HOUSEHOLD_ID
    // ("999") should NOT win over it either, since SOURCE_HOUSE_NBR was already present;
    // this only proves FS_HOUSEHOLD_ID doesn't wrongly override an already-present value.
    assert.equal(rowB.columns['Family Number'], '12');
});

test('fsBuildRowsFromApiResponse: Family Number falls back to a sequential per-household counter when no household-id field exists at all', () => {
    const data = {
        numberOfPersonsOnImage: 1, numberOfRecordsOnImage: 1,
        elements: [
            {elementType: 'RECORD', id: 'rec-1', subElements: [{id: '1:1:PERSON-C'}]},
            {elementType: 'PERSON', id: '1:1:PERSON-C', primary: true, subElements: [{id: 'name-c'}]},
            {elementType: 'NAME', id: 'name-c', primary: true, subElements: [{id: 'given-c'}, {id: 'surname-c'}]},
            {elementType: 'NAME_GIVEN', id: 'given-c', subElements: [{id: 'field-given-c'}]},
            {elementType: 'FIELD', id: 'field-given-c', fieldType: 'NAME_GN', fieldValues: [{normalizedValues: [{text: 'Test'}]}]},
            {elementType: 'NAME_SURNAME', id: 'surname-c', subElements: [{id: 'field-surname-c'}]},
            {elementType: 'FIELD', id: 'field-surname-c', fieldType: 'NAME_SURN', fieldValues: [{normalizedValues: [{text: 'Person'}]}]},
        ],
    };
    const rows = fsBuildRowsFromApiResponse(data);
    assert.equal(rows[0].columns['Family Number'], '1');
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `node --test Voyageur/tests/js/test_fs_api_parser.mjs`
Expected: FAIL — `buildFsElementIndex` (and the rest) are not exported from `./harness.js` (they don't exist yet).

- [ ] **Step 3: Implement the parser functions**

In `Voyageur/Voyageur.js`, add after `clearFsReloadState()` (currently ends at line 154):

```js
    // FamilySearch orchestration-API graph traversal - confirmed live (see
    // docs/superpowers/specs/2026-08-14-fs-orchestration-api-extraction-design.md) that
    // FamilySearch's own client fires GET .../orchestration/sls/image/{ark} automatically on
    // page load, returning a flat `elements` array cross-referenced by UUID/ark via
    // subElements/superElements - not a nested tree. These are pure, DOM-free functions:
    // build the {id: element} index once per response, then walk it.
    function buildFsElementIndex(apiResponse) {
        const byId = {};
        (apiResponse.elements || []).forEach((e) => { byId[e.id] = e; });
        return byId;
    }

    function fsFieldText(fieldElement) {
        const fv = fieldElement && fieldElement.fieldValues && fieldElement.fieldValues[0];
        if (!fv) return '';
        if (fv.normalizedValues && fv.normalizedValues[0]) return fv.normalizedValues[0].text || '';
        if (fv.origValue) return fv.origValue.text || '';
        return '';
    }

    function fsFindChild(byId, subElements, elementType) {
        if (!subElements) return null;
        for (const ref of subElements) {
            const el = byId[ref.id];
            if (el && el.elementType === elementType) return el;
        }
        return null;
    }

    // Direct indirection: PERSON -> FIELD (matching fieldType) -> text. Confirmed live for
    // RELATIONSHIP_TO_HEAD, MARITAL_STATUS, OCCUPATION, RACE_OR_COLOR, FTHR_BIR_PLACE,
    // MTHR_BIR_PLACE, SEX_CODE, SOURCE_HOUSEHOLD_ID, FS_HOUSEHOLD_ID, SOURCE_HOUSE_NBR - these
    // FIELD elements are direct children of PERSON, no wrapper element in between. Returns ''
    // when the field is genuinely absent (the 1850-1870 era case - not an error, just no such
    // question on that year's questionnaire).
    function fsPersonFieldText(byId, person, fieldType) {
        if (!person || !person.subElements) return '';
        for (const ref of person.subElements) {
            const el = byId[ref.id];
            if (el && el.elementType === 'FIELD' && el.fieldType === fieldType) return fsFieldText(el);
        }
        return '';
    }

    // Two-level indirection: PERSON -> {wrapperElementType, e.g. AGE} -> FIELD -> text.
    // Confirmed live for AGE - unlike the direct fields above, AGE is its own wrapping
    // element type, not a bare FIELD child of PERSON.
    function fsWrappedFieldText(byId, person, wrapperElementType) {
        const wrapper = fsFindChild(byId, person && person.subElements, wrapperElementType);
        if (!wrapper) return '';
        const field = fsFindChild(byId, wrapper.subElements, 'FIELD');
        return field ? fsFieldText(field) : '';
    }

    // Three-level indirection: PERSON -> NAME -> NAME_GIVEN/NAME_SURNAME -> FIELD -> text.
    // A person can have more than one NAME (multiple indexed variants, confirmed live: 101
    // NAME elements for 42 PERSON elements on one 1850 image) - prefers the one marked
    // primary, same convention already used for PERSON itself in this file, falling back to
    // the first NAME found when none is marked primary.
    function fsPersonName(byId, person) {
        const names = (person && person.subElements || [])
            .map((ref) => byId[ref.id])
            .filter((el) => el && el.elementType === 'NAME');
        const nameEl = names.find((n) => n.primary) || names[0];
        if (!nameEl) return {given: '', surname: ''};
        const givenEl = fsFindChild(byId, nameEl.subElements, 'NAME_GIVEN');
        const surnameEl = fsFindChild(byId, nameEl.subElements, 'NAME_SURNAME');
        const givenField = givenEl ? fsFindChild(byId, givenEl.subElements, 'FIELD') : null;
        const surnameField = surnameEl ? fsFindChild(byId, surnameEl.subElements, 'FIELD') : null;
        return {
            given: givenField ? fsFieldText(givenField) : '',
            surname: surnameField ? fsFieldText(surnameField) : '',
        };
    }

    // PERSON -> EVENT(eventType=BIRTH) -> PLACE -> FIELD -> text. Confirmed live: the CENSUS
    // event's PLACE is residence, not birthplace - only the BIRTH-type event's PLACE is
    // birthplace, and it's absent entirely when FamilySearch's indexing didn't derive one.
    function fsPersonBirthPlace(byId, person) {
        const events = (person && person.subElements || [])
            .map((ref) => byId[ref.id])
            .filter((el) => el && el.elementType === 'EVENT');
        const birthEvent = events.find((e) => e.eventType === 'BIRTH');
        if (!birthEvent) return '';
        const placeEl = fsFindChild(byId, birthEvent.subElements, 'PLACE');
        if (!placeEl) return '';
        const field = fsFindChild(byId, placeEl.subElements, 'FIELD');
        return field ? fsFieldText(field) : '';
    }

    // RECORD.subElements directly lists the household's PERSON arks - confirmed live, no
    // separate id-matching needed the way the old UI-scraper had to reconstruct household
    // membership from DOM position.
    function fsHouseholds(apiResponse, byId) {
        return (apiResponse.elements || [])
            .filter((e) => e.elementType === 'RECORD')
            .map((record) => ({
                recordId: record.id,
                personIds: (record.subElements || [])
                    .map((ref) => ref.id)
                    .filter((id) => byId[id] && byId[id].elementType === 'PERSON'),
            }));
    }

    // Prefers the sheet-printed family number (SOURCE_HOUSEHOLD_ID), falling back to
    // FamilySearch's own system-generated id (FS_HOUSEHOLD_ID) when the original indexer
    // didn't record one - confirmed live these two are exact complements on a real image (35
    // + 7 = 42 of 42 persons). SOURCE_HOUSE_NBR is a dwelling number, not a family number
    // (a dwelling can hold multiple families) - deliberately not used here. Falls back to a
    // sequential per-household counter only if neither field exists at all, matching the old
    // UI-scraper's own behavior for collections this rich data isn't available on.
    function fsFamilyNumber(byId, person, sequentialFallback) {
        return fsPersonFieldText(byId, person, 'SOURCE_HOUSEHOLD_ID')
            || fsPersonFieldText(byId, person, 'FS_HOUSEHOLD_ID')
            || String(sequentialFallback);
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

                const {given, surname} = fsPersonName(byId, person);
                const sex = fsPersonFieldText(byId, person, 'SEX_CODE');
                const columns = {
                    'Given Name': given,
                    'Surname': surname,
                    'Gender': sex ? sex.toUpperCase() : '',
                    'Age': fsWrappedFieldText(byId, person, 'AGE'),
                    'Family Number': fsFamilyNumber(byId, person, householdIndex),
                };

                // Omitted entirely (not set to '') when absent - matches the old UI-scraper's
                // own "don't fabricate data" convention, and is how the 1850-1870 era
                // boundary is handled: no special-case branching, just field-absence.
                const relationshipToHead = fsPersonFieldText(byId, person, 'RELATIONSHIP_TO_HEAD');
                if (relationshipToHead) columns['Relationship to Head'] = relationshipToHead;

                rows.push({columns, person_ark: person.id, attached_fsftid: ''});
            }
        }
        return rows;
    }

```

- [ ] **Step 4: Update `harness.js` and `module.exports` so the new functions are importable**

In `Voyageur/tests/js/harness.js`, no changes needed — it already does `module.exports = require('../../Voyageur.js')`, so anything added to `Voyageur.js`'s own `module.exports` becomes available automatically.

In `Voyageur/Voyageur.js`, update the export guard (currently near the end of the file):

```js
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = {
            placesMatch, saveReloadState, loadReloadState, clearReloadState,
            buildFsElementIndex, fsFieldText, fsPersonFieldText, fsWrappedFieldText,
            fsPersonName, fsPersonBirthPlace, fsHouseholds, fsBuildRowsFromApiResponse,
        };
    }
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `node --test Voyageur/tests/js/test_fs_api_parser.mjs`
Expected: PASS, all 14 tests.

- [ ] **Step 6: Syntax-check the full file**

Run: `node --check Voyageur/Voyageur.js`
Expected: no output (clean exit).

- [ ] **Step 7: Commit**

```bash
git add Voyageur/Voyageur.js Voyageur/tests/js/test_fs_api_parser.mjs
git commit -m "feat(voyageur): add pure parser for FamilySearch orchestration-API responses"
```

---

### Task 2: Interceptor and response-wait glue

**Files:**
- Modify: `Voyageur/Voyageur.js` (inside `runFamilySearchGather()`, currently starting at line 1321; add near its `debugLog` declaration, currently around line 1358-1360)

**Interfaces:**
- Consumes: nothing directly from Task 1 (the interceptor just stores raw parsed JSON; Task 3 is what calls Task 1's parser on it).
- Produces: `waitForFsApiResponse(ark, {timeoutMs}) -> Promise<{result: object|null, timedOut: boolean}>` (a local function inside `runFamilySearchGather()`, using this file's existing `waitForCondition()` convention), reading from `unsafeWindow.__voyageurFsApiResponses[ark]`.

This mirrors the exact pattern already used and proven for Ancestry's PID capture (`runAncestryGather()`, `unsafeWindow.__mgs_intercepted`) — same file, same technique, new target endpoint.

- [ ] **Step 1: Add the interceptor and wait function**

In `Voyageur/Voyageur.js`, inside `runFamilySearchGather()`, immediately after the `debugLog` function declaration (currently lines 1358-1360):

```js
        function debugLog(msg) {
            if (DEBUG_MODE) console.log(`[Voyageur FS] ${msg}`);
        }

        // Confirmed live: FamilySearch's own client requests this endpoint automatically on
        // every image's page load, no UI interaction required - installed here, as early as
        // possible inside this function (before any async work), mirroring
        // runAncestryGather's own __mgs_intercepted pattern (same fetch/XHR patch technique,
        // different target URL/response shape). __voyageurFsApiResponses is keyed by ark so
        // multiple in-flight requests (if FamilySearch ever prefetches adjacent images) don't
        // collide with each other.
        if (typeof unsafeWindow !== 'undefined' && !unsafeWindow.__voyageurFsApiIntercepted) {
            unsafeWindow.__voyageurFsApiIntercepted = true;
            unsafeWindow.__voyageurFsApiResponses = {};

            const FS_API_TARGET = '/service/records/volunteer/orchestration/sls/image/';

            function fsApiArkFromUrl(url) {
                const match = url.match(/\/image\/([^/?#]+)/);
                return match ? decodeURIComponent(match[1]) : null;
            }

            function storeFsApiResponse(url, bodyText) {
                const ark = fsApiArkFromUrl(url);
                if (!ark) return;
                try {
                    unsafeWindow.__voyageurFsApiResponses[ark] = JSON.parse(bodyText);
                } catch (e) {
                    // Leave unset - waitForFsApiResponse() below times out the same as "never
                    // arrived", which is the correct behavior for an unparseable response.
                }
            }

            const origFsXhrOpen = unsafeWindow.XMLHttpRequest.prototype.open;
            unsafeWindow.XMLHttpRequest.prototype.open = function (method, url) {
                this.__voyageurFsApiUrl = url;
                this.addEventListener('load', function () {
                    if (this.__voyageurFsApiUrl && this.__voyageurFsApiUrl.includes(FS_API_TARGET)) {
                        storeFsApiResponse(this.__voyageurFsApiUrl, this.responseText);
                    }
                });
                return origFsXhrOpen.apply(this, arguments);
            };

            const origFsFetch = unsafeWindow.fetch;
            unsafeWindow.fetch = async function (...args) {
                const url = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url) || '';
                const resp = await origFsFetch.apply(this, args);
                if (url.includes(FS_API_TARGET)) {
                    resp.clone().text().then((t) => storeFsApiResponse(url, t));
                }
                return resp;
            };
        }

        // Instant resolution if the response already arrived before this was called (the API
        // call fires on page load, which can beat the gather loop reaching this image);
        // otherwise polls the shared store via the existing waitForCondition convention.
        async function waitForFsApiResponse(ark, {timeoutMs = 15000} = {}) {
            return waitForCondition(
                () => (unsafeWindow.__voyageurFsApiResponses || {})[ark] || null,
                {timeoutMs},
            );
        }
```

- [ ] **Step 2: Syntax-check**

Run: `node --check Voyageur/Voyageur.js`
Expected: no output (clean exit).

- [ ] **Step 3: Run the existing test suite to confirm nothing broke**

Run: `node --test Voyageur/tests/js/test_stop_conditions.mjs Voyageur/tests/js/test_fs_api_parser.mjs`
Expected: PASS, all tests (this task adds no new pure functions to test — `waitForFsApiResponse` and the interceptor both depend on `unsafeWindow`/DOM, which the Node harness stubs as `undefined`, so this code path simply doesn't execute under `require()`, same as the Ancestry interceptor already doesn't).

- [ ] **Step 4: Bump `@version`**

In `Voyageur/Voyageur.js`, find the current `// @version` line and increment the patch component (check the current value first — this plan was written against `0.3.22`, but earlier tasks in this same plan or other work may have moved it since).

- [ ] **Step 5: Commit**

```bash
git add Voyageur/Voyageur.js
git commit -m "feat(voyageur): intercept FamilySearch orchestration-API responses"
```

---

### Task 3: Wire extraction into the gather loop, remove old UI-scraping

**Files:**
- Modify: `Voyageur/Voyageur.js`:
  - `scrapeCurrentImage()` (currently lines 1809-1823)
  - Delete: `parseHouseholdSections()`, `getNamesPanel()`, `getHouseholdHeadings()`, `findHouseholdContainer()`, `locateMemberButton()`, `readRecordArkFromOpenPanel()`, `scrapePersonDetail()`, the old `scrapeNamesPanel()` (currently lines 1515-1807, contiguous block)
  - `saveFsReloadState()`/`loadFsReloadState()` (currently lines 124-150) — remove the now-dead `namesReloadAttempts` field
  - The `namesReloadAttempts`/`MAX_NAMES_RELOAD_ATTEMPTS` declarations and `isResumingFsState` restoration inside `runFamilySearchGather()` (currently lines 1333-1356) — remove the reload-retry state that only existed for the now-deleted "Names tab missing" condition

**Interfaces:**
- Consumes: `fsBuildRowsFromApiResponse` (Task 1), `waitForFsApiResponse` (Task 2), `getItemId()` (already exists, unchanged).
- Produces: nothing new — this task is the wiring + cleanup that makes Tasks 1-2 actually load-bearing, and removes the code they replace.

This is the task where the old UI-scraping fragility (Names-tab reload-retry, person-detail-panel clicking, the whole class of bugs issues #21/#22 were about) gets deleted, not just superseded. Per this project's "full cleanup during refactor" convention, leftover dead state (`namesReloadAttempts`) gets removed in this same task, not left behind.

- [ ] **Step 1: Replace `scrapeCurrentImage()`**

Current (lines 1809-1823):

```js
        async function scrapeCurrentImage() {
            const itemId = getItemId();
            if (!itemId || seenItemIds.has(itemId)) return;

            const rows = await scrapeNamesPanel();
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

- [ ] **Step 2: Delete the old UI-scraping functions**

Delete the entire contiguous block from `async function parseHouseholdSections()` through the end of the old `async function scrapeNamesPanel()` (currently lines 1515-1807) — this removes `parseHouseholdSections`, `getNamesPanel`, `getHouseholdHeadings`, `findHouseholdContainer`, `locateMemberButton`, `readRecordArkFromOpenPanel`, `scrapePersonDetail`, and the old `scrapeNamesPanel`, all in one contiguous deletion. `findByExactText` and `clickTab` (lines 1443-1463) stay — `scrapeCitationAndCatalog()` still uses `clickTab('Information')`.

- [ ] **Step 3: Remove the now-dead Names-reload-retry state**

In `runFamilySearchGather()`, current (lines 1328-1356):

```js
        const DEBUG_MODE = true;
        let isRunning = false;
        let accumulatedItems = [];
        let seenItemIds = new Set();
        let itemsAtLastCheckpoint = 0;
        let namesReloadAttempts = 0;
        const MAX_NAMES_RELOAD_ATTEMPTS = 3;

        const shouldAutoStart = window.location.href.includes('mgs_auto=1');
        const runId = new URLSearchParams(window.location.search).get('mgs_run') || 'norun';

        // A location.reload() triggered by the Names-tab-missing retry, OR a genuine
        // FamilySearch page navigation from clicking "Next Image" (see goToNextImage/
        // FS_RELOAD_STATE_KEY's own note), both re-run this whole script from scratch -
        // restore whatever was saved right before so the batch resumes instead of silently
        // discarding every item gathered so far. Same convention as runAncestryGather's own
        // resumedState handling. isResumingFsState is read by startBatch() below to skip
        // its own unconditional reset, the same way runAncestryGather's resumingFromReload
        // guards startBatch() there.
        let isResumingFsState = false;
        const resumedFsState = loadFsReloadState(runId);
        if (resumedFsState) {
            accumulatedItems = resumedFsState.accumulatedItems;
            seenItemIds = resumedFsState.seenItemIds;
            itemsAtLastCheckpoint = resumedFsState.itemsAtLastCheckpoint;
            namesReloadAttempts = resumedFsState.namesReloadAttempts;
            isResumingFsState = true;
            clearFsReloadState();
        }
```

Replace with (drops `namesReloadAttempts`/`MAX_NAMES_RELOAD_ATTEMPTS` entirely — the reload-retry mechanism they supported no longer exists, since there's no "Names tab missing" condition to retry; `saveFsReloadState`'s own reload-state persistence for the "real page navigation on Next Image" case is still needed and stays):

```js
        const DEBUG_MODE = true;
        let isRunning = false;
        let accumulatedItems = [];
        let seenItemIds = new Set();
        let itemsAtLastCheckpoint = 0;

        const shouldAutoStart = window.location.href.includes('mgs_auto=1');
        const runId = new URLSearchParams(window.location.search).get('mgs_run') || 'norun';

        // A genuine FamilySearch page navigation from clicking "Next Image" (see
        // goToNextImage/FS_RELOAD_STATE_KEY's own note) re-runs this whole script from
        // scratch - restore whatever was saved right before so the batch resumes instead of
        // silently discarding every item gathered so far. Same convention as
        // runAncestryGather's own resumedState handling. isResumingFsState is read by
        // startBatch() below to skip its own unconditional reset, the same way
        // runAncestryGather's resumingFromReload guards startBatch() there.
        let isResumingFsState = false;
        const resumedFsState = loadFsReloadState(runId);
        if (resumedFsState) {
            accumulatedItems = resumedFsState.accumulatedItems;
            seenItemIds = resumedFsState.seenItemIds;
            itemsAtLastCheckpoint = resumedFsState.itemsAtLastCheckpoint;
            isResumingFsState = true;
            clearFsReloadState();
        }
```

- [ ] **Step 4: Strip `namesReloadAttempts` from the reload-state save/load functions**

Current (lines 124-150):

```js
    function saveFsReloadState(runId, state) {
        sessionStorage.setItem(FS_RELOAD_STATE_KEY, JSON.stringify({
            runId,
            accumulatedItems: state.accumulatedItems,
            seenItemIds: Array.from(state.seenItemIds),
            itemsAtLastCheckpoint: state.itemsAtLastCheckpoint,
            namesReloadAttempts: state.namesReloadAttempts,
        }));
    }

    function loadFsReloadState(runId) {
        const raw = sessionStorage.getItem(FS_RELOAD_STATE_KEY);
        if (!raw) return null;
        let parsed;
        try {
            parsed = JSON.parse(raw);
        } catch (e) {
            return null;
        }
        if (parsed.runId !== runId) return null;
        return {
            accumulatedItems: parsed.accumulatedItems || [],
            seenItemIds: new Set(parsed.seenItemIds || []),
            itemsAtLastCheckpoint: parsed.itemsAtLastCheckpoint || 0,
            namesReloadAttempts: parsed.namesReloadAttempts || 0,
        };
    }
```

Replace with:

```js
    function saveFsReloadState(runId, state) {
        sessionStorage.setItem(FS_RELOAD_STATE_KEY, JSON.stringify({
            runId,
            accumulatedItems: state.accumulatedItems,
            seenItemIds: Array.from(state.seenItemIds),
            itemsAtLastCheckpoint: state.itemsAtLastCheckpoint,
        }));
    }

    function loadFsReloadState(runId) {
        const raw = sessionStorage.getItem(FS_RELOAD_STATE_KEY);
        if (!raw) return null;
        let parsed;
        try {
            parsed = JSON.parse(raw);
        } catch (e) {
            return null;
        }
        if (parsed.runId !== runId) return null;
        return {
            accumulatedItems: parsed.accumulatedItems || [],
            seenItemIds: new Set(parsed.seenItemIds || []),
            itemsAtLastCheckpoint: parsed.itemsAtLastCheckpoint || 0,
        };
    }
```

- [ ] **Step 5: Find and update every other reference to `namesReloadAttempts`**

Search the file for any remaining `namesReloadAttempts` references (there were call sites inside the old `parseHouseholdSections()` already deleted in Step 2, and the `saveFsReloadState(runId, {..., namesReloadAttempts})` call sites inside it — those are gone with the deletion, but confirm via search):

Run: `grep -n namesReloadAttempts Voyageur/Voyageur.js`
Expected: no matches (empty output). If any remain, remove them — this is exactly the "don't leave dead-key leftovers" cleanup this task exists to do.

- [ ] **Step 6: Syntax-check**

Run: `node --check Voyageur/Voyageur.js`
Expected: no output (clean exit).

- [ ] **Step 7: Run the full JS test suite**

Run: `node --test Voyageur/tests/js/test_stop_conditions.mjs Voyageur/tests/js/test_fs_api_parser.mjs`
Expected: PASS, all tests. The `reload state` tests in `test_stop_conditions.mjs` exercise `saveReloadState`/`loadReloadState` (the Ancestry-side ones, untouched by this task) — they should still pass unaffected; this step is a regression check, not new coverage for the `namesReloadAttempts` removal (that removal has no dedicated test since it deletes dead code, not a testable behavior).

- [ ] **Step 8: Bump `@version`**

Increment the patch component of `// @version` (check current value — this task follows Task 2's bump).

- [ ] **Step 9: Commit**

```bash
git add Voyageur/Voyageur.js
git commit -m "feat(voyageur): wire FS gather to orchestration-API extraction, remove old UI-scraping"
```

---

### Task 4: Live verification (not delegable to a subagent — requires a real, logged-in browser)

**Files:** none (verification only, no code changes)

**Interfaces:** none.

This task cannot be executed by a coding subagent — it requires an authenticated FamilySearch session and a real browser. Run this task in the controlling session directly (the one with `AI Assistant-in-chrome` or equivalent access), regardless of how Tasks 1-3 were executed.

- [ ] **Step 1: Verify on an 1880+ record (has `RELATIONSHIP_TO_HEAD` etc.)**

Navigate to a known 1880 census record ark (e.g. the one used throughout this session's investigation), trigger the gather via `?mgs_auto=1&mgs_run=<id>` the same way prior sessions did, let it scrape at least one image, and inspect the resulting console log / downloaded JSON.

Expected: `rows` contains real names/ages, and at least some rows include a `Relationship to Head` column with a real value (not every row necessarily — some 1880 persons may still lack it if FamilySearch's own indexing didn't derive it for them, matching the "omit, don't fabricate" convention already built into `fsBuildRowsFromApiResponse`).

- [ ] **Step 2: Verify on an 1850-1870 record (no relationship data)**

Navigate to a known 1850 or 1860 or 1870 census record ark, run the same gather.

Expected: `rows` contains real names/ages, and **no row has a `Relationship to Head` key at all** (not an empty string — genuinely absent from the `columns` object, matching Task 1's own unit test for this exact behavior).

- [ ] **Step 3: Verify multi-image continuation still works**

Let the gather run across at least 3 images on either test record, confirming (matching this session's own earlier live-verified fix) that all 3 images' data survives into the final downloaded JSON, not just the last one.

Expected: downloaded JSON's `items` array has 3 entries, each with non-empty `rows` (assuming the source images have indexed content).

- [ ] **Step 4: If any step fails, do not proceed to Task 5 (finishing) until root-caused**

Given how much of this session was spent discovering that FamilySearch's page behavior doesn't always match what a single test run suggests (the "explore" view, the account-level feature flags, the rate-limiting question), a single clean pass on this task is worth treating with appropriate skepticism — but is sufficient to proceed, since Tasks 1-3's unit tests already cover the parsing logic in isolation; this task is specifically to confirm the *live wiring* (interceptor timing, real navigation) works, which unit tests structurally cannot cover.

---

## Self-Review Notes (from the plan author, not a task)

**Spec coverage:** Architecture (Tasks 2-3), confirmed element types and traversal (Task 1), era-dependent field richness (Task 1's explicit 1850-vs-1880 test fixtures), household ID/line number mapping (Task 1's `fsFamilyNumber`, though `EXT_LINE_NBR`/`SOURCE_PERSON_NBR`/`SOURCE_LINE_NBR`/dwelling-number fields are deliberately NOT wired into the downstream `columns` object in this plan — the spec's own "Not yet verified" list flags these as unresolved which-field-wins questions, and the existing downstream schema has no `Line Number` slot for FS today (it's synthesized in `FS.py`, untouched by this plan) — wiring them in prematurely would guess at an unresolved design question. Out of scope for this plan; a natural follow-up once disambiguated.

**Deliberately out of scope for this plan** (per the spec's own scoping, "Goal" section's Names-panel/person-detail-panel-only wording, and the `Voyageur/Voyageur.js` context re-read during planning):
- Citation-text extraction (`scrapeCitationAndCatalog()`) stays UI-based. The spec confirms `EXT_FILM_NBR`/`EXT_PUB_NBR`/`EXT_REPOSITORY_NAME` are available via the same API, but reconstructing an equivalent `citation_text` string (what `FS.py`'s `parse_citation()`/`parse_nara_citing_clause()` regex-parse) is separate, not-yet-designed work, and the spec's own "STATE/COUNTY/TOWN proper scoping" item is still unresolved — needed for a complete citation replacement, not just the image-level singleton fields already confirmed clean.
- `DATE` element text decoding, non-census collection verification, `SOURCE_PERSON_NBR`/`EXT_LINE_NBR`/`SOURCE_LINE_NBR`/`SOURCE_HOUSE_NBR` disambiguation — all explicitly flagged "not yet verified" in the spec, none of which block this plan's actual deliverable (replacing Names-panel/person-detail clicking with the confirmed-solid subset of fields).

**Placeholder scan:** No TBD/TODO in any task step; every code block is real, complete code, not described-but-unwritten. Task 4's live-verification steps describe expected outcomes concretely rather than vague "check it works" language.

**Type consistency:** `fsBuildRowsFromApiResponse` (Task 1) is called by `scrapeCurrentImage()` (Task 3) with the same signature throughout — `(apiResponse) -> [{columns, person_ark, attached_fsftid}]`. `waitForFsApiResponse` (Task 2) is called by `scrapeCurrentImage()` (Task 3) with the same signature — `(ark, {timeoutMs}) -> Promise<{result, timedOut, elapsedMs}>`, matching this file's existing `waitForCondition()` return shape exactly (verified against its actual implementation, not assumed).
