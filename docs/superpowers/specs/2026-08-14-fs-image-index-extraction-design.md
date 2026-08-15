# FamilySearch Image-Index Extraction (Image Browser path) — Design Spec

## Goal

Extend `Voyageur.js`'s FamilySearch gather to cover records reached via **Image Browser**
(township/place navigation), which lands on a structurally different page than the "Names"
panel the existing orchestration-API extraction (Tasks 1-3 of
`docs/superpowers/plans/2026-08-14-fs-orchestration-api-extraction.md`) was built against.
This is not a replacement of that work — it's a second, parallel extraction path, selected
per-image based on which page actually rendered.

## Background

Task 4 of the prior plan (live verification) surfaced a real gap: navigating to a record via
FamilySearch's **Search** (name search) shows the "Names" panel, which the orchestration API
(`GET .../service/records/volunteer/orchestration/sls/image/{ark}`) backs. Navigating to the
same collection via **Image Browser** (browsing directly to a township/place) instead shows
the older "Image Index" panel, and the orchestration API never fires at all on that page.

Confirmed live, twice, on two different collections/eras (an 1860 and an 1880 US Federal
Census record): this is a **navigation-method split, not an era or collection split**. Image
Browser always renders the Image Index page; Search always renders the Names panel,
regardless of the record's year. The user's stated reason for preferring Image Browser is
also load-bearing for this design: it's the natural way to run a systematic town-by-town
gather, it's easier to pinpoint a specific location than search, and — critically — Search
does not appear to respect township boundaries the way Image Browser does, undermining the
existing town-boundary stop-condition logic (`placesMatch`, `runExtractionLoop`) that this
project already built for exactly this kind of systematic gather.

## Confirmed live: what the Image Index page actually uses

The Image Index page fires `POST /search/filmdatainfo/image-data` (plus a companion
`waypoint-data` call, not yet needed for extraction) instead of the orchestration API. This
was captured directly via a temporary Tampermonkey-injected interceptor (the same technique
Task 2 already uses for the orchestration API, just patched in temporarily to confirm the
shape) against two real records:

- 1860, Dakota Territory, collection 1473181 (`ark:/61903/3:1:33S7-9YBJ-9PD7`)
- 1880, Dakota Territory (Pembina), collection 1417683 (`ark:/61903/3:1:33S7-9YBZ-XVG`)

The response is a rich, GEDCOM X-flavored JSON with a `persons[]` array — richer than the
rendered table (which only shows Name/Sex/Age/Birth Year/Birthplace/Race/Page Number).
Structurally it's `persons[].facts[].(fields[].values[] | date.fields[].values[])`, a
list-of-facts-per-person model, distinct from the orchestration API's flat `elements[]` graph
with `subElements`/`superElements` cross-references.

**Response envelope essentials:**
- `arkId` (e.g. `"3:1:33S7-9YBJ-9PD7"`) — identifies which image this response is for. This
  is the only reliable correlation key: the *request* URL is the same generic
  `/search/filmdatainfo/image-data` for every image, unlike the orchestration API's per-ark
  request path.
- `persons[]` — each has `display: {name, gender, birthDate, birthPlace}` (a convenience
  summary, not the source of truth) and `facts[]` (the actual field data).
- `links.record.href` — points to `sg30p0.familysearch.org/platform/records/records/{recordId}`.

## Confirmed live: field identification — GEDCOM X standard types, with a labelId fallback

**This was checked against FamilySearch's own published GEDCOM X Field Types specification**
(`http://gedcomx.org/field-types/v1`, github.com/FamilySearch/gedcomx-record), not assumed
from the two samples alone. That spec defines standard, documented field-type URIs including
`Given`, `Surname`, `Gender`, `Age`, `Race`, `Ethnicity`, `Occupation`, `MaritalStatus`,
`Household`, `IsHeadOfHousehold`, `RelationshipToHead`, `FatherBirthPlace`, `MotherBirthPlace`.

