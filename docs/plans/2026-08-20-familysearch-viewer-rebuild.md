# FamilySearch Viewer Rebuild Implementation Plan

> **For AGY:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** Fix the FamilySearch (FS) gather path in `Voyageur.js` / `FS.py`, which currently
produces images but no usable index data (empty `rows`, `incomplete: true` on every item,
final JSON often never materializing) - and separately, restore enumeration-district (ED)
scoped batching, which FamilySearch's own UI silently dropped, and fix two data-quality
defects confirmed against a real captured gather (2026-08-20): only 5-6 of the fields already
being extracted actually reach the output, and the two identifier fields carried per person
are mislabeled. Root cause of items 1-4 is a FamilySearch site redesign confirmed live
2026-08-19/20, not a regression in our own code; items 5-7 are pre-existing defects
surfaced by testing against real data today:

1. FamilySearch now server-side redirects `?view=index` to `?view=explore`, so the tab-based
   classic page our scraper was built against is no longer reachable.
2. In `explore` view, control labels ("Names", "Save Record", "Information", "Go to image N")
   exist **only** as `aria-label` attributes on icon-only buttons - zero visible DOM text -
   so any `textContent`-based detection structurally cannot work.
3. The orchestration API that supplies row/citation JSON moved off
   `sg30p0.familysearch.org/service/records/volunteer/orchestration/sls/image/{ark}` onto
   `www.familysearch.org/records/images/orchestration/...` - different host, different path -
   so the existing fetch/XHR interception never sees a matching response and times out on
   every image.
4. **(confirmed with the user, 2026-08-20)** `explore` view no longer bounds navigation to
   the target enumeration district/township - it dumps the batch into the full microfilm
   roll. The user's actual workflow has always been "manually find and paste the starting
   image's URL for a given ED, let the tool gather forward until the ED changes" - the
   *starting point* is still user-provided and unaffected, but the *stopping point* is now
   broken because FamilySearch's own UI no longer enforces it.
5. **(confirmed against a real captured gather, 2026-08-20)** `detectFsPageType()` still
   throws "Unrecognized page." on every single image of a real run - item 2 above is not yet
   fixed in shipped code, only planned (Task 2 below).
6. **(confirmed against a real captured gather, 2026-08-20)** Only 5-6 columns
   (`Given Name`/`Surname`/`Gender`/`Age`/`Family Number`/`Relationship to Head`) reach the
   output JSON, even though `fsCanonicalFieldsFromApiPerson()` already extracts birthplace,
   marital status, occupation, race, and both parents' birthplaces from the orchestration API
   - `fsColumnsFromCanonicalFields()` deliberately discards them before they reach `columns`.
