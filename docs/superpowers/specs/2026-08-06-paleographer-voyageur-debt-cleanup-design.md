# Paleographer / Voyageur Debt Cleanup — Design

## Goal

Remove verified dead code, fix a broken CLI mode, and consolidate duplicated
logic across `Paleographer/Paleographer.py` and `Voyageur/` (`LAC.py`,
`lac_client.py`, `A.py`, `FS.py`) as a self-contained branch that merges
before sub-project 3 (Voyageur building the Commissioner-shaped scaffold for
Parish and Scrip) begins. No new features. No behavior change except the one
explicit bug fix (`crosscheck`).

## Background

An audit (AI Assistant/AGY digest, independently re-verified line-by-line
against the actual repo) found dead code, a disconnected CLI mode, and
duplicated logic spanning both modules. Two of the digest's claims were
fabricated (`census_schema.py`'s `infer_spec_name`, `lac_client.py`'s
`_IMAGE_CACHE_DIR`/`build_search_query` — neither exists anywhere in the
repo) and are excluded from scope below. One real finding — an entire
orphaned module, `Paleographer/postprocess.py` — was missed by the digest
and found during manual re-verification. Every item below was confirmed via
direct grep/read against the current repo state before being included.

## Architecture

A single branch off `Unify` (the branch sub-projects 1-2 already landed on).
No new subsystems. Paleographer.py already imports `LAC` as `voyageur_lac`
(with an existing try/except import-fallback for different execution
contexts — see `Paleographer.py:56-64`); consolidation below reuses that
existing cross-import rather than introducing a new shared module for the
`COLLECTIONS` table. The two normalization-helper duplicates (Paleographer.py
vs. FS.py) and the two retry-helper duplicates (A.py vs. FS.py) each need a
genuinely new shared module, since neither existing file is a natural import
target for the other.

## Scope

### Delete (dead code — verified zero call sites repo-wide, no dynamic/dict-based dispatch found)

- `Paleographer/postprocess.py` (entire file, 25 functions) and
  `Paleographer/tests/test_postprocess.py` (its only importer). A comment at
  `Paleographer.py:74` ("POSTPROCESS (folded from postprocess.py)") confirms
  these functions were copied into `Paleographer.py` and the source file was
  never removed. Nothing in production imports `postprocess`.
- `Paleographer.py:381-398` `clean_race`, `Paleographer.py:400-438`
  `clean_date_and_place` — the folded-in copies are themselves uncalled.
  Race/date-place fields are actually normalized inline via `cap_case`
  elsewhere (see `Paleographer.py:657`).
- `Paleographer.py:327-330` `MONTHS_REGEX`, `:331-336` `DATE_PATTERN`,
  `:337-340` `NARRATIVE_JUNK_REGEX` — sole consumer was the now-deleted
  `clean_date_and_place`. Confirm no other consumer before deleting each.
- `Voyageur/LAC.py:77-82` `get_env_paths()` — zero callers anywhere in the
  repo. (Distinct from `Voyageur/Voyageur.py:276` `_lac_get_env_paths()`,
  which is used but lives in the confirmed-dead pre-split monolith — do not
  touch `Voyageur.py`.)
- `Voyageur/LAC.py:49-55` `resolve_pid_from_filename()` — zero callers
  within `LAC.py`. `Paleographer.py:1893` has its own separate, actually-used
  definition of the same name (called at `Paleographer.py:1909` and, once
  `crosscheck` is wired up, `:2055`) — that copy is unrelated and stays.

### Fix

- `Paleographer.py` `main()` (~2202-2255): add the missing
  `if args.mode == "crosscheck":` dispatch branch, calling
  `cross_check_claim_record(record, cookies, media_dir)` per record in the
  loaded dataset (following the same load/process/save shape as the
  existing `enrich`/`resolve-names` branches at `:2219-2229` and
  `:2244-2254`). `crosscheck` is currently accepted by argparse
  (`:2204`, `:2210`) and documented in `--help`, but silently falls through
  to standard extraction instead of running. The implementation
  (`cross_check_claim_record`, `build_claim_search_query`,
  `build_claim_search_queries`) already exists and is correct — it resolves
  a Scrip claim record's own LAC PID from its filename, downloads that
  document, then searches LAC for other documents referencing the same
  claim/affidavit/scrip number and appends them to `source_documents`. This
  needs a `--cookie-file` argument added to the `crosscheck` mode's argparse
  block (the other three modes don't need cookies; `crosscheck` does, for
  `lac_client.search`) — read cookies the same way `LAC.py main()` does via
  `load_cookies()`.
- `Voyageur/LAC.py` `load_cookies()` (58-71): replace its `sys.exit(1)` with
  raising the exception types it already constructs (`FileNotFoundError`,
  `ValueError`) — matches the function's own existing exception-raising
  code, just without the premature exit. `main()` (~407-462) already has a
  surrounding try/except for this call; extend it to catch and exit there
  instead.

### Restructure

- `Voyageur/LAC.py` `main()`: replace the implicit
  `if args.volume: ... else: ...` dispatch with explicit argparse
  subcommands `volume` and `reel`, each owning its existing flags
  (`--archival-number`, `--cookie-file`, `--media-dir`, `--workers` for
  `volume`; the URL-based flags for `reel`). Internal logic of each path is
  unchanged — this only changes how `main()` routes to it. Do **not** add a
  `scaffold` subcommand here — that belongs to sub-project 3.
