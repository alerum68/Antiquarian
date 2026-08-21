/* global globalThis */
import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const {
    getCountryFromState, incompleteItemsSummary, findByAriaLabel
} = require('./harness.js');

test('getCountryFromState correctly maps states and provinces', () => {
    assert.equal(getCountryFromState('Alabama'), 'USA');
    assert.equal(getCountryFromState('Ontario'), 'Canada');
    assert.equal(getCountryFromState('Unknown'), 'USA');
});

test('incompleteItemsSummary maps missing ids correctly', () => {
    const items = [
        { page_number: 1, image_id: 'A', item_id: '1', incomplete: true },
        { page_number: 2, image_id: 'B', item_id: '2', incomplete: false },
        { page_number: 3, image_id: 'C', item_id: '3', incomplete: true }
    ];
    const summary = incompleteItemsSummary(items);
    assert.equal(summary.length, 2);
    assert.equal(summary[0].page_number, 1);
    assert.equal(summary[0].image_id, 'A');
    assert.equal(summary[0].item_id, '1');
});

// findByAriaLabel: the test harness's `document` is a plain {} stub (no jsdom - see
// harness.js), so DOM query behavior is exercised via a minimal hand-built
// querySelectorAll stub rather than a real DOM, matching the project's "no new
// dependencies" convention.
function fakeElement(ariaLabel) {
    return { getAttribute: (name) => (name === 'aria-label' ? ariaLabel : null) };
}

test('findByAriaLabel: matches exact aria-label regardless of visible text content', () => {
    globalThis.document.querySelectorAll = () => [fakeElement('Names'), fakeElement('Save Record')];
    const el = findByAriaLabel('button', 'Names');
    assert.equal(el.getAttribute('aria-label'), 'Names');
});

test('findByAriaLabel: returns null when no match', () => {
    globalThis.document.querySelectorAll = () => [fakeElement('Save Record')];
    assert.equal(findByAriaLabel('button', 'Names'), null);
});
