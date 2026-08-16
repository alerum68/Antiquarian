# Paleographer Structural Split — Design

## Goal

Split `Paleographer/Paleographer.py` (2,148 lines, four historically
separate files stitched together behind banner comments) into a thin
dispatcher plus real sibling modules — mirroring the pattern `Voyageur.py`
was rewritten to in the prior sub-project. Confirm the Sub-project 3/4
scaffold-consumption work is actually complete. Fix two small, real bugs
found during investigation. No behavior change beyond those two fixes.

This is "Sub-project 6" as scoped in
`docs/superpowers/specs/2026-08-06-census-commissioner-wiring-design.md:188-196`.

## Background

`Paleographer.py`'s own module docstring claims it "never changes when a
new record type is added." That's true for its extraction/transcription
path (driven entirely by `TYPE_CFG`/`.pmt` files, no record-type
whitelist). It is **not** true for its enrichment path: `enrich`,
`crosscheck`, `partition`, and `resolve-names` (the `SCRIP ENRICHMENT &
PARTITIONING` banner, `Paleographer.py:1749-2019`) are hardcoded to Scrip
vocabulary (`claim_number`, `scrip_number`, `affidavit_number`,
`rg_series_code`) and Scrip's LAC data source. This is confirmed correct
scope for those functions to keep — not a defect to generalize — but the
file's structure and the GUI both currently hide that split:

- The two halves are folded into one file "for test-suite compatibility"
  (`Paleographer.py:11-15`), despite `engine.py`/`agy_engine.py` already
  existing as standalone siblings that the folded-in code duplicates
  verbatim.
- The original reason for folding — "self-contained entrypoint, no
  sibling-file imports required at runtime" (commit `9663cdb`) — no longer
  applies and may never have: `Antiquarian.py:1869`
  (`target_cwd = os.path.dirname(target_script_path)`) already launches
  every script, including `Paleographer.py`, with its own directory as
  `cwd`, exactly the mechanism the Voyageur dispatcher rewrite relies on.
- `Antiquarian.py`'s Enrich/Partition/Resolve-Names/Crosscheck buttons
  (`:1566-1574`) are built once and stay clickable regardless of selected
  Record Type — a Parish or Census user can click "Enrich Metadata" today
  and get a silent no-op (`classify_sheet_collection` falls to
  `UNKNOWN_COLLECTION_LABEL` for any sheet without a Scrip-shaped
  `rg_series_code`).

Separately, `Archivist.py` has its own independent Scrip-only branching
(`is_scrip`, `Archivist.py:3608` and 16 further call sites) for GEDCOM
compilation — same root pattern, different file. **Explicitly out of scope
for this sub-project** (see below); noted here so it isn't rediscovered as
a surprise later.

## Architecture

Mirror `Voyageur/Voyageur.py`'s post-rewrite shape exactly: a thin
dispatcher that routes on `sys.argv[1]` to a sibling module's `main()`,
each sibling fully self-contained for its own concern.

- **`Paleographer/Paleographer.py`** (rewritten, ~35-40 lines) — parses
  `sys.argv[1]`: no arg or a bare filename (today's `DEBUG_FILE` positional
  quirk, `Paleographer.py:1346-1349`) routes to `Extract.py`; `enrich`,
  `crosscheck`, `partition`, `resolve-names` route to `ScripTools.py`.
  Docstring updated to state plainly that extraction is record-type-generic
  and enrichment is Scrip-specific — the current "never changes" claim gets
  scoped accurately instead of dropped, since it's true for half the file.
- **`Paleographer/Extract.py`** (new) — today's `CONFIGURATION`,
  `MASTER DB HELPERS`, `FILE CLASSIFICATION`, `SYNCHRONOUS/BATCH
  PROCESSING` sections (`Paleographer.py:1289-1748`) plus its own `main()`.
  Imports `engine`/`agy_engine` as real sibling modules (`import engine`,
  `import agy_engine`) instead of folding their contents in — deletes the
  `ENGINE` (532-1023) and `AGY ENGINE` (1024-1288) banners, ~756 duplicated
  lines. `engine.py`/`agy_engine.py` themselves are untouched; they were
  already correct.
