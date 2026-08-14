# FamilySearch Orchestration-API Extraction — Design

**Status:** Draft, pending user review
**Related:** GitHub issue #23 (originating discovery), issue #22 (superseded by this design's navigation approach), issue #21 (the UI-scraping bug this design ultimately replaces the fix for)

## Goal

Replace `Voyageur.js`'s FamilySearch UI-scraping (Names-panel clicking, person-detail-panel clicking) with direct extraction from FamilySearch's own internal orchestration API, and move the FS gather off the Tampermonkey/`webbrowser.open()` architecture onto a Python/Playwright-driven one. Ancestry's gather (`A.py`/`runAncestryGather()`) is unaffected — this is FS-only.

## Background: what was tried before, and why it wasn't enough

Issue #21 fixed the Names-tab detection bug in the existing UI-scraper (Tampermonkey userscript clicking through FamilySearch's "Names" panel and each person's detail panel). While live-verifying that fix, issue #22 was opened for a second problem: FamilySearch routes into an "explore" view (triggered by clicking a household member already attached to Family Tree) that has no reliable next-image navigation control — extensively tested (hover-mounted buttons, virtualized filmstrip, cosmetic-only number input), never fully solved.

Investigating *why* that navigation broke led to discovering that FamilySearch's own client loads each image's full indexed data via an internal API call, which sidesteps the UI-clicking fragility at the source rather than continuing to patch around it.

## Architecture

The gather no longer treats the FamilySearch record viewer as a UI to click through. Per image:

1. Navigate to the image (Playwright `page.goto()`/click, not Tampermonkey DOM interaction).
2. FamilySearch's own client automatically fires `GET sg30p0.familysearch.org/service/records/volunteer/orchestration/sls/image/{ark}` — confirmed live, no UI interaction required to trigger it.
3. Playwright's native `page.on("response")` captures that response — no `unsafeWindow.fetch`/`XMLHttpRequest.prototype` patching needed (that was a Tampermonkey-specific workaround; Playwright observes network traffic directly via CDP).
4. A parser builds a `{id: element}` index from the response's flat `elements` array once, then extracts household/person/citation data via typed traversal functions (below).
5. That structured data replaces what `scrapeNamesPanel()`/`scrapeCitationAndCatalog()` currently produce for FS — same downstream shape (`{item_id, citation_text, catalog_items, rows}`), new source.
6. Advance to the next image.

**This entire class of navigation problem (issue #22) becomes moot as a side effect.** The "explore" view was only ever triggered by clicking into an already-tree-attached person's own detail panel — a UI interaction this design never performs. Only plain image-to-image navigation remains, which Playwright's CDP-level clicks handle more reliably than the DOM-dispatch tricks that failed in Tampermonkey (confirmed live during this investigation: a genuine trusted click succeeded where synthetic `dispatchEvent` calls did not).

## Why Playwright, not Tampermonkey

The interception technique doesn't need Tampermonkey at all — `unsafeWindow.fetch` patching was only ever a workaround for not having native network access from inside a userscript. Playwright has that natively. Moving off Tampermonkey also removes an entire class of fragility this investigation ran into repeatedly (JS-realm event-dispatch failures, DOM-based navigation controls that don't mount reliably, `@run-at document-start` re-injection races).

