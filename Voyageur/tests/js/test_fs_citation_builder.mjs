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