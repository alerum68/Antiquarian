# Archivist Structural Split — Design

> **Post-implementation note:** `ScripProfile.py` (named throughout this doc) was
> subsequently renamed to `Scrip.py` for naming consistency with `Census.py`/`General.py`.
> The `ScripProfile` class name is unchanged. References below to the filename are
> historical — read `ScripProfile.py` as `Scrip.py`.

## Goal

Split `Archivist/Archivist.py` (3,691 lines, GEDCOM-compilation logic for
two flavors of gathered data stitched into one file) into a thin dispatcher
plus real sibling modules — mirroring the pattern established for
`Voyageur.py` and `Paleographer.py`. Unlike those two, Archivist's
record-type-specific branching (`is_scrip`) doesn't select a whole module up
front; it's interleaved inside shared GEDCOM-building functions at ~10
points. A plain module split would only relocate the `if is_scrip` checks,
not fix them, so this design also replaces the boolean-flag branching with a
small `Profile` strategy-pattern mechanism. No behavior change beyond that
mechanism swap — every branch keeps doing exactly what it does today, just
reached through a profile object instead of a global-config flag check.

This is the sub-project explicitly deferred by
`docs/superpowers/specs/2026-08-06-paleographer-structural-split-design.md:158-163`.

## Background

`Archivist.py` reads a single JSON file (from Voyageur and/or Paleographer)
and emits GEDCOM 5.5.1 in RM and FTM flavors. It handles two structurally
different input shapes:

- **Census** — a flat list of people per scanned page, needing
  household-grouping (no explicit family relationships in the source data).
- **General** — explicit per-participant roles, no grouping needed. Covers
  Parish (church-register) records today, and Scrip (Métis/Half-breed
  scrip commission) records, with a third category (any future non-census
  record type) implicitly supported by the same code path.

These two flavors already share zero logic below the entry point:
`build_gedcom_from_census`/`run_census_flavor` and
`build_gedcom_from_general`/`run_general_flavor` never call into each
other's helpers (confirmed by grep — no census-only helper is referenced
from line 1999 onward, and `GENERAL_CONFIG` is never referenced before it).
A handful of genuinely generic helpers (`clean_val`, `cap_case`,
`format_gedcom_date`, `weblink_lines`, `resolve_source_id`,
`get_source_templates`/`load_source_template_lines`/
`_rmst_element_to_gedcom`, `split_full_name`, ...) are used by both.

Within the General flavor, Scrip gets bespoke treatment via
`is_scrip = GENERAL_CONFIG.get('omit_source_id_prefix')`, checked at 10
call sites: `generate_uid`, `build_individual` (custom "Scrip" fact vs.
generic EVEN, date fallback), `_build_citation_block` (citation title/page
format, proof_status override, source-ID resolution — the largest
divergence), `get_volume_sources` (skips the TID 10009 Parish citation
template), and `build_gedcom_from_general` (media caption format, extra
source-template assembly). This is not a set of independent toggles — it's
two different compilation strategies sharing one call graph.

## Architecture

Same top-level shape as the prior two splits: a thin `Archivist.py`
dispatcher, sibling modules for each concern, a shared-helpers module the
siblings import (mirroring `Voyageur/_gather_helpers.py` and
`Paleographer/engine.py`). The one structural addition is the `Profile`
mechanism, needed because — unlike Voyageur's A/FS/LAC or Paleographer's
Extract/ScripTools, which each run as a whole module chosen once at the top
— Scrip and Parish records flow through the *same* shared functions and
diverge mid-function. A single top-level module swap can't reach into the
middle of `_build_citation_block`; the dispatcher instead resolves *which
profile object* to hand to `General.py`, and every interior branch point
calls the profile instead of checking a flag.

- **`Archivist/Utils.py`** (new) — every helper confirmed used by both
  flavors, plus the shared module-level `.env` config: `get_env_int`,
  `safe_path`, `resolve_source_id` (+ the source-ID registry and
  `PRECODED_SOURCE_IDS`), `clean_val`, `_titlecase_callback`, `cap_case`,
  `clean_place`, `format_gedcom_date`, `get_proof_status`,
  `estimate_birth_from_age`, `wrap_text`, `dedent_citation_lines`,
  `weblink_lines`, `resolve_gedcom_output_targets`,
  `resolve_gedcom_output_path`, `get_event_gedcom_tag`, `is_family_event`
  (+ `FACT_TYPES` loading), `get_source_templates`,
  `load_source_template_lines`, `_rmst_element_to_gedcom`,
  `split_full_name`, and the `CellValue` type alias. Config: `ORG_NAME`,
  `RESEARCHER`, `SOFTWARE_NAME`/`SOFTWARE_VERS`, `COPYRIGHT_START`,
  `GEDCOM_NOTE`, `GEDCOM_CONC`, `REVIEW_COLOR`, `SUBM_ADDRESS`,
  `MGS_GROUP_URL`, `ANCESTRY_GROUP_URL`, `ROOT_SOURCE_ID`, `CALL_NUMBER`,
  `REPOSITORY`/`REPOSITORY_LOC`, `COLLECTION_URL`/`COLLECTION_NAME`,
  `PUBLISHER`, `PUB_LOC`, `PROGRAM_DIR`, `RM_DIR`, `FTM_DIR`, `JSON_DIR`,
  `GEDCOM_OUTPUT_PATH`/`GEDCOM_OUTPUT_NAME`/`GEDCOM_OUTPUT_MODE`,
  `IMAGE_DIR`, `IMAGE_EXTENSION`, `FORM_TYPE`, `JSON_FILE`, `CURRENT_DATE`,
  `APID_DB`, `ANCESTRY_IMAGE_BASE_ID`/`BASE_ID`.
