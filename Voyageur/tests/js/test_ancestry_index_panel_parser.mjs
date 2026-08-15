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
    assert.equal(columns['Gender'], 'M');
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

test('ancestryColumnsFromIndexPanelRecord: SelfGender normalizes Male/Female/unrecognized to M/F/U', () => {
    // Confirmed live (Task 5 verification): the API's SelfGender value is a full word,
    // unlike the DOM table's single-letter form - normalized to the M/F/U literal every
    // other sex-bearing field in this codebase (and Commissioner's schema) expects.
    const male = ancestryColumnsFromIndexPanelRecord(
        {recordFields: [{fieldName: 'SelfGender', value: 'Male', correctedValue: null}]}, {});
    assert.equal(male['Gender'], 'M');

    const female = ancestryColumnsFromIndexPanelRecord(
        {recordFields: [{fieldName: 'SelfGender', value: 'Female', correctedValue: null}]}, {});
    assert.equal(female['Gender'], 'F');

    const unknown = ancestryColumnsFromIndexPanelRecord(
        {recordFields: [{fieldName: 'SelfGender', value: 'Unknown', correctedValue: null}]}, {});
    assert.equal(unknown['Gender'], 'U');
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
