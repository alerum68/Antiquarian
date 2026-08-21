/* global globalThis */
import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const {
    buildFsElementIndex, fsFieldText, fsPersonFieldText, fsWrappedFieldText,
    fsPersonName, fsPersonEventPlace, fsPersonBirthPlace, fsPersonResidencePlace,
    fsResidencePlaceToBrowsePath, fsImageLevelFieldText, fsImageLevelLocation, fsHouseholds,
    fsBuildRowsFromApiResponse, fsBuildCitationTextFromApiResponse,
    fsRawFieldsFromApiPerson, fsPersonArkFromAttachments, backfillFsPersonArks,
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
                    {id: 'name-a'}, {id: 'age-a'}, {id: 'event-birth-a'}, {id: 'event-census-a'},
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
            {elementType: 'EVENT', id: 'event-census-a', eventType: 'CENSUS', subElements: [{id: 'place-census-a'}]},
            {elementType: 'PLACE', id: 'place-census-a', subElements: [{id: 'field-census-place-a'}]},
            {elementType: 'FIELD', id: 'field-census-place-a', fieldType: 'PLACE', fieldValues: [{normalizedValues: [{text: 'St Paul, Ramsey, Minnesota'}]}]},
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

            // --- Image-level singleton fields (confirmed live: once per image, not per
            // person/record) - EXT_REPOSITORY_NAME's real captured value carries a trailing
            // "(NARA)" that fsBuildCitationTextFromApiResponse must strip. ---
            {elementType: 'FIELD', id: 'field-film-nbr', fieldType: 'EXT_FILM_NBR', fieldValues: [{normalizedValues: [{text: '367'}]}]},
            {elementType: 'FIELD', id: 'field-repo-name', fieldType: 'EXT_REPOSITORY_NAME', fieldValues: [{normalizedValues: [{text: 'The U.S. National Archives and Records Administration (NARA)'}]}]},
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

test('fsPersonResidencePlace: resolves PERSON -> EVENT(eventType=CENSUS) -> PLACE -> FIELD', () => {
    const data = makeApiResponse();
    const byId = buildFsElementIndex(data);
    assert.equal(fsPersonResidencePlace(byId, byId['1:1:PERSON-A']), 'St Paul, Ramsey, Minnesota');
});

test('fsPersonResidencePlace: returns empty string when no CENSUS event exists', () => {
    const data = makeApiResponse();
    const byId = buildFsElementIndex(data);
    assert.equal(fsPersonResidencePlace(byId, byId['1:1:PERSON-B']), '');
});

test('fsPersonEventPlace: BIRTH and CENSUS on the same person read independently', () => {
    const data = makeApiResponse();
    const byId = buildFsElementIndex(data);
    const person = byId['1:1:PERSON-A'];
    assert.equal(fsPersonEventPlace(byId, person, 'BIRTH'), 'Maine, United States');
    assert.equal(fsPersonEventPlace(byId, person, 'CENSUS'), 'St Paul, Ramsey, Minnesota');
});

test('fsResidencePlaceToBrowsePath: reverses specific-to-general comma text into general-to-specific segments', () => {
    assert.deepEqual(fsResidencePlaceToBrowsePath('St Paul, Ramsey, Minnesota'), ['Minnesota', 'Ramsey', 'St Paul']);
});

test('fsResidencePlaceToBrowsePath: empty text produces an empty array', () => {
    assert.deepEqual(fsResidencePlaceToBrowsePath(''), []);
});

test('fsImageLevelFieldText: finds a FIELD anywhere in the flat elements array by fieldType', () => {
    const data = makeApiResponse();
    assert.equal(fsImageLevelFieldText(data, 'EXT_FILM_NBR'), '367');
    assert.equal(fsImageLevelFieldText(data, 'EXT_REPOSITORY_NAME'),
        'The U.S. National Archives and Records Administration (NARA)');
});

test('fsImageLevelFieldText: returns empty string when the field does not exist', () => {
    const data = makeApiResponse();
    assert.equal(fsImageLevelFieldText(data, 'NOT_A_REAL_FIELD_TYPE'), '');
});

// fsImageLevelLocation: user-directed design (2026-08-21), confirmed live via a full raw
// orchestration-API capture (a real 1950 Pembina, ND census image) - STATE/COUNTY/CITY/
// DISTRICT_ENUMERATION are directly available as image-level FIELD elements, far more
// reliable than parsing them back out of citation prose text. Fixture shape matches that
// real capture: a canonical PLACE-level entry (real text) appears BEFORE several blank
// per-person-residence STATE/COUNTY/CITY fields elsewhere in the same flat array - .find()
// must land on the first (real) one, not one of the later blanks.
test('fsImageLevelLocation: reads state/county/city/enumeration_district from image-level FIELDs', () => {
    const data = {
        elements: [
            {elementType: 'FIELD', fieldType: 'STATE', fieldValues: [{origValue: {text: 'North Dakota'}}]},
            {elementType: 'FIELD', fieldType: 'COUNTY', fieldValues: [{origValue: {text: 'Pembina'}}]},
            {elementType: 'FIELD', fieldType: 'CITY', fieldValues: [{origValue: {text: 'Advance'}}]},
            {elementType: 'FIELD', fieldType: 'DISTRICT_ENUMERATION', fieldValues: [{origValue: {text: '34-1'}}]},
            // Later, blank per-person-residence entries - must not win over the real ones above.
            {elementType: 'FIELD', fieldType: 'STATE', fieldValues: [{origValue: {text: ''}}]},
            {elementType: 'FIELD', fieldType: 'COUNTY', fieldValues: [{origValue: {text: ''}}]},
            {elementType: 'FIELD', fieldType: 'CITY', fieldValues: [{origValue: {text: ''}}]},
        ],
    };
    assert.deepEqual(fsImageLevelLocation(data), {
        state: 'North Dakota', county: 'Pembina', city: 'Advance', enumeration_district: '34-1',
    });
});

test('fsImageLevelLocation: blank fields when none exist at all', () => {
    assert.deepEqual(fsImageLevelLocation({elements: []}), {
        state: '', county: '', city: '', enumeration_district: '',
    });
});

test('fsBuildCitationTextFromApiResponse: builds the full prose citation with browse path and NARA clause', () => {
    const data = makeApiResponse();
    const byId = buildFsElementIndex(data);
    const primaryPerson = byId['1:1:PERSON-A'];
    const text = fsBuildCitationTextFromApiResponse(data, byId, primaryPerson, {
        collectionName: '1900 United States Census',
        url: 'https://www.familysearch.org/ark:/61903/3:1:33SQ-GRCN-QMV',
        imageNumber: '3', imageTotal: '14',
    });
    assert.equal(text,
        '"1900 United States Census," database with images, FamilySearch '
        + '(https://www.familysearch.org/ark:/61903/3:1:33SQ-GRCN-QMV : '
        + new Date().toLocaleDateString('en-US', {day: 'numeric', month: 'long', year: 'numeric'})
        + '), Minnesota > Ramsey > St Paul > image 3 of 14; citing NARA microfilm publication 367 '
        + '(Washington D.C.: The U.S. National Archives and Records Administration, n.d.).');
});

test('fsBuildCitationTextFromApiResponse: no film/repository fields ends with a bare period, no NARA clause', () => {
    const data = {numberOfPersonsOnImage: 0, numberOfRecordsOnImage: 0, elements: []};
    const byId = buildFsElementIndex(data);
    const text = fsBuildCitationTextFromApiResponse(data, byId, null, {collectionName: 'Test Collection', url: 'https://example.com'});
    assert.ok(text.endsWith('.'));
    assert.ok(!text.includes('citing NARA'));
});

test('fsHouseholds: groups PERSON arks by RECORD.subElements directly, no extra matching', () => {
    const data = makeApiResponse();
    const byId = buildFsElementIndex(data);
    const households = fsHouseholds(data, byId);
    assert.equal(households.length, 2);
    assert.deepEqual(households[0].personIds, ['1:1:PERSON-A']);
    assert.deepEqual(households[1].personIds, ['1:1:PERSON-B']);
});

// 2026-08-20: explicit user direction - stop hand-picking which fields matter at
// extraction time. fsBuildRowsFromApiResponse now surfaces every field
// fsRawFieldsFromApiPerson finds, keyed by FamilySearch's own vocabulary
// (fieldType/elementType/eventType-derived), with zero renaming to human-friendly
// labels - renaming/GEDCOM-mapping happens downstream in Archivist via a
// declarative field map, never here.
test('fsBuildRowsFromApiResponse: 1880-style person gets every raw field, keyed by FamilySearch fieldType', () => {
    const rows = fsBuildRowsFromApiResponse(makeApiResponse());
    const rowA = rows.find(r => r.record_ark === '1:1:PERSON-A');
    assert.deepEqual(rowA.columns, {
        NAME_GIVEN: 'ELIZA M.', NAME_SURNAME: 'FISK', AGE: '38',
        EVENT_BIRTH_PLACE: 'Maine, United States', EVENT_CENSUS_PLACE: 'St Paul, Ramsey, Minnesota',
        RELATIONSHIP_TO_HEAD: 'Head', MARITAL_STATUS: 'Married', OCCUPATION: 'Farmer',
        RACE_OR_COLOR: 'White', FTHR_BIR_PLACE: 'Germany', MTHR_BIR_PLACE: 'Vermont, United States',
        SEX_CODE: 'F', SOURCE_HOUSEHOLD_ID: '90',
    });
    // record_ark is the record/persona identifier (always present); person_ark is a true
    // enduring identifier and is never fabricated - empty until a real one is found (see
    // docs/plans/2026-08-20-familysearch-viewer-rebuild.md Task 4).
    assert.equal(rowA.person_ark, '');
});

test('fsBuildRowsFromApiResponse: 1850-style person only has the fields actually present, nothing fabricated', () => {
    const rows = fsBuildRowsFromApiResponse(makeApiResponse());
    const rowB = rows.find(r => r.record_ark === '1:1:PERSON-B');
    assert.deepEqual(rowB.columns, {
        NAME_GIVEN: 'Bozil', NAME_SURNAME: 'Delmer', AGE: '47',
        SEX_CODE: 'M', SOURCE_HOUSE_NBR: '12',
    });
    assert.ok(!('RELATIONSHIP_TO_HEAD' in rowB.columns));
    assert.ok(!('MARITAL_STATUS' in rowB.columns));
});

// fsPersonArkFromAttachments: true Family Tree person id (entityId), confirmed live
// 2026-08-21 via /service/tree/links/sources/attachments (fires automatically once the
// Names panel loads - not per-click). globalThis.unsafeWindow is `undefined` by default in
// this harness (see harness.js); tests give it a real object temporarily to exercise the
// lookup.
test('fsPersonArkFromAttachments: returns the entityId when this record_ark has an attachment on file', () => {
    globalThis.unsafeWindow = {__voyageurFsAttachments: {'1:1:6F7Z-QJKR': 'KLBM-H9P'}};
    assert.equal(fsPersonArkFromAttachments('1:1:6F7Z-QJKR'), 'KLBM-H9P');
    globalThis.unsafeWindow = undefined;
});

test('fsPersonArkFromAttachments: returns empty string (not undefined) when no attachment exists - the common case', () => {
    globalThis.unsafeWindow = {__voyageurFsAttachments: {'1:1:6F7Z-QJKR': 'KLBM-H9P'}};
    assert.equal(fsPersonArkFromAttachments('1:1:6F7Z-QJKT'), '');
    globalThis.unsafeWindow = undefined;
});

test('fsPersonArkFromAttachments: safe when unsafeWindow or the attachments map is entirely absent', () => {
    globalThis.unsafeWindow = undefined;
    assert.equal(fsPersonArkFromAttachments('1:1:6F7Z-QJKR'), '');
});

// Matches by substring, not exact key equality - an
// exact-match lookup kept failing live even for a person confirmed to have a real
// attachment, because the stored key can carry more around the persona ark than a clean
// extraction assumes (trailing path segments, a leading host/scheme, etc.).
test('fsPersonArkFromAttachments: matches when the stored key carries extra text around record_ark', () => {
    globalThis.unsafeWindow = {__voyageurFsAttachments: {
        'https://www.familysearch.org/ark:/61903/1:1:6F7Z-QJKR/some-trailing-segment': 'KLBM-H9P',
    }};
    assert.equal(fsPersonArkFromAttachments('1:1:6F7Z-QJKR'), 'KLBM-H9P');
    globalThis.unsafeWindow = undefined;
});

// backfillFsPersonArks: real-run regression (2026-08-21) - the attachments endpoint fires
// MULTIPLE separate times for one page (one real capture showed a 3-source batch, then a
// LATER, separate 12-source batch with Jess G Crowston's real KLBM-H9P entry). Waiting for
// only the first response isn't enough - a row built before the later batch arrives must
// still get filled in once it does.
test('backfillFsPersonArks: picks up a later-arriving batch across rounds', async () => {
    globalThis.unsafeWindow = {__voyageurFsAttachments: {}};
    const rows = [
        {columns: {}, record_ark: '1:1:6F7Z-QJKR', person_ark: ''},
        {columns: {}, record_ark: '1:1:OTHER', person_ark: 'ALREADY-SET'},
    ];
    setTimeout(() => {
        globalThis.unsafeWindow.__voyageurFsAttachments['1:1:6F7Z-QJKR'] = 'KLBM-H9P';
    }, 5);
    await backfillFsPersonArks(rows, {maxRounds: 5, roundDelayMs: 10});
    assert.equal(rows[0].person_ark, 'KLBM-H9P');
    assert.equal(rows[1].person_ark, 'ALREADY-SET');
    globalThis.unsafeWindow = undefined;
});

test('backfillFsPersonArks: gives up after maxRounds when nothing ever arrives - never fabricated', () => {
    globalThis.unsafeWindow = {__voyageurFsAttachments: {}};
    const rows = [{columns: {}, record_ark: '1:1:NEVER-ATTACHED', person_ark: ''}];
    return backfillFsPersonArks(rows, {maxRounds: 2, roundDelayMs: 5}).then(() => {
        assert.equal(rows[0].person_ark, '');
        globalThis.unsafeWindow = undefined;
    });
});

test('backfillFsPersonArks: returns immediately with no delay when nothing is missing', async () => {
    globalThis.unsafeWindow = {__voyageurFsAttachments: {}};
    const rows = [{columns: {}, record_ark: '1:1:X', person_ark: 'ALREADY'}];
    const startedAt = Date.now();
    await backfillFsPersonArks(rows, {maxRounds: 10, roundDelayMs: 1000});
    assert.ok(Date.now() - startedAt < 200, 'must not wait a full round when nothing is missing');
    globalThis.unsafeWindow = undefined;
});

test('fsBuildRowsFromApiResponse: populates person_ark from a real captured attachments-map entry', () => {
    globalThis.unsafeWindow = {__voyageurFsAttachments: {'1:1:PERSON-A': 'KLBM-H9P'}};
    const rows = fsBuildRowsFromApiResponse(makeApiResponse());
    const rowA = rows.find(r => r.record_ark === '1:1:PERSON-A');
    const rowB = rows.find(r => r.record_ark === '1:1:PERSON-B');
    assert.equal(rowA.person_ark, 'KLBM-H9P');
    assert.equal(rowB.person_ark, '', 'PERSON-B has no attachment on file - must stay empty, not fabricated');
    globalThis.unsafeWindow = undefined;
});

test('fsRawFieldsFromApiPerson: direct FIELD children captured verbatim, keyed by fieldType', () => {
    const data = makeApiResponse();
    const byId = buildFsElementIndex(data);
    const raw = fsRawFieldsFromApiPerson(byId, byId['1:1:PERSON-A']);
    assert.equal(raw.MARITAL_STATUS, 'Married');
    assert.equal(raw.OCCUPATION, 'Farmer');
    assert.equal(raw.RACE_OR_COLOR, 'White');
    assert.equal(raw.FTHR_BIR_PLACE, 'Germany');
    assert.equal(raw.MTHR_BIR_PLACE, 'Vermont, United States');
    assert.equal(raw.SOURCE_HOUSEHOLD_ID, '90');
});

test('fsRawFieldsFromApiPerson: NAME wrapper produces NAME_GIVEN/NAME_SURNAME keys', () => {
    const data = makeApiResponse();
    const byId = buildFsElementIndex(data);
    const raw = fsRawFieldsFromApiPerson(byId, byId['1:1:PERSON-A']);
    assert.equal(raw.NAME_GIVEN, 'ELIZA M.');
    assert.equal(raw.NAME_SURNAME, 'FISK');
});

test('fsRawFieldsFromApiPerson: EVENT wrapper produces EVENT_<eventType>_PLACE keys for both BIRTH and CENSUS', () => {
    const data = makeApiResponse();
    const byId = buildFsElementIndex(data);
    const raw = fsRawFieldsFromApiPerson(byId, byId['1:1:PERSON-A']);
    assert.equal(raw.EVENT_BIRTH_PLACE, 'Maine, United States');
    assert.equal(raw.EVENT_CENSUS_PLACE, 'St Paul, Ramsey, Minnesota');
});

test('fsRawFieldsFromApiPerson: AGE wrapper is keyed by its own elementType', () => {
    const data = makeApiResponse();
    const byId = buildFsElementIndex(data);
    assert.equal(fsRawFieldsFromApiPerson(byId, byId['1:1:PERSON-A']).AGE, '38');
});

test('fsRawFieldsFromApiPerson: era-absent fields are simply absent from the raw map, not blank-valued', () => {
    const data = makeApiResponse();
    const byId = buildFsElementIndex(data);
    const raw = fsRawFieldsFromApiPerson(byId, byId['1:1:PERSON-B']);
    assert.ok(!('RELATIONSHIP_TO_HEAD' in raw));
    assert.ok(!('MARITAL_STATUS' in raw));
    assert.equal(raw.NAME_GIVEN, 'Bozil');
    assert.equal(raw.SOURCE_HOUSE_NBR, '12');
});
