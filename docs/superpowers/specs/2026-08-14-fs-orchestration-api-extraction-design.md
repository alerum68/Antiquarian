# FamilySearch Orchestration-API Extraction — Design

**Status:** Design settled, ready for implementation planning
**Related:** GitHub issue #23 (originating discovery), issue #22 (navigation problem this design's data-extraction path avoids triggering in the first place, since it never opens a person's detail panel), issue #21 (the UI-scraping bug this design ultimately replaces the fix for)

## Goal

Replace `Voyageur.js`'s FamilySearch UI-scraping *for household/citation data* (Names-panel clicking, person-detail-panel clicking) with direct extraction from FamilySearch's own internal orchestration API — **delivered via the existing Tampermonkey userscript**, not a new automation stack. Ancestry's gather (`A.py`/`runAncestryGather()`) is unaffected — this is FS-only.

## Background: what was tried before, and why it wasn't enough

Issue #21 fixed the Names-tab detection bug in the existing UI-scraper (Tampermonkey userscript clicking through FamilySearch's "Names" panel and each person's detail panel). While live-verifying that fix, issue #22 was opened for a second problem: FamilySearch routes into an "explore" view (triggered by clicking a household member already attached to Family Tree) that has no reliable next-image navigation control — extensively tested (hover-mounted buttons, virtualized filmstrip, cosmetic-only number input), never fully solved.

Investigating *why* that navigation broke led to discovering that FamilySearch's own client loads each image's full indexed data via an internal API call, which sidesteps the UI-clicking fragility at the source rather than continuing to patch around it.

## Architecture

The gather no longer treats the FamilySearch record viewer's "Names" panel as a UI to click through for *data*. Navigation between images stays as-is (the existing Tampermonkey `goToNextImage()`/hover-mount fixes from #21). Per image:

1. Navigate to the image (existing Tampermonkey navigation logic, unchanged).
2. FamilySearch's own client automatically fires `GET sg30p0.familysearch.org/service/records/volunteer/orchestration/sls/image/{ark}` — confirmed live, no UI interaction required to trigger it.
3. The userscript's own `unsafeWindow.fetch`/`XMLHttpRequest.prototype.open` patch (same pattern already used elsewhere in this file for Ancestry's PID capture) intercepts that response.
4. A parser builds a `{id: element}` index from the response's flat `elements` array once, then extracts household/person/citation data via typed traversal functions (below).
5. That structured data replaces what `scrapeNamesPanel()`/`scrapeCitationAndCatalog()` currently produce for FS — same downstream shape (`{item_id, citation_text, catalog_items, rows}`), new source.
6. Advance to the next image via the existing navigation logic.

