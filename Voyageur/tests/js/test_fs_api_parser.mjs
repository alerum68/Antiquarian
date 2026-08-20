/* global globalThis */
import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const {
    buildFsElementIndex, fsFieldText, fsPersonFieldText, fsWrappedFieldText,
    fsPersonName, fsPersonEventPlace, fsPersonBirthPlace, fsPersonResidencePlace,
    fsResidencePlaceToBrowsePath, fsImageLevelFieldText, fsHouseholds,
    fsBuildRowsFromApiResponse, fsBuildCitationTextFromApiResponse,
    fsCanonicalFieldsFromApiPerson, fsColumnsFromCanonicalFields,
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
        'Family Number': '2',
    });
    assert.ok(!('Relationship to Head' in rowB.columns));
});

test('fsBuildRowsFromApiResponse: Family Number falls back to FS_HOUSEHOLD_ID when SOURCE_HOUSE_NBR exists', () => {
    const data = makeApiResponse();
    // Give PERSON-B both FS_HOUSEHOLD_ID and the pre-existing SOURCE_HOUSE_NBR to prove
    // FS_HOUSEHOLD_ID is used and is not overridden/blocked by SOURCE_HOUSE_NBR.
    data.elements.push(
        {elementType: 'FIELD', id: 'field-fshouseholdid-b', fieldType: 'FS_HOUSEHOLD_ID', fieldValues: [{normalizedValues: [{text: '999'}]}]},
    );
    data.elements.find(e => e.id === '1:1:PERSON-B').subElements.push({id: 'field-fshouseholdid-b'});
    const rows = fsBuildRowsFromApiResponse(data);
    const rowB = rows.find(r => r.person_ark === '1:1:PERSON-B');
    // SOURCE_HOUSE_NBR ("12") is a dwelling number, not a family number - it is never
    // consulted by fsFamilyNumber. FS_HOUSEHOLD_ID ("999") is used as the family number.
    assert.equal(rowB.columns['Family Number'], '999');
});

test('fsBuildRowsFromApiResponse: Family Number prefers SOURCE_HOUSEHOLD_ID over FS_HOUSEHOLD_ID when both exist', () => {
    const data = makeApiResponse();
    // Give PERSON-A (who already has SOURCE_HOUSEHOLD_ID '90') an additional FS_HOUSEHOLD_ID field of '999'.
    data.elements.push(
        {elementType: 'FIELD', id: 'field-fshouseholdid-a', fieldType: 'FS_HOUSEHOLD_ID', fieldValues: [{normalizedValues: [{text: '999'}]}]},
    );
    data.elements.find(e => e.id === '1:1:PERSON-A').subElements.push({id: 'field-fshouseholdid-a'});
    const rows = fsBuildRowsFromApiResponse(data);
    const rowA = rows.find(r => r.person_ark === '1:1:PERSON-A');
    // SOURCE_HOUSEHOLD_ID ("90") should win over FS_HOUSEHOLD_ID ("999").
    assert.equal(rowA.columns['Family Number'], '90');
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