Cross-checked against the actual captured 1880 response: every standard type URI needed for
**per-person facts** is genuinely present as the outer `"type"` on the relevant `facts[]`
entry — confirmed present: `http://gedcomx.org/Age`, `/Gender`, `/Given`, `/Surname`,
`/MaritalStatus`, `/Occupation`, `/Race`, `/RelationshipToHead` (plus `/Original` and
`/Interpreted`, the same raw-vs-normalized distinction Task 1's `fsFieldText()` already
handles for the orchestration API's `origValue`/`normalizedValues`).

**Not present as standard types in the captured data:** `Household`, `IsHeadOfHousehold`,
`FatherBirthPlace`, `MotherBirthPlace` — even though the spec defines them. These fields only
carry FamilySearch's own proprietary, undocumented `labelId` string (nested inside each
field's `values[]` entries): `FS_HOUSEHOLD_ID` / `SOURCE_HOUSEHOLD_ID` for household grouping,
`PR_FTHR_BIR_PLACE` / `PR_MTHR_BIR_PLACE` for parents' birthplace.

**Design consequence:** the per-person canonical-field extractor uses the standard
`gedcomx.org` type URI as the primary discriminator wherever one is confirmed present (age,
gender, given/surname, marital status, occupation, race, relationship-to-head), and falls
back to the proprietary `labelId` only for the fields that don't expose one (household ID,
father/mother birthplace). This is a firmer foundation than relying on the proprietary
`labelId` for everything, since the standard-URI fields are drawn from a documented,
versioned, cross-collection specification rather than reverse-engineered from two samples.

**Confirmed household-ID precedence duality carries over directly:** the 1860 sample used
`FS_HOUSEHOLD_ID`; the 1880 sample used `SOURCE_HOUSEHOLD_ID`. This is the exact same two-key
precedence Task 1's `fsFamilyNumber()` already resolves for the orchestration API
(`SOURCE_HOUSEHOLD_ID || FS_HOUSEHOLD_ID || sequential fallback`) — the same precedence rule
applies here unchanged.

**Confirmed era-dependent field presence matches the existing design exactly:** the 1860
sample's raw JSON has no relationship/marital/occupation facts at all (not blank — genuinely
absent), matching Task 1's existing "1850-1870 lacks these fields" boundary. The 1880 sample
has all of them. No year-branching code is needed here either — field presence alone drives
it, same convention as Task 1.

**Confirmed citation-relevant fields present:** `EXT_PUB_NBR`, `EXT_REPOSITORY_NAME`,
`FS_FILM_NBR`, `FS_DIGITAL_FILM_NBR`, `SOURCE_SHEET_LTR`, `SOURCE_SHEET_NBR`,
`SOURCE_PERSON_NBR` — all via `labelId` (no standard-URI equivalents observed for these,
consistent with them being record-administrative rather than person-demographic facts, a
category the field-types spec doesn't cover as thoroughly).

**Open item, not blocking this design:** whether the orchestration API (Task 1's already-
shipped data source) also carries these same standard `gedcomx.org` type URIs alongside its
own field-type strings is unconfirmed — Task 1's `RACE_OR_COLOR` field-type string doesn't
match the standard `Race` URI's naming cleanly, suggesting the orchestration API may use a
different, also-proprietary convention of its own. This should be checked before refactoring
Task 1's `fsBuildRowsFromApiResponse` (see Architecture below), but doesn't change this
document's own design.

## Architecture

Two source-specific traversals reduce a person down to a common **canonical field map**
(plain object keyed by canonical names: `givenName`, `surname`, `sex`, `age`, `birthplace`,
`householdIdSource`, `householdIdFs`, `relationshipToHead`, `maritalStatus`, `occupation`,
`race`, `fatherBirthplace`, `motherBirthplace` — a key absent, never blank, when the
underlying field is genuinely not present). One shared builder turns that canonical map into
the `columns` object both extraction paths ultimately produce, so nothing downstream of
`scrapeCurrentImage()` changes.

```
                     ┌─ Names panel present ──► fsCanonicalFieldsFromApiPerson()   ─┐
page-type detection ─┤                                                              ├─► fsColumnsFromCanonicalFields() ─► columns
                     └─ Image Index present ──► fsCanonicalFieldsFromImageIndexPerson() ─┘
```

**Components:**

1. **`fsCanonicalFieldsFromApiPerson(personElement, elementIndex)`** — refactor of the
   per-field lookups currently inline in Task 1's `fsBuildRowsFromApiResponse`. Walks the
   orchestration API's `elements[]` graph for one PERSON, returns the canonical map. This is
   the one piece of already-shipped code this plan touches; Task 1's existing 22 tests are
   the regression contract — they must pass unchanged after the refactor, proving behavior
   is preserved exactly.

2. **`fsCanonicalFieldsFromImageIndexPerson(personObj)`** — new. Walks one entry of
   `filmdatainfo/image-data`'s `persons[]` array (`facts[]` → standard type URI when
   present, else `fields[].values[].labelId`), returns the same canonical map shape.

3. **`fsColumnsFromCanonicalFields(canonicalFields, sequenceFallback)`** — new, shared by
   both paths. Applies the household-ID precedence
   (`householdIdSource || householdIdFs || sequenceFallback`) and the existing
   "omit key entirely, don't set it to ''" convention for absent relationship/marital/
   occupation/race/parent-birthplace fields. Produces the exact `columns` shape
   `fsBuildRowsFromApiResponse` already produces today (`Given Name`, `Surname`, `Gender`,
   `Age`, `Family Number`, `Relationship to Head` when present).

