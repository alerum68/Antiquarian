# Action-Based Gather Triggers & DOM-Extraction Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove Ancestry's DOM-table-scraper fallback and its DOM-index-detection reload loop now that the index-panel API path is proven reliable, replacing the reliability they provided with a cheap end-of-run retry pass and a loud warning when a page still comes back empty.

**Architecture:** `extractCurrentPageData()` (Ancestry) and `scrapeCurrentImage()` (FS) stop falling back to DOM/reload loops on an API timeout; instead they flag the page `incomplete` and queue it. When the forward pass ends, a short retry pass revisits each queued page once via a real navigation (reusing each provider's existing reload-state mechanism), then finalizes with a persistent toast, a JSON `incomplete_pages` field, and a terminal banner naming anything still incomplete.

**Tech Stack:** Vanilla JS (Tampermonkey userscript, `Voyageur/Voyageur.js`), Python 3 (`Voyageur/A.py`, `Voyageur/FS.py`, `Voyageur/_gather_helpers.py`), `node:test` (JS unit tests via `Voyageur/tests/js/harness.js`), `pytest` (Python unit tests).

**Spec:** `docs/superpowers/specs/2026-08-15-action-based-gather-triggers-design.md`

## Global Constraints

- Comments: terse, single-line, WHY-only. No rambling/narrative comments, no discovery-history anecdotes embedded in code, no AI attribution anywhere (commit messages, comments, docs).
- Never fabricate or guess data. A page/item whose API response never arrives is flagged `incomplete`, never filled with guessed values.
- No new blind time-based delays. Every wait added in this plan is either a bounded API-response wait (already existing pattern) or a real navigation-completion check.
- JS pure functions added in this plan must be exported from `module.exports` at the bottom of `Voyageur.js` and covered by a `Voyageur/tests/js/*.mjs` test using the existing `harness.js` convention.
- Run JS tests with: `node --test "Voyageur/tests/js/*.mjs"` (from the repo root).
- Run Python tests with: `pytest Voyageur/tests/ -q` (from the repo root).

---

### Task 1: Ancestry — remove the DOM-table-scraper fallback

**Files:**
- Modify: `Voyageur/Voyageur.js:1004-1149` (delete `findDetailTab`, `findFieldRow`, `ensureInfoPanelOpen`, `readAlternateEntries`, `readPersonAlternates` and their lead comment)
- Modify: `Voyageur/Voyageur.js:1151-1388` (`extractCurrentPageData()` — remove the DOM-table loop branch, return `{placeBoundaryCrossed, pageEntry}` instead of pushing internally)
- Modify: `Voyageur/Voyageur.js:1618` (the one call site inside `runExtractionLoop()`, minimal update — full rewrite of the surrounding block happens in Task 2)

**Interfaces:**
- Produces: `extractCurrentPageData()` — no arguments (was `(rows)`), returns `Promise<{placeBoundaryCrossed: boolean, pageEntry: object|null}>`. `pageEntry` now includes an `incomplete: boolean` field (`true` when the index-panel API never returned records for this page).
- Consumes: `waitForAncestryIndexPanelResponse`, `ancestryRowsFromIndexPanelResponse`, `ancestryCountryFromState`, `getEnumerationDistrict`, `scrapeSourceCitation`, `parseFilmRollFromImageId`, `getBaseImageId`, `placesMatch` — all unchanged, already defined earlier in the file.

- [ ] **Step 1: Delete the DOM-only alternate-reading helpers**

Delete the entire block from the `// Ancestry's own per-person Detail panel...` comment through the end of `readPersonAlternates()` (`Voyageur.js:1004-1149` in the current file — confirmed via `grep -n` these five declarations, `findDetailTab`/`findFieldRow`/`ensureInfoPanelOpen`/`readAlternateEntries`/`readPersonAlternates`, have no callers anywhere else in the file).

- [ ] **Step 2: Rewrite `extractCurrentPageData()` to drop the DOM branch and return instead of push**

Replace the whole function (currently `Voyageur.js:1151-1388`) with:

```javascript
async function extractCurrentPageData() {
    let imageId = getBaseImageId();
    let country = "USA", state = "", county = "", city = "", placeDetails = "", enumerationDistrict = "";

    let dbid = "0";
    const dbMatch = window.location.href.match(/collections\/(\d+)/i) || window.location.href.match(/dbid=(\d+)/i) || window.location.href.match(/view\/\d+:(\d+)/i);
    if (dbMatch) dbid = dbMatch[1];

    if (typeof unsafeWindow !== 'undefined' && unsafeWindow.__PRELOADED_STATE__) {
        const info = unsafeWindow.__PRELOADED_STATE__.viewer?.imageInfo;
        const pathArr = info?.browsePath || [];
        state = pathArr[0] || "";
        county = pathArr[1] || "";
        city = pathArr[2] || "";
        country = ancestryCountryFromState(state);
        const ed = getEnumerationDistrict(pathArr, info?.structureType);
        enumerationDistrict = ed.value;
        placeDetails = pathArr.slice(3).filter((_, i) => (i + 3) !== ed.index).join(" - ") || "";
    }

    const citation = await scrapeSourceCitation();
    const imageIdGuess = parseFilmRollFromImageId(imageId);
    const filmNumber = citation.film || imageIdGuess.film;
    const rollNumber = citation.roll || imageIdGuess.roll;
    if (citation.ed) enumerationDistrict = citation.ed;
    const repository = citation.repository || "";
    const repositoryLoc = citation.repositoryLoc || "";
    const publisher = citation.publisher || "";
    const pubLoc = citation.pubLoc || "";

    if (DEBUG_MODE) {
        console.log(`[MGS DEBUG] page ${batchPageCounter} | url: ${window.location.href} | cached pids: ${typeof unsafeWindow !== 'undefined' ? unsafeWindow.__mgs_pids.length : 'n/a'}`);
    }

    const pageEntry = {
        page_number: batchPageCounter,
        image_id: imageId,
        country: country, state: state, county: county, city: city, place_details: placeDetails,
        enumeration_district: enumerationDistrict, film_number: filmNumber, roll_number: rollNumber,
        apid_db: dbid !== "0" ? dbid : "",
        repository: repository, repository_loc: repositoryLoc, publisher: publisher, pub_loc: pubLoc,
        people: [],
        incomplete: false,
    };

    // API is the only extraction path - DOM-table scraping proved unnecessary in the
    // common case and unreliable as a fallback (see design spec).
    const dbIdForApi = (dbid && dbid !== "0") ? dbid : null;
    let apiSourcedPeople = null;
    if (dbIdForApi && imageId) {
        const apiWait = await waitForAncestryIndexPanelResponse(dbIdForApi, imageId, {timeoutMs: 8000});
        if (!apiWait.timedOut && apiWait.result && Array.isArray(apiWait.result.records) && apiWait.result.records.length > 0) {
            apiSourcedPeople = ancestryRowsFromIndexPanelResponse(apiWait.result).filter((p) => {
                if (p.pid && seenPids.has(p.pid)) return false;
                if (p.pid) seenPids.add(p.pid);
                return true;
            });
            debugLog(`Ancestry index-panel-data API: ${apiSourcedPeople.length} people (${apiWait.elapsedMs}ms).`);
        } else {
            debugLog(`Ancestry index-panel-data API ${apiWait.timedOut ? 'timed out' : 'returned no records'} after ${apiWait.elapsedMs}ms.`);
        }
    }

    if (apiSourcedPeople) {
        pageEntry.people.push(...apiSourcedPeople);
    } else {
        pageEntry.incomplete = true;
    }

    const thisPlace = {
        state: pageEntry.state, county: pageEntry.county,
        city: pageEntry.city, enumeration_district: pageEntry.enumeration_district,
    };
    if (firstPagePlace === null) {
        firstPagePlace = thisPlace;
    } else if (!placesMatch(thisPlace, firstPagePlace)) {
        return {placeBoundaryCrossed: true, pageEntry: null};
    }

    return {placeBoundaryCrossed: false, pageEntry};
}
```

- [ ] **Step 3: Update the one call site so extraction still works end-to-end**

`runExtractionLoop()` still has its old `if (!isUnindexed) { ... else if (rows && rows.length > 1) { ...extractCurrentPageData(rows)... } }` wrapper at this point (Task 2 removes that wrapper) — inside it, replace:

```javascript
                        const extractResult = await extractCurrentPageData(rows);
                        if (extractResult && extractResult.placeBoundaryCrossed) {
                            debugLog(`Place boundary crossed at page ${batchPageCounter}. Stopping and discarding this page.`);
                            if (window.showToast) window.showToast("New town detected - stopping batch.", "error", 3000);
                            stopBatch();
                            break;
                        }
```

with:

```javascript
                        const extractResult = await extractCurrentPageData();
                        if (extractResult.placeBoundaryCrossed) {
                            debugLog(`Place boundary crossed at page ${batchPageCounter}. Stopping and discarding this page.`);
                            if (window.showToast) window.showToast("New town detected - stopping batch.", "error", 3000);
                            stopBatch();
                            break;
                        }
                        if (extractResult.pageEntry) accumulatedPages.push(extractResult.pageEntry);
```

- [ ] **Step 4: Verify JS syntax and the existing suite still pass**

Run: `node --check Voyageur/Voyageur.js`
Expected: no output (syntax OK)

Run: `node --test "Voyageur/tests/js/*.mjs"`
Expected: `59 pass, 0 fail` (unchanged — this task touches no exported pure function)

- [ ] **Step 5: Commit**

```bash
git add Voyageur/Voyageur.js
git commit -m "refactor(voyageur): remove Ancestry DOM-table-scraper fallback"
```

---

### Task 2: Ancestry — remove the DOM-index-detection reload loop, add end-of-run retry pass

**Files:**
- Modify: `Voyageur/Voyageur.js:70-107` (`saveReloadState`/`loadReloadState`/`clearReloadState`)
- Modify: `Voyageur/Voyageur.js` (`runAncestryGather()` init block, `startBatch()`, `stopBatch()`, `runExtractionLoop()` — line numbers shifted by Task 1, anchor on function names)
- Modify: `Voyageur/Voyageur.js` (`downloadFinalJson()` — Ancestry's)
- Modify: `Voyageur/Voyageur.js` (bottom pure-function section + `module.exports`)
- Modify: `Voyageur/tests/js/test_stop_conditions.mjs`
- Create: `Voyageur/tests/js/test_retry_helpers.mjs`

**Interfaces:**
- Consumes: `extractCurrentPageData()`, `pageEntry.incomplete` — both from Task 1.
- Produces: `buildRetryNavigationUrl(url, runIdValue)` — pure, exported. `ancestryIncompletePagesSummary(pages)` — pure, exported. `saveReloadState`/`loadReloadState` now also carry `pagesNeedingRetry`, `retryPhase`, `currentRetryTarget` (replacing `indexReloadAttempts`).

- [ ] **Step 1: Write failing tests for the two new pure functions**

Create `Voyageur/tests/js/test_retry_helpers.mjs`:

```javascript
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `node --test "Voyageur/tests/js/test_retry_helpers.mjs"`
Expected: FAIL — `buildRetryNavigationUrl is not a function` (not yet exported)

- [ ] **Step 3: Add the two pure functions and export them**

In the bottom pure-function section of `Voyageur.js` (near `ancestryCountryFromState`), add:

```javascript
function buildRetryNavigationUrl(url, runIdValue) {
    const separator = url.includes('?') ? '&' : '?';
    return `${url}${separator}mgs_auto=1&mgs_run=${runIdValue}`;
}

function ancestryIncompletePagesSummary(pages) {
    return (pages || [])
        .filter((p) => p.incomplete)
        .map((p) => ({page_number: p.page_number, image_id: p.image_id}));
}
```

`fsIncompleteItemsSummary` is added in Task 3 (FS track) — leave its test in this file failing for now; Step 4 below only wires the two Ancestry-side functions into `module.exports`.

Update `module.exports` to add `buildRetryNavigationUrl, ancestryIncompletePagesSummary,` to the existing list.

- [ ] **Step 4: Run again — Ancestry-side tests pass, FS-side test still fails (expected until Task 3)**

Run: `node --test "Voyageur/tests/js/test_retry_helpers.mjs"`
Expected: 4 pass (`buildRetryNavigationUrl` x2, `ancestryIncompletePagesSummary` x2), 1 fail (`fsIncompleteItemsSummary is not a function`)

- [ ] **Step 5: Extend the reload-state shape, replacing `indexReloadAttempts`**

Replace `saveReloadState`/`loadReloadState` (`Voyageur.js:70-107`, now shifted after Task 1) with:

```javascript
    const RELOAD_STATE_KEY = 'voyageur_a_reload_state';

    function saveReloadState(state) {
        sessionStorage.setItem(RELOAD_STATE_KEY, JSON.stringify({
            pageUrl: window.location.href,
            accumulatedPages: state.accumulatedPages,
            batchPageCounter: state.batchPageCounter,
            seenPids: Array.from(state.seenPids),
            firstPagePlace: state.firstPagePlace,
            pagesNeedingRetry: state.pagesNeedingRetry,
            retryPhase: state.retryPhase,
            currentRetryTarget: state.currentRetryTarget,
        }));
    }

    function loadReloadState() {
        const raw = sessionStorage.getItem(RELOAD_STATE_KEY);
        if (!raw) return null;
        let parsed;
        try {
            parsed = JSON.parse(raw);
        } catch (e) {
            return null;
        }
        if (parsed.pageUrl !== window.location.href) return null;
        return {
            accumulatedPages: parsed.accumulatedPages || [],
            batchPageCounter: parsed.batchPageCounter || 1,
            seenPids: new Set(parsed.seenPids || []),
            firstPagePlace: parsed.firstPagePlace || null,
            pagesNeedingRetry: parsed.pagesNeedingRetry || [],
            retryPhase: parsed.retryPhase || false,
            currentRetryTarget: parsed.currentRetryTarget || null,
        };
    }

    function clearReloadState() {
        sessionStorage.removeItem(RELOAD_STATE_KEY);
    }
```

- [ ] **Step 6: Update `test_stop_conditions.mjs` for the new shape**

Replace the `indexReloadAttempts: 1` reload-state test (`Voyageur/tests/js/test_stop_conditions.mjs:33-52`) with:

```javascript
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
```

Also replace the two remaining `indexReloadAttempts: 1` occurrences (the URL-changed test and the `clearReloadState` test, `test_stop_conditions.mjs:57` and `:66`) with `pagesNeedingRetry: [], retryPhase: false, currentRetryTarget: null,` — those tests don't assert on this field, just need the call to match the new state shape.

- [ ] **Step 7: Remove the DOM-index-detection reload loop from `runExtractionLoop()`**

In `runAncestryGather()`'s init block, remove:

```javascript
        let indexReloadAttempts = 0;
        const MAX_INDEX_RELOAD_ATTEMPTS = 3;
```

and add:

```javascript
        let pagesNeedingRetry = [];
        let inRetryPhase = false;
        let currentRetryTarget = null;
```

Update the `resumedState` restore block:

```javascript
        let resumingFromReload = false;
        const resumedState = loadReloadState();
        if (resumedState) {
            accumulatedPages = resumedState.accumulatedPages;
            batchPageCounter = resumedState.batchPageCounter;
            seenPids = resumedState.seenPids;
            firstPagePlace = resumedState.firstPagePlace;
            pagesNeedingRetry = resumedState.pagesNeedingRetry;
            inRetryPhase = resumedState.retryPhase;
            currentRetryTarget = resumedState.currentRetryTarget;
            resumingFromReload = true;
            clearReloadState();
        }
```

Replace the whole `runExtractionLoop()` body with:

```javascript
        async function runExtractionLoop() {
            while (isAutoExtracting) {
                const nextBtnSelector = 'button[aria-label="Next image"], .pagination.right button.page, .nextButton, button[title="Next image"]';
                const nextBtnWait = await waitForCondition(() => document.querySelector(nextBtnSelector), {timeoutMs: 5000});
                const nextBtn = nextBtnWait.result;
                const isNextDisabled = isNextBtnDisabled(nextBtn);

                if (window.showToast) window.showToast(`Transcribing page ${batchPageCounter}...`, "success", 1500);
                const extractResult = await extractCurrentPageData();
                if (extractResult.placeBoundaryCrossed) {
                    debugLog(`Place boundary crossed at page ${batchPageCounter}. Stopping and discarding this page.`);
                    if (window.showToast) window.showToast("New town detected - stopping batch.", "error", 3000);
                    stopBatch();
                    break;
                }
                if (extractResult.pageEntry) {
                    accumulatedPages.push(extractResult.pageEntry);
                    if (extractResult.pageEntry.incomplete) {
                        pagesNeedingRetry.push({
                            page_number: extractResult.pageEntry.page_number,
                            image_id: extractResult.pageEntry.image_id,
                            url: window.location.href,
                        });
                    }
                }

                await downloadCurrentImage();

                if (batchPageCounter % CHECKPOINT_INTERVAL_PAGES === 0) {
                    downloadCheckpointJson();
                }

                let finalNextBtn = nextBtn;
                let finalIsNextDisabled = isNextDisabled;
                if (!finalNextBtn || !document.body.contains(finalNextBtn)) {
                    const recheck = await waitForCondition(() => document.querySelector(nextBtnSelector), {timeoutMs: 5000});
                    finalNextBtn = recheck.result;
                    finalIsNextDisabled = isNextBtnDisabled(finalNextBtn);
                }

                if (finalNextBtn && !finalIsNextDisabled) {
                    const prevUrl = window.location.href;
                    if (window.showToast) window.showToast("Advancing to next page...", "success", 1000);
                    if (typeof unsafeWindow !== 'undefined') {
                        unsafeWindow.__mgs_pids = [];
                    }
                    finalNextBtn.click();
                    const navWait = await waitForCondition(() => window.location.href !== prevUrl, {timeoutMs: 15000});
                    if (navWait.timedOut) {
                        if (window.showToast) window.showToast("Navigation timed out. Stopping.", "error");
                        stopBatch();
                        break;
                    }
                    batchPageCounter++;
                } else {
                    stopBatch();
                    break;
                }
            }
        }
```

- [ ] **Step 8: Add the retry pass and wire it into `startBatch()`/`stopBatch()`**

Add, right after `runExtractionLoop()`:

```javascript
        async function finishBatch() {
            if (pagesNeedingRetry.length > 0) {
                await runAncestryRetryPass();
                return;
            }
            const incomplete = ancestryIncompletePagesSummary(accumulatedPages);
            if (incomplete.length > 0) {
                const pageList = incomplete.map((p) => p.page_number).join(', ');
                if (window.showToast) {
                    window.showToast(`Incomplete pages (no index data received): ${pageList}`, 'error', 3600000);
                }
            }
            clearReloadState();
            downloadFinalJson();
        }

        async function runAncestryRetryPass() {
            const target = pagesNeedingRetry.shift();
            saveReloadState({
                accumulatedPages, batchPageCounter, seenPids, firstPagePlace,
                pagesNeedingRetry, retryPhase: true, currentRetryTarget: target,
            });
            window.location.href = buildRetryNavigationUrl(target.url, runId);
        }

        async function retryCurrentPageThenContinue() {
            batchPageCounter = currentRetryTarget.page_number;
            const extractResult = await extractCurrentPageData();
            if (!extractResult.placeBoundaryCrossed && extractResult.pageEntry && extractResult.pageEntry.people.length > 0) {
                const idx = accumulatedPages.findIndex((p) => p.page_number === currentRetryTarget.page_number);
                if (idx !== -1) {
                    accumulatedPages[idx] = extractResult.pageEntry;
                    accumulatedPages[idx].incomplete = false;
                }
            }
            await downloadCurrentImage();
            currentRetryTarget = null;
            await finishBatch();
        }
```

Replace `startBatch()`'s reset block and tail:

```javascript
        function startBatch() {
            isAutoExtracting = true;
            if (!resumingFromReload) {
                accumulatedPages = [];
                seenPids.clear();
                batchPageCounter = 1;
                firstPagePlace = null;
                pagesNeedingRetry = [];
                lastPageSignature = "INITIAL_STATE_NOT_SET";
            }
            resumingFromReload = false;

            if (window._startBtn) window._startBtn.style.display = 'none';
            if (window._stopBtn) window._stopBtn.style.display = 'block';
            if (window._statusLight) window._statusLight.classList.add('running');
            if (window.showToast) window.showToast("Starting Batch Extraction...", "success");

            if (inRetryPhase) {
                inRetryPhase = false;
                retryCurrentPageThenContinue().catch((err) => {
                    console.error('[MGS] Retry pass crashed:', err);
                    downloadFinalJson();
                });
                return;
            }

            runExtractionLoop().catch((err) => {
                console.error('[MGS] Extraction loop crashed:', err);
                if (window.showToast) window.showToast(`Extraction stopped: ${err.message || err}`, 'error', 4000);
                stopBatch();
            });
        }

        function stopBatch() {
            if (!isAutoExtracting) return;
            isAutoExtracting = false;
            if (window._startBtn) window._startBtn.style.display = 'block';
            if (window._stopBtn) window._stopBtn.style.display = 'none';
            if (window._statusLight) window._statusLight.classList.remove('running');
            debugLog("Batch stopped.");
            finishBatch().catch((err) => console.error('[MGS] finishBatch crashed:', err));
        }
```

- [ ] **Step 9: Add `incomplete_pages` to the downloaded JSON**

In Ancestry's `downloadFinalJson()`:

```javascript
        function downloadFinalJson() {
            if (accumulatedPages.length === 0) {
                if (window.showToast) window.showToast("No data gathered to download.", "error");
                return;
            }
            const {year, locationStr} = getYearAndLocation();
            const payload = {
                census_year: year, location: locationStr, pages: accumulatedPages,
                incomplete_pages: ancestryIncompletePagesSummary(accumulatedPages),
            };
            triggerJsonDownload(JSON.stringify(payload, null, 2), `${year} - ${locationStr} - ANC.json`);
            if (window.showToast) window.showToast("Success! Master JSON Downloaded.", "success", 5000);
        }
```

- [ ] **Step 10: Verify JS syntax and the full suite**

Run: `node --check Voyageur/Voyageur.js`
Expected: no output

Run: `node --test "Voyageur/tests/js/*.mjs"`
Expected: `test_retry_helpers.mjs` shows 4 pass (Ancestry-side), 1 still-failing (`fsIncompleteItemsSummary`, resolved in Task 3); every other file unchanged and passing.

- [ ] **Step 11: Commit**

```bash
git add Voyageur/Voyageur.js Voyageur/tests/js/test_stop_conditions.mjs Voyageur/tests/js/test_retry_helpers.mjs
git commit -m "feat(voyageur): replace Ancestry's DOM-reload loop with an end-of-run retry pass"
```

---

### Task 3: FamilySearch — same retry-pass treatment for the orchestration/Image-Index API waits

**Files:**
- Modify: `Voyageur/Voyageur.js:119-149` (`saveFsReloadState`/`loadFsReloadState`)
- Modify: `Voyageur/Voyageur.js` (`scrapeCurrentImage()` → split into `buildFsItemData()` + thin wrapper)
- Modify: `Voyageur/Voyageur.js` (`runFamilySearchGather()` init block, `startBatch()`, `stopBatch()`, `runLoop()`, `downloadFinalJson()` — FS's)
- Modify: `Voyageur/Voyageur.js` (bottom pure-function section + `module.exports`)
- Modify: `Voyageur/tests/js/test_retry_helpers.mjs` (from Task 2 — the `fsIncompleteItemsSummary` test already exists there and starts passing once exported)

**Interfaces:**
- Consumes: `buildRetryNavigationUrl` (Task 2), `fsIncompleteItemsSummary` (test already written in Task 2, function added here), `waitForFsApiResponse`, `waitForFsImageIndexResponse`, `fsBuildRowsFromApiResponse`, `fsBuildRowsFromImageIndexResponse`, `fsBuildCitationTextFromImageIndexResponse`, `detectFsPageType`, `scrapeCitationAndCatalog` — all unchanged.
- Produces: `buildFsItemData(itemId)` — `Promise<{item_id, citation_text, catalog_items, rows, incomplete}>`, no DOM push/seen-check side effects (those stay in the thin `scrapeCurrentImage()` wrapper). `fsIncompleteItemsSummary(items)` — pure, exported.

- [ ] **Step 1: Add `fsIncompleteItemsSummary` and export it**

Next to `ancestryIncompletePagesSummary` in the bottom pure-function section:

```javascript
function fsIncompleteItemsSummary(items) {
    return (items || [])
        .filter((i) => i.incomplete)
        .map((i) => ({item_id: i.item_id}));
}
```

Add `fsIncompleteItemsSummary,` to `module.exports`.

- [ ] **Step 2: Run `test_retry_helpers.mjs` to confirm it now fully passes**

Run: `node --test "Voyageur/tests/js/test_retry_helpers.mjs"`
Expected: 5 pass, 0 fail.

- [ ] **Step 3: Split `scrapeCurrentImage()` into a pure-ish builder and a thin wrapper**

Replace `scrapeCurrentImage()` with:

```javascript
        async function buildFsItemData(itemId) {
            const pageType = await detectFsPageType();
            let rows = [];
            let citationText = '';
            let catalogItems = [];
            let incomplete = false;

            if (pageType === 'image-index') {
                const apiWait = await waitForFsImageIndexResponse(itemId);
                if (apiWait.result) {
                    rows = fsBuildRowsFromImageIndexResponse(apiWait.result);
                    const imageMatch = document.body.innerText.match(/Image\s+(\d+)\s+of\s+(\d+)/i);
                    citationText = fsBuildCitationTextFromImageIndexResponse(apiWait.result, {
                        imageNumber: imageMatch ? imageMatch[1] : undefined,
                        imageTotal: imageMatch ? imageMatch[2] : undefined,
                    });
                } else {
                    incomplete = true;
                    debugLog(`No Image-Index response arrived for item ${itemId} after ${apiWait.elapsedMs}ms.`);
                    if (window.fsShowToast) window.fsShowToast('No index data received for this image.', 'error', 4000);
                }
                const catalog = await scrapeCitationAndCatalog();
                catalogItems = catalog.catalogItems;
            } else if (pageType === 'names') {
                const apiWait = await waitForFsApiResponse(itemId);
                if (apiWait.result) {
                    rows = fsBuildRowsFromApiResponse(apiWait.result);
                } else {
                    incomplete = true;
                    debugLog(`No orchestration-API response arrived for item ${itemId} after ${apiWait.elapsedMs}ms.`);
                    if (window.fsShowToast) window.fsShowToast('No index data received for this image.', 'error', 4000);
                }
                const citation = await scrapeCitationAndCatalog();
                citationText = citation.citationText;
                catalogItems = citation.catalogItems;
            } else {
                incomplete = true;
                debugLog(`Neither Names nor Image Index tab found for item ${itemId} - unrecognized page shape.`);
                if (window.fsShowToast) window.fsShowToast('Unrecognized page.', 'error', 4000);
            }

            return {item_id: itemId, citation_text: citationText, catalog_items: catalogItems, rows, incomplete};
        }

        async function scrapeCurrentImage() {
            const itemId = getItemId();
            if (!itemId || seenItemIds.has(itemId)) return;

            const itemData = await buildFsItemData(itemId);
            await downloadFsImage(itemId);

            seenItemIds.add(itemId);
            accumulatedItems.push(itemData);
            if (itemData.incomplete) {
                pagesNeedingRetry.push({item_id: itemId, url: window.location.href});
            }

            debugLog(`Scraped item ${itemId}: ${itemData.rows.length} index rows.`);
        }
```

- [ ] **Step 4: Extend the FS reload-state shape**

Replace `saveFsReloadState`/`loadFsReloadState` (`Voyageur.js:119-149`) with:

```javascript
    const FS_RELOAD_STATE_KEY = 'voyageur_fs_reload_state';

    function saveFsReloadState(runId, state) {
        sessionStorage.setItem(FS_RELOAD_STATE_KEY, JSON.stringify({
            runId,
            accumulatedItems: state.accumulatedItems,
            seenItemIds: Array.from(state.seenItemIds),
            itemsAtLastCheckpoint: state.itemsAtLastCheckpoint,
            pagesNeedingRetry: state.pagesNeedingRetry,
            retryPhase: state.retryPhase,
            currentRetryTarget: state.currentRetryTarget,
        }));
    }

    function loadFsReloadState(runId) {
        const raw = sessionStorage.getItem(FS_RELOAD_STATE_KEY);
        if (!raw) return null;
        let parsed;
        try {
            parsed = JSON.parse(raw);
        } catch (e) {
            return null;
        }
        if (parsed.runId !== runId) return null;
        return {
            accumulatedItems: parsed.accumulatedItems || [],
            seenItemIds: new Set(parsed.seenItemIds || []),
            itemsAtLastCheckpoint: parsed.itemsAtLastCheckpoint || 0,
            pagesNeedingRetry: parsed.pagesNeedingRetry || [],
            retryPhase: parsed.retryPhase || false,
            currentRetryTarget: parsed.currentRetryTarget || null,
        };
    }

    function clearFsReloadState() {
        sessionStorage.removeItem(FS_RELOAD_STATE_KEY);
    }
```

- [ ] **Step 5: Add `pagesNeedingRetry`/retry-phase state to `runFamilySearchGather()`'s init block**

```javascript
        let pagesNeedingRetry = [];
        let inRetryPhase = false;
        let currentRetryTarget = null;

        let isResumingFsState = false;
        const resumedFsState = loadFsReloadState(runId);
        if (resumedFsState) {
            accumulatedItems = resumedFsState.accumulatedItems;
            seenItemIds = resumedFsState.seenItemIds;
            itemsAtLastCheckpoint = resumedFsState.itemsAtLastCheckpoint;
            pagesNeedingRetry = resumedFsState.pagesNeedingRetry;
            inRetryPhase = resumedFsState.retryPhase;
            currentRetryTarget = resumedFsState.currentRetryTarget;
            isResumingFsState = true;
            clearFsReloadState();
        }
```

- [ ] **Step 6: Add the FS retry pass, wire into `startBatch()`/`stopBatch()`**

Add, right after `runLoop()`:

```javascript
        async function finishBatch() {
            if (pagesNeedingRetry.length > 0) {
                await runFsRetryPass();
                return;
            }
            const incomplete = fsIncompleteItemsSummary(accumulatedItems);
            if (incomplete.length > 0) {
                const idList = incomplete.map((i) => i.item_id).join(', ');
                if (window.fsShowToast) {
                    window.fsShowToast(`Incomplete images (no index data received): ${idList}`, 'error', 3600000);
                }
            }
            clearFsReloadState();
            downloadFinalJson();
        }

        async function runFsRetryPass() {
            const target = pagesNeedingRetry.shift();
            saveFsReloadState(runId, {
                accumulatedItems, seenItemIds, itemsAtLastCheckpoint,
                pagesNeedingRetry, retryPhase: true, currentRetryTarget: target,
            });
            window.location.href = buildRetryNavigationUrl(target.url, runId);
        }

        async function retryCurrentItemThenContinue() {
            const itemData = await buildFsItemData(currentRetryTarget.item_id);
            if (!itemData.incomplete) {
                const idx = accumulatedItems.findIndex((i) => i.item_id === currentRetryTarget.item_id);
                if (idx !== -1) accumulatedItems[idx] = itemData;
            }
            await downloadFsImage(currentRetryTarget.item_id);
            currentRetryTarget = null;
            await finishBatch();
        }
```

Replace `startBatch()`:

```javascript
        function startBatch() {
            isRunning = true;
            if (!isResumingFsState) {
                accumulatedItems = [];
                seenItemIds.clear();
                itemsAtLastCheckpoint = 0;
                pagesNeedingRetry = [];
            }
            isResumingFsState = false;
            if (window._fsStartBtn) window._fsStartBtn.style.display = 'none';
            if (window._fsStopBtn) window._fsStopBtn.style.display = 'block';
            if (window._fsStatusLight) window._fsStatusLight.classList.add('running');
            if (window.fsShowToast) window.fsShowToast('Starting Gather...', 'success');

            if (inRetryPhase) {
                inRetryPhase = false;
                retryCurrentItemThenContinue().catch((err) => {
                    console.error('[Voyageur FS] Retry pass crashed:', err);
                    downloadFinalJson();
                });
                return;
            }

            runLoop().catch((err) => {
                console.error('[Voyageur FS] Loop crashed:', err);
                if (window.fsShowToast) window.fsShowToast(`Gather stopped: ${err.message || err}`, 'error', 4000);
                stopBatch();
            });
        }
```

Replace `stopBatch()`:

```javascript
        function stopBatch() {
            if (!isRunning) return;
            isRunning = false;
            if (window._fsStartBtn) window._fsStartBtn.style.display = 'block';
            if (window._fsStopBtn) window._fsStopBtn.style.display = 'none';
            if (window._fsStatusLight) window._fsStatusLight.classList.remove('running');
            debugLog('Batch stopped.');
            finishBatch().catch((err) => console.error('[Voyageur FS] finishBatch crashed:', err));
        }
```

(`clearFsReloadState()` moved out of `stopBatch()` into `finishBatch()`'s tail — clearing it immediately would wipe state a subsequent retry pass still needs.)

- [ ] **Step 7: Add `incomplete_pages` to FS's downloaded JSON**

```javascript
        function downloadFinalJson() {
            if (accumulatedItems.length === 0) {
                if (window.fsShowToast) window.fsShowToast('No data gathered to download.', 'error');
                return;
            }

            const collectionTitle = document.title || 'FamilySearch Gather';
            const payload = {
                source: 'FS', collection_title: collectionTitle, items: accumulatedItems,
                incomplete_pages: fsIncompleteItemsSummary(accumulatedItems),
            };
            const safeName = collectionTitle.replace(/[/\\?%*:|"<>]/g, '-').slice(0, 120);
            triggerFsJsonDownload(JSON.stringify(payload, null, 2), `FS - ${safeName}.json`);

            if (window.fsShowToast) window.fsShowToast('Success! Gather JSON downloaded.', 'success', 5000);
        }
```

- [ ] **Step 8: Verify JS syntax and the full suite**

Run: `node --check Voyageur/Voyageur.js`
Expected: no output

Run: `node --test "Voyageur/tests/js/*.mjs"`
Expected: all tests pass, including the now-complete `test_retry_helpers.mjs` (5/5).

- [ ] **Step 9: Commit**

```bash
git add Voyageur/Voyageur.js Voyageur/tests/js/test_retry_helpers.mjs
git commit -m "feat(voyageur): add FS end-of-run retry pass for orchestration/Image-Index API timeouts"
```

---

### Task 4: Shared — noisy terminal warning for incomplete pages (A.py/FS.py)

**Files:**
- Modify: `Voyageur/_gather_helpers.py` (new `print_incomplete_pages_warning()`)
- Modify: `Voyageur/A.py:20` (import), `Voyageur/A.py:217` (call site)
- Modify: `Voyageur/FS.py:47` (import), `Voyageur/FS.py:872` (call site)
- Create: `Voyageur/tests/test_gather_helpers.py` (add to existing file — check current name/location first, see Step 1)

**Interfaces:**
- Produces: `print_incomplete_pages_warning(entries: list, label: str) -> None` in `_gather_helpers.py`.
- Consumes: the `incomplete_pages` list from the raw gather JSON (`[{"page_number": N, "image_id": "..."}]` for Ancestry, `[{"item_id": "..."}]` for FS — both from Tasks 2/3).

- [ ] **Step 1: Confirm the existing Python test file's import convention**

Run: `head -10 Voyageur/tests/test_gather_helpers.py`
Expected: `import _gather_helpers as gh` (module alias, not `from ... import name`) — confirmed this session. New tests call `gh.print_incomplete_pages_warning(...)`, not a bare name.

- [ ] **Step 2: Write the failing test**

Add to `Voyageur/tests/test_gather_helpers.py`:

```python
def test_print_incomplete_pages_warning_prints_bordered_banner(capsys):
    entries = [{"page_number": 12, "image_id": "4240106-00130"}, {"page_number": 15, "image_id": "4240106-00133"}]
    gh.print_incomplete_pages_warning(entries, "page(s)")
    out = capsys.readouterr().out
    assert "2 page(s) incomplete" in out
    assert "page 12 (image 4240106-00130)" in out
    assert "page 15 (image 4240106-00133)" in out
    assert "!" * 70 in out


def test_print_incomplete_pages_warning_prints_item_id_when_no_page_number(capsys):
    gh.print_incomplete_pages_warning([{"item_id": "1:1:MCVW-DP2"}], "item(s)")
    out = capsys.readouterr().out
    assert "item 1:1:MCVW-DP2" in out


def test_print_incomplete_pages_warning_no_output_when_empty(capsys):
    gh.print_incomplete_pages_warning([], "page(s)")
    assert capsys.readouterr().out == ""
```

No import changes needed — `gh` already exposes every module-level function.

- [ ] **Step 3: Run to verify it fails**

Run: `pytest Voyageur/tests/test_gather_helpers.py -v`
Expected: FAIL — `AttributeError: module '_gather_helpers' has no attribute 'print_incomplete_pages_warning'`

- [ ] **Step 4: Implement it in `_gather_helpers.py`**

Add:

```python
def print_incomplete_pages_warning(entries: list, label: str) -> None:
    if not entries:
        return
    border = "!" * 70
    print(f"\n{border}")
    print(f"[WARNING] {len(entries)} {label} incomplete - no index data received:")
    for entry in entries:
        page_number = entry.get("page_number")
        identifier = entry.get("image_id") or entry.get("item_id", "")
        if page_number is not None:
            print(f"  - page {page_number} (image {identifier})")
        else:
            print(f"  - item {identifier}")
    print(f"{border}\n")
```

- [ ] **Step 5: Run to verify it passes**

Run: `pytest Voyageur/tests/test_gather_helpers.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 6: Wire into A.py**

Add `print_incomplete_pages_warning,` to the multi-line `from _gather_helpers import (...)` block (`A.py:11-22`), alphabetically between `move_with_retry,` and `resolve_census_image_dir,`. In `main()`, right after `raw_gather = json.load(f)` (`A.py:217`):

```python
        with open(final_json, "r", encoding="utf-8") as f:
            raw_gather = json.load(f)
        print_incomplete_pages_warning(raw_gather.get("incomplete_pages", []), "page(s)")
        normalized = normalize_ancestry_census_gather(raw_gather, dbid)
```

- [ ] **Step 7: Wire into FS.py**

Add `print_incomplete_pages_warning,` to the multi-line `from _gather_helpers import (...)` block (`FS.py:37-49`), alphabetically between `move_with_retry,` and `resolve_census_image_dir,`. In `main()`, right after `raw_data = json.loads(_read_text_with_retry(raw_json_file))` (`FS.py:872`):

```python
    raw_data = json.loads(_read_text_with_retry(raw_json_file))
    print_incomplete_pages_warning(raw_data.get("incomplete_pages", []), "item(s)")
    print("\n[System] Converting raw scrape into Gather JSON...")
```

- [ ] **Step 8: Run the full Python suite**

Run: `pytest Voyageur/tests/ -q`
Expected: all pass, no new failures.

Run: `python -m py_compile Voyageur/A.py Voyageur/FS.py Voyageur/_gather_helpers.py`
Expected: no output (syntax OK)

- [ ] **Step 9: Commit**

```bash
git add Voyageur/_gather_helpers.py Voyageur/A.py Voyageur/FS.py Voyageur/tests/test_gather_helpers.py
git commit -m "feat(voyageur): print a bordered terminal warning for incomplete gather pages"
```

---

### Task 5: FS citation-builder investigation (live capture — user-performed)

This task cannot be executed by an agent: FamilySearch's search requires an authenticated account (confirmed this session — an unauthenticated automated browser session got 0 results / stuck spinners against FamilySearch's search UI), and per this project's established discipline, live gather/network verification runs in the user's own real browser, not Claude-driven automation.

**Goal:** capture one real orchestration-API `names`-page response and determine two open questions from the design spec, so a follow-up plan can implement `fsBuildCitationTextFromOrchestrationResponse()` with real field names instead of guessed ones.

**Procedure:**

1. Log into FamilySearch, search for and open any US census record that lands on the "Names" tab (not "Image Index" — Task 3's `detectFsPageType()` is how the code itself tells the two apart).
2. Open DevTools → Network tab, filter for `orchestration/sls/image`.
3. Reload the record page once so the request fires fresh; click the matching request; copy the full JSON response.
4. Save it as `Voyageur/tests/fixtures/fs_orchestration_names_response.json` (new file, new `fixtures/` directory if it doesn't exist yet).
5. In that JSON's `elements` array, look for `RECORD`-level (not `PERSON`-level) `FIELD` elements whose `fieldType` looks like it carries: collection title, the image/record URL, state/county/township/district (browse path), film number, and repository name — the same concepts `fsBuildCitationTextFromImageIndexResponse()` already reads from the *other* endpoint's differently-shaped response (`Voyageur.js`, search `fsBuildCitationTextFromImageIndexResponse` for the field list to match against).
6. Separately, check both this response and a saved Image-Index response (`Voyageur/tests/js/test_fs_image_index_parser.mjs` already has real sample data inline) for anything resembling the Film/Digital Note catalog table (`scrapeCitationAndCatalog()`'s `catalogItems` shape: `{label, item_number, note}`).
7. Report back: the exact `fieldType` strings found for each concept in step 5 (or "not present" if genuinely absent), and whether either source carries catalog-item-equivalent data.

**Output of this task is not code** — it's the fixture file plus the field-type findings, which become the input to a short follow-up plan implementing `fsBuildCitationTextFromOrchestrationResponse()` (and, if catalog items are found in JSON, dropping `scrapeCitationAndCatalog()`/the Information-tab click entirely). That follow-up plan is out of this plan's scope — writing it now with guessed field names would violate this project's "never fabricate data" discipline the same way shipping guessed GEDCOM fields would.

---

## Self-Review

**Spec coverage:**
- Ancestry DOM-table-scraper removal → Task 1. ✓
- Ancestry DOM-index-detection reload loop removal → Task 2. ✓
- End-of-run retry pass, both providers → Tasks 2, 3. ✓
- Noisy warning (toast + JSON field + terminal banner) → Tasks 2, 3 (toast + JSON), Task 4 (banner). ✓
- FS citation-text JSON-sourcing (issue #25) → Task 5 (investigation only; implementation is an explicitly-deferred follow-up, matching the spec's own "genuinely unresolved" framing for this piece). ✓
- HBCA/LAC audit → already covered in the spec itself as "no code changes needed"; no task required.
- Rate-limiter/file-retry sleeps → explicitly out of scope per spec; no task touches them.

**Placeholder scan:** no TBD/TODO; Task 5 is an investigation task by design (its own procedure is fully concrete), not a stand-in for undone implementation work.

**Type consistency:** `extractCurrentPageData()` return shape (`{placeBoundaryCrossed, pageEntry}`, Task 1) is consumed identically in Task 2's rewritten `runExtractionLoop()`. `buildFsItemData()`'s return shape (Task 3) matches what `scrapeCurrentImage()` and `retryCurrentItemThenContinue()` both expect. `pagesNeedingRetry`/`retryPhase`/`currentRetryTarget` field names are identical across `saveReloadState`/`loadReloadState` (Task 2) and `saveFsReloadState`/`loadFsReloadState` (Task 3). `ancestryIncompletePagesSummary`/`fsIncompleteItemsSummary` signatures match their call sites in both `finishBatch()` and `downloadFinalJson()`.

---

Plan complete and saved to `docs/superpowers/plans/2026-08-15-action-based-gather-triggers.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
