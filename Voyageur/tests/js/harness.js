// Loads Voyageur.js in plain Node so its pure, DOM-free helper functions can be
// unit-tested. Voyageur.js is a single-file Tampermonkey userscript with no build
// step and no module boundary - the whole thing is one IIFE dispatched by
// `window.location.hostname` at its top level (see the "Dispatch by hostname"
// block). Stubbing a hostname that matches neither Ancestry nor FamilySearch means
// that dispatch never calls into any gather function, so none of the DOM-heavy
// code ever runs - only function declarations happen, which is all a Node
// `require()` needs to reach the `module.exports` guard at the end of the file.
'use strict';

global.window = {location: {hostname: 'test.invalid', href: 'https://test.invalid/'}};
global.document = {};
global.sessionStorage = {
    _store: {},
    getItem(key) { return Object.prototype.hasOwnProperty.call(this._store, key) ? this._store[key] : null; },
    setItem(key, value) { this._store[key] = String(value); },
    removeItem(key) { delete this._store[key]; },
};
global.unsafeWindow = undefined;
global.performance = {now: () => Date.now()};
global.GM_xmlhttpRequest = () => {};

module.exports = require('../../Voyageur.js');
