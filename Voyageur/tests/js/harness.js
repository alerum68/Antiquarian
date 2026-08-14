// Loads Voyageur.js in plain Node so its pure, DOM-free helper functions can be
// unit-tested. Voyageur.js is a single-file Tampermonkey userscript with no build
// step and no module boundary - the whole thing is one IIFE dispatched by
// `window.location.hostname` at its top level (see the "Dispatch by hostname"
// block). Stubbing a hostname that matches neither Ancestry nor FamilySearch means
// that dispatch never calls into any gather function, so none of the DOM-heavy
// code ever runs - only function declarations happen, which is all a Node
// `require()` needs to reach the `module.exports` guard at the end of the file.
'use strict';

/* global globalThis, window, document, sessionStorage, unsafeWindow, performance, GM_xmlhttpRequest, module, require */

/** @type {Storage & {_store: Record<string, string>}} */
const mockSessionStorage = {
    _store: {},
    /** @param {string} key */
    getItem(key) { return Object.prototype.hasOwnProperty.call(this._store, key) ? this._store[key] : null; },
    /** @param {string} key @param {*} value */
    setItem(key, value) { this._store[key] = String(value); },
    /** @param {string} key */
    removeItem(key) { delete this._store[key]; },
    get length() { return Object.keys(this._store).length; },
    clear() { this._store = {}; },
    /** @param {number} index */
    key(index) { return Object.keys(this._store)[index] || null; },
};

globalThis.window = {location: {hostname: 'test.invalid', href: 'https://test.invalid/'}};
globalThis.document = {};
globalThis.sessionStorage = mockSessionStorage;
globalThis.unsafeWindow = undefined;
globalThis.performance = {now: () => Date.now()};
globalThis.GM_xmlhttpRequest = () => {};

module.exports = require('../../Voyageur.js');
