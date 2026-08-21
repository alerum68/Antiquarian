/* global globalThis */
import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const {
    fsImageIndexFieldText, fsImageIndexFindByType,
    fsRawFieldsFromImageIndexPerson, fsBuildRowsFromImageIndexResponse, fsLastUriSegment,
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

// 2026-08-20: explicit user direction - capture every field this API returns, keyed by
// FamilySearch's own GedcomX type URI (trimmed to its trailing segment via
// fsLastUriSegment), with zero renaming/curation at extraction time.
test('fsRawFieldsFromImageIndexPerson: 1880-style person gets every rich field, keyed by its raw type', () => {
    const data = makeImageIndex1880Response();
    const raw = fsRawFieldsFromImageIndexPerson(data.records[0].persons[0]);
    assert.equal(raw.Given, 'Prince A.');
    assert.equal(raw.Surname, 'Gatchill');
    assert.equal(raw.Gender, fsLastUriSegment('http://gedcomx.org/Male'));
    assert.equal(raw.Age, '38 years');
    assert.equal(raw.RelationshipToHead, 'Head');
    assert.equal(raw.SourceHouseholdId, '8735134');
    assert.equal(raw.FatherBirthPlace, 'Maine, United States');
    assert.equal(raw.MotherBirthPlace, 'Maine, United States');
    assert.equal(raw.Race, 'White');
    assert.equal(raw.Occupation, 'Editor');
    assert.equal(raw.MaritalStatus, 'Married');
    assert.equal(raw.Birth_Place, 'Maine, United States');
    // Census fact's place has no single "Place" sub-field (unlike Birth) - State/County/
    // Township/District are its own sub-fields and must all be captured, not just skipped.
    assert.equal(raw.Census_State, 'Dakota Territory');
    assert.equal(raw.Census_County, 'Pembina');
    assert.equal(raw.Census_Township, 'Pembina');
    assert.equal(raw.Census_District, 'ED 75');
});

test('fsRawFieldsFromImageIndexPerson: spouse with a clean single RelationshipToHead value', () => {
    const data = makeImageIndex1880Response();
    const raw = fsRawFieldsFromImageIndexPerson(data.records[0].persons[1]);
    assert.equal(raw.RelationshipToHead, 'Wife');
    assert.equal(raw.Given, 'Hattie O.');
    assert.equal(raw.SourceHouseholdId, '8735134');
});

test('fsRawFieldsFromImageIndexPerson: 1860-style person omits era-absent fields entirely, uses HouseholdId type', () => {
    const data = makeImageIndex1860Response();
    const raw = fsRawFieldsFromImageIndexPerson(data.records[0].persons[0]);
    assert.ok(!('RelationshipToHead' in raw));
    assert.ok(!('MaritalStatus' in raw));
    assert.ok(!('Occupation' in raw));
    assert.ok(!('FatherBirthPlace' in raw));
    assert.ok(!('MotherBirthPlace' in raw));
    assert.ok(!('SourceHouseholdId' in raw));
    assert.equal(raw.HouseholdId, '1');
    assert.equal(raw.Given, 'Joseph');
    assert.equal(raw.Race, 'White');
    // 1860 sample uses MinorCivilDivision where 1880 used Township for the same concept -
    // both must survive verbatim, not be normalized to one shared key.
    assert.equal(raw.Census_MinorCivilDivision, 'On the Red River');
});

test('fsBuildRowsFromImageIndexResponse: builds one row per person with the full raw field set', () => {
    const rows = fsBuildRowsFromImageIndexResponse(makeImageIndex1880Response());
    assert.equal(rows.length, 2);
    const prince = rows.find(r => r.record_ark === '1:1:MCVW-PYP');
    assert.equal(prince.columns.Given, 'Prince A.');
    assert.equal(prince.columns.RelationshipToHead, 'Head');
    assert.equal(prince.person_ark, '');
    const hattie = rows.find(r => r.record_ark === '1:1:MCVW-PY2');
    assert.equal(hattie.columns.RelationshipToHead, 'Wife');
    assert.equal(hattie.columns.SourceHouseholdId, '8735134');
});

test('fsBuildRowsFromImageIndexResponse: 1860-style row omits RelationshipToHead entirely', () => {
    const rows = fsBuildRowsFromImageIndexResponse(makeImageIndex1860Response());
    assert.equal(rows.length, 1);
    assert.ok(!('RelationshipToHead' in rows[0].columns));
    assert.equal(rows[0].columns.Given, 'Joseph');
    assert.equal(rows[0].record_ark, '1:1:MF36-Z6D');
});

test('fsBuildRowsFromImageIndexResponse: empty records array produces no rows, no throw', () => {
    assert.deepEqual(fsBuildRowsFromImageIndexResponse({records: []}), []);
    assert.deepEqual(fsBuildRowsFromImageIndexResponse({}), []);
});