The current FS launch mechanism (`Voyageur/_gather_helpers.py`'s `launch_gather_browser()`, via `webbrowser.open()`) opens a URL in the user's already-running, already-logged-in Chrome. That mechanism is being replaced for FS specifically with a Playwright-driven browser instance.

## Headless: not viable — confirmed live, with important caveats

The original ask was full headless operation. Confirmed live, decisively:

- Playwright's bundled Chromium gets blocked (403, Imperva Incapsula bot-detection challenge page) regardless of headless/headed.
- Launching the user's **real installed Chrome** via Playwright's `channel="chrome"` option, in **headed** (visible) mode, loaded cleanly with no challenge on one test.
- The same `channel="chrome"` in **headless** mode still got the Incapsula 403 challenge. Headless itself is a detected signal, independent of which browser binary is used.
- **Headed real Chrome is therefore a hard requirement, not a preference.** A gather run needs a visible browser window.

Active headless-evasion techniques (`--headless=new`, `navigator.webdriver` patching, stealth plugins) were deliberately **not pursued** — they cross from automating a browser into actively defeating FamilySearch's security measures, with real risk to the user's own FamilySearch account (not just an anonymous IP), and no guarantee of continued effectiveness against an actively-maintained anti-bot vendor.

### Open risk: possible rate/frequency-based escalation — UNRESOLVED

While testing the headed-Chrome approach across several consecutive launches in a short window, results were inconsistent: one clean success, then an explicit Incapsula block on a near-identical config, then a hard connection timeout that didn't even reach a challenge page. This pattern is consistent with **frequency-based escalation** (repeated automated-looking traffic from the same session/IP triggering progressively stricter detection), not a static per-request check.

This was **not resolved** before pausing — live testing was deliberately stopped to avoid compounding whatever block/rate-limit state might already be active, rather than continuing to probe blind. This is the single most important open question before this design can be trusted for real production use: **does repeated, spaced-out gather usage (the actual intended use pattern) stay reliable, or does automated traffic volume itself eventually get penalized regardless of headed/real-Chrome precautions?**

This must be re-tested — after an unknown cooldown period — with deliberate spacing between requests, before committing further implementation effort. Findings from that retest may change the headless/auth conclusions above.

## Session/login handling

FamilySearch login cannot be automated (credential-entry rule — the user logs in manually). Design:

1. First run (or whenever the session is no longer valid): launch headed real Chrome, user logs in manually, save `context.storage_state()` (cookies + localStorage) to a local file.
2. Subsequent runs: launch headed real Chrome, load the saved `storage_state`, check for a definitive logged-in signal before proceeding.
3. If the saved session is no longer valid (expired, logged out elsewhere), fall back to step 1.

**Confirmed-good, reusable detection technique:** a login-completion check must use a *positive* signal (an element that only exists when authenticated), checked only after the page has had a real chance to render. The `"Sign In"-text-absent` check tried first is a trap — it false-positives immediately, before the logged-out page has even finished mounting its own "Sign In" element, since "not yet rendered" and "genuinely absent" are indistinguishable to a naive absence check. The confirmed-working positive signal: `button[aria-label^="Account: "]` (FamilySearch's account-menu button), present only once actually logged in — verified against the real live site.

**Not yet tested:** whether a saved `storage_state` from one headed-Chrome session actually stays valid and gets accepted on a *separate* later headed-Chrome launch (the original ask that started this whole investigation, before it detoured into headless testing). This needs its own dedicated test pass, ideally as part of the same re-test that addresses the rate-limiting question above.

## Confirmed response shape

Top level:

```json
{
  "deprecatedImage": false,
  "elements": [ /* flat array, ~2000 entities for a dense image */ ],
  "languages": [...],
  "numberOfPersonsOnImage": 45,
  "numberOfRecordsOnImage": 6
}
```

`numberOfPersonsOnImage`/`numberOfRecordsOnImage` matched exactly what the old UI-scraper independently counted for the same image — strong confirmation this is the same underlying data, not a different/partial dataset.

`elements` is a flat, UUID-cross-referenced graph (not a nested tree) — every relationship between entities is via `subElements`/`superElements` id pointers, resolved through a `{id: element}` index built once per response.

### Confirmed element types (real captured data, not inferred)

| `elementType` | Represents | Notes |
|---|---|---|
| `RECORD` | One household | `subElements` directly lists the household's `PERSON` arks — no separate matching needed |
| `PERSON` | One person | `id` is the person-level ark (`1:1:...`), matching the format already used elsewhere in this codebase |
| `NAME` → `NAME_GIVEN`/`NAME_SURNAME` → `FIELD` | A person's name | A person can have >1 `NAME` (multiple indexed variants) - not always 1:1 with `PERSON` (confirmed on 1850: 101 `NAME` for 42 `PERSON`) |
| `RELATIONSHIP` | Exact link between two people | `relType`: `PARENT_CHILD`, `COUPLE` (confirmed values); `superElements` gives both person arks with `order: FIRST`/`SECOND` telling which side is which. **Not present on all collections** — confirmed absent entirely on 1850 (0 instances; relationship-to-head wasn't a recorded census column that year), present on 1880 (34-44 instances) |
| `AGE` → `FIELD` | Age | |
| `EVENT` (`eventType`: `CENSUS` or `BIRTH`, confirmed both) → `PLACE` → `FIELD` | Residence (CENSUS) / birthplace (BIRTH) | The `BIRTH`-type event is how birthplace becomes available at all — the current UI-scraper never captures this |
| `DATE` | Event date | Structure confirmed, text decoding not yet verified |
| `FIELD` | Leaf text value, everywhere | `fieldValues[0].normalizedValues[0].text`, or `fieldValues[0].origValue.text` when no normalized form exists |

### Confirmed working traversal (real data, both 1850 and 1880)

```js
const byId = {};
data.elements.forEach(e => { byId[e.id] = e; });

function fieldText(field) {
    const fv = field.fieldValues[0];
    return fv.normalizedValues ? fv.normalizedValues[0].text : fv.origValue.text;
}

function textOf(el) {
    if (!el) return null;
    const field = el.subElements.map(s => byId[s.id]).find(e => e && e.elementType === 'FIELD');
    return field ? fieldText(field) : null;
}

const person = data.elements.find(e => e.elementType === 'PERSON' && e.primary);
const linked = person.subElements.map(s => byId[s.id]).filter(Boolean);

const nameEl = linked.find(e => e.elementType === 'NAME');
const given = textOf(nameEl.subElements.map(s => byId[s.id]).find(e => e && e.elementType === 'NAME_GIVEN'));
const surname = textOf(nameEl.subElements.map(s => byId[s.id]).find(e => e && e.elementType === 'NAME_SURNAME'));

const age = textOf(linked.find(e => e.elementType === 'AGE'));

const birthEvent = linked.find(e => e.elementType === 'EVENT' && e.eventType === 'BIRTH');
const birthPlace = birthEvent
    ? textOf(birthEvent.subElements.map(s => byId[s.id]).find(e => e && e.elementType === 'PLACE'))
    : null;
```

Real results from this exact traversal: `"ELIZA M." "FISK"`, age `"38"`, born `"Maine, United States"` (1880 record); `"Bozil" "Delmer"`, age `"47"` (1850 record) — zero UI interaction for any of it.

### Household ID / line number — richer than the UI ever exposed

`FS.py` currently synthesizes a fake Line Number (`row_index + 1`) with an explicit code comment noting *"FamilySearch's census index never exposes an actual Line Number on any year checked"* via the UI. The raw API has real values the UI simply never surfaces:

| `fieldType` | Coverage (1850 example, 42 persons) | Scope | Real values seen |
|---|---|---|---|
| `SOURCE_HOUSE_NBR` | 42 of 42 (always present) | per person | dwelling number, e.g. "92" |
| `SOURCE_HOUSEHOLD_ID` | 35 of 42 | per person | family number as originally indexed, e.g. "90" |
| `FS_HOUSEHOLD_ID` | 7 of 42 (exact complement of the above — 35+7=42) | per person | FamilySearch's own system-generated fallback family number, used only when `SOURCE_HOUSEHOLD_ID` is absent |
| `SOURCE_LINE_NBR` | 1 per `RECORD` (household), not per person | per household | the household head's sheet line, e.g. "33" — other members are implicitly consecutive lines beneath, not individually numbered |

Mapping for the existing downstream schema: `family_number` reads `SOURCE_HOUSEHOLD_ID`, falling back to `FS_HOUSEHOLD_ID` when absent. `SOURCE_HOUSE_NBR` (dwelling number) and `SOURCE_LINE_NBR` (household's starting line) are new fields with no current home in the schema — worth adding as `type_specific_fields` entries rather than overloading `family_number`.

### Citation data — also available via the API, not just UI

Confirmed live: `EXT_FILM_NBR` ("367"), `EXT_PUB_NBR` ("M432" — the exact NARA publication number the current UI-scraped citation text also produces), `EXT_REPOSITORY_NAME` ("The U.S. National Archives and Records Administration (NARA)") are `FIELD` elements present once per image (image-level singletons, safe to read via a simple first-match lookup).

**Caveat, not yet resolved:** `STATE`/`COUNTY`/`TOWN`/`TOWNSHIP`-type fields are *not* image-level singletons — they're per-person/per-record fields (residence location for each family), and a naive first-match lookup pulled a garbled value in testing. These need proper scoping (which record/person they belong to) before being trusted for citation purposes, unlike the film/publication/repository fields above.

## Downstream integration

Target output shape is unchanged from what `scrapeNamesPanel()`/`scrapeCitationAndCatalog()` currently produce, consumed by `FS.py`'s `build_census_json()`:

```json
{
  "item_id": "...",
  "citation_text": "...",
  "catalog_items": [...],
  "rows": [
    {"columns": {"Given Name": "...", "Surname": "...", "Age": "...", "Family Number": "...", "Relationship to Head": "..."},
     "person_ark": "...", "attached_fsftid": ""}
  ]
}
```

`RELATIONSHIP` elements should replace the current "Relationship to Head" logic, which today only trusts the household head's own UI panel and falls back to omitting the column when FamilySearch's indexing left it ambiguous (see the existing `hasRealRelationshipData` check in `Voyageur.js`). With explicit `PARENT_CHILD`/`COUPLE` links for every person, this should become more complete and more reliable, not just differently-sourced — but the exact mapping from `RELATIONSHIP` graph edges to a single "Relationship to Head" string per person still needs real design work (a person can be a `PARENT_CHILD` target of one person and a `COUPLE` partner of another simultaneously — resolving that to "head of household" perspective isn't a trivial 1:1 mapping).

## Scope decisions

- **Full replacement**, not hybrid-with-fallback: the user's explicit call, given git provides rollback safety and the confirmed data coverage across two different census years (1850, 1880) with zero code changes needed between them.
- **Parser targets the existing downstream contract first** (Given Name/Surname/Age/Sex/Family Number/Relationship-to-head), with the richer data (birthplace, exact relationships, dwelling number) captured as a genuine upgrade since the schema already has slots (`birth_place`, `occupation`, `residence`, etc.) that have always been null from FamilySearch gathers specifically.
- **Citation data**: film/publication/repository fields via the same API; location fields (state/county/town) need further scoping work before being trusted — flagged above, not yet solved.

## Not yet verified — must be tested before implementation is trusted

1. **Rate/frequency-based escalation** (see "Open risk" above) — the single biggest unresolved question.
2. **`storage_state` persistence across separate headed-Chrome launches** — the original question that started this whole line of investigation; got sidetracked into headless testing before being answered.
3. **`DATE` element text decoding** — structure confirmed, never actually resolved to a value.
4. **Verification across collection types beyond US census** (church records, other countries) — everything confirmed so far is US census 1850/1880 only.
5. **`RELATIONSHIP`-to-"Relationship to Head" mapping** — real design work, not yet started.
6. **Location field (`STATE`/`COUNTY`/`TOWN`) proper scoping** for citation purposes.

## Next steps

Given the unresolved rate-limiting question in particular, this design should not proceed to an implementation plan until that's re-tested (after a cooldown period) and the `storage_state` persistence question is answered. Both are cheap, focused spikes — not architectural questions — but they gate whether headed-Playwright is actually viable for real production use, which everything else in this design depends on.
