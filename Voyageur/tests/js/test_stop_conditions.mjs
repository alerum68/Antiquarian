/* global globalThis */
import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const {
    placesMatch, saveReloadState, loadReloadState, clearReloadState,
    markFsRunStopped, isFsRunStopped, clearFsRunStopped,
} = require('./harness.js');

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
    globalThis.sessionStorage._store = {};
    globalThis.window.location.href = 'https://www.ancestry.com/imageviewer/collections/6742/images/4240106-00130';
    assert.equal(loadReloadState(), null);
});

test('reload state: save then load round-trips on the same page URL', () => {
    globalThis.sessionStorage._store = {};
    globalThis.window.location.href = 'https://www.ancestry.com/imageviewer/collections/6742/images/4240106-00130';

    saveReloadState({
        accumulatedPages: [{page_number: 1}],
        batchPageCounter: 2,
        seenPids: new Set(['p1', 'p2']),
        firstPagePlace: {state: 'Dakota Territory', county: 'Pembina', city: 'Not Stated', enumeration_district: '076'},
        pagesNeedingRetry: [{page_number: 1, image_id: 'a1', url: 'https://www.ancestry.com/imageviewer/collections/6742/images/4240106-00129'}],
        retryPhase: true,
        currentRetryTarget: {page_number: 3, image_id: 'a3', url: 'https://www.ancestry.com/imageviewer/collections/6742/images/4240106-00131'},
    });

    const restored = loadReloadState();
    assert.deepEqual(restored.accumulatedPages, [{page_number: 1}]);
    assert.equal(restored.batchPageCounter, 2);
    assert.ok(restored.seenPids instanceof Set);
    assert.deepEqual([...restored.seenPids].sort(), ['p1', 'p2']);
    assert.deepEqual(restored.firstPagePlace, {state: 'Dakota Territory', county: 'Pembina', city: 'Not Stated', enumeration_district: '076'});
    assert.deepEqual(restored.pagesNeedingRetry, [{page_number: 1, image_id: 'a1', url: 'https://www.ancestry.com/imageviewer/collections/6742/images/4240106-00129'}]);
    assert.equal(restored.retryPhase, true);
    assert.deepEqual(restored.currentRetryTarget, {page_number: 3, image_id: 'a3', url: 'https://www.ancestry.com/imageviewer/collections/6742/images/4240106-00131'});
});

test('reload state: load returns null when the page URL has changed since saving', () => {
    globalThis.sessionStorage._store = {};
    globalThis.window.location.href = 'https://www.ancestry.com/imageviewer/collections/6742/images/4240106-00130';
    saveReloadState({accumulatedPages: [], batchPageCounter: 1, seenPids: new Set(), firstPagePlace: null, pagesNeedingRetry: [], retryPhase: false, currentRetryTarget: null});

    globalThis.window.location.href = 'https://www.ancestry.com/imageviewer/collections/6742/images/4240106-00131';
    assert.equal(loadReloadState(), null);
});

test('reload state: clearReloadState removes saved state', () => {
    globalThis.sessionStorage._store = {};
    globalThis.window.location.href = 'https://www.ancestry.com/imageviewer/collections/6742/images/4240106-00130';
    saveReloadState({accumulatedPages: [], batchPageCounter: 1, seenPids: new Set(), firstPagePlace: null, pagesNeedingRetry: [], retryPhase: false, currentRetryTarget: null});

    clearReloadState();
    assert.equal(loadReloadState(), null);
});

// Regression: a goToNextImage() navigation already in flight when Stop is clicked can land
// after stopBatch() already ran on the old page - too late for that page's own
// history.replaceState() URL-strip to affect a navigation already committed to a URL built
// while mgs_auto=1 was still present. This sessionStorage-backed flag is the fallback that
// still blocks shouldAutoStart on that later landing. See FS_STOPPED_RUNS_KEY's own note.
test('FS stopped-run tracking: isFsRunStopped is false before any stop is marked', () => {
    globalThis.sessionStorage._store = {};
    assert.equal(isFsRunStopped('run-abc'), false);
});

test('FS stopped-run tracking: markFsRunStopped makes isFsRunStopped true for that run only', () => {
    globalThis.sessionStorage._store = {};
    markFsRunStopped('run-abc');
    assert.equal(isFsRunStopped('run-abc'), true);
    assert.equal(isFsRunStopped('run-xyz'), false);
});

test('FS stopped-run tracking: clearFsRunStopped un-blocks a deliberate restart of the same run', () => {
    globalThis.sessionStorage._store = {};
    markFsRunStopped('run-abc');
    clearFsRunStopped('run-abc');
    assert.equal(isFsRunStopped('run-abc'), false);
});

test('FS stopped-run tracking: multiple runs tracked independently', () => {
    globalThis.sessionStorage._store = {};
    markFsRunStopped('run-1');
    markFsRunStopped('run-2');
    assert.equal(isFsRunStopped('run-1'), true);
    assert.equal(isFsRunStopped('run-2'), true);
    clearFsRunStopped('run-1');
    assert.equal(isFsRunStopped('run-1'), false);
    assert.equal(isFsRunStopped('run-2'), true);
});
