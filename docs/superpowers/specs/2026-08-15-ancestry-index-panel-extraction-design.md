# Ancestry Index-Panel-Data Extraction — Design

**Status:** Design settled, ready for implementation planning
**Related:** GitHub issue #24 (follow-up: extend to all census years, Canadian records, State records — explicitly NOT this plan's scope). Sibling/precedent: `docs/superpowers/specs/2026-08-14-fs-orchestration-api-extraction-design.md` — same shape of discovery (site's own internal API, network-intercepted via the existing Tampermonkey userscript), same delivery mechanism.

## Goal

Add a second data source for Ancestry's per-image person-index data — `Voyageur.js`'s own internal `imageviewer/api/record/index-panel-data` network call — alongside the existing DOM-table scraper, **as a fallback pair, not a replacement**: the API path runs first; if it doesn't fire/times out, the existing DOM-table scraper (unchanged) takes over. Unlike the FS orchestration-API work (a full replacement), the user explicitly wants both paths kept for now — DOM scraping is deliberately not being removed this round; a future cleanup pass will drop whichever path proves unnecessary once the API path is verified stable in production.

FS's gather (`FS.py`) is unaffected — this is Ancestry-only.

## Background: how this was discovered

While investigating whether Ancestry exposes anything comparable to FamilySearch's orchestration API (the FS work above), live network-request inspection on the exact same Ancestry census image already used throughout this project's own live-verification testing (`dbId=7667`, `imageId=4211353_00001`, 1860 Dakota Territory) surfaced several genuine JSON API endpoints Ancestry's own client calls on page load — none of which `Voyageur.js` currently intercepts. `Voyageur.js` already has one XHR interceptor installed for Ancestry (`unsafeWindow.fetch`/`XMLHttpRequest.prototype.open` patch, used today only for `extractPidsFromText(text)` — sniffing PIDs out of whatever response text flows through). This design extends that same, already-installed interceptor rather than adding a second one.

## Confirmed endpoints (real captured traffic, not inferred)

| Endpoint | Fires when | Shape |
|---|---|---|
| `GET /imageviewer/api/record/index-panel-data?dbId={dbId}&imageId={imageId}` | The person-index panel is opened/visible on an image (same trigger as the DOM table) | **The target of this design** — full per-person field data, see below |
| `GET /imageviewer/api/record/simple-records?dbId={dbId}&imageId={imageId}` | Same trigger | Lighter: `[{"DisplayValue": "...", "HouseholdId": "...", "Pid": 123}]` — not needed, `index-panel-data` is a superset |
| `GET /imageviewer/api/collections/collection-text?dbId={dbId}&imageId={imageId}&path={browsePath}` | Citation ("Source" tab) opened | `{"OnlineSourceInfo": "...", "OriginalSourceInfo": "...", "OnlineDescription": "...", "Citation": null, "BrowseDescription": "", "BrowseValue": "On Red River"}` — clean JSON version of what `scrapeSourceCitation()` currently regex-parses from rendered DOM text. **Out of scope for this plan** (this plan is `index-panel-data` only) — noted here because it's the natural next target, tracked under issue #24, not built now. |
| `GET /imageviewer/api/collection/id?dbId={dbId}&isInstitutionalUser=false&treespage=1` | Page load | Collection title + `onlineSourceInfo`, but response body also includes the signed-in user's own Ancestry tree list (account-specific, unrelated data mixed in) — noisier than `collection-text`, not useful here |

## `index-panel-data` response shape (confirmed)

```json
{
  "records": [
    {
      "pid": 17613762,
      "householdId": "17613762",
      "fullName": "Joseph Kosses",
      "recordFields": [
        {"fieldName": "SourceDwellingNumber", "value": "1", "correctedValue": null},
        {"fieldName": "SelfGivenName", "value": "Joseph", "correctedValue": null}
      ],
      "citation": null,
      "isUserCreated": false
    }
  ],
  "fieldLabels": [
    {"fieldName": "SourceDwellingNumber", "labelText": "Dwelling Number", "isLocking": false, "isEditable": false, "cellIndex": 1}
  ],
  "editableFormData": false,
  "isIndexPanelVisible": false,
  "isIndexPanelVisibleBeforeFullScreen": false,
  "isIndexPanelDataLoading": false,
  "isIndexPanelError": false,
  "fieldName": null
}
```

