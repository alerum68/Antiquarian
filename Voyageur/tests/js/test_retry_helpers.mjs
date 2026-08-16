import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { buildRetryNavigationUrl, ancestryIncompletePagesSummary, fsIncompleteItemsSummary } = require('./harness.js');

test('buildRetryNavigationUrl: appends mgs_auto/mgs_run with ? when the URL has no query string', () => {
    const url = buildRetryNavigationUrl('https://www.ancestry.com/imageviewer/collections/6742/images/4240106-00130', 'abc123');
    assert.equal(url, 'https://www.ancestry.com/imageviewer/collections/6742/images/4240106-00130?mgs_auto=1&mgs_run=abc123');
});

test('buildRetryNavigationUrl: appends with & when the URL already has a query string', () => {
    const url = buildRetryNavigationUrl('https://www.familysearch.org/ark:/61903/3:1:XXXX?cc=1417683', 'abc123');
    assert.equal(url, 'https://www.familysearch.org/ark:/61903/3:1:XXXX?cc=1417683&mgs_auto=1&mgs_run=abc123');
});

test('ancestryIncompletePagesSummary: filters to only incomplete pages, keeps page_number/image_id only', () => {
    const pages = [
        {page_number: 1, image_id: 'a1', incomplete: false, people: [{}]},
        {page_number: 2, image_id: 'a2', incomplete: true, people: []},
        {page_number: 3, image_id: 'a3', incomplete: true, people: []},
    ];
    assert.deepEqual(ancestryIncompletePagesSummary(pages), [
        {page_number: 2, image_id: 'a2'},
        {page_number: 3, image_id: 'a3'},
    ]);
});

test('ancestryIncompletePagesSummary: empty when nothing is incomplete', () => {
    assert.deepEqual(ancestryIncompletePagesSummary([{page_number: 1, image_id: 'a1', incomplete: false}]), []);
});

test('fsIncompleteItemsSummary: filters to only incomplete items, keeps item_id only', () => {
    const items = [
        {item_id: '1:1:AAAA', incomplete: false},
        {item_id: '1:1:BBBB', incomplete: true},
    ];
    assert.deepEqual(fsIncompleteItemsSummary(items), [{item_id: '1:1:BBBB'}]);
});