- **`Archivist/Census.py`** (new) — every census-only symbol, moved
  verbatim: `HouseholdUnit`, `FlagRecord`, `get_gender`, `get_census_era`,
  `get_census_template_id`, `CENSUS_TEMPLATES`, the household-parsing chain
  (`get_age`, `spouse_evaluation`, `child_evaluation`, `find_parent`,
  `parse_household`, `normalize_relationship`, `is_relationship_column`,
  `find_relationship_column`, `resolve_cross_family_links`,
  `append_unit_if_not_empty`, `parse_household_relational`), the census
  GEDCOM builders (`get_row_val`, `build_census_citation`,
  `get_census_notes`, `get_occupation_value`, `get_education_value`,
  `get_birth_date`, `build_residence_event`,
  `build_dynamic_events_and_notes`, `build_census_task`,
  `get_census_sources`, `get_location_string`, `parse_alternate_entries`,
  `build_alternate_name_lines`, `build_alternate_birth_lines`,
  `build_gedcom_from_census`, `get_json_fallback`, `load_census_dataframe`,
  `build_census_dataframe_from_unified`, `run_census_flavor`), and
  census-only config (`CENSUS_YEAR`, `CENSUS_ERA`, `CENSUS_SOURCE_ID`,
  `STATE`/`COUNTY`/`TOWNSHIP`/`ENUMERATION_DISTRICT`/`FILM_NUMBER`/
  `ROLL_NUMBER`, `MIN_MARRIAGE_AGE`, `MAX_SPOUSE_AGE_GAP`,
  `HUSBAND_CHILD_AGE_GAP`, `WIFE_CHILD_AGE_GAP`, `REVIEW_THRESHOLD`,
  `ANCESTRY_START_RECORD_ID`).
- **`Archivist/General.py`** (new) — shared general-flavor orchestration
  plus the `Profile` protocol and `GeneralProfile` (today's non-Scrip/
  default behavior, i.e. today's `else` branches): `GENERAL_CONFIG`,
  `extract_volume`, `get_dynamic_source_id`, `get_by_semantic`,
  `get_all_by_semantic`, `get_role_name`, `resolve_family_links`,
  `assign_spouses_by_sex`, `evaluate_task_priority`, `generate_uid`,
  `generate_media_uid`, `generate_media_uid_for_path`,
  `generate_media_uid_for_lac_asset`, `generate_fam_uid`,
  `_build_citation_block`, `build_general_citation`,
  `build_custom_fact_lines`, `build_witness_links`, `build_individual`,
  `build_family`, `get_source_root`, `get_volume_sources`,
  `build_gedcom_from_general`, `apply_record_type_field_remap`,
  `apply_extracted_parish_name`, `apply_resolved_source_id`,
  `run_general_flavor`. Every site that currently reads
  `GENERAL_CONFIG.get('omit_source_id_prefix')` calls the active
  `Profile` instead (see below). `run_general_flavor` gains a `profile`
  parameter.
- **`Archivist/ScripProfile.py`** (new) — `ScripProfile` (implements the
  `Profile` protocol structurally — no import of `General.py` needed,
  avoiding a circular import) plus every Scrip-only helper, moved verbatim:
  `_scrip_record_year`, `select_scrip_template_id`,
  `resolve_scrip_template_id`, `_scrip_template_field_value`,
  `get_scrip_citation_fields`, `get_scrip_template_sources`.
- **`Archivist/Archivist.py`** (rewritten, ~40-50 lines) — thin dispatcher.
  Keeps `resolve_json_input` and the input-loading/`is_census` detection
  logic from today's `__main__` block. For census, calls
  `Census.run_census_flavor(data)` unchanged. For general, resolves
  `record_type_name` against `PROFILE_REGISTRY = {"Scrip": ScripProfile}`
  (falling back to `GeneralProfile`), instantiates it, and calls
  `General.run_general_flavor(data, target_software, profile=profile)`.
  The registry lives here, not in `General.py`, specifically so `General.py`
  never has to import `ScripProfile.py` (which would cycle back if
  `ScripProfile.py` needed anything from `General.py`).

### The `Profile` protocol

A `typing.Protocol` (structural typing — no inheritance required, which is
what lets `ScripProfile.py` avoid importing `General.py`) with one method or
property per diverging behavior, resolved by grepping each of the 10
existing `is_scrip` call sites for what actually differs:

- `is_alternate_scheme: bool` — replaces the bare flag for simple gates:
  which UID scheme applies, whether the scrip-year date fallback applies,
  whether the custom-fact-vs-EVEN choice applies, whether proof_status gets
  forced to `"proven"`, whether the TID 10009 template gets skipped.
- `generate_participant_uid(identity, role, occ) -> Optional[str]` — Scrip
  returns its identity-based short form when `identity` is present;
  `GeneralProfile` returns `None`, signaling "fall through to the existing
  hash-based scheme" (that fallback logic is unchanged and stays inline in
  `General.generate_uid`, not duplicated into either profile).