- `records[].pid` — a real, stable numeric Ancestry person ID. This project's own `A.py`/`Voyageur.js` already uses "PID" as the per-person REFN/rec_id concept (scraped from a link `href` today) — `pid` here is the same concept, straight from the API, no DOM/href parsing needed.
- `records[].householdId` — a **real, explicit household grouping ID** straight from Ancestry. Today, `census_schema.py`'s `_household_key()` infers households from the Family Number/Dwelling Number *column values* (fragile — varies by year, sometimes absent). `householdId` is a direct, always-present replacement signal (confirmed present on all 4 tested years).
- `records[].recordFields[].correctedValue` — Ancestry's own manual-correction layer. Not surfaced by the DOM table at all. **Out of scope for this plan** — always read `value`, never `correctedValue`; a future task can decide whether corrections should override.
- `records[].citation` — was `null` on every record tested (all 4 years). Not used by this plan.
- `fieldLabels` — self-describing: maps each `fieldName` to its human-readable column header for *this* collection. The `fieldName` vocabulary itself (see below) is stable across census years; only which fields are present, and their `cellIndex`/label wording, varies. This plan keys its own field map on `fieldName`, not on label text or DOM header text — `fieldName` doesn't drift the way rendered header text can.

## Confirmed field sets across 4 real census years (Pembina, ND / Minnesota Territory / Dakota Territory)