7. **(confirmed against a real captured gather, 2026-08-20; user's own diagnosis)** The
   `person_ark` field (e.g. `1:1:6F7D-8CBW`) is actually this person's *record/persona*
   identifier - their appearance in this specific document, not an enduring identity. The
   `attached_fsftid` field, which should carry that enduring Person identifier, is hardcoded
   to always be empty (`Voyageur.js` line ~419: `attached_fsftid: ''`) - no extraction is even
   attempted. The two fields are both mislabeled and one is entirely unimplemented.

**Architecture:** `Voyageur.js`'s FS gather path needs six coordinated changes: page-type
detection switches from `textContent` exact-match (`findByExactText`) to `aria-label`
exact-match; the FS gather loop gains the same place/ED-boundary-crossing stop condition the
Ancestry loop already has; the fetch/XHR interception's `FS_API_TARGET` and ark-extraction
regex move to the new host+path; the response parser gets verified/adjusted against the new
endpoint's actual JSON shape; `fsColumnsFromCanonicalFields()` stops discarding
already-extracted fields; and the two identifier fields get renamed to their correct meaning,
with a genuine attempt made to populate a true Person identifier where one exists. Critically,
**the "capture everything, map later" architecture the user asked for already exists** -
`Voyageur/census_schema.py`'s `_normalize_participant()`, driven by a declarative YAML field
map (`Voyageur/field_maps/familysearch_census.yaml`), already maps known column names to
schema fields and preserves *any* unrecognized column under
`type_specific_fields.unmapped` rather than dropping it. This is not a rearchitecture task -
it is: stop discarding fields before they reach that layer, and extend the YAML map to name
the newly-surfaced fields. Navigation (`goToNextImage()`/`advanceViaFilmstripThumbnail()`)
already uses `aria-label` matching and needs no structural change, but a live-observed "image
count went backwards" anomaly under `explore` view needs a stronger post-click confirmation
than the current `href !== prevUrl` check.

**Critical constraint - Task 1 blocks Tasks 6, 7, and half of Task 5:** the new orchestration
endpoint's exact path/query format, JSON response shape, and whether a true enduring Person
identifier exists anywhere in that response are all unknown. A same-origin `fetch()` replay of
a captured URL failed in live testing (likely a signed/single-use URL or a header a plain
`fetch()` doesn't replicate), so Task 1 must capture the response from inside the page's own
authenticated context (the userscript itself, which already runs in `unsafeWindow`), not via
DevTools console reconnaissance. Tasks 2, 3, and 4 are independent of Task 1 and can proceed
immediately - Task 3 in particular needs no new data capture at all, since the fields it
surfaces are already being extracted by shipped (if uncommitted) code.

---

**Not doing yet (user's explicit deferral, 2026-08-20):** the same raw-passthrough treatment
(Task 3) should eventually apply to the Ancestry gather path too
(`ancestryColumnsFromIndexPanelRecord`/`ancestryRowsFromIndexPanelResponse` in `Voyageur.js`,
which currently do their own curated field-mapping). The user asked for this explicitly but
said to plan it as a separate task *after* this FS plan is fully finished, not now - do not
start it as part of this plan.

---

## Global Constraints

- Line length <= 120 chars for all Python files (pycodestyle).
- Never fabricate data: if a field is absent, leave it as `""` or `"Unknown_*"`, never guess.
- Preserve the existing `sg30p0`/old-path interception as a fallback alongside the new one -
  FamilySearch may be mid-rollout (some records/collections might still serve the old
  endpoint). Never remove old-path support until confirmed universally replaced.
- Do not touch `normalize_familysearch_gather_url()`'s `view=index` forcing (see Task 5's
  predecessor investigation, 2026-08-20 session) - dropping it fixes nothing (the redirect
  happens server-side regardless of what's requested) and may still matter for
  not-yet-migrated collections.
- `findByExactText()` stays as-is for any DOM text matching that still works. Add a new
  `findByAriaLabel()` helper alongside it rather than changing its contract.
- `placesMatch()` (module-level, `Voyageur.js` ~line 72) is shared between Ancestry and FS -
  reuse it as-is; do not fork a FS-specific copy.
- **Never drop a column to "clean up" the output.** The whole point of Task 3/4 is that an
  unrecognized field is preserved under `type_specific_fields.unmapped`, not discarded - this
  is existing, working behavior in `census_schema.py`; do not change it.
- JS changes must not regress the already-passing 79 Node tests in `Voyageur/tests/js/`.
- Run `node --test "Voyageur/tests/js/*.mjs"` after every JS task (note: there is no
  `run_tests.js` entry point - glob the `.mjs` files directly).
- Run `python -m pycodestyle --max-line-length=120 Voyageur/FS.py Voyageur/_gather_helpers.py Voyageur/census_schema.py Archivist/Census.py`
  after every Python task.
- Manual/live verification steps in this plan require an actual FamilySearch session
  (Tampermonkey deployed, logged in) - they cannot be automated in CI. Mark them clearly and
  do not claim a task complete on the Node/pytest suite alone when a live check is specified.
- **Tampermonkey does not auto-sync from the file on disk.** Confirmed live 2026-08-20: the
  installed script was stuck on `@version 0.3.29` through this entire session's earlier work
  until manually re-pasted into the Tampermonkey editor and saved. After every JS change meant
  for live testing, the file's content must be manually copied into Tampermonkey's editor
  (select-all, paste, `Ctrl+S`) before any live/manual verification step in this plan - do not
  assume a saved file is automatically live.

---

## Reference: confirmed live findings (2026-08-19/20)

### 1. `view=index` no longer reachable

Direct navigation to `https://www.familysearch.org/ark:/61903/<ark>?view=index&lang=en` (no
batch flags) gets server-redirected to `?view=explore&lang=en&...` for the tested record
(`3:1:3QHN-PQHW-1YY2`, 1950 census). Confirmed via address bar entry, not just script-driven
navigation. We keep requesting `view=index` anyway (see Global Constraints) - this finding
motivates Tasks 2/6, not a URL-normalizer change.

### 2. Control labels are `aria-label`-only, not DOM text

Exhaustive `document.querySelectorAll('*')` + `textContent` search (exact match,
case-insensitive, substring, whole-DOM) found zero occurrences of "Names", "Save Record",
etc. `[aria-label]` search found them immediately:

```
BUTTON:Names
BUTTON:Save Record
ASIDE:Information
BUTTON:Go to image 1
BUTTON:Go to image 4
BUTTON:Copy Citation to clipboard
```

Current code, `Voyageur.js` (`findByExactText`, ~line 1789):

```js
function findByExactText(selector, text) {
    const candidates = document.querySelectorAll(selector);
    for (const el of candidates) {
        if (el.textContent.trim() === text) return el;
    }
    return null;
}
```

Used by `detectFsPageType()` (~line 1812):

```js
async function detectFsPageType({timeoutMs = 15000} = {}) {
    const wait = await waitForCondition(() => {
        if (findByExactText('[role="tab"], button, a', 'Names')) return 'names';
        if (findByExactText('[role="tab"], button, a', 'Image Index')) return 'image-index';
        return null;
    }, {timeoutMs});
    return wait.result;
}
```

This times out (returns `null`) on every `explore`-view page, landing every item in
`buildFsItemData()`'s `else` branch: `incomplete: true`, empty `rows`, "Unrecognized page."
toast - confirmed still reproducing on a real captured gather today (see Reference 5 below).

Note: `goToNextImage()`/`advanceViaFilmstripThumbnail()` (~lines 1963-2044) **already** match
on `aria-label` - navigation mechanics are not part of this problem, only page-type/tab
detection is.

### 3. Orchestration API moved host + path

`Voyageur.js` (~line 1559):

```js
const FS_API_TARGET = '/service/records/volunteer/orchestration/sls/image/';
```

```js
function fsApiArkFromUrl(url) {
    const match = url.match(/\/image\/([^/?#]+)/);
    return match ? decodeURIComponent(match[1]) : null;
}
```

Live `performance.getEntriesByType('resource')` on the same `explore`-view page: **zero**
requests contain `sg30p0` or match `FS_API_TARGET`. Requests confirmed live to
`https://www.familysearch.org/records/images/orchestration/...` (exact full path/query not
yet captured). This new path does not contain the literal substring `/image/` that
`fsApiArkFromUrl`'s regex requires, so the ark-extraction regex will also need updating once
the real path structure is known (Task 1).

### 4. ED/township scoping is lost under `explore` view (confirmed with user, 2026-08-20)

The classic `index` view bounded navigation to the target enumeration district. `explore`
view does not - it dumps the batch into the full microfilm roll. Fix: mirror Ancestry's
existing `placesMatch()`/`firstPagePlace` boundary-crossing stop, using location fields
`buildFsItemData()` already extracts. See Task 5.

### 5. `detectFsPageType()` still reproducing "Unrecognized page." on real data (2026-08-20)

A real 14-image gather (run `9501594f`, 1950 census, Pembina) produced only 1 usable item;
the other 13 all show `"incomplete": true, "rows": []` - the toast fired on every one. This
confirms Reference 2's diagnosis is correct and Task 2 is not yet implemented in the version
that was live-tested (the fix exists only as a plan, not shipped code). No new information
here beyond "the planned fix in Task 2 is still needed and still correct as scoped."

### 6. Only 5-6 columns reach the output despite richer data already being extracted

`Voyageur.js`, `fsCanonicalFieldsFromApiPerson()` (~line 357):

```js
function fsCanonicalFieldsFromApiPerson(byId, person) {
    const {given, surname} = fsPersonName(byId, person);
    const sex = fsPersonFieldText(byId, person, 'SEX_CODE');
    return {
        givenName: given, surname: surname, sex: sex ? sex.toUpperCase() : '',
        age: fsWrappedFieldText(byId, person, 'AGE'),
        birthplace: fsPersonBirthPlace(byId, person),
        householdIdSource: fsPersonFieldText(byId, person, 'SOURCE_HOUSEHOLD_ID'),
        householdIdFs: fsPersonFieldText(byId, person, 'FS_HOUSEHOLD_ID'),
        relationshipToHead: fsPersonFieldText(byId, person, 'RELATIONSHIP_TO_HEAD'),
        maritalStatus: fsPersonFieldText(byId, person, 'MARITAL_STATUS'),
        occupation: fsPersonFieldText(byId, person, 'OCCUPATION'),
        race: fsPersonFieldText(byId, person, 'RACE_OR_COLOR'),
        fatherBirthplace: fsPersonFieldText(byId, person, 'FTHR_BIR_PLACE'),
        motherBirthplace: fsPersonFieldText(byId, person, 'MTHR_BIR_PLACE'),
    };
}
```

But `fsColumnsFromCanonicalFields()` (~line 388), called immediately after, only surfaces 5
fields into `columns` (6 including the conditionally-added `Relationship to Head`) and its own
comment admits the rest are extracted and thrown away:

```js
// ... maritalStatus/occupation/race/fatherBirthplace/motherBirthplace/birthplace are
// captured in canonicalFields but deliberately not added here - see this plan's Global
// Constraints.
```

This is **not** a data-availability gap requiring new API research - the fields are already
being pulled from the orchestration response live (per
`docs/superpowers/specs/2026-08-14-fs-orchestration-api-extraction-design.md`, itself
confirmed against two real captures). It is a discard step. See Task 3.

### 7. `person_ark`/`attached_fsftid` are mislabeled and one is unimplemented

`Voyageur.js`, `fsBuildRowsFromApiResponse()` (~line 407):

```js
rows.push({columns, person_ark: person.id, attached_fsftid: ''});
```

`person.id` is the orchestration graph's `PERSON` element id - this is a **record/persona**
identifier (this person's appearance in this specific document), not an enduring cross-record
identity. `attached_fsftid` is hardcoded to `''` unconditionally - no extraction of any kind
is attempted. The 2026-08-14 design doc that introduced this shape documents the exact same
gap (its own downstream-integration example shows `"attached_fsftid": ""` verbatim) - this was
a known, deferred gap from the start, not a regression.

**User's correction (2026-08-20, authoritative):** the field currently called `person_ark`
should be renamed `record_ark` (it identifies the record, not the person). The field currently
called `attached_fsftid` should actually be understood as - and populated as - the true
`person_ark`: FamilySearch's enduring Family Tree attachment identifier for this individual,
when one exists. See Task 4, which is partially blocked on Task 1 (need real captured data to
find whether/where such a field exists in the orchestration response at all).

This propagates cleanly through the existing pipeline once renamed - confirmed by reading
(not yet testing) the full chain:
- `Voyageur/census_schema.py` `_normalize_participant()` (~line 210) already passes through
  `pid`/`extracted_url`/`fsftid`/`person_ark`/`familysearch_url` verbatim into
  `type_specific_fields` - a rename here is a one-line key-name change per passthrough field.
- `Archivist/Census.py` reads `row['PersonArk']` (~line 1326) as the `_FSFTID` GEDCOM tag's
  fallback source when no explicit FSFTID is present, with a comment already correctly
  describing it as "this specific individual's FamilySearch persona id" - i.e. the code
  already understood the semantic distinction, it just used the wrong field/tag names.

**Open design question, not yet resolved - flagged for the user before Task 4 is finalized:**
once `attached_fsftid` genuinely differs in meaning from `record_ark` (persona id), should
`Archivist/Census.py`'s `_FSFTID` GEDCOM tag still fall back to `record_ark` when no true
Person identifier was found (current behavior, arguably semantically wrong - a persona id is
not a valid FamilySearch Tree person id), or should `_FSFTID` simply be omitted when no true
attachment exists (more correct, but a real behavior change - fewer individuals would get a
`_FSFTID` tag than today, even though today's tag was arguably fabricated-looking). Task 4
proceeds with the omit-when-absent behavior as the default per GEDCOM-correctness precedent
set earlier this branch (`_FSFTID`/`_APID` individual-level placement fixes), but this default
should be confirmed with the user before Task 4's Step 3 ships.

---

## Task 1: Capture the live orchestration response (spike - blocks Tasks 6, 7, and Task 4's Person-identifier research)

**Files:**
- Temporary instrumentation: `Voyageur/Voyageur.js` (reverted at the end of this task)

Manual `fetch()` replay from DevTools console failed against a captured URL, so capture must
happen from inside the already-authenticated page context instead - add a temporary logging
hook to the userscript's own fetch/XHR patch (same location as `FS_API_TARGET`, ~line 1559),
deploy it (see Global Constraints re: manual Tampermonkey sync), and gather one real image in
a live FamilySearch session.

### Step 1: Add temporary capture logging

In `Voyageur.js`, inside the existing FS fetch/XHR patch block (~lines 1580-1599), add a
broader, temporary listener (in addition to the existing `FS_API_TARGET`-scoped one) that
logs **any** request whose URL contains `orchestration`, regardless of host/path, printing
the full URL and response body via `console.log` and also triggering
`triggerFsJsonDownload()` (already defined, ~line 1980) with the raw response text so it
saves to disk as a file:

```js
const origFsFetchSpike = unsafeWindow.fetch;
unsafeWindow.fetch = async function (...args) {
    const url = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url) || '';
    const resp = await origFsFetchSpike.apply(this, args);
    if (/orchestration/i.test(url)) {
        resp.clone().text().then((t) => {
            console.log('[SPIKE orchestration]', url);
            triggerFsJsonDownload(JSON.stringify({url, body: t}, null, 2), 'SPIKE_orchestration.json');
        });
    }
    return resp;
};
```

### Step 2: Deploy and run live

- Manually paste the updated file into Tampermonkey's editor and save (see Global
  Constraints - no auto-sync exists).
- Navigate to a fresh census ark image that actually has person data on it (a cover/title
  page will not trigger a real orchestration call).
- The gather script only activates when `sessionStorage.getItem('run_fs_gather') === 'true'`
  or the URL contains `mgs_auto=1` (confirmed live 2026-08-20 - a plain page visit does
  **not** trigger it, the floating panel will not even exist). Set the flag from the console
  if not launching through the normal Antiquarian-driven flow:
  `sessionStorage.setItem('run_fs_gather', 'true')`, then reload.
- Confirm a `SPIKE_orchestration.json` file downloads.

### Step 3: Record findings back into this plan

Before proceeding to Task 6/7 or Task 4's identifier research, append a new subsection under
"Reference" above with:
- The exact new URL (path + query params, with the ark/image id marked).
- The full top-level JSON key structure of the response body.
- Whether it still uses the old `elements`/`subElements`/`superElements` graph shape
  (`elementType`/`fieldType` discriminators) or something different.
- **Specifically for Task 4:** whether any field on the `PERSON` element (or a related
  element reachable from it) carries an enduring Family Tree person identifier distinct from
  `person.id` - check for anything resembling `personId`, `treePersonId`, `fsftid`, or a
  `subElements`/relationship reference to a differently-typed element. Record whichever is
  found, or record clearly "not present in this response" if genuinely absent.

### Step 4: Revert the temporary instrumentation

Remove the Step 1 block entirely once findings are recorded - it must not ship.

### Step 5: Commit

```
git add docs/plans/2026-08-20-familysearch-viewer-rebuild.md
git commit -m "docs(voyageur): record live-captured FS orchestration response shape"
```

---

## Task 2: Add `findByAriaLabel()` and switch `detectFsPageType()` to use it

**Files:**
- Modify: `Voyageur/Voyageur.js` (`findByExactText` area, `detectFsPageType`)
- Test: `Voyageur/tests/js/test_utilities.mjs` (or wherever `findByExactText` is tested)

### Step 1: Write the failing test

```js
test('findByAriaLabel: matches exact aria-label regardless of visible text content', () => {
    document.body.innerHTML = '<button aria-label="Names"><svg></svg></button>'
        + '<button aria-label="Save Record"></button>';
    const el = findByAriaLabel('button', 'Names');
    assert.equal(el.getAttribute('aria-label'), 'Names');
});

test('findByAriaLabel: returns null when no match', () => {
    document.body.innerHTML = '<button aria-label="Save Record"></button>';
    assert.equal(findByAriaLabel('button', 'Names'), null);
});
```

### Step 2: Run tests to verify they fail

```
node --test "Voyageur/tests/js/*.mjs"
```

Expected: `findByAriaLabel is not defined`.

### Step 3: Implement `findByAriaLabel()` and update `detectFsPageType()`

In `Voyageur.js`, next to `findByExactText` (~line 1789):

```js
function findByAriaLabel(selector, label) {
    const candidates = document.querySelectorAll(selector);
    for (const el of candidates) {
        if ((el.getAttribute('aria-label') || '').trim() === label) return el;
    }
    return null;
}
```

Update `detectFsPageType()` (~line 1812) to try both, aria-label first, text second (do not
drop `findByExactText` support per Global Constraints):

```js
async function detectFsPageType({timeoutMs = 15000} = {}) {
    const wait = await waitForCondition(() => {
        if (findByAriaLabel('[role="tab"], button, a', 'Names')
            || findByExactText('[role="tab"], button, a', 'Names')) return 'names';
        if (findByAriaLabel('[role="tab"], button, a', 'Image Index')
            || findByExactText('[role="tab"], button, a', 'Image Index')) return 'image-index';
        return null;
    }, {timeoutMs});
    return wait.result;
}
```

Update `module.exports` to include `findByAriaLabel`.

### Step 4: Run tests to verify they pass

```
node --test "Voyageur/tests/js/*.mjs"
```

### Step 5: Live smoke-check

> Deploy to Tampermonkey (manual paste + save - see Global Constraints), set
> `run_fs_gather` and reload on a real image, confirm no "Unrecognized page." toast.

### Step 6: Commit

```
git add Voyageur/Voyageur.js Voyageur/tests/js
git commit -m "fix(voyageur/js): detect FS page type via aria-label, not text content"
```

---

## Task 3: Raw-passthrough extraction - capture every field FamilySearch's API returns, rename nothing

**STATUS: implemented 2026-08-20 (JS side).** Not blocked on Task 1.

**Superseded design note:** this task originally planned a curated, hand-picked list of
additional named fields (birthplace, marital status, etc., under pretty labels like "Marital
Status"). **The user explicitly rejected that approach mid-session**: "what is contained in
the JSON on FS is more important than what we're set to import... I want to change the code
so it just imports the JSON from the website fully into the JSON output, without transforming
and cleaning columns at all." The curated-list version was never shipped; it was replaced by
the generic raw-passthrough design below before any commit.

**What shipped:** two new functions replace `fsCanonicalFieldsFromApiPerson`/
`fsCanonicalFieldsFromImageIndexPerson`/`fsColumnsFromCanonicalFields` (all three deleted):

- **`fsRawFieldsFromApiPerson(byId, person)`** (orchestration API path) - walks every
  `subElement` reachable from a `PERSON` element and records it verbatim under FamilySearch's
  own vocabulary: direct `FIELD` children keyed by `fieldType` (e.g. `MARITAL_STATUS`,
  `RACE_OR_COLOR`, `FTHR_BIR_PLACE`, `SOURCE_HOUSEHOLD_ID` - whatever exists, no whitelist);
  `NAME` wrappers produce `NAME_GIVEN`/`NAME_SURNAME`; `EVENT` wrappers produce
  `EVENT_<eventType>_PLACE` (so both `EVENT_BIRTH_PLACE` and `EVENT_CENSUS_PLACE` survive
  independently); any other single-`FIELD`-holding wrapper (e.g. `AGE`) is keyed by its own
  `elementType`.
- **`fsRawFieldsFromImageIndexPerson(person)`** (Image-Index API path) - same principle for
  GedcomX's differently-shaped API: fields/facts/name-parts keyed by their type URI's trailing
  segment via a new `fsLastUriSegment()` helper (e.g. `http://gedcomx.org/MaritalStatus` ->
  `MaritalStatus`); a fact's nested `place.fields` are walked in full (not just a single
  `"Place"` lookup) so multi-segment places like Census's State/County/Township/District all
  survive as `<FactType>_<PlaceFieldType>` (e.g. `Census_State`, `Census_Township`) alongside
  Birth's simpler `Birth_Place`.

Both `fsBuildRowsFromApiResponse()` and `fsBuildRowsFromImageIndexResponse()` now set
`columns` directly from these functions - no intermediate "canonical fields" shape, no
sequence-based `Family Number` synthesis (dropped: `census_schema.py`'s existing
`_household_key()` page-number fallback already handles the "no household field at all" case
without fabricating a counter-based one - see Global Constraints, "never fabricate data").

**Why this satisfies "capture everything, map later" without a rearchitecture:**
`Voyageur/census_schema.py`'s `_normalize_participant()` (Architecture section) already maps
known column names to schema fields via a declarative YAML file and preserves anything
unrecognized under `type_specific_fields.unmapped` rather than dropping it. That machinery is
unchanged and still works - it just now receives FamilySearch's raw field names
(`MARITAL_STATUS`, `RACE_OR_COLOR`, ...) instead of a curated 5-6-field subset. Everything
Task 3 surfaces that the YAML map doesn't yet recognize by name lands safely in `unmapped`,
visible for review, never lost.

**Files (all committed as part of this task):**
- Modified: `Voyageur/Voyageur.js` - `fsRawFieldsFromApiPerson`/`fsRawFieldsFromImageIndexPerson`/
  `fsLastUriSegment` added; `fsCanonicalFieldsFromApiPerson`/`fsCanonicalFieldsFromImageIndexPerson`/
  `fsColumnsFromCanonicalFields` removed; `fsBuildRowsFromApiResponse`/
  `fsBuildRowsFromImageIndexResponse` updated to use the new functions; `module.exports` updated.
- Modified: `Voyageur/tests/js/test_fs_api_parser.mjs`, `test_fs_image_index_parser.mjs` - stale
  curated-field tests replaced with raw-passthrough tests covering both real fixture people
  (1880-style with every field, 1850/1860-style with era-absent fields genuinely absent).

**Remaining work for this task (not yet done):**

### Extend `familysearch_census.yaml` for the newly-visible raw field names

The YAML field map (`Voyageur/field_maps/familysearch_census.yaml`) still maps the *old*
pretty names (`"Marital Status"`, `"Race"`, `"Birth Place"`) that extraction no longer
produces. Real raw output now uses FamilySearch's own names (`MARITAL_STATUS`,
`RACE_OR_COLOR`, `EVENT_BIRTH_PLACE`, `NAME_GIVEN`, `NAME_SURNAME`, `SOURCE_HOUSEHOLD_ID`,
`FS_HOUSEHOLD_ID`, `RELATIONSHIP_TO_HEAD`, `SEX_CODE`, `AGE`, `FTHR_BIR_PLACE`,
`MTHR_BIR_PLACE`, and whatever else Task 1's real capture reveals). Until the YAML is updated,
every field will land in `type_specific_fields.unmapped` (safe, not lost, but not properly
mapped to GEDCOM either) and every participant will be flagged for review.

**This is the concrete next step - do this before Task 9's live smoke test**, once real output
confirms the exact raw key spellings (some inference above, e.g. `EVENT_BIRTH_PLACE`, should
be verified against real data, not just the fixture). Rewrite
`familysearch_census.yaml`'s `participant_fields`/`participant_facts` keys to match the new
raw names instead of the old pretty ones, e.g.:

```yaml
participant_fields:
  "NAME_GIVEN": std_given
  "NAME_SURNAME": std_surname
  "SEX_CODE": sex
  "AGE": age
  "EVENT_BIRTH_PLACE": birth_place
  "RACE_OR_COLOR": race
  "RELATIONSHIP_TO_HEAD": role_name
  "SOURCE_HOUSEHOLD_ID": family_number   # via record_fields, not participant_fields - see below
  "FS_HOUSEHOLD_ID": family_number       # ditto
```

> `SOURCE_HOUSEHOLD_ID`/`FS_HOUSEHOLD_ID` drive household grouping via `record_fields` (see
> `_household_key()`), not `participant_fields` - map them in the `record_fields:` section,
> matching the existing `"Family Number": family_number` pattern, not the block above.

```yaml
participant_facts:
  "MARITAL_STATUS": MaritalStatus   # or an existing FACT_TYPE_TO_COLUMN-compatible name -
  "OCCUPATION": Occupation           # confirm against Archivist/Census.py's FACT_TYPE_TO_COLUMN
  "FTHR_BIR_PLACE": FatherBirthplace  # dict (~line 1503) rather than inventing new fact names
  "MTHR_BIR_PLACE": MotherBirthplace
```

Write a test locking in each new mapping (mirroring the pattern already used elsewhere in
`Voyageur/tests` for field-map coverage), run
`python -m pytest Voyageur/tests -k field_map -v`, then commit.

### Live smoke-check (once the YAML is updated)

> Deploy to Tampermonkey, gather 2-3 real images with people who have birthplace/occupation/
> race/marital-status data on the actual census form, confirm the raw field names appear in
> `columns` of the downloaded JSON exactly as FamilySearch names them, and confirm (after
> the YAML update above) they are no longer landing in `type_specific_fields.unmapped`.

---

## Task 4: Rename `person_ark`->`record_ark`; correctly populate a true Person identifier

**STATUS: COMPLETE 2026-08-21.** All of Steps 1-7 done: the rename (JS + `census_schema.py` +
`Census.py`), the real extraction (via `/service/tree/links/sources/attachments`
interception - see Step 4 below for the full finding), and the `_FSFTID` fallback update
(omit, per Step 5). `FS.py`'s `build_census_json()` also needed a fix not originally scoped
in this task (it was still reading the pre-rename `person_ark`/`attached_fsftid` keys,
caught only by running a real gather end-to-end - see this branch's commit history), and
`Paleographer/prompts/Census.pmt` needed `record_ark` (and several Task 3 occupation-detail
fields) added to its `extra_fields.participant` list - Commissioner's per-document-type
schema (`extra="forbid"`) rejects any `type_specific_fields` key not declared there, which a
real gather surfaced as validation errors Task 3 hadn't anticipated.

The "omit vs. fall back to record_ark" open question is moot now that Step 4 found a real
extraction path - `PersonArk` genuinely populates for personas with a Tree attachment, so
`_FSFTID` appears correctly for them without needing a compromise fallback.

**Files:**
- Modify: `Voyageur/Voyageur.js` (`fsBuildRowsFromApiResponse`, ~line 419)
- Modify: `Voyageur/census_schema.py` (`_normalize_participant`'s passthrough list, ~line 210)
- Modify: `Archivist/Census.py` (`load_census_dataframe`, `build_census_dataframe_from_unified`,
  the `_FSFTID`-fallback block ~line 1326-1335)
- Test: `Voyageur/tests/js/test_fs_api_parser.mjs`, `Voyageur/tests/test_census_ingestion.py`,
  `Archivist/tests/test_census_ingestion.py`

### Step 1: Write the failing JS test

```js
test('fsBuildRowsFromApiResponse: emits record_ark (not person_ark) from the PERSON element id', () => {
    const apiResponse = makeApiResponse();
    const rows = fsBuildRowsFromApiResponse(apiResponse);
    assert.ok('record_ark' in rows[0]);
    assert.ok(!('person_ark' in rows[0]) || rows[0].person_ark === '');
});
```

> If Task 1 finds a real Person-identifier field, add a second assertion here once the
> fixture (`makeApiResponse()`) is extended to include it - see Step 4.

### Step 2: Run tests to verify they fail

```
node --test "Voyageur/tests/js/*.mjs"
```

### Step 3: Rename in `Voyageur.js`, `census_schema.py`, and `Census.py`

`Voyageur.js` (~line 419):

```js
rows.push({columns, record_ark: person.id, person_ark: ''});
```

> `person_ark` here is intentionally left as an empty-string placeholder pending Step 4's
> real extraction, matching the existing "no fabrication" convention rather than reusing
> `record_ark`'s value under the new name.

`census_schema.py`'s passthrough list (~line 210): replace `"person_ark"` with both
`"record_ark"` and `"person_ark"` (both now genuinely distinct, both pass through unchanged):

```python
for passthrough_key in ("pid", "extracted_url", "fsftid", "record_ark", "person_ark",
                        "familysearch_url", "alternate_birth_places"):
    if person.get(passthrough_key):
        participant["type_specific_fields"][passthrough_key] = person[passthrough_key]
```

`Archivist/Census.py`: rename the `PersonArk` DataFrame column to `RecordArk` in both
population sites (`load_census_dataframe` ~line 1489, `build_census_dataframe_from_unified`
~line 1572), reading from the renamed source keys:

```python
row['RecordArk'] = person.get('record_ark', '')
# ... and the unified-schema site:
row['RecordArk'] = pts.get('record_ark', '')
```

Add a new `PersonArk` column alongside it (not replacing it) at both sites, reading the new
`person_ark` field - this stays empty until Step 4 populates real data upstream:

```python
row['PersonArk'] = person.get('person_ark', '')   # legacy site
row['PersonArk'] = pts.get('person_ark', '')       # unified site
```

### Step 4: Investigate and populate a true Person identifier - RESOLVED 2026-08-21

**Not DOM-only after all - a real, interceptable network call carries it.** User's own
Jess Guy Crowston example (FamilySearch's UI: "Attached in Tree to Jesse Guy Crowston ...
KLBM-H9P", absent from the orchestration API JSON) was chased via a temporary broad
network-URL spike, then a targeted response-body spike, both deployed live and removed
after use (per this task's own "revert before commit" convention). Found:

`POST /service/tree/links/sources/attachments` fires **automatically** once the Names panel
loads - not gated behind clicking into a specific person, and covers every persona on the
page/household in one batch. Response shape:

```json
{"attachedSourcesMap": {
  "https://www.familysearch.org/ark:/61903/1:1:6F7Z-QJKR": [
    {"persons": [{"entityId": "KLBM-H9P", "contributorId": "...", "tags": [...]}], "sourceId": "..."}
  ]
}}
```

`persons[0].entityId` is the true Family Tree person id - confirmed exact match to the UI's
displayed id. Most personas have no entry at all (never attached by anyone) - absence is the
common case, not an error, matching every other "don't fabricate" convention in this file.

**Implemented:** `runFamilySearchGather()`'s existing fetch/XHR interception (same pattern as
the orchestration API's own `FS_API_TARGET` watch) gained a second target,
`FS_ATTACHMENTS_TARGET = '/service/tree/links/sources/attachments'`, storing parsed results in
`unsafeWindow.__voyageurFsAttachments` keyed by the exact `record_ark` string (ark stripped
from the response's full URL via a new `fsAttachmentArkFromUri()`). A new exported helper,
`fsPersonArkFromAttachments(recordArk)`, looks this up; both `fsBuildRowsFromApiResponse()`
and `fsBuildRowsFromImageIndexResponse()` now call it when building each row's `person_ark`,
replacing the empty-placeholder from Step 3. Tests added in `test_fs_api_parser.mjs` cover
the lookup (hit, miss, and `unsafeWindow` absent) and end-to-end population via
`fsBuildRowsFromApiResponse`.

### Step 5: `_FSFTID` fallback logic - RESOLVED (omit), matches the default this plan proposed

Current code (~line 1326-1335), already updated:

```python
row_person_ark = get_row_val(row, ['PersonArk'], '')
indi_fsftid = row_fsftid or row_person_ark
```

`RecordArk` is not read here at all - it never feeds `_FSFTID`. Since Step 4 resolved with a
real extraction path (not a permanent dead-end), `PersonArk` will now genuinely populate for
personas that have a Tree attachment, and `_FSFTID` will correctly appear for them - this
was not just a "no data ever" compromise.

### Step 6: Update existing tests for the rename

`Archivist/tests/test_census_ingestion.py` and `Voyageur/tests/test_census_ingestion.py`
already have tests asserting `_FSFTID`/`_APID` placement and the ark-fallback behavior (added
earlier this branch - search for `test_census_gedcom_fsftid_falls_back_to_persons_own_ark`).
Update these to use `RecordArk`/`PersonArk`'s new meanings; do not delete the coverage, adapt
it.

### Step 7: Run tests to verify they pass

```
node --test "Voyageur/tests/js/*.mjs"
python -m pytest Voyageur/tests Archivist/tests -k "ark or fsftid" -v
```

### Step 8: Live smoke-check

> Deploy, gather real images, confirm the output JSON has both `record_ark` (always present,
> distinct per person) and `person_ark` (present only when Task 1/Step 4 found real data to
> populate it, otherwise absent/empty - not fabricated).

### Step 9: Lint and commit

```
python -m pycodestyle --max-line-length=120 Voyageur/census_schema.py Archivist/Census.py
git add Voyageur/Voyageur.js Voyageur/census_schema.py Archivist/Census.py Voyageur/tests Archivist/tests
git commit -m "fix(voyageur,archivist): rename person_ark->record_ark, populate true person_ark where available"
```

---

## Task 5: Add FS place/ED-boundary-crossing detection (restores ED-scoped batching)

**Files:**
- Modify: `Voyageur/Voyageur.js` (`scrapeCurrentImage`, `runLoop`, `saveFsReloadState`,
  `loadFsReloadState`, FS gather top-level scope)
- Test: `Voyageur/tests/js/test_stop_conditions.mjs`

Not blocked on Task 1. Independently implementable using fields `buildFsItemData()` already
returns.

### Step 1: Write the failing test

`placesMatch()` itself is already tested and shared - confirm the FS-returned shape
(`state`/`county`/`city`/`enumeration_district`) is field-compatible with zero adaptation:

```js
test('scrapeCurrentImage-equivalent: place mismatch against firstItemPlace signals boundary crossed', () => {
    const first = {state: 'North Dakota', county: 'Pembina', city: 'Walhalla', enumeration_district: '12'};
    const next = {state: 'North Dakota', county: 'Pembina', city: 'Neche', enumeration_district: '13'};
    assert.equal(placesMatch(first, next), false);
});
```

### Step 2: Run tests to verify they fail (if a new wrapper was introduced) or confirm existing coverage suffices

```
node --test "Voyageur/tests/js/*.mjs"
```

### Step 3: Add `firstItemPlace` tracking and the boundary check

Add `let firstItemPlace = null;` alongside the other FS gather state vars (~line 1381).
Restore it on reload alongside the other resumed state (~lines 1399-1410):

```js
firstItemPlace = resumedFsState.firstItemPlace || null;
```

Persist it in `saveFsReloadState()` (~line 178-188) and return it from `loadFsReloadState()`
(~line 190-208):

```js
// saveFsReloadState:
firstItemPlace: state.firstItemPlace,
// loadFsReloadState return object:
firstItemPlace: parsed.firstItemPlace || null,
```

Update `scrapeCurrentImage()` (~lines 1925-1941) to compare and signal a boundary crossing:

```js
async function scrapeCurrentImage() {
    const itemId = getItemId();
    if (!itemId) return {progressed: false, reason: 'no-item-id'};
    if (seenItemIds.has(itemId)) return {progressed: false, reason: 'already-seen'};

    const itemData = await buildFsItemData(itemId);

    const thisPlace = {
        state: itemData.state, county: itemData.county,
        city: itemData.city, enumeration_district: itemData.enumeration_district,
    };
    if (firstItemPlace === null) {
        firstItemPlace = thisPlace;
    } else if (!placesMatch(thisPlace, firstItemPlace)) {
        debugLog(`Place boundary crossed at item ${itemId}: `
            + `${JSON.stringify(firstItemPlace)} -> ${JSON.stringify(thisPlace)}`);
        return {progressed: false, reason: 'place-boundary-crossed'};
    }

    await downloadFsImage(itemId);

    seenItemIds.add(itemId);
    accumulatedItems.push(itemData);
    if (itemData.incomplete) {
        pagesNeedingRetry.push({item_id: itemId, url: window.location.href});
    }

    debugLog(`Scraped item ${itemId}: ${itemData.rows.length} index rows.`);
    return {progressed: true};
}
```

> Note the image itself is **not** downloaded for the boundary-crossing item - it belongs to
> the next ED/town, not this batch, same as Ancestry's `extractCurrentPageData()` returning
> `pageEntry: null` on a crossed boundary.

Update `runLoop()` (~line 2052-ish) to show a distinguishing toast on this specific reason:

```js
const result = await scrapeCurrentImage();
if (!result.progressed) {
    if (result.reason === 'place-boundary-crossed' && window.fsShowToast) {
        window.fsShowToast('New town/ED detected - stopping batch.', 'error', 3000);
    }
    stopBatch();
    break;
}
```

Update the `saveFsReloadState()` call site inside `runLoop()` to include `firstItemPlace`.

### Step 4: Run tests to verify they pass

```
node --test "Voyageur/tests/js/*.mjs"
```

### Step 5: Live smoke-check

> Deploy to Tampermonkey. Start a batch on a real ED known to span into a neighboring ED/town
> within a small number of images. Confirm: images within the starting ED are gathered
> normally; the first image belonging to the next ED/town is **not** downloaded and **not**
> included in the final JSON; the batch stops with the "New town/ED detected" toast; the
> final JSON's item count matches the actual number of images in the target ED.

### Step 6: Commit

```
git add Voyageur/Voyageur.js Voyageur/tests/js
git commit -m "feat(voyageur/js): stop FS batch at ED/town boundary, mirroring Ancestry"
```

---

## Task 6: Update orchestration API interception target (host + path)

**Blocked on Task 1's captured URL structure.**

**Files:**
- Modify: `Voyageur/Voyageur.js` (`FS_API_TARGET`, `fsApiArkFromUrl`, ~lines 1559-1599)
- Test: `Voyageur/tests/js/test_fs_api_parser.mjs`

### Step 1: Write the failing test using Task 1's captured URL shape

```js
test('fsApiArkFromUrl: extracts ark from the new orchestration path', () => {
    const url = 'https://www.familysearch.org/records/images/orchestration/<REAL_PATH>';
    assert.equal(fsApiArkFromUrl(url), '<expected-ark-from-captured-sample>');
});
```

### Step 2: Run tests to verify they fail

```
node --test "Voyageur/tests/js/*.mjs"
```

### Step 3: Update `FS_API_TARGET` and `fsApiArkFromUrl`

Keep the old target as a secondary check (don't drop old-path support):

```js
const FS_API_TARGET = '/service/records/volunteer/orchestration/sls/image/';   // legacy
const FS_API_TARGET_NEW = '/records/images/orchestration/';                     // current

function fsApiArkFromUrl(url) {
    let match = url.match(/<pattern derived from Task 1 capture>/);
    if (!match) match = url.match(/\/image\/([^/?#]+)/);
    return match ? decodeURIComponent(match[1]) : null;
}
```

Update both the XHR `load` listener check and the `fetch` wrapper's `url.includes(...)` check
to test against **either** target.

### Step 4: Run tests to verify they pass

```
node --test "Voyageur/tests/js/*.mjs"
```

### Step 5: Live smoke-check

> Deploy, load a real image, confirm `waitForFsApiResponse()` resolves (no "No index data
> received for this image." toast) and `rows` is non-empty.

### Step 6: Commit

```
git add Voyageur/Voyageur.js Voyageur/tests/js
git commit -m "fix(voyageur/js): match FS orchestration API's new host and path"
```

---

## Task 7: Verify/adjust response parsing against the new JSON shape

**Blocked on Task 1's captured response body.**

**Files:**
- Modify (if shape changed): `Voyageur/Voyageur.js`
  (`fsBuildRowsFromApiResponse`, `buildFsElementIndex`, `fsBuildCitationTextFromApiResponse`,
  `fsCanonicalFieldsFromApiPerson`)
- Test: `Voyageur/tests/js/test_fs_api_parser.mjs`

### Step 1: Compare captured shape against existing fixtures

The existing test fixture (`makeApiResponse()`) encodes the *old*
`elements`/`subElements`/`superElements` graph. Diff Task 1's captured real response against
it field-by-field.

### Step 2a: If the shape is unchanged (same graph, just moved transport)

Add a regression test using the real captured payload (redact personal/session data first) as
a fixture:

```js
test('fsBuildRowsFromApiResponse: parses a real captured explore-view response', () => {
    const real = require('./fixtures/captured_orchestration_response.json');
    const rows = fsBuildRowsFromApiResponse(real);
    assert.ok(rows.length > 0);
});
```

### Step 2b: If the shape changed

Write failing tests against the new shape first (use Task 1's actual captured structure), then
update the affected parser functions, keeping the old-shape code path alive behind a
shape-detection check if both are still seen live.

### Step 3: Run tests to verify they pass

```
node --test "Voyageur/tests/js/*.mjs"
```

### Step 4: Live smoke-check

> Deploy, gather 2-3 real images, inspect the resulting JSON: `rows` populated with real
> names/ages/relationships, `citation_text` non-empty and plausible.

### Step 5: Commit

```
git add Voyageur/Voyageur.js Voyageur/tests/js
git commit -m "fix(voyageur/js): adjust FS response parsing for the new orchestration payload"
```

---

## Task 8: Strengthen post-click navigation confirmation (known "went backwards" anomaly)

**Files:**
- Modify: `Voyageur/Voyageur.js` (`goToNextImage`, `advanceViaFilmstripThumbnail`)

Live-observed 2026-08-20: during an `explore`-view auto-batch, the image counter jumped
13 -> 7 -> ... -> 14 with console errors (`AbortError`, `Uncaught runtime.lastError: Could not
establish connection.`) around the same time. Current navigation-confirmation logic only
checks `window.location.href !== prevUrl`. This matters more now that Task 5 depends on
correctly sequencing which image's place data is being compared.

### Step 1: Add ark-based confirmation, not just URL-change

```js
const prevArk = getItemId();
nextBtn.click();
const navWait = await waitForCondition(() => getItemId() !== prevArk, {timeoutMs: 10000});
```

### Step 2: Add a `debugLog` on every navigation for post-hoc diagnosis

```js
debugLog(`Navigated: ${prevArk} -> ${getItemId()} (advanced=${!navWait.timedOut})`);
```

### Step 3: Live smoke-check

> Run a real multi-page `explore`-view batch (5+ images), confirm the console log shows
> monotonically-expected ark progression with no unexplained jumps. If jumps still occur,
> capture the console log and re-open investigation - lower-priority, do not let it block
> Tasks 1-7.

### Step 4: Run JS test suite

```
node --test "Voyageur/tests/js/*.mjs"
```

### Step 5: Commit

```
git add Voyageur/Voyageur.js
git commit -m "fix(voyageur/js): confirm FS navigation by ark change, not just href change"
```

---

## Task 9: Full regression + live end-to-end FS smoke test

### Step 1: Full automated suite

```
node --test "Voyageur/tests/js/*.mjs"
python -m pytest Voyageur/tests Archivist/tests -v
```

Expected: all pass, no regressions.

### Step 2: Live 5-page FS smoke test

> Run a real 5-page FS gather end-to-end and confirm every item from this plan:
> - Auto-batch completes without "Unrecognized page." or "No index data received" toasts
>   (Tasks 2, 6, 7).
> - Final JSON downloads with real data, not just per-image jpgs.
> - `rows` contain real names/ages/relationships AND birthplace/occupation/race/marital
>   status where the source image has them (Task 3) - spot-check against the actual scanned
>   image.
> - `record_ark` is present and distinct per person; `person_ark` is present only where a
>   true identifier was actually found, never fabricated (Task 4).
> - Batch correctly stops at the target ED/town's boundary instead of continuing into the
>   full roll (Task 5).
> - Feed the JSON through `Archivist/Census.py`'s GEDCOM builder; confirm individual-level
>   `_FSFTID`/`_APID` placement and correct image paths, and confirm `_FSFTID` behavior
>   matches whatever was decided for Task 4's open question.

### Step 3: Lint everything touched

```
python -m pycodestyle --max-line-length=120 Voyageur/FS.py Voyageur/_gather_helpers.py Voyageur/census_schema.py Archivist/Census.py
```

### Step 4: Update task tracker

Update `docs/plans/task.md` to mark this plan complete.

### Step 5: Final commit

```
git add docs/plans/task.md
git commit -m "chore: mark familysearch viewer rebuild complete"
```