4. **Image-Index interceptor + `waitForFsImageIndexResponse(ark, {timeoutMs})`** — mirrors
   Task 2's XHR/fetch patch pattern exactly (double-install guard, per-ark waiter map,
   event-driven resolution — reusing the corrected pattern from Task 2's own fix round, not
   the original buggy `waitForCondition()`-based version). The one structural difference:
   keyed by the **response body's** `arkId` field, not the request URL, since
   `/search/filmdatainfo/image-data`'s URL is identical for every image.

5. **Page-type detection** — a single DOM check (does a "Names" tab exist, or an "Image
   Index" tab) run once per image inside `scrapeCurrentImage()`, before awaiting either data
   source. Reuses the file's existing tab-detection conventions (`findByExactText`,
   `clickTab`) rather than inventing a new one.

6. **`fsBuildRowsFromImageIndexResponse(apiResponse)`** — new, mirrors Task 1's
   `fsBuildRowsFromApiResponse` signature and return shape
   (`[{columns, person_ark, attached_fsftid}]`) exactly, so `scrapeCurrentImage()` can call
   either interchangeably. `person_ark`/`attached_fsftid` come from `links.record.href` and
   the person's own tree-attachment link respectively (exact link shapes to be confirmed
   during implementation against the full captured response, not yet fully characterized in
   this design).

7. **`fsBuildCitationTextFromImageIndexResponse(apiResponse)`** — new. Builds the same prose
   `citation_text` string `scrapeCitationAndCatalog()` currently scrapes from the
   "Information" tab's UI, entirely from JSON fields, so the Image-Index path never depends
   on that UI read. `FS.py`'s downstream parsing (`parse_citation()`, `parse_nara_citing_clause()`,
   `parse_census_browse_path()`) is a **deliberately untouched regression boundary** — this
   function's only job is to produce a string that regex-matches the exact same way a
   UI-scraped one already does, verified against real fixture strings from
   `Voyageur/tests/test_fs.py`:

   ```
   "<collection_name>," database with images, FamilySearch (<url> : <date>),
   <state> > <county>[ > <township>][ > ED <n>] > image <N> of <total>;
   citing NARA microfilm publication <publication> (<repo_loc>: <repo_name>, n.d.).
   ```

   Field sources, confirmed against the captured JSON unless noted:
   - `collection_name` ← `collections[].collections[].title`
   - `url` ← the page's own ark URL (`window.location.href`, already available)
   - `date` ← current date at gather time (format is not parsed downstream — the
     `CITATION_RE`/`url_match` regex only requires *some* text after `" : "`, so no specific
     format is required)
   - `state`/`county`/`township` ← `EVENT_STATE`/`EVENT_COUNTY`/`EVENT_TOWNSHIP`
   - `ED <n>` ← `ENUMERATION_DISTRICT`, only when present (matches `parse_census_browse_path()`'s
     own optional ED-segment handling)
   - `publication` ← `FS_FILM_NBR` or `FS_DIGITAL_FILM_NBR`
   - `repo_name` ← `EXT_REPOSITORY_NAME`
   - **`repo_loc` — NOT CONFIRMED.** No matching field found in either captured sample. Likely
     a fixed value ("Washington, D.C.") for NARA-sourced US census microfilm specifically,
     but this is an assumption, not a verified fact — flagged below, must be confirmed (or
     deliberately hardcoded with that reasoning stated) during implementation, not silently
     assumed.
   - **`image <N> of <total>` — `total` NOT CONFIRMED from this endpoint's JSON.** The Image
     Index page's own UI already displays this (`Image 1 of 3`) — reading that one specific,
     stable, already-rendered number is a legitimate fallback per this project's "no UI
     unless there's no other option" rule, since no other JSON source for it was found in
     `filmdatainfo/image-data` (the companion `waypoint-data` endpoint may carry it, but that
     endpoint is out of scope for this plan). `N` itself (current image position) doesn't need
     this: it's decided by ordering, not a field.

   **Deliberately deferred, not built now:** a further, cross-language redesign where JS emits
   a *structured* citation object and `FS.py` reads it directly, retiring `parse_citation()`/
   `parse_nara_citing_clause()`/`parse_census_browse_path()` entirely instead of round-tripping
   through prose. This was scoped out during design specifically to keep this plan JS-only and
   avoid touching tested, working Python code in the same pass — a real improvement, revisit
   as a separate follow-up once this path has shipped and proven itself.

## Data flow

