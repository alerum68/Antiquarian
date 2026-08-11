# FamilySearch Household-View Gather Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **SUPERSEDED:** This plan is historical. Its checklist steps marked `- [ ]` were superseded and never executed as written; see the live tracker `docs/plans/task.md` for the actual disposition.

**Goal:** Replace `Voyageur.js`'s `scrapeIndexRows()` (which reads FamilySearch's old "Image Index" `<table>`, now gone) with a scraper for FamilySearch's new household-grouped "Names" panel, producing the same `{columns, person_ark, attached_fsftid}` row shape so `Voyageur/FS.py` needs no changes.

**Architecture:** Three new JS functions replace one old one inside `runFamilySearchGather()`: `parseHouseholdSections()` reads the Names panel's bulk household/role list with zero clicks; `scrapePersonDetail(buttonEl)` clicks one person's row and reads their "View Name" detail panel; `scrapeNamesPanel()` orchestrates both, dedupes same-household repeats, assigns a synthetic `Family Number` per household section, and assembles rows in the pre-existing shape. A new Python regression test locks in the design's core compatibility claim — that `FS.py`'s `build_census_json()`/`Archivist/Census.py` require no changes — before any JS is touched, so a violated assumption surfaces immediately rather than after the rewrite.

**Tech Stack:** JavaScript (Tampermonkey userscript, no build step, no test runner), Python/pytest (`Voyageur/tests/test_fs.py`).

## Global Constraints