- While restructuring, replace the duplicated `archival_number: str = "RG15"`
  defaults in `retrieve_volume_pids()` (~242) and `retrieve_volume()`
  (~395) with the existing `DEFAULT_ARCHIVAL_NUMBER` module constant
  (`LAC.py:43`), which was defined for exactly this and never referenced.

### Consolidate (single source of truth, no behavior change)

- `COLLECTIONS` table (`LAC.py:44`) vs. Paleographer.py's separate copy plus
  `collection_for_series_code`/`collection_for_volume`
  (`Paleographer.py:1912-1951`): keep `LAC.py`'s table canonical. Delete
  Paleographer.py's duplicate table and both functions; replace their call
  sites (`Paleographer.py:1960`, `:1965`) with
  `voyageur_lac.collection_for_series_code(...)` /
  `voyageur_lac.collection_for_volume(...)` using the existing
  `voyageur_lac` import.
- `_move_with_retry`/`_cleanup_checkpoint_files`, verbatim-duplicated in
  `Voyageur/A.py:16-45` and `Voyageur/FS.py:772-800`: extract both into a
  new `Voyageur/_retry_utils.py`; both `A.py` and `FS.py` import from it.
  (`_read_text_with_retry`/`_unlink_with_retry` exist only in `FS.py`, not
  duplicated — leave them where they are, or move them into the same new
  module if that reads more naturally once it exists — implementer's call.)
- Normalization helpers independently reimplemented in both
  `Paleographer.py` (`_titlecase_callback`/`cap_case` at `:80-100`, date
  parsing at `:103-164`, `derive_record_identity` at `:167-178`,
  `derive_role_number`/`derive_role_semantic` at `:180-203`) and
  `Voyageur/FS.py` (`cap_case` at `:44-66`, `MONTH_NAMES`/
  `_DATE_PATTERNS`/`parse_to_iso` at `:153-203`, `derive_record_identity`
  at `:206-216`, `derive_role_numbers`/`derive_role_semantics` at
  `:219-237`): extract one shared implementation into a new
  `Commissioner/normalization.py` (Commissioner already sits below both
  Paleographer and Voyageur as shared schema/validation ground) and have
  both files import from it. Function names currently differ slightly
  between the two copies (`derive_role_number` vs. `derive_role_numbers`,
  singular vs. plural) — the implementer must diff both copies for real
  behavioral differences before picking one as canonical; if they've
  diverged in behavior (not just naming), surface that rather than silently
  picking one.

### Harden error handling

- `Voyageur/A.py` downloads-dir polling loop (~121-137) and
  `Voyageur/FS.py`'s equivalent (~864-880): narrow `except Exception: pass`
  to `except OSError: pass` — these wrap `Path.iterdir()`/`stat()` calls,
  which only raise `OSError` subclasses under normal failure; a bare
  `Exception` catch risks masking unrelated bugs.
- `Voyageur/A.py` image-move loop (~209-216) and `Voyageur/FS.py`'s
  equivalent (~962-968): keep the broad catch (individual file moves can
  fail in varied ways) but replace the silent `pass` with a printed/logged
  message naming the file that failed, matching `_move_with_retry`'s own
  existing `[ERROR]` print convention.
- `Paleographer.py` `has_usable_text_layer` (~968-973) and
  `optimize_pdf_for_upload` (~992-999): same treatment — keep the broad
  catch, replace silent `pass`/fallback with a logged message so a PDF
  failure is visible instead of silently forcing the expensive
  vision-fallback path.

## Explicitly out of scope

- `Voyageur/lac_client.py`'s `_worker_download_loop`
  `if "403" in err_str:` string-based rate-limit detection. Fixing this
  properly requires giving `LacCallError` a structured status-code
  attribute — a change to the exception's shape and every one of its five
  raise sites in `lac_client.py`, which is a larger, separate change.
- Any change to `Voyageur/Voyageur.py` (confirmed-dead pre-split monolith,
  out of scope since sub-project 1).
- Any change to `Commissioner/models.py` or scaffold-related work — that is
  sub-project 3, sequenced after this branch merges.

## Testing

- Full `pytest` suite and `pycodestyle --max-line-length=120` stay green
  throughout — run after each task, not just at the end.
- Deletions and consolidations (moving code without changing behavior) get
  no new tests — existing tests exercising the moved/deleted code must
  still pass (or, for `postprocess.py`'s own tests, be deleted alongside
  it).
- `crosscheck` wiring gets a new unit test in
  `Paleographer/tests/` mocking `lac_client.search` and
  `voyageur_lac.download_pid_bundle` (no real network calls — consistent
  with the standing constraint against executing LAC/Canadiana network
  code pending AI Assistant issue #81159). Cover: own-PID resolution succeeds and
  merges into the record; own-PID resolution fails and appends a
  `review_reason` instead of raising; related-PID search finds results and
  appends to `source_documents`; search raises `LacSearchAuthError` and the
  loop breaks with a `review_reason` rather than propagating.
- `Commissioner/normalization.py`'s extracted functions get tests only if
  the two original copies had none (check both `Paleographer/tests/` and
  `Voyageur/tests/` first) — if tests already exist for either copy, move
  and adapt them rather than writing new ones from scratch.
