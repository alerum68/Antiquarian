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