- No behavior change to `Voyageur/FS.py`, `Archivist/Census.py`, or `downloadFsImage()` — this plan's Task 1 test exists specifically to prove that constraint holds; if it doesn't pass unmodified, stop and re-open the design rather than patching Python to fit.
- No extraction or replay of an auth bearer token to reach the private `platform/records/*` API — stays DOM-based (see design's Background section on the 401).
- `person_ark`/PID must come only from the Tree Attachment link (`/en/tree/person/{PID}`, no `/details/` segment) — never from the "VIEW RECORD" link, which yields `record_ark` instead (see design's terminology note on this exact confusion during brainstorming).
- Match elements by visible/accessible text, never by FamilySearch's own CSS class names — the established convention in this file (see `findByExactText`'s own comment) and the reason the old scraper survived this long relative to a class-name-based one would have.
- No comments restating what code does; only comments capturing non-obvious WHY, matching this file's existing comment style.
- Spec: `docs/superpowers/specs/2026-08-07-familysearch-household-view-gather-design.md`.

---

## Symbol reference (verified by direct read against `Voyageur/Voyageur.js` and `Voyageur/FS.py` before Task 1 started)

- `waitForCondition(checkFn, {timeoutMs, target})` (`Voyageur.js:27`) — module-level shared helper, returns `Promise<{result, elapsedMs, timedOut}>`. `checkFn` returning a truthy value resolves immediately or on the next DOM mutation.
- `findByExactText(selector, text)` (`Voyageur.js:1251`) — returns the first element matching `selector` whose `textContent.trim() === text`, or `null`.
- `clickTab(tabText)` (`Voyageur.js:1261`) — waits for and clicks a `[role="tab"], button, a` matching `tabText` via `findByExactText`; returns `false` if not found within 5s.
- `debugLog(msg)` (`Voyageur.js:1166`) — `console.log('[Voyageur FS] ' + msg)` when `DEBUG_MODE` (always `true` today).
- `getItemId()` (`Voyageur.js:1273`) — extracts the current image's item id from the URL path.
- `scrapeIndexRows()` (`Voyageur.js:1323-1411`) — **deleted by this plan**, replaced by `parseHouseholdSections()` + `scrapePersonDetail()` + `scrapeNamesPanel()`.
- `scrapeCurrentImage()` (`Voyageur.js:1413-1427`) — calls `scrapeIndexRows()` today; Task 4 repoints it to `scrapeNamesPanel()`.
- `FS.build_census_json(raw, items_raw, catalog_items)` (`FS.py:578`) — consumes `it.get("rows", [])`, each row read as `row.get("columns", {})` / `row.get("person_ark", "")` / `row.get("attached_fsftid", "")`. Column keys already recognized by the downstream pipeline (per `Voyageur/tests/test_fs.py:58-77`'s existing fixture and `Archivist/Census.py`'s own candidate-list constants): `"Given Name"`, `"Surname"`, `"Gender"` (**not** `"Sex"` — confirmed against `Census.py:94`'s `get_gender()`), `"Age"`, `"Relationship to Head"` (`Census.py:448`'s `RELATIONSHIP_COLUMN_CANDIDATES`), `"Family Number"` (`Census.py:1065`'s candidate list).
- `Census.normalize_relationship()`/`REL_SPOUSE`/`REL_CHILD` (`Census.py:449-468`) — lowercases and strips punctuation only; recognizes plain-English values verbatim (`"Spouse"`, `"Child"`, `"Wife"`, `"Son"`, `"Daughter"`, `"Head"`, `"Self"`, ...). No further mapping needed for values FamilySearch's own Household Details panel already uses.

---

### Task 1: Lock in the "no Python changes needed" claim with a regression test

**Files:**
- Modify: `Voyageur/tests/test_fs.py`

**Interfaces:**
- Consumes: `FS.build_census_json(raw: dict, items_raw: List[dict], catalog_items: Dict[str, dict]) -> dict` (existing, unchanged signature).
- Produces: nothing new — this task adds coverage only, proving the design's core assumption before any JS is touched.

- [ ] **Step 1: Write the test, using the new scraper's target row shape**

Add to `Voyageur/tests/test_fs.py`:

```python
def test_build_census_json_accepts_household_view_row_shape():
    """Locks in this design's core claim: the household-view scraper (replacing the old
    Image Index table scraper) can produce rows in this exact shape with zero FS.py/Census.py
    changes - see docs/superpowers/specs/2026-08-07-familysearch-household-view-gather-design.md.
    Column keys and values mirror what a real View Name panel showed live (Joseph Rolette
    household, 1850 Minnesota census): Given Name/Surname split from Essential Information,
    Gender from "Sex: M", Relationship to Head from Household Details ("Spouse"/"Child"),
    Family Number synthesized per household section (not from FamilySearch, which has no
    such field)."""
    raw = {"collection_title": "Minnesota, 1850 federal census : population schedules"}
    items_raw = [{
        "item_id": "3:1:S3HY-67NL-ZP",
        "citation_text": '"Minnesota, 1850 federal census," database with images, FamilySearch '
                          '(https://familysearch.org : 3 August 2026), Kittson > image 39; '
                          "NARA microfilm publication.",
        "rows": [
            {"columns": {"Given Name": "Joseph", "Surname": "Rolette", "Gender": "M", "Age": "35",
                        "Relationship to Head": "Head", "Family Number": "1"},
             "person_ark": "MZ2Z-WM4", "attached_fsftid": "9CJG-851"},
            {"columns": {"Given Name": "Angelic", "Surname": "Rolette", "Gender": "F", "Age": "30",
                        "Relationship to Head": "Spouse", "Family Number": "1"},
             "person_ark": "MZ2Z-WM5", "attached_fsftid": ""},
            {"columns": {"Given Name": "Joseph", "Surname": "Rolette", "Gender": "M", "Age": "9",
                        "Relationship to Head": "Child", "Family Number": "1"},
             "person_ark": "MZ2Z-WM6", "attached_fsftid": ""},
            {"columns": {"Given Name": "George", "Surname": "Monison", "Gender": "M", "Age": "22",
                        "Relationship to Head": "No Relation", "Family Number": "1"},
             "person_ark": "MZ2Z-WM7", "attached_fsftid": ""},
            {"columns": {"Given Name": "J Baptiste", "Surname": "Cardinal", "Gender": "M", "Age": "40",
                        "Family Number": "2"},
             "person_ark": "MZ2Z-XX1", "attached_fsftid": ""},
        ],
    }]

    result = FS.build_census_json(raw, items_raw, {})

    people = result["pages"][0]["people"]
    assert len(people) == 5
    assert people[0]["pid"] == "MZ2Z-WM4"
    assert people[0]["person_ark"] == "MZ2Z-WM4"
    assert people[0]["fsftid"] == "9CJG-851"
    assert people[0]["familysearch_url"] == "https://www.familysearch.org/ark:/61903/1:1:MZ2Z-WM4"
    assert people[0]["columns"]["Relationship to Head"] == "Head"
    # J Baptiste Cardinal's household has no relationship data at all (the bare-"Primary"
    # case confirmed live) - the column must simply be absent, not fabricated as empty string.
    assert "Relationship to Head" not in people[4]["columns"]
```

- [ ] **Step 2: Run the test to verify it already passes against unmodified `FS.py`**

Run: `cd Voyageur && pytest tests/test_fs.py::test_build_census_json_accepts_household_view_row_shape -v`
Expected: **PASS**, with zero changes to `FS.py` or `Archivist/Census.py`. This is not a red-green cycle — a failure here means the design's central compatibility claim is wrong and Task 2 onward should not proceed until that's resolved (re-open `docs/superpowers/specs/2026-08-07-familysearch-household-view-gather-design.md`'s Background section).

- [ ] **Step 3: Run the full Voyageur test suite to confirm nothing else regressed**

Run: `cd Voyageur && pytest tests/ -v`
Expected: all PASS (same count as before this change, plus the one new test).

- [ ] **Step 4: Commit**

```bash
git add Voyageur/tests/test_fs.py
git commit -m "test: lock in build_census_json's tolerance of the household-view scraper's row shape"
```

---

### Task 2: `parseHouseholdSections()` — bulk household/role list read, no clicks

**Files:**
- Modify: `Voyageur/Voyageur.js` (inside `runFamilySearchGather()`, replacing the start of `scrapeIndexRows()`, `Voyageur.js:1323-1411`)

**Interfaces:**
- Consumes: `findByExactText`, `clickTab`, `waitForCondition` (all existing, unchanged).
- Produces: `async function parseHouseholdSections(): Promise<Array<{householdLabel: string, members: Array<{name: string, roleHint: string, viewButton: Element}>}>>` — consumed by Task 4's `scrapeNamesPanel()`. `viewButton` is the clickable element Task 3's `scrapePersonDetail()` clicks.

- [ ] **Step 1: Add `parseHouseholdSections()`**

Insert immediately before `scrapeIndexRows()` in `Voyageur.js` (`scrapeIndexRows()` itself is deleted in Task 4, once nothing references it):

```javascript
async function parseHouseholdSections() {
    const ok = await clickTab('Names');
    if (!ok) return [];

    // FamilySearch renders the "Names" panel shell immediately but fills in household
    // content a beat later (same skeleton-then-fill race already handled for the old
    // Image Index table and the citation panel) - wait for at least one household
    // heading, or the panel's own "no names" state, before reading anything.
    const namesWait = await waitForCondition(() => {
        if (document.body.innerText.includes('No names have been indexed for this image')) {
            return {empty: true};
        }
        const heading = [...document.querySelectorAll('h1, h2, h3, h4, h5, h6')]
            .find(h => /\sHousehold$/.test(h.textContent.trim()));
        return heading ? {found: true} : null;
    }, {timeoutMs: 15000});
    if (!namesWait.result || namesWait.result.empty) return [];

    // FamilySearch's own household heading level/tag isn't assumed stable (matches this
    // file's own "don't trust FamilySearch's markup" convention) - collect every heading
    // and every list-like container in document order, then attribute each container to
    // whichever heading precedes it, up to the next heading.
    const headings = [...document.querySelectorAll('h1, h2, h3, h4, h5, h6')]
        .filter(h => /\sHousehold$/.test(h.textContent.trim()));
    const listContainers = [...document.querySelectorAll('[role="list"], ul, ol')];

    const sections = [];
    for (let i = 0; i < headings.length; i++) {
        const heading = headings[i];
        const nextHeading = headings[i + 1] || null;
        const inRange = (el) => {
            const afterThis = heading.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING;
            const beforeNext = !nextHeading
                || (nextHeading.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING);
            return afterThis && beforeNext;
        };
        const container = listContainers.find(inRange);
        if (!container) continue;

        const items = [...container.querySelectorAll('[role="listitem"], li')];
        const members = items.map(item => {
            // The list item's own visible text is "{Name}\n{Role}" (confirmed live: e.g.
            // "Joseph Rolette\nPrimary | Spouse") - the accessible "Click to view {name}"
            // button is a second, separately-labeled element inside the same item, not the
            // one carrying the name/role text itself.
            const lines = item.innerText.split('\n').map(s => s.trim()).filter(Boolean);
            const name = lines[0] || '';
            const roleHint = lines[1] || '';
            const viewButton = [...item.querySelectorAll('button')].find(b => {
                const label = b.getAttribute('aria-label') || b.textContent || '';
                return label.trim().startsWith('Click to view');
            });
            return viewButton ? {name, roleHint, viewButton} : null;
        }).filter(Boolean);

        sections.push({householdLabel: heading.textContent.trim(), members});
    }
    return sections;
}
```

- [ ] **Step 2: Live-verify against the reference record**

Open `https://www.familysearch.org/ark:/61903/3:1:S3HY-67NL-ZP?view=index&personArk=%2Fark%3A%2F61903%2F1%3A1%3AMZ2Z-WM4&cc=1401638&lang=en` (the Rolette record used throughout this design's brainstorming) with the updated userscript active, open DevTools console, and run:

```javascript
await parseHouseholdSections()
```

Expected: an array whose first element has `householdLabel: "Joseph Rolette Household"` and 5 `members` (Joseph Rolette/Primary, Angelic Rolette/Primary | Spouse, Joseph Rolette/Primary | Child, Virginia Rolette/Primary | Child, George D Monison/Primary), plus further elements for the Cardinal/Matwein/Dejarlais/Lasert households also visible on that image. If the household/list grouping comes back empty or wrong, inspect the live DOM (right-click a household heading → Inspect) and adjust the heading/list selectors above before proceeding — this step is this task's actual test, there being no automated harness for DOM scraping in this file (see Global Constraints).

- [ ] **Step 3: Commit**

```bash
git add Voyageur/Voyageur.js
git commit -m "feat(fs-gather): add parseHouseholdSections for the new Names panel"
```

---

### Task 3: `scrapePersonDetail()` — per-person View Name panel read

**Files:**
- Modify: `Voyageur/Voyageur.js` (inserted after `parseHouseholdSections()`, before the old `scrapeIndexRows()`)

**Interfaces:**
- Consumes: `waitForCondition`, `debugLog` (existing).
- Produces: `async function scrapePersonDetail(viewButton: Element, expectedName: string): Promise<{recordArk: string, personArk: string, given: string, surname: string, gender: string, age: string, relationship: string, extraFields: Record<string,string>}>` — consumed by Task 4.

- [ ] **Step 1: Add `scrapePersonDetail()`**

```javascript
async function scrapePersonDetail(viewButton, expectedName) {
    viewButton.click();

    // Same race as every other panel in this file: wait for the View Name panel to render
    // for THIS person specifically (not a still-rendering previous person's panel left over
    // from the last click), matching the citation panel's own name-anchored wait.
    const panelWait = await waitForCondition(() => {
        const heading = findByExactText('h1, h2, h3, h4, h5, h6', 'View Name');
        if (!heading || !heading.closest) return null;
        const panel = heading.closest('[role="complementary"], aside, div');
        if (!panel || !panel.innerText.includes(expectedName)) return null;
        return panel;
    }, {timeoutMs: 10000});
    if (!panelWait.result) {
        debugLog(`scrapePersonDetail: View Name panel never matched "${expectedName}"`);
        return {recordArk: '', personArk: '', given: '', surname: '', gender: '', age: '',
                relationship: '', extraFields: {}};
    }
    const panel = panelWait.result;
    const panelText = panel.innerText;

    // "VIEW RECORD" always points at this specific indexed entry (record_ark) - the Tree
    // Attachment section, when present, points at the real Family Tree person (person_ark
    // == PID) via a DIFFERENT href shape than the old UI used
    // ("/en/tree/person/{PID}", no "/details/" segment - confirmed live, the old
    // "/tree/person/details/{PID}" regex no longer matches anything on this page).
    const recordArkLink = [...panel.querySelectorAll('a[href]')]
        .find(a => /ark:\/61903\/1:1:([A-Z0-9]{4}-[A-Z0-9]{3,4})/.test(a.getAttribute('href')));
    const recordArkMatch = recordArkLink
        && recordArkLink.getAttribute('href').match(/ark:\/61903\/1:1:([A-Z0-9]{4}-[A-Z0-9]{3,4})/);
    const recordArk = recordArkMatch ? recordArkMatch[1] : '';

    const personArkLink = [...panel.querySelectorAll('a[href]')]
        .find(a => /\/tree\/person\/([A-Z0-9]{4}-[A-Z0-9]{3,4})(?:$|[/?])/.test(a.getAttribute('href')));
    const personArkMatch = personArkLink
        && personArkLink.getAttribute('href').match(/\/tree\/person\/([A-Z0-9]{4}-[A-Z0-9]{3,4})/);
    const personArk = personArkMatch ? personArkMatch[1] : '';

    // Essential Information/Household Details/Events/Additional Facts render as
    // "Heading\nLabel\nValue\nLabel\nValue..." blocks in the panel's own innerText - parsed
    // the same way scrapeCitationAndCatalog already parses the Citation panel's prose
    // (heading-anchored regex over innerText), since FamilySearch's field markup isn't a
    // stable target any more than its tab markup is.
    const givenMatch = panelText.match(/Given Name:\s*(.+)/);
    const surnameMatch = panelText.match(/Surname:\s*(.+)/);
    const sexMatch = panelText.match(/Sex:\s*(\w+)/);
    const ageMatch = panelText.match(/Age:\s*(\d+)/);

    // This person's own relationship-to-primary, from the Household Details section, which
    // lists every household member as "{Relationship}\n{Name}" pairs - find the pair whose
    // name matches THIS person and take its relationship label. The household's own primary/
    // head has no such pair (nobody lists their own relationship to themselves) and gets
    // "Head" directly instead. Households with no real relationship data (every member shown
    // as bare "Primary" in the list) have no matching pair either - relationship stays ''
    // rather than being fabricated, matching Census.py's own tolerance of an absent value.
    let relationship = '';
    const householdMatch = panelText.match(/Household Details([\s\S]*?)(?:\n\n|Events\n|$)/);
    if (householdMatch) {
        const relPairs = [...householdMatch[1].matchAll(
            /(Household\s*•\s*Census|Spouse|Child|Father|Mother|No Relation)\n(.+)/g)];
        const selfLine = relPairs.find(([, , name]) => name && name.trim() === expectedName);
        if (selfLine) {
            relationship = selfLine[1].startsWith('Household') ? 'Head' : selfLine[1];
        } else if (relPairs.some(([, label]) => label.startsWith('Household'))
                   && panelText.includes(`${expectedName}\n\nVIEW RECORD`)) {
            relationship = 'Head';
        }
    }

    return {
        recordArk, personArk,
        given: givenMatch ? givenMatch[1].trim() : '',
        surname: surnameMatch ? surnameMatch[1].trim() : '',
        gender: sexMatch ? sexMatch[1].trim().toUpperCase() : '',
        age: ageMatch ? ageMatch[1].trim() : '',
        relationship,
        extraFields: {},
    };
}
```

**Note for the implementer:** the Household Details self-vs-head detection above (the `relPairs`/`selfLine` block) is this plan's best read of the panel's `innerText` shape from a live read during design brainstorming, not a character-verified regex — confirm it against the real panel's `innerText` (log it to the console: `panel.innerText`) during Task 5's live-verification pass and correct the regex if the actual line breaks differ.

- [ ] **Step 2: Live-verify against the reference record**

In the same DevTools console (page still on the Rolette record, `Names` panel open):

```javascript
const sections = await parseHouseholdSections();
const joseph = sections[0].members[0];
await scrapePersonDetail(joseph.viewButton, joseph.name)
```

Expected: `{recordArk: "MZ2Z-WM4", personArk: "9CJG-851", given: "Joseph", surname: "Rolette", gender: "M", age: "35", relationship: "Head", extraFields: {}}`. If `panel.innerText` doesn't match the assumed shape, log it directly and adjust the regexes in Step 1 before proceeding.

- [ ] **Step 3: Commit**

```bash
git add Voyageur/Voyageur.js
git commit -m "feat(fs-gather): add scrapePersonDetail for the View Name panel"
```

---

### Task 4: `scrapeNamesPanel()` — assemble, dedupe, wire in, delete the old scraper

**Files:**
- Modify: `Voyageur/Voyageur.js`

**Interfaces:**
- Consumes: `parseHouseholdSections()`, `scrapePersonDetail()` (Tasks 2-3), `debugLog`.
- Produces: `async function scrapeNamesPanel(): Promise<Array<{columns: Record<string,string>, person_ark: string, attached_fsftid: string}>>` — replaces `scrapeIndexRows()`'s return value at its one call site, `scrapeCurrentImage()` (`Voyageur.js:1417`).

- [ ] **Step 1: Delete `scrapeIndexRows()`**

Remove `Voyageur.js:1323-1411` (the full function, from `async function scrapeIndexRows() {` through its closing `}`) — now fully superseded by Tasks 2-3.

- [ ] **Step 2: Add `scrapeNamesPanel()`** in its place

```javascript
async function scrapeNamesPanel() {
    const sections = await parseHouseholdSections();
    if (sections.length === 0) return [];

    const rows = [];
    for (let familyNumber = 0; familyNumber < sections.length; familyNumber++) {
        const {members} = sections[familyNumber];

        // FamilySearch's own index can surface the same person twice within one household
        // (confirmed live: "Josette Cardinal" appeared twice under "J Baptiste Cardinal
        // Household") - build_census_json() has no row-level dedup of its own (unlike the
        // Parish path's match_and_link_records), so a duplicate scraped here is a duplicate
        // person in the final GEDCOM. Skip a repeat of the same name+role within the same
        // household rather than scraping it a second time.
        const seen = new Set();
        const deduped = members.filter(m => {
            const key = `${m.name}|${m.roleHint}`;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        });

        for (const member of deduped) {
            const detail = await scrapePersonDetail(member.viewButton, member.name);

            const columns = {
                'Given Name': detail.given || member.name.split(' ').slice(0, -1).join(' '),
                'Surname': detail.surname || member.name.split(' ').slice(-1).join(' '),
                'Gender': detail.gender,
                'Age': detail.age,
                'Family Number': String(familyNumber + 1),
            };
            if (detail.relationship) {
                columns['Relationship to Head'] = detail.relationship;
            }

            rows.push({columns, person_ark: detail.recordArk, attached_fsftid: detail.personArk});
        }
    }
    return rows;
}
```

- [ ] **Step 3: Repoint `scrapeCurrentImage()` to call the new scraper**

In `Voyageur.js:1413-1427`, change:

```javascript
            const rows = await scrapeIndexRows();
```

to:

```javascript
            const rows = await scrapeNamesPanel();
```

(No other change needed in `scrapeCurrentImage()` — `rows` is consumed downstream in the same shape as before.)

- [ ] **Step 4: Live-verify the full per-image flow**

On the Rolette record page, with the batch UI's "Start Auto-Batch" NOT clicked (avoid a real multi-image batch run for this check), open DevTools console and run:

```javascript
await scrapeNamesPanel()
```

Expected: an array of row objects covering every household visible on the image (Rolette, Cardinal, both Matwein households, Dejarlais, Lasert, ...), each shaped like
`{columns: {"Given Name": ..., "Surname": ..., "Gender": ..., "Age": ..., "Family Number": ..., "Relationship to Head"?: ...}, person_ark: ..., attached_fsftid: ...}`. Confirm:
- Joseph Rolette's row has `person_ark: "MZ2Z-WM4"`, `attached_fsftid: "9CJG-851"`, `columns["Relationship to Head"] === "Head"`.
- The Cardinal household's rows have no `"Relationship to Head"` key at all (the bare-"Primary" case).
- Only one "Josette Cardinal" row exists, not two.

- [ ] **Step 5: Commit**

```bash
git add Voyageur/Voyageur.js
git commit -m "feat(fs-gather): replace scrapeIndexRows with scrapeNamesPanel for the new UI"
```

---

### Task 5: End-to-end live verification against a real gather

**Files:** none (verification only).

**Interfaces:** none.

- [ ] **Step 1: Run a real gather against the reference record**

With `Voyageur/.env`'s `FS_URL` set to the Rolette record URL, run `Voyageur/FS.py` standalone (`cd Voyageur && python FS.py`) or via Scriptorium's own Voyageur tab, letting the batch UI's "Start Auto-Batch" run for at least the 2-3 images starting at image 39, then "Stop & Download JSON".

Expected: a `FS - {collection}.json` file downloads with no console errors reported by the userscript's own toast notifications, and `item_id` `3:1:S3HY-67NL-ZP` (image 39) present with all households from Step 4 above.

- [ ] **Step 2: Feed the captured raw JSON through `FS.py`'s conversion pipeline**

```bash
cd Voyageur
python -c "
import json, FS
raw = json.load(open('PATH_TO_DOWNLOADED_FS_JSON'))
items_raw = raw['items']
catalog_items = FS.dedup_catalog_items(items_raw)
record_family = FS.detect_record_family_from_raw(raw, catalog_items)
assert record_family == 'census', record_family
built = FS.build_census_json(raw, items_raw, catalog_items)
normalized = FS.normalize_familysearch_census_gather(built, raw.get('collection_title', ''))
print(json.dumps(normalized['sheets'][0]['records'][:2], indent=2))
"
```

(Replace `PATH_TO_DOWNLOADED_FS_JSON` with Step 1's actual downloaded file path.)

Expected: runs without exception, prints at least one household correctly grouped with a head, spouse, and children under one family, matching what `Archivist/Census.py`'s own household-parsing already does for Ancestry-sourced data — confirming Task 1's regression test reflects real gathered data, not just a hand-built fixture.

- [ ] **Step 3: Run the full test suite one more time**

Run: `cd Voyageur && pytest tests/ -v` and `cd Archivist && pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 4: Commit** (only if Steps 1-3 required any fixes to Tasks 1-4's code)

```bash
git add Voyageur/Voyageur.js Voyageur/tests/test_fs.py
git commit -m "fix(fs-gather): correct household-view scraper against a live gather run"
```