All captured live, this session, against real Ancestry data. `fieldName` is the API's own stable key; `→ column` is the target this plan maps it to in `Voyageur.js`'s existing row-`columns` shape (the same shape the DOM-scraper already produces, so `census_schema.py`/`ancestry_census.yaml` need **zero changes** downstream of this parser — it's a drop-in second producer of the same `columns` dict).

### 1850 (dbId `8054`, sample `imageId` `4195937-00039`, Joseph Rolette household, Pembina, Minnesota Territory)

17 fields. Real sample values (Joseph Rolette, line 1):

| `fieldName` | Sample value | → `columns` key |
|---|---|---|
| `LineNumber` | `"1"` | `Line Number` |
| `SourceDwellingNumber` | `"1"` | `Dwelling Number` |
| `Famnum` | `"1"` | `Family Number` |
| `SelfGivenName` | `"Joseph"` | `Given Name` |
| `SelfSurname` | `"Rolette"` | `Surname` |
| `SelfResidenceAge` | `"28"` | `Age` |
| `SelfBirthYear` | `"1822"` | `Birth Year` |
| `SelfGender` | `"Male"` | `Gender` |
| `SelfRace` | `"White"` | `Race` |
| `SelfResidenceOccupation` | `"Clerk"` | `Occupation` |
| `SelfResidenceIndustry` | `"Not Specified Retail Trade"` | `Industry` *(already an existing `ancestry_census.yaml` target — `"Industry": Occupation` in `participant_facts`, confirmed present in the file before this plan; no YAML change needed for this field, just a JS-side `fieldName → "Industry"` mapping entry)* |
| `SelfResidenceRealEstateValue` | `""` | `Real Estate Value` |
| `SelfBirthPlace` | (not captured in sample, field present) | `Birth Place` |
| `SelfResidenceMarriedWithinYear` | `""` | `Married within Year` |
| `SelfResidenceAttendedSchool` | `""` | `Attended School` |
| `SelfResidenceCannotRead` | `""` | `Cannot Read, Write` |
| `SelfResidenceDisabilityCondition` | `""` | `Disability Condition` |

42 records, 8 distinct `householdId`s on this image.

### 1860 (dbId `7667`, `imageId` `4211353_00001`, Joseph Kosses household, Dakota Territory — the collection this project's other live-verification testing already uses)

17 fields (same shape as 1850, minus `LineNumber`/`SelfResidenceIndustry`, plus `SelfResidencePersonalEstateValue` — matches real US census history: personal estate value was added as a census question starting 1860). Real sample (Joseph Kosses, dwelling 1):

`SourceDwellingNumber:"1"`, `Famnum:"1"`, `SelfSurname:"Kosses"`, `SelfGivenName:"Joseph"`, `SelfResidenceAge:"32"`, `SelfBirthYear:"1828"`, `SelfGender:"Male"`, `SelfRace:"White"`, `SelfResidenceOccupation:"Hunter"`, `SelfResidenceRealEstateValue:""`, `SelfResidencePersonalEstateValue:"300"`, `SelfBirthPlace:"Hudsen Bay Ter T"`, `SelfResidenceMarriedWithinYear:""`, `SelfResidenceAttendedSchool:""`, `SelfResidenceCannotRead:""`, `SelfResidenceDisabilityCondition:""`.

**Confirmed: `LineNumber` is genuinely absent from 1860's `fieldLabels` list** (present in 1850, 1880, 1920 — 1860 is the outlier). The field map must treat every field as optional per collection, keyed off whatever `fieldLabels` this specific response actually lists, not assume a fixed set.

30 records on this image, 28 distinct households (matches this session's earlier live FS gather of the same location: 28 households).

### 1880 (dbId `6742`, `imageId` `4240106-00102`, Doty household, Dakota Territory)

27 fields — real US-history-accurate jump: 1880 was the first census year to record relationship-to-head, marital status, and parents' birthplace (matches this project's existing FS-side era-boundary design, `census_schema.get_census_era()`, which already treats 1880 as the relationship-data boundary for FamilySearch — this confirms the same boundary applies to Ancestry's data too, from the API side, not just DOM rendering).

**Note: no `Famnum`/Family Number field in 1880's list at all** — only `SourceDwellingNumber`. Real 1880 census schedules only recorded dwelling number + line number, not a separate family number — this is correct, not a gap.

| `fieldName` | → `columns` key / target |
|---|---|
| `LineNumber` | `Line Number` |
| `SelfResidenceStreetAddress` | `Street` *(already added to `ancestry_census.yaml` this session)* |
| `SourceDwellingNumber` | `Dwelling Number` |
| `SelfSurname` | `Surname` |
| `SelfGivenName` | `Given Name` |
| `SelfRace` | `Race` |
| `SelfGender` | `Gender` |
| `SelfResidenceAge` | `Age` |
| `SelfBirthMonth` | *new* → `Birth Month` |
| `SelfBirthYear` | `Birth Year` |
| `SelfRelationToHead` | `Relationship to Head` *(existing target — `ancestry_census.yaml` already has this alias-mapped)* |
| `SelfMaritalStatus` | *new* → `Marital Status` |
| `SelfResidenceMarriedWithinYear` | `Married within Year` |
| `SelfResidenceOccupation` | `Occupation` |
| `SelfResidenceMonthsUnEmployedPastYear` | *new* → `Months Not Employed` |
| `SelfResidenceIsSick` | *new* → `Sick` |
| `SelfResidenceIsBlind` | *new* → `Blind` |
| `SelfResidenceIsDeafDumb` | *new* → `Deaf Dumb Blind Insane` *(existing note-column target already recognized by `Census.py`'s `get_census_notes`/`CORE_COLUMNS` — reuse it)* |
| `SelfResidenceIsIdiotic` | *new* → `Idiotic Pauper Convict` *(existing note-column target, reuse)* |
| `SelfResidenceIsInsane` | *new* → `Deaf Dumb Blind Insane` *(same reused target as `IsDeafDumb` — both feed the same combined note column Census.py already knows how to render)* |
| `SelfResidenceIsMaimed` | *new* → `Disability Condition` |
| `SelfResidenceAttendedSchool` | `Attended School` |
| `SelfResidenceCannotRead` | `Cannot Read, Write` |
| `SelfResidenceCannotWrite` | *new* → `Cannot Read, Write` *(same target as `CannotRead` — 1880 splits the question in two, this project's existing schema only has one combined column; both map to it)* |
| `SelfBirthPlace` | `Birth Place` |
| `FatherBirthPlace` | *new* → `Father Foreign Born` *(existing note-column target — reuse; not a perfect semantic match (existing column is boolean-ish "foreign born" flag, API gives an actual place), but reusing the existing recognized column is the pragmatic call for this plan; a precise fact-type is issue #24 follow-up territory)* |
| `MotherBirthPlace` | *new* → `Mother Foreign Born` *(same reasoning as `FatherBirthPlace`)* |

### 1920 (dbId `6061`, `imageId` `4383784_00215`, Mary J Darylus household, Pembina, North Dakota — a state by 1920, no longer a territory)

28 fields. Real sample (Mary J Darylus, head, line 1): `LineNumber:"1"`, `SelfResidenceStreetAddress:""`, `HouseNumber:"Farm"`, `Famnum:"1"`, `SelfSurname:"Darylus"`, `SelfGivenName:"Mary J"`, `SelfRelationToHead:"Head"`, `SelfResidenceHomeOwnership:"Owned"`, `SelfResidenceHomeMortgaged:"Mortgaged"`, `SelfGender:"Female"`, `SelfRace:"White"`, `SelfResidenceAge:"67"`, `SelfBirthYear:"1853"`, `SelfMaritalStatus:"Widowed"`, `SelfArrivalYear:"1882"`, `SelfResidenceNaturalizationStatus:"Naturalized"`, `SelfNaturalizationYear:""`, `SelfResidenceAttendedSchool:""`, `SelfResidenceCanRead:"Yes"`, `SelfResidenceCanWrite:"Yes"`, `SelfBirthPlace:"Canada"`, `SelfResidenceLanguageSpoken:"English"`, `FatherBirthPlace:"Ireland"`, `MotherBirthPlace:"Ireland"`, `SelfResidenceAbleToSpeakEnglish:"Yes"`, `SelfResidenceOccupation:"None"`, `SelfResidenceIndustry:""`, `SelfResidenceIsEmployed:""`.

New fields vs. 1880/1850, mapping targets:

| `fieldName` | → target |
|---|---|
| `HouseNumber` | *new* → `House Number` *(already added to `ancestry_census.yaml`'s `record_fields` this session as a `dwelling_number` alias — do NOT also map this as a `type_specific_fields.street` target; that would be the exact ambiguous-header conflict already caught and avoided once this session)* |
| `SelfResidenceHomeOwnership` | *new* → `Home Ownership` (Miscellaneous fact) |
| `SelfResidenceHomeMortgaged` | *new* → `Home Mortgaged` (Miscellaneous fact) |
| `SelfArrivalYear` | *new* → `Immigration Year` *(existing target, already an `Immigration` fact-type alias)* |
| `SelfResidenceNaturalizationStatus` | *new* → `Naturalization Status` *(existing target, already a `Naturalization` fact-type alias)* |
| `SelfNaturalizationYear` | *new* → `Year of Naturalization` *(existing target)* |
| `SelfResidenceCanRead` | *new* → `Cannot Read, Write` *(inverse-sense reuse: API says "Able to read" Yes/No, existing column is framed as "Cannot Read, Write" — this plan does NOT invert the value; it's captured as-is under the same column, matching how 1880's `CannotRead`/`CannotWrite` also feed this one column. Flagged as an imperfect-but-pragmatic reuse, same as the disability-field reuses above.)* |
| `SelfResidenceCanWrite` | *new* → same as above |
| `SelfResidenceLanguageSpoken` | *new* → `Native Tongue` (Miscellaneous fact) |
| `SelfResidenceAbleToSpeakEnglish` | *new* → `Speaks English` (Miscellaneous fact) |
| `SelfResidenceIndustry` | → `Industry` *(same existing target as 1850's `SelfResidenceIndustry` — already `"Industry": Occupation` in `participant_facts`, no YAML change needed)* |
| `SelfResidenceIsEmployed` | *new* → `Employment Field` (Miscellaneous fact) |

## Architecture

1. Extend `Voyageur.js`'s existing Ancestry `XMLHttpRequest.prototype.open` patch (currently only calling `extractPidsFromText(this.responseText)` on every response) to ALSO check if `url` contains `/imageviewer/api/record/index-panel-data` — if so, parse the JSON body and resolve a waiter keyed by `` `${dbId}:${imageId}` `` (extracted from the URL's query string), mirroring the existing FS `waitForFsApiResponse`/`waitForFsImageIndexResponse` waiter-map pattern (a plain object mapping key → `{resolve, promise}`, NOT `waitForCondition()` on a non-DOM condition — that pattern was already tried and reverted once this session for FS, for a related reason; don't reintroduce it here).
2. New pure function `ancestryColumnsFromIndexPanelRecord(record, fieldLabelsByName)` — takes one `records[]` entry, returns a `columns` dict using the `fieldName → columns key` table above. An unrecognized `fieldName` is left as-is: pass it through under its own raw `fieldName` string as the column key (matching this project's existing "never silently drop, always flag for review" convention — `census_schema.py`'s `_normalize_participant` already treats any column name it doesn't recognize as `unmapped` and flags the record for review; an Ancestry `fieldName` the map above doesn't cover will hit that exact same existing path once it reaches `census_schema.py`, no new review-flagging logic needed here).
3. New function `ancestryRowsFromIndexPanelResponse(apiResponse)` — maps every `records[]` entry through step 2, and additionally sets `pid` (from `record.pid`) and a new `household_id` key (from `record.householdId`) on each row, alongside `columns`.
4. Wire into the gather loop (wherever the DOM-table scrape currently runs, per-image): call `waitForAncestryIndexPanelResponse(dbId, imageId, {timeoutMs})` first. On success, use `ancestryRowsFromIndexPanelResponse()`. On timeout/no capture, fall back to the existing DOM-table scraper **completely unchanged** — same function, same output shape, no modification needed to it at all for this plan.
5. `census_schema.py`'s `_household_key()`: prefer `person.household_id` (the new field from step 3) over the existing `family_number`/`dwelling_number`-column-based inference, when present. Falls back to the existing column-based logic unchanged when `household_id` is absent (i.e., when the DOM-scraper fallback path produced the row instead).

## Field-map changes required (`Voyageur/field_maps/ancestry_census.yaml`)

Add these `participant_fields` entries (new headers this session's live investigation surfaced, not yet in the file):

```yaml
  "Birth Month": type_specific_fields.birth_month
  "Marital Status": type_specific_fields.marital_status
```

Add these `participant_facts` entries (target: `Miscellaneous` fact-type bucket, matching the existing pattern for "Maiden Name"/"Quality"):

```yaml
  "Months Not Employed": Miscellaneous
  "Home Ownership": Miscellaneous
  "Home Mortgaged": Miscellaneous
  "Native Tongue": Miscellaneous
  "Speaks English": Miscellaneous
  "Employment Field": Miscellaneous
```

`Industry` needs NO change — confirmed already present in the current file (`"Industry": Occupation` in `participant_facts`). `Sick`/`Blind`/`Disability Condition` reuse the existing `Disability Condition` → `Miscellaneous` mapping already present. `Deaf Dumb Blind Insane`/`Idiotic Pauper Convict`/`Father Foreign Born`/`Mother Foreign Born`/`Cannot Read, Write`/`Naturalization Status`/`Year of Naturalization`/`Immigration Year` reuse existing entries already present in the file today. No changes needed for those — they're listed in the field-set tables above only to document which API `fieldName` feeds them.

## Scope decisions

- **Fallback pair, not replacement** — explicit user call, opposite of the FS orchestration-API decision. DOM-table scraping stays fully intact and unmodified as the fallback path. A future cleanup task (not this plan) removes whichever path proves unnecessary once the API path is confirmed stable in production use.
- **`index-panel-data` only** — `collections/collection-text` (the clean citation-JSON endpoint) is a separate, natural next target, explicitly deferred to issue #24, not built here.
- **`correctedValue` ignored** — always read `value`. Deciding whether user corrections should override is out of scope.
- **New fields get real mappings now** (not left unmapped) — this session already has complete, real field data for 4 census years, so field-map coverage is added as part of this plan rather than deferred to "extend later." The user's "leave as is, extend later" guidance applies to a *future, not-yet-seen* `fieldName` (a census year not yet researched), not to the fields already catalogued above.
- **Imperfect target reuse is accepted, not blocking** — several new fields (Father/Mother Birthplace → the existing "foreign born" boolean-ish columns; Can Read/Can Write → the existing combined "Cannot Read, Write" column) reuse existing downstream columns even though the semantic fit isn't perfect. Building bespoke new fact-types/GEDCOM rendering for each is real work, correctly scoped to issue #24, not this plan — the priority here is that no data is silently dropped, not that every field gets ideal GEDCOM rendering immediately.
- **State census records, Canadian records, and remaining census years (1790-1840, 1900, 1910, 1930-1950)** — explicitly out of scope, tracked under issue #24.

## Not yet verified — should be tested during implementation, not blocking

1. **Household grouping via `householdId` in practice** — confirmed the field exists and is populated correctly across all 4 tested years, but `census_schema.py`'s `_household_key()` preferring it over column-based inference hasn't been live-verified end-to-end through a full gather → GEDCOM yet.
2. **Waiter-map key collisions** — `` `${dbId}:${imageId}` `` as the wait key assumes at most one in-flight `index-panel-data` request per image at a time during a gather; not stress-tested against rapid page-to-page navigation.
3. **`pid` uniqueness/stability** across a re-gather of the same image (should be stable — it's Ancestry's own person ID — but not independently re-confirmed on a second fetch of the same image in this session).

## Next steps

Ready for an explicit, code-complete implementation plan (`writing-plans` skill) — every field mapping, every new function signature, and every real test fixture value needed is already captured above.