Image loads → both interceptors are already installed (harmless — the one for the page type
that isn't showing simply never sees a matching request) → `scrapeCurrentImage()` checks the
DOM for which tab is present → awaits the matching wait function → the matching per-person
canonical-field extractor runs per person → `fsColumnsFromCanonicalFields()` builds each
row's `columns` → same `{columns, person_ark, attached_fsftid}` row assembly and
`accumulatedItems.push()` as today.

## Error handling

Same conventions as the existing Image-Index-absent path Task 3 already built: if neither tab
is found (page still loading, or an unrecognized third page shape), the page-type check waits
via the file's existing `waitForCondition()` up to its timeout, then logs and shows a toast,
continuing with `rows = []` rather than blocking the batch. No fabricated data for absent
fields — matches the existing project-wide convention.

## Testing

- New tests for `fsCanonicalFieldsFromImageIndexPerson()` using **trimmed real captures**
  from tonight's live 1860 and 1880 responses as fixtures — genuine data, not synthetic,
  which is a stronger fixture than Task 1's original synthetic ones.
- New tests for `fsColumnsFromCanonicalFields()` directly: household-ID precedence (both
  orderings), era-appropriate omission (relationship/marital/occupation/race/parent-
  birthplace all individually absent vs. present).
- Task 1's existing 22-test suite re-run unchanged after the `fsBuildRowsFromApiResponse`
  refactor, as the regression contract for that refactor.
- New test for the page-type detection helper (DOM fixture with each tab present/absent).
- New tests for `fsBuildCitationTextFromImageIndexResponse()` asserting the produced string
  round-trips correctly through `FS.py`'s existing `CITATION_RE`/`NARA_CITING_RE` — the real
  regression contract for this function, not just "does it contain the right substrings."
- No new test needed for the interceptor/wait function itself, same reasoning as Task 2:
  it depends on `unsafeWindow`, which the Node harness stubs as `undefined`.

## Scope decisions

- **In scope:** Image Index page detection, `filmdatainfo/image-data` interception and
  parsing, the shared canonical-field/columns layer, `fsBuildRowsFromApiResponse`'s refactor
  to route through the shared builder, and building `citation_text` from JSON fields
  (`fsBuildCitationTextFromImageIndexResponse`) rather than relying on
  `scrapeCitationAndCatalog()`'s UI read — per explicit direction: JSON extraction is
  preferred everywhere it's available, UI reads only where genuinely nothing else exists
  (the one confirmed remaining case: total image count, see above).
- **Deferred, not built now:** the structured cross-language citation redesign (JS emits
  structured fields, `FS.py` consumes them directly instead of regex-parsing prose) —
  explicitly scoped out to keep this plan JS-only; a real improvement to revisit later, not
  a rejected idea.
- **Out of scope:** restructuring the downstream Python pipeline (`FS.py`, `census_schema.py`,
  Commissioner models, Archivist's GEDCOM 5.5.1 builder) to consume GEDCOM X shapes directly.
  Considered and explicitly rejected — nothing downstream consumes GEDCOM X today, both
  extraction paths already collapse to the same flat `columns` dict before leaving
  `Voyageur.js`, and pushing GEDCOM X further downstream would be a much larger, separate
  initiative unrelated to covering the Image Browser navigation path.
- **Out of scope:** `waypoint-data` (the companion endpoint) — not needed for row extraction;
  may carry the total-image-count this plan otherwise reads from the UI, worth checking as a
  follow-up, not blocking this plan.

## Not yet verified

- Exact shape of `person_ark`/`attached_fsftid` derivation from `links.record.href` and any
  tree-attachment link on the Image Index response — need to inspect a person with a
  confirmed Family Tree attachment, not yet captured.
- Whether the orchestration API also carries standard `gedcomx.org` type URIs (see Open item
  above) — check before starting the `fsBuildRowsFromApiResponse` refactor.
- NARA repository location (`repo_loc` in the citation template) — no matching JSON field
  found in either capture; likely a fixed "Washington, D.C." for US census microfilm, but
  this is an assumption to confirm (or knowingly hardcode with reasoning stated), not a
  verified fact.
- Total image count for the "image N of total" citation segment — not found in
  `filmdatainfo/image-data`'s JSON; current plan is to read the one already-rendered UI
  number as the sole UI fallback in this whole plan, but `waypoint-data`'s response hasn't
  been inspected and may carry it instead.
- Field coverage beyond the two captured samples (1860/1880 US Federal Census only) — other
  years, non-census collections, and non-US collections are unverified. The standard-type-URI
  foundation should generalize better than the proprietary labelId convention would have, but
  this is not proven beyond what's been captured.
