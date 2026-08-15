# Census Pipeline Symmetry + Marriage Details Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close five real, confirmed gaps found while live-verifying the 2026-08-15 Ancestry Index-Panel-Data plans (original + field-coverage extension) and reviewing the adjacent Complex Field Integration plan: (1) FamilySearch drops several fields its own API already extracts, unlike Ancestry; (2) a chunk of the newly-built dynamic-occupation feature is unreachable dead code because nothing ever produces the raw column names it looks for; (3) Ancestry gathers mislabel every Canadian record's country/collection title as American; (4) Commissioner's `Census.pmt` schema silently rejects several `type_specific_fields` keys `ancestry_census.yaml` has been mapping into since the original plan's Task 4, live-confirmed via a Pydantic `extra_forbidden` error; (5) a new "Marriage Details" custom fact type (first-married date, number of marriages, widowed status), following the precedent of the existing "Race"/"Scrip" custom facts.

**Why these five together:** all were found in the same review/live-verification pass and touch the same handful of files (`Voyageur.js`, both `field_maps/*.yaml`, `Census.pmt`, `Census.py`, `FactTypes.json`) — sequencing them separately would mean repeatedly re-deriving the same context. Task order matters: Task 4 (Commissioner schema) must land before Task 5 (Marriage Details) can be validated end-to-end, since Marriage Details' `facts[]` entries need `FACT_TYPE_TO_COLUMN`/`Census.pmt` wiring that Task 4 establishes the pattern for.