- **`Paleographer/ScripTools.py`** (new) — today's `SCRIP ENRICHMENT &
  PARTITIONING` section (1749-2019) plus its own `main()`/argparse block
  (today's `main()` branches for `enrich`/`crosscheck`/`partition`/
  `resolve-names`, `Paleographer.py:2027-2096`), behavior unchanged except
  the one bug fix below. Named for what it does — this is intentionally
  Scrip-only, not a generalization attempt.
- **`POSTPROCESS` functions** (`Paleographer.py:76-531`) split by actual
  call site, not by guesswork at design time:
  - To `ScripTools.py`: the maiden/dit-name chain —
    `resolve_dataset_maiden_names`, `resolve_maiden_name_for_record`,
    `fix_participant_name`, `fix_all_participant_names_in_record`,
    `parse_single_name`, `clean_dit_name`, `build_composite_record_number`
    — these are only reachable from `resolve-names` mode.
  - To `Extract.py`: `derive_role_numbers`/`derive_role_semantics`/
    `derive_suffixes`, `apply_defaults`, `fix_mojibake`,
    `extract_citation_fields`, `merge_same_claim_records`,
    `strip_diacritics` and the small private helpers — these are only
    reachable from `finalize_record`/`finalize_page_data` in the
    extraction path.
  - The implementer must grep each function's actual call sites before
    moving it — the list above is this design's best read of the code, not
    a guarantee; if a function turns out to be called from both files,
    it goes into a new `Paleographer/_shared.py` instead of being
    duplicated.

## Scope

### Split (structural only, no behavior change)

- Rewrite `Paleographer.py` as the thin dispatcher described above.
- Create `Extract.py`, moving the sections listed above verbatim except for
  the `engine`/`agy_engine` import change.
- Create `ScripTools.py`, moving the sections listed above verbatim.
- Delete the now-fully-duplicated `ENGINE`/`AGY ENGINE` banner content from
  the old `Paleographer.py` (superseded by `Extract.py` importing the
  standalone files).

### Fix (real bugs found during investigation)

- **`build_claim_search_query`/`build_claim_search_queries`**
  (`Paleographer.py:1843-1867`, moving to `ScripTools.py`): currently read
  `record.get("claim_number")` / `record.get("scrip_number")` /
  `record.get("affidavit_number")` at the top level of `record`. Every
  other reader of Scrip's type-specific fields goes through
  `record["type_specific_fields"]`, per `build_merged_schema`
  (`Paleographer.py:684-705`, nests all `.pmt`-declared `extra_fields`
  there). Fix the three reads to go through `type_specific_fields`. This
  is a real bug independent of the split — worth a regression test
  either way.
- **UI gating**: in `Antiquarian.py`, disable (not hide — keep layout
  stable) the Enrich Metadata / Partition Collections / Resolve Names
  buttons unless the currently selected Record Type is `Scrip`. Wire this
  into `_on_record_type_change` (`Antiquarian.py:1523-1536`), which
  already runs on every Record Type switch; add button
  enable/disable alongside the existing settings-form rebuild.
  `crosscheck` was already effectively gated behind Scrip-only cookie/PID
  logic and fails loudly (`FATAL ERROR` on cookie load) rather than
  silently no-opping, so gating it too is for UI consistency, not a
  correctness fix.

### Verify (confirm already-done work, add coverage only if a gap is real)

- Confirm `_sheet_is_placeholder`/`get_processed_files`/`merge_sheets`
  (`Paleographer.py:1434-1470`, moving to `Extract.py`) have a test
  covering the actual placeholder round trip: a `MASTER_DB` seeded with a
  `build_empty_sheet`-shaped placeholder for a given `file_name`,
  extraction runs and produces real content for that file, `merge_sheets`
  replaces the placeholder in place rather than appending a duplicate
  sheet. Check `Paleographer/tests/test_master_db_merge.py` first — if
  this case is already covered, no new test is needed; if not, add one.
  This is the "consume the Sub-project 3 scaffold as pure analysis" half
  of Sub-project 6's original scope — investigation during brainstorming
  found the mechanism itself already implemented by Sub-projects 3/4, so
  this step is verification, not new implementation.

### Rename

- `CENSUS_URL` → `A_URL` throughout: `Voyageur/A.py:58`,
  `Antiquarian.py:106,235,331`, `Voyageur/.env`, `Archivist/.env`. Purely
  mechanical — same env var, new name, matching the `FS_URL`/`LAC_URL`
  convention the other two Voyageur sources already follow.

## Explicitly out of scope

- Generalizing `ScripTools.py`'s logic to work for non-Scrip record types.
  Confirmed correct scope for it to stay Scrip-specific.
- `Archivist.py`'s independent `is_scrip` branching (16 call sites,
  `Archivist.py:3608` and others) — same root pattern (bespoke per-type
  polish hardcoded to Scrip's name), different file, would need its own
  design (a real per-`.pmt` compilation-profile mechanism, analogous to
  what `.pmt` already gives extraction, doesn't exist yet for Archivist).
  Left as documented debt for a future sub-project.
- `Voyageur/LAC.py`'s hardcoded 2-entry record-type dict
  (`RECORD_TYPE_ARG_TO_DOCUMENT_TYPE`) and `Voyageur/FS.py`'s
  `record_family`/`record_type_name` reconciliation gap
  (self-flagged at `FS.py:833-835`) — both found while checking whether a
  new record type needs zero code changes; neither is inside
  `Paleographer.py`, out of scope here.
- Any change to `engine.py`/`agy_engine.py`'s own logic — only their
  import path from `Extract.py` changes.

## Testing

- Full `pytest` suite stays green after every task.
- `test_engine.py`, `test_agy_engine.py`, `test_schema.py` are untouched
  (still import the standalone `engine`/`agy_engine` files directly).
- `test_master_db_merge.py`, `test_paleographer_pipeline.py`,
  `test_crosscheck.py`, `test_settings_standalone.py` currently do
  `importlib.import_module("Paleographer")` and must be repointed to
  `Extract` or `ScripTools` depending on which functions each test
  exercises — mechanical rework, same pattern
  `test_voyageur_dispatcher.py` established for the Voyageur split.
- New test for the `type_specific_fields` nesting fix: a record with
  `type_specific_fields: {"claim_number": "123"}` (the shape a real
  extraction produces) yields a non-empty search query; the old top-level
  read would have returned `None`/empty for the same input.
- New test for UI gating: `_on_record_type_change` disables the three
  buttons when Record Type != Scrip and re-enables them when it is.
- `CENSUS_URL`/`A_URL` rename: existing tests referencing the env var by
  name get updated in place; no new test needed for a pure rename.
