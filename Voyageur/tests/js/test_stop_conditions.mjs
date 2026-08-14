import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { placesMatch, saveReloadState, loadReloadState, clearReloadState } = require('./harness.js');

test('placesMatch: identical place tuples match', () => {
    const a = {state: 'Dakota Territory', county: 'Pembina', city: 'Not Stated', enumeration_district: '076'};
    const b = {state: 'Dakota Territory', county: 'Pembina', city: 'Not Stated', enumeration_district: '076'};
    assert.equal(placesMatch(a, b), true);
});

test('placesMatch: different enumeration_district does not match, even with identical city', () => {
    const a = {state: 'Dakota Territory', county: 'Pembina', city: 'Not Stated', enumeration_district: '076'};
    const b = {state: 'Dakota Territory', county: 'Pembina', city: 'Not Stated', enumeration_district: '077'};
    assert.equal(placesMatch(a, b), false);
});

test('placesMatch: different city does not match', () => {
    const a = {state: 'Dakota Territory', county: 'Pembina', city: 'Walhalla', enumeration_district: '076'};
    const b = {state: 'Dakota Territory', county: 'Pembina', city: 'Neche', enumeration_district: '076'};
    assert.equal(placesMatch(a, b), false);
});

test('reload state: loadReloadState returns null when nothing saved', () => {
    global.sessionStorage._store = {};
    global.window.location.href = 'https://www.ancestry.com/imageviewer/collections/6742/images/4240106-00130';
    assert.equal(loadReloadState(), null);
});

test('reload state: save then load round-trips on the same page URL', () => {
    global.sessionStorage._store = {};
    global.window.location.href = 'https://www.ancestry.com/imageviewer/collections/6742/images/4240106-00130';

    saveReloadState({
        accumulatedPages: [{page_number: 1}],
        batchPageCounter: 2,
        seenPids: new Set(['p1', 'p2']),
        firstPagePlace: {state: 'Dakota Territory', county: 'Pembina', city: 'Not Stated', enumeration_district: '076'},
        indexReloadAttempts: 1,
    });

    const restored = loadReloadState();
    assert.deepEqual(restored.accumulatedPages, [{page_number: 1}]);
    assert.equal(restored.batchPageCounter, 2);
    assert.ok(restored.seenPids instanceof Set);
    assert.deepEqual([...restored.seenPids].sort(), ['p1', 'p2']);
    assert.deepEqual(restored.firstPagePlace, {state: 'Dakota Territory', county: 'Pembina', city: 'Not Stated', enumeration_district: '076'});
    assert.equal(restored.indexReloadAttempts, 1);
});

test('reload state: load returns null when the page URL has changed since saving', () => {
    global.sessionStorage._store = {};
    global.window.location.href = 'https://www.ancestry.com/imageviewer/collections/6742/images/4240106-00130';
    saveReloadState({accumulatedPages: [], batchPageCounter: 1, seenPids: new Set(), firstPagePlace: null, indexReloadAttempts: 1});

    global.window.location.href = 'https://www.ancestry.com/imageviewer/collections/6742/images/4240106-00131';
    assert.equal(loadReloadState(), null);
});

test('reload state: clearReloadState removes saved state', () => {
    global.sessionStorage._store = {};
    global.window.location.href = 'https://www.ancestry.com/imageviewer/collections/6742/images/4240106-00130';
    saveReloadState({accumulatedPages: [], batchPageCounter: 1, seenPids: new Set(), firstPagePlace: null, indexReloadAttempts: 1});

    clearReloadState();
    assert.equal(loadReloadState(), null);
});