- `build_citation_title(rec, part, ...) -> str`,
  `build_citation_page(rec, ...) -> str`,
  `resolve_citation_source_id(rec, vol) -> str`,
  `citation_extra_fields(rec, part, vol, target_software) -> List[str]` —
  the diverging blocks inside `_build_citation_block` (title format, page
  format, source-ID/template resolution, RM `_TMPLT`/`FIELD` detail rows).
- `primary_event_override(rec, part) -> Optional[...]` — the custom
  "Scrip" fact vs. generic EVEN choice in `build_individual`.
- `media_caption(sheet, vol, meta) -> str` — surname/claim vs. Vol/Page
  caption in `build_gedcom_from_general`.
- `extra_source_records(json_data, target_software) -> list` — the
  `get_scrip_template_sources`/TID-10009-skip-and-substitute logic,
  currently split across `get_volume_sources` and
  `build_gedcom_from_general`.

Exact method signatures are an implementation detail for the plan, not
fixed by this design — the list above is this design's best read of the
current branches, not a guarantee. The implementer must grep each
`is_scrip` site's actual surrounding code before finalizing signatures; if
a branch turns out to need more than the method it was assigned above, the
method signature grows to fit it rather than a new global flag being
reintroduced.

## Scope

### Split (structural)

- Create `Utils.py`, `Census.py` moving the listed symbols verbatim.
- Create `General.py` with the `Profile` protocol, `GeneralProfile`
  (today's default/`else` behavior), and the shared orchestration functions
  listed above, each converted from `GENERAL_CONFIG.get('omit_source_id_prefix')`
  checks to calls on an active profile.
- Create `ScripProfile.py` with `ScripProfile` (today's `if is_scrip`
  behavior) and the Scrip-only helpers listed above.
- Rewrite `Archivist.py` as the thin dispatcher described above, including
  the `PROFILE_REGISTRY`.
- Delete the now-fully-relocated content from the old `Archivist.py`.

### Explicitly out of scope

- Any change to what GEDCOM output looks like for existing Scrip or Parish
  data — this is a structural refactor, not a formatting change. The
  golden-file regression test (below) exists specifically to catch
  accidental drift.
- Generalizing `ScripProfile` beyond Scrip, or building a third profile —
  no third record type exists yet to design against. `GeneralProfile`
  remains the default for anything that isn't `"Scrip"`, which already
  covers a hypothetical future type with zero code changes (same as today).
- Making the profile mechanism declarative/`.pmt`-driven. Citation-string
  composition and template-priority resolution are procedural logic, not
  data; forcing them into YAML would either invent a templating language or
  just wrap this design's Python in an extra indirection layer. Considered
  and rejected during brainstorming (see conversation) in favor of the
  Python strategy pattern above.
- Any change to `Voyageur.py`/`Paleographer.py` or their sibling modules.

## Testing

- Full `pytest` suite stays green after every task.
- `Archivist/tests/test_archivist.py` (1,078 lines) and
  `test_census_ingestion.py` currently import `Archivist` directly and must
  be repointed to `Utils`/`Census`/`General`/`ScripProfile` depending on
  which functions each test exercises — same mechanical pattern used for
  the Paleographer test repoint.
- New golden-file regression test, added *before* the `Profile` extraction
  step: run one representative Scrip fixture and one representative Parish
  fixture through `build_gedcom_from_general` on the pre-refactor code,
  capture the GEDCOM output (both RM and FTM) as golden files. After the
  `Profile` extraction, re-run the same fixtures through the new code path
  and diff byte-for-byte against the golden files. This is the safety net
  for the highest-risk step in this design — 10 scattered boolean checks
  becoming profile method calls is exactly the kind of change where a
  transcription slip silently changes output instead of failing loudly.
- New unit tests for `GeneralProfile` and `ScripProfile` in isolation,
  covering each protocol method's return value against a minimal
  hand-built `rec`/`part` fixture, independent of the golden-file
  end-to-end coverage above.