For records where clicking into a household member triggers the "explore" view (issue #22), this design's data path no longer needs to make that click at all — the API is read directly, without opening any person's detail panel. Image-to-image *navigation* still uses the existing #22 fixes if a gather happens to land on the "explore" view for other reasons, but the data-extraction path itself never triggers that view in the first place.

## Why Tampermonkey, not Playwright — reversed decision, confirmed live

**This design originally proposed moving to Playwright, specifically to enable headless operation. That direction was tested live and abandoned.** Kept here as a record of what was tried, since it's directly relevant to why Tampermonkey was the right call after all:

- Playwright's bundled Chromium gets blocked (403, Imperva Incapsula bot-detection challenge page) regardless of headless/headed.
- Real installed Chrome via `channel="chrome"`, headed, loaded the plain portal page cleanly across multiple independent attempts (fresh, cache-empty contexts each time).
- The same config in **headless** mode still got the Incapsula 403 challenge — headless itself is a detected signal, independent of browser binary.
- **Critically: the actual sign-in flow itself got blocked (Error 15) even under headed real Chrome**, despite the plain portal page loading fine. Automating login is the part that actually matters for a working design, and it's exactly the part that failed, consistently, regardless of configuration tweaks (fresh context, real Chrome binary, cache clearing).
- Active headless-evasion techniques (`--headless=new`, `navigator.webdriver` patching, stealth plugins) were deliberately **not pursued** — real risk to the user's own FamilySearch account, not just an IP, for uncertain and likely temporary payoff against an actively-maintained anti-bot vendor.

The deciding insight: `AI Assistant-in-chrome` (also automated, also CDP-adjacent) has been completely reliable against FamilySearch all session — because it drives the user's real, already-authenticated, human-operated browser, not a freshly-spawned automation profile attempting to authenticate itself. Tampermonkey has exactly that same property. The orchestration-API interception technique never actually needed Playwright — `unsafeWindow.fetch` patching inside the existing userscript does the identical job, and was already confirmed live to work cleanly (captured real 1850 and 1880 data, zero blocks) well before Playwright was ever introduced into this design. Playwright was pursued purely to chase headless operation; with headless confirmed non-viable regardless of implementation, there's no remaining reason to leave the proven, already-working Tampermonkey delivery mechanism.

**Net effect on the design:** no new browser automation stack, no session/login-persistence problem to solve (the user's existing, real, logged-in browser session is used, exactly as today), no headless capability (never achievable here). Everything else — the API, the parser, the confirmed data — carries over unchanged.

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

### Era-dependent field richness — confirmed by the user's own domain knowledge, matches existing codebase handling

A later, richer capture on an 1880 record surfaced a substantially larger field set than any earlier capture (1850 or 1880) had shown — including several fields that make earlier "unsolved" design problems trivial. **Per the user: 1850-1870 does not carry relationship-to-head data at all; 1880-1950 does.** Matches real US census history exactly - 1880 was the first US census year to record "relationship to head of household" as a questionnaire column at all (also the first to record marital status and parents' birthplace), so years before it have no such data to expose, API or otherwise. This is the same kind of era-dependent shape difference `census_schema.py`'s existing `get_census_era()`/`era == "pre1850"` handling already anticipates for Ancestry-sourced data - the FS parser needs the equivalent era-awareness, not a new concept, with the boundary specifically at 1880 (not 1850, which is what the existing `pre1850` naming might suggest at a glance).

**Newly confirmed fields (1880-1950), with real decoded values:**

| `fieldType` | Represents | Real value seen |
|---|---|---|
| `RELATIONSHIP_TO_HEAD` | Relationship to household head, **as a direct string** | "Other" (John Chislem) |
| `MARITAL_STATUS` | | "Single" (Joseph Lawrenson) |
| `OCCUPATION` | | "House Carpenter" (John Wimlaw) |
| `RACE_OR_COLOR` | | "White" (Annie E. Robb) |
| `FTHR_BIR_PLACE` / `MTHR_BIR_PLACE` | Father's/mother's birthplace | "Germany" / "District of Columbia, United States" |
| `MISC_FLAG_NEW_HOUSEHOLD` | Marks the first person of a new household | "X" (Henry C. Feldman) - a second, redundant way to detect household boundaries alongside `RECORD.subElements` |
| `SOURCE_SHEET_LTR` / `SOURCE_SHEET_NBR` | Census sheet letter/number | "A" / "48" |
| `SOURCE_PERSON_NBR` | A per-person position number | "9" (Oscar Close) - relationship to `EXT_LINE_NBR` below not yet disambiguated |
| `EXT_LINE_NBR` | **Per-person** sheet line number | "00036" (Matilda A. Tuschimsky) - resolves the earlier limitation that `SOURCE_LINE_NBR` is household-level only; this appears to be the true per-individual line number the UI never exposed either |
| `DISTRICT` (on a `PLACE` element, not `PERSON`) | Enumeration district | "ED 75" |

**Impact on open design questions:** `RELATIONSHIP_TO_HEAD` being a direct string field, if it holds up across more records, likely **eliminates** the "map `RELATIONSHIP` graph edges to a single string" problem flagged as unsolved design work below - read the field directly instead of walking the relationship graph. `EXT_LINE_NBR` likely resolves the per-person line number gap the `SOURCE_LINE_NBR` finding left open. Both should be re-verified across a few more 1880+ records before the parser design finalizes on them as the primary source (only confirmed on one record's capture so far), but this changes the shape of the "Downstream integration" and "Household ID / line number" sections above in the parser's favor - noted here rather than fully rewritten yet, since the household/line-number section above was written before this capture and should be revisited together with it.

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

## Old-style "Image Index" page — resolved, treated as unreachable

Checked live on a second account specifically to test this: the older table-style "Image Index" UI was not reachable there either — only the "Names" panel UI, same as the primary account (the presentation *within* the Names panel varies, not whether it's present at all). Combined with the earlier session finding that FamilySearch's "updated look" flag applies retroactively and persistently once triggered, this is treated as **the only UI style in practice going forward** — no old-style fallback path, no UI-style branching logic needed anywhere in this design. If a genuinely old-style page turns up in the future (a different account that's never triggered the flag, or a collection FamilySearch hasn't migrated), that's a new, separate problem to solve then, not a condition this design needs to handle now.

## Not yet verified — must be tested before implementation is trusted

1. **`DATE` element text decoding** — structure confirmed, never actually resolved to a value.
2. **Verification across collection types beyond US census** (church records, other countries) — everything confirmed so far is US census 1850/1880 only.
3. **`RELATIONSHIP`-to-"Relationship to Head" mapping** — likely no longer needed. `RELATIONSHIP_TO_HEAD` is a direct field (confirmed value: "Other"), so the parser can read it straight rather than walking the `RELATIONSHIP` graph, on 1880+ records. Confirmed on only one record so far - worth re-checking on a couple more 1880+ records before the implementation plan locks this in, but the graph-mapping problem this item originally flagged is probably moot.
4. **Location field (`STATE`/`COUNTY`/`TOWN`) proper scoping** for citation purposes.
5. **`SOURCE_PERSON_NBR` vs `EXT_LINE_NBR`** — both are per-person numeric fields with different real values on the same record; which one (if either) is the actual sheet line number vs. some other per-person ordinal isn't disambiguated yet.

## Next steps

None of the remaining open items changes the overall architecture the way the old-style-page question could have — they're implementation-detail items (date parsing, relationship mapping, location scoping) reasonable to resolve during implementation rather than blocking it. This design is ready to move toward an implementation plan.