**Not in this plan:** the FS "Information tab" elimination (tracked as [issue #25](https://github.com/alerum68/Scriptorium/issues/25)); the general FS/Ancestry mapping-review session mentioned in prior plans' self-review notes (numbered-duplicate fields, income/earnings, tribe/clan, etc. — still deliberately unmapped passthrough, not this plan's job to resolve).

## Global Constraints

- **Confirm before mapping — no invented fieldNames.** Every raw fieldName/column header referenced below is either already confirmed live (cited from `docs/superpowers/specs/2026-08-15-census-field-coverage-research.md`) or explicitly marked "needs live confirmation" in its own task. Do not extend a task's field list without one or the other.
- **`participant_fields` is a flat overwrite, `participant_facts`/`facts[]` is a combine-safe list.** (`census_schema.py`'s `_normalize_participant`.) Route anything that could co-occur with another same-target field through `participant_facts`, never `participant_fields`, unless the two are provably mutually exclusive on every real collection (document why, per the existing `SelfResidence1HomeMortgaged` comment's own precedent).
- **`node --check Voyageur/Voyageur.js`** must pass after every JS change, before every commit.
- **`node --test Voyageur/tests/js/`** (from `Voyageur/`) must show only passing tests after every JS test change.
- **`pytest`** (from `Voyageur/`, `Archivist/`, and `Commissioner/` respectively) must show only passing tests after every Python change.
- **Live verification is not subagent-delegable** for the same reason established in every prior plan this session: it requires the user's own logged-in browser, and Chrome automation inflates `Voyageur.js`'s timers ~20x, giving a false read.

---

### Task 1: Wire up the dead dynamic-occupation-enrichment fields (Ancestry)

**Problem, confirmed live:** `Archivist/Census.py`'s `get_occupation_value()` (Complex Field Integration plan, commit `2b14665`) reads `row.get('Usual Occupation')`, `'Employer'`, `'Class of Worker'`, `'Hours Worked'`, `'Weeks Worked'`, `'Out Of Work'`, `'Seeking Work')` — but **none of these raw header strings appear anywhere in `field_maps/ancestry_census.yaml`, `field_maps/familysearch_census.yaml`, or `ANCESTRY_INDEX_FIELD_TO_COLUMN`** (confirmed via grep, zero matches). The function's own unit test constructs a `pd.Series` directly with those exact keys, bypassing the gather/field-map pipeline entirely — it passes, but the feature can never fire on real gathered data. This is not incorrect, just currently inert.

**Real confirmed fieldName vocabulary** (from the research spec, cross-year US+Canada pass):
`SelfResidenceEmployer`/`SelfEmploymentEmployer`, `SelfResidenceUsualOccupation`, `SelfResidenceUsualClassOfWorker`/`SelfResidenceClassofWorker`, `SelfResidenceHoursWorked`, `SelfResidenceWeeksWorked`, `SelfResidenceOutOfWork`, `SelfResidenceSeekingWork`, `SelfResidenceMonthsUnEmployedPastYear` (already mapped to `Months Not Employed` — do not re-map).

**Files:** `Voyageur/Voyageur.js`, `Voyageur/field_maps/ancestry_census.yaml`, `Voyageur/tests/js/test_ancestry_index_panel_parser.mjs`.

- [ ] **Step 1:** Add `ANCESTRY_INDEX_FIELD_TO_COLUMN` entries mapping each confirmed fieldName above to a new column header (`'Employer'`, `'Usual Occupation'`, `'Class of Worker'`, `'Hours Worked'`, `'Weeks Worked'`, `'Out Of Work'`, `'Seeking Work'`) — matching exactly the header text `get_occupation_value()` already expects.
- [ ] **Step 2:** Add corresponding `participant_fields` entries in `ancestry_census.yaml` targeting `type_specific_fields.<snake_case_name>` for each (these are per-participant raw text `get_occupation_value()` reads directly off the DataFrame — they should NOT be flattened into a single `facts[]` entry, since `build_census_dataframe_from_unified` needs each as its own real DataFrame column by that exact name; confirm the DataFrame-column-naming path in `build_census_dataframe_from_unified` before assuming `type_specific_fields.*` values surface as DataFrame columns with the *header* name — if they don't, these seven need a small dedicated block in `build_census_dataframe_from_unified` instead, mirroring how `Married within Year`/`Street` are special-cased there today).
- [ ] **Step 3:** Add JS tests proving each fieldName resolves to its target column (mirror the existing `test_ancestry_index_panel_parser.mjs` style).
- [ ] **Step 4:** Add a Python test in `test_census_ingestion.py` proving a real end-to-end row (built via `census_schema.normalize_and_validate_census`, not a hand-built `pd.Series`) reaches `get_occupation_value()` with these fields populated and produces the expected sentence — this is the test the original plan should have had; it's what would have caught this gap.
- [ ] **Step 5:** Live-verify: run a gather against a US year confirmed to carry `SelfResidenceEmployer`/`SelfResidenceUsualOccupation` (check the research spec's per-year field lists for the best candidate — likely 1930/1940), confirm `1 OCCU` output actually includes employer/industry text and the `2 NOTE` includes Class of Worker/Hours Worked.
- [ ] **Step 6:** Run full JS + Python suites, commit.

---

### Task 2: FamilySearch field-coverage symmetry

**Problem, confirmed by reading the code:** `fsColumnsFromCanonicalFields()` in `Voyageur.js` extracts `maritalStatus`/`occupation`/`race`/`birthplace`/`fatherBirthplace`/`motherBirthplace` into `canonicalFields` (both `fsCanonicalFieldsFromApiPerson` and `fsCanonicalFieldsFromImageIndexPerson` produce them) — then discards all but `Given Name`/`Surname`/`Gender`/`Age`/`Family Number`/`Relationship to Head` before they ever become a `columns` entry, with a comment citing "no slots yet" in the downstream schema. That reason is no longer true: `census_schema.py`/`ancestry_census.yaml` now have those slots (Task 4 of the original Ancestry plan, this session). Separately, `field_maps/familysearch_census.yaml` is still explicitly marked `DRAFT status... not confirmed against a live FamilySearch census gather`, and is missing most of what `ancestry_census.yaml` now has (no Marital Status, Birth Month, Street, Property, Disability, Religion, Nationality, Home Ownership, etc.).

**Files:** `Voyageur/Voyageur.js`, `Voyageur/field_maps/familysearch_census.yaml`, `Voyageur/tests/js/test_fs_api_parser.mjs`, `Voyageur/tests/js/test_fs_image_index_parser.mjs`.

- [ ] **Step 1:** Extend `fsColumnsFromCanonicalFields()` to forward `maritalStatus` → `'Marital Status'`, `occupation` → `'Occupation'`, `race` → `'Race'`, `birthplace` → `'Birth Place'`, `fatherBirthplace` → `'Father Foreign Born'`, `motherBirthplace` → `'Mother Foreign Born'` (matching `ancestry_census.yaml`'s existing target headers exactly, so no new YAML targets are needed on the Python side — only new *keys*). Empty-string values must still be omitted, matching the existing convention.
- [ ] **Step 2:** Update the existing `fsColumnsFromCanonicalFields`/`fsBuildRowsFromApiResponse`/`fsBuildRowsFromImageIndexResponse` unit tests (22+ tests across two files) to assert these new columns appear when the fixture data has them — this task explicitly touches "already-shipped, already-reviewed code" (same caution the original FS Image-Index plan's Task 1 called out), so the regression contract is the existing tests passing **plus** new assertions, not a rewrite.
- [ ] **Step 3:** Bring `field_maps/familysearch_census.yaml` out of DRAFT status: add every `ancestry_census.yaml` `participant_fields`/`participant_facts` entry that has a plausible FS equivalent (Marital Status, Birth Month, Street/Street Address/Address, Married within Year, Highest Grade of School Completed, Immigration Year, Naturalization, Veteran Status, Real Estate/Personal Estate Value, Cannot Read/Write, Disability Condition, Religion, Nationality — Religion/Nationality already exist as real `FactTypes.json` entries per Task 2 of the field-coverage-extension plan). Do not guess at FS-specific header spellings that were never confirmed — reuse the exact same header strings `fsColumnsFromCanonicalFields`/`fsBuildRowsFromImageIndexResponse` already produce (check both files for the literal strings each function emits before writing the YAML key).
- [ ] **Step 4:** Live-verify against a real FamilySearch census gather (any US or Canadian year already used this session is fine — the 1860 Dakota Territory record is FS's own long-standing default test record): confirm Marital Status/Occupation/Race/Birthplace now appear in the normalized JSON's participant fields, and that Religion/Nationality land as real facts when the collection carries them.
- [ ] **Step 5:** Run full JS + Python suites, commit.

---

### Task 3: Fix Canadian country/collection-title mislabeling (Ancestry)

**Problem, confirmed live** (2026-08-15 Canadian live verification, dbId `1578`, Ontario): every Ancestry gather's JSON carries `"country": "USA"` and a `collection_title` of `"<year> US Federal Census - <location>"` regardless of the record's actual country. Three independent hardcoded strings, not one:

1. `Voyageur.js` line ~1163: `let country = "USA", ...` — never reassigned for Ancestry gathers.
2. `A.py`'s `normalize_ancestry_census_gather()`: `collection_title = f"{census_year_raw} US Federal Census - {raw_gather.get('location', '')}"` — hardcoded regardless of the page's own `country` field.
3. `Archivist/Census.py`: `COLLECTION_NAME or f'{CENSUS_YEAR} United States Federal Census'` (three call sites: citation weblink name, source title, and — most consequentially — the on-disk image folder name via `f"{CENSUS_YEAR} US Federal Census"` in the nested image-directory path).

**Files:** `Voyageur/Voyageur.js`, `Voyageur/A.py`, `Archivist/Census.py`, corresponding test files.

- [ ] **Step 1:** In `Voyageur.js`, add a small pure function `ancestryCountryFromState(state)` returning `'Canada'` when `state` matches a Canadian province/territory name (mirror `Gazetteer.CA_PROVINCE_NAMES` from `Gazetteer/Gazetteer.py`, plus historical names already added to `Archivist/Census.py`'s `CANADIAN_PROVINCES_AND_TERRITORIES` this session — keep the two lists in sync, or better, have one be the source of truth others cite). Call it after `state = pathArr[0] || ""` is set, replacing the hardcoded `country = "USA"` default. Add a unit test.
- [ ] **Step 2:** In `A.py`'s `normalize_ancestry_census_gather()`, read the actual country from `raw_gather["pages"][0]["country"]` (falling back to `"USA"` only if genuinely absent) and build `collection_title` accordingly — `"US Federal Census"` for USA, `"Census of Canada"` for Canada (no other country currently gathered). Add/update the existing unit test for this function.
- [ ] **Step 3:** In `Archivist/Census.py`, make the three `COLLECTION_NAME or f'{CENSUS_YEAR} United States Federal Census'`-style fallbacks country-aware the same way — this needs a `COUNTRY` global/row-level signal analogous to `CENSUS_YEAR`'s own; check how `CENSUS_YEAR` itself is threaded through `run_census_flavor`/module globals and mirror that pattern for country, rather than inventing a new mechanism. **This step touches the on-disk image folder naming (`nested_dir`) — verify with the user before changing it**, since existing users' `Media/` folder structure may already have Canadian records filed under a `"... US Federal Census ..."` path from before this fix; a silent rename could orphan existing image files from future re-gathers pointing at the new Canada-labeled path. Confirm the intended behavior (rename-on-fix vs. only new-gather-uses-new-path) before implementing.
- [ ] **Step 4:** Live-verify: re-run the same Canadian test gather (dbId `1578`) and confirm `country: "Canada"`/`"Census of Canada"` throughout the JSON, citation, and GEDCOM output; confirm a fresh US gather (e.g. the 1860 Dakota Territory record) is completely unaffected (still `"USA"`/`"US Federal Census"`).
- [ ] **Step 5:** Run full JS + Python suites, commit.

---

### Task 4: Extend Commissioner's `Census.pmt` schema (closes the live-confirmed validation gap)

**Problem, confirmed live** (same Canadian gather): `[WARN] Commissioner validation failed for '1871 US Federal Census - Ontario...': 1 validation error for CensusParticipantExtra / marital_status / Extra inputs are not permitted`. `Commissioner/record_registry.py` dynamically builds a `extra="forbid"` Pydantic model per document type from `Paleographer/prompts/<DocumentType>.pmt`'s YAML front-matter `extra_fields.participant`/`.record` lists. Reading `Census.pmt`'s current list directly confirms it's missing several keys `ancestry_census.yaml`/`census_schema.py` have been writing into `type_specific_fields` since the original plan's Task 4 (this session) — and one pre-existing gap that predates this session entirely:

Currently declared (`Census.pmt`'s `extra_fields.participant`): `line_number, pid, extracted_url, fsftid, person_ark, familysearch_url, unmapped`.

**Missing** (confirmed by cross-referencing every `type_specific_fields.*` target in `census_schema.py`'s passthrough list and both YAML field-maps against this list): `street` (string), `married_within_year` (string), `birth_month` (string), `marital_status` (string), `alternate_birth_places` (list — this one is unrelated to this session's work, a pre-existing gap in the original `alternate_birth_places` passthrough feature).

**Files:** `Paleographer/prompts/Census.pmt`, `Commissioner/tests/test_record_registry.py` (or wherever `Census` document-type validation is tested — check for the existing test file first).

- [ ] **Step 1:** Add the five missing entries to `Census.pmt`'s `extra_fields.participant` list, matching the existing declaration format (`{name: <key>, type: <string|list>}`).
- [ ] **Step 2:** Also do the equivalent audit against `Task 1`'s and `Task 2`'s new `type_specific_fields` keys once those are implemented (this task should run **after** Tasks 1-2 land, or be revisited once they do, so the declared list is complete in one pass rather than needing a second commit).
- [ ] **Step 3:** Add a regression test proving a participant with every one of these fields populated passes `validate_participant_extra_fields("Census", ...)` without raising.
- [ ] **Step 4:** Re-run the exact Canadian live-gather-and-GEDCOM-generation sequence from this session and confirm the `[WARN] Commissioner validation failed` line no longer appears.
- [ ] **Step 5:** Run full Python suite (Voyageur + Archivist + Commissioner), commit.

---

### Task 5: New "Marriage Details" custom fact type

**User's requirement:** a new personal fact recording marriage history detail (when first married, how many marriages, widowed status), added the same way "Race" (a custom `FactTypes.json` entry, `code: "10001"`, `gedcom_tag: "EVEN"`) was added — not a new document type like "Scrip" (which is a whole separate record type, not applicable here; this is a per-participant fact within the existing Census — and potentially Parish — pipelines).

**Real confirmed fieldName vocabulary** (research spec, Canadian + US years): `SelfMarriageAge`, `SelfMarriageMonth`, `SelfMarriageYear`, `SelfResidenceCurrentMarriageNumber`, `SelfResidenceWidowed`, `SelfResidenceWomanMarried`, `SelfResidenceYearsMarried`. **Keep these separate from the existing `marital_status`/`married_within_year` fields** (`SelfMaritalStatus`/`SelfResidenceMaritalStatus`/`SelfResidenceMarriedWithinYear`) — those already have their own home (`type_specific_fields.marital_status`/`.married_within_year`) and represent a different concept (current status vs. marriage history detail); do not conflate them. This also directly resolves the "Widowed" column confirmed live and unmapped on the Ontario 1871 test gather (108/316 participants) and validates the earlier decision (this session) not to guess `Widowed1` onto `marital_status` — it belongs here instead.

**Design, following the "Race" precedent exactly:**
- `FactTypes.json`'s `person` bucket gets a new entry `"Marriage Details": {"gedcom_tag": "EVEN", "use_value": true, "use_date": true, "use_place": false, "custom": true, "code": "10005"}` (next available custom code after Race=10001/dit Name=10002/Scrip=10004 — 10003 is an existing unexplained gap; do not reuse it without confirming why it's absent).
- Because this is a **composite, multi-value** fact (unlike Race's single value), it does not fit the single-column `FACT_TYPE_TO_COLUMN` → flat-DataFrame-cell mechanism (multiple raw fields mapping to one target column would silently overwrite each other in `build_census_dataframe_from_unified`'s `row[col] = ...` assignment — the same class of bug already found and fixed this session for `Widowed1`). Instead, follow `get_occupation_value()`'s own established `(value, notes)` tuple pattern:
  - New `get_marriage_details_value(row) -> Tuple[str, str]` in `Archivist/Census.py`, reading dedicated raw columns (`Widowed`, `Number of Marriages`, `Age at Marriage`, `Marriage Month`, `Marriage Year`, `Years Married`, `Woman Married within Year`) directly off the DataFrame — mirroring `get_occupation_value`'s exact structure (primary-value selection, then a `notes_parts`/`"; ".join(...)` block for the rest). Primary `value` = the widowed/marital status signal if present, else the most specific single marriage-history datum available; everything else goes in `notes`.
  - A new dedicated GEDCOM emission block in `build_gedcom_from_census`, modeled byte-for-byte on the existing Race block: `ged.extend([f"1 FACT {value}", "2 TYPE Marriage Details", f"2 DATE {CENSUS_YEAR}"] + ([f"2 NOTE {notes}"] if notes else []) + ["2 _PROOF proven"] + cit)`.
- New `ancestry_census.yaml` `participant_fields` entries mapping each confirmed raw header to its own `type_specific_fields.*` key (matching Task 1's pattern of dedicated per-field DataFrame columns, not a collapsed `facts[]` entry — same reasoning: this data needs to reach a dedicated Python function by exact column name, not be pre-flattened).
- New `ANCESTRY_INDEX_FIELD_TO_COLUMN` entries mapping the confirmed fieldNames above to those same header strings.
- `Census.pmt`'s `extra_fields.participant` gets the new keys declared (same mechanism as Task 4 — do this as part of this task's own commit, not a separate one, since they're introduced together).
- **FamilySearch side:** research (do not guess) whether FS's orchestration-API/Image-Index responses expose equivalent marriage-history fields before adding anything to `familysearch_census.yaml` for this — if Task 2's live verification doesn't surface them, leave FS-side Marriage Details for a future pass rather than inventing field names.

**Files:** `Commissioner/FactTypes.json`, `Paleographer/prompts/Census.pmt`, `Voyageur/Voyageur.js`, `Voyageur/field_maps/ancestry_census.yaml`, `Archivist/Census.py`, plus test files for all of the above.

- [ ] **Step 1:** Add the `FactTypes.json` entry, confirm `code: "10005"` doesn't collide with any other bucket (check `family` too), add/extend a Commissioner test asserting the entry exists and is well-formed (mirror however Race/Religion/Nationality are already covered, if at all — check first).
- [ ] **Step 2:** Add the `ANCESTRY_INDEX_FIELD_TO_COLUMN` entries + `ancestry_census.yaml` `participant_fields` entries for the 7 confirmed fieldNames, with JS + Python tests using real values from the research spec (Donald MacDonald/other real Canadian test records already used this session are good fixture sources if their raw field values were captured).
- [ ] **Step 3:** Implement `get_marriage_details_value()` in `Census.py` with a unit test suite mirroring `get_occupation_value()`'s own test structure (employed/unemployed-analog cases: widowed-with-detail, married-with-detail, no-data-at-all).
- [ ] **Step 4:** Wire the new function into `build_gedcom_from_census`'s per-participant loop (same location as the Race/Occupation/Nationality blocks), add the `Census.pmt` extra_fields declarations from Task 4's Step 2 follow-up.
- [ ] **Step 5:** Live-verify: re-gather the Ontario 1871 test record (dbId `1578`) — which already has real live "Widowed" data confirmed present on 108/316 participants — and confirm `1 FACT <value> / 2 TYPE Marriage Details` now appears in the generated GEDCOM for those participants, with correct values, and that the "Widowed" unmapped-column review flag is gone.
- [ ] **Step 6:** Run full JS + Python (Voyageur + Archivist + Commissioner) suites, commit.

---

## Self-Review Notes (for whoever executes this plan)

- **Task ordering matters.** Task 4 should run after Tasks 1-2 (so its `Census.pmt` audit is complete in one pass) but before Task 5 (which depends on the same mechanism). Tasks 1-3 are independent of each other and could run in parallel if using subagent-driven-development.
- **Every "confirmed live" field-name claim in this plan is sourced from `docs/superpowers/specs/2026-08-15-census-field-coverage-research.md`**, the same research pass the original and field-coverage-extension Ancestry plans drew from — not re-derived or guessed for this plan.
- **Task 3 Step 3 has a real backward-compatibility question** (existing Canadian images filed under a "US Federal Census" folder path) that needs a decision before implementation, not just during — flagged explicitly rather than silently deferred to whoever writes the code.
- **Task 5's FS-side deferral is deliberate**, not an oversight — this project's own established discipline (repeated across every plan this session) is "confirm live before mapping, never invent a fieldName," and no FS marriage-history fieldName has been confirmed yet.
