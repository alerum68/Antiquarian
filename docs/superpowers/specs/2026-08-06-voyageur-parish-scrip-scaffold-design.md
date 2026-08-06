# Voyageur Builds the Parish/Scrip Scaffold (Sub-project 3 of the Voyageur-owns-ingestion rework)

## What this is

Sub-project 2 wired Commissioner validation into Voyageur's Census gather.
This sub-project does the equivalent groundwork for Parish and Scrip, but the
underlying problem is different from Census in one important way: Census's
FamilySearch/Ancestry index tells Voyageur exactly how many records exist on
a page (one per index row). Parish and Scrip have no such structure when the
source is LAC/Canadiana images — Voyageur only knows an image exists, not
what (or how many) genealogical records are on it.

Originally scoped narrower ("Voyageur builds an empty-content scaffold for
LAC's image-only harvest"), this sub-project grew during brainstorming once
it became clear that FamilySearch's own Parish index is *also* frequently
incomplete — indexers skip fields to save time, same as any other index — so
the real requirement isn't "empty vs. full," it's "every record, regardless
of how complete its gather made it, needs a reliable way to find its way back
to its source image for a later, user-triggered AI-fill pass."

## Goals

- Every Parish/Scrip record Voyageur produces — whether index-derived
  (`FS.py`) or image-only (`LAC.py`) — carries a real
  `document_metadata.file_name`/`file_type` pointing at its actual source
  image file, using the same `Commissioner.models.DocumentMetadata` field
  Paleographer's own AI path already reads and writes
  (`tag_document_metadata`, Paleographer.py:1401-1406).
- `FS.py`'s `build_universal_json` (FS.py:421-461) is fixed: it already
  downloads and moves each image to the project folder and already builds a
  `document_metadata` dict per sheet, but leaves `file_name`/`file_type` as
  empty strings (FS.py:449-452). Wire in the real moved-image filename.
- `LAC.py`'s image-only harvest (`volume`/`reel` subcommands) gains an actual
  JSON output step, which does not exist today — it currently only writes
  download checkpoints. For each downloaded asset it builds one
  Commissioner-shaped `Sheet`, with real `document_metadata`, wrapping
  exactly one empty-content `Record` (`participants: []`, everything else
  `None`) — Voyageur cannot know record count from a bare image, so it
  registers the image and defers record-splitting to whatever reads the
  image later.
- That output is written directly into the same `MASTER_DB` file
  Paleographer's own run already reads/writes for the active record type
  (`parish_register.json` / `scrip_records.json`, resolved the same way
  Paleographer resolves it — see Architecture). This is a deliberate choice:
  it means Paleographer's later on-demand run finds Voyageur's scaffolded
  images already sitting in its own database with nothing extra to merge.
- Because writing into `MASTER_DB` directly creates a real collision with
  Paleographer's existing "already processed" logic (see Architecture), this
  sub-project also makes the two minimal fixes needed to make that safe:
  `get_processed_files` and `merge_sheets` (both Paleographer.py) start
  distinguishing an empty scaffold sheet from an actually-filled one.
- Both `LAC.py` and `FS.py` validate their output via
  `Commissioner.record_registry.parse_collection()` before writing, using the
  same non-blocking pattern Sub-project 2 established for Census: log a
  warning on failure, never crash the gather, never skip the write.
- AI-filling stays entirely on-demand. Nothing in this sub-project triggers
  AI extraction automatically — Paleographer's `main()` already only runs
  when explicitly launched by the user, and this sub-project doesn't change
  that. It only changes what Paleographer finds already present in
  `MASTER_DB` the next time it *is* launched.

## Non-goals (explicitly out of scope for this sub-project)

- No change to `Voyageur/A.py`. It has no Parish/Scrip path today (Census/
  Ancestry only) — adding one is a separate, future concern, tracked as
  Sub-project 7 (see "What comes after this sub-project").
- No change to `FS.py`'s Census-only `build_census_json` path — Census is
  already fully wired per Sub-project 2.
- No rework of Paleographer's actual extraction/prompt logic to treat a
  pre-existing scaffold record as analysis input (e.g. pre-seeding the AI
  prompt with whatever partial data Voyageur already gathered, or teaching
  it to split one scaffold image into N detected records instead of
  inventing sheet/record bookkeeping from scratch). That consumption-side
  rework is Sub-project 4. This sub-project's Paleographer-side changes are
  strictly limited to the two "don't silently break on a pre-seeded empty
  sheet" fixes above — nothing about *how* Paleographer extracts changes.
- No change to `Commissioner.models`' `Sheet`/`Record`/`DocumentMetadata`
  shape. An empty scaffold record is expressed structurally with fields
  already in the model (`participants: []`, everything else `None`) — no new
  field is needed to mark "this is a placeholder."
- No hard-fail/blocking validation mode — same deferral to Sub-project 5 that
  Sub-project 2 established.
- The unrelated memory inefficiency in `rasterize_pdf_to_images` (loads an
  entire PDF into RAM before chunked processing) is explicitly out of scope
  here. It's real and worth fixing, but it's Paleographer's existing
  extraction path, not Voyageur's scaffold-building — tracked as its own new
  sub-project, sequenced before the current Sub-project 4 (see "What comes
  after").

## Architecture

**The MASTER_DB collision.** Paleographer's `get_processed_files`
(Paleographer.py:1428-1434) treats a file as already processed purely by
whether *any* sheet in `MASTER_DB` has a matching
`document_metadata.file_name` — it never checks whether that sheet has real
content. If `LAC.py` seeds `MASTER_DB` with an empty scaffold sheet for every
downloaded image, every one of those images would be silently skipped
forever the next time Paleographer runs, since a matching `file_name` is
already present. Real content never arrives.

The fix: `get_processed_files` treats a sheet as processed only if at least
one of its records has a non-empty `participants` list. A genealogical
record without a primary participant is not a real record under this
schema — every filled sheet Paleographer or FS.py has ever produced already
satisfies this, so the fix is behavior-neutral for every existing case and
only changes what happens for a scaffold-only (all-empty) sheet.

A related gap: `merge_sheets` (Paleographer.py:1437-1442) unconditionally
extends `master_data["sheets"]` — it has no notion of "replace this
placeholder" versus "append a new sheet." Once `get_processed_files` no
longer treats an empty scaffold sheet as processed, Paleographer will
re-process that image and try to merge in a real, filled sheet for the same
`file_name` — which today would just sit alongside the empty placeholder as
a duplicate. `merge_sheets` gains a lookup: for each incoming sheet, if an
existing sheet in `master_data["sheets"]` has the same
`document_metadata.file_name` *and* every one of its records has empty
`participants` (i.e. it's a scaffold placeholder), replace it in place
instead of appending. A real sheet is still simply appended if no matching
placeholder exists — unchanged from today.

**Scaffold construction.** `Commissioner/record_registry.py` gains one new
function: `build_empty_sheet(file_name: str, file_type: str, page_id:
Optional[str] = None) -> dict`, returning a dict matching `Sheet`'s shape —
`document_metadata` with the given `file_name`/`file_type` and every other
field `None`, `records: [<one empty Record dict>]`. This mirrors
`Commissioner.normalization`'s precedent (established in the just-merged
debt-cleanup work) of Commissioner hosting logic genuinely shared across
Voyageur call sites, rather than each gather script re-deriving the same
dict literal.

**`LAC.py`'s new write path.** Both harvest entry points
(`download_volume_assets`/`download_volume_assets_multiworker` for `volume`,
and `download_images`/`_run_reel` for `reel`) already call
`download_pid_bundle`/equivalent per asset and already checkpoint
incrementally after each success — the same pattern the scaffold write
follows, to survive interruption on a multi-hour harvest without losing
already-downloaded structure. `MASTER_DB`'s in-memory dict is loaded once at
the top (mirroring `load_checkpoint`'s one-time load), each successful
asset's `source_documents` entries are converted to scaffold sheets via
`build_empty_sheet` and appended, and the file is rewritten after each
success — never re-read from disk mid-run, only re-serialized, matching how
`save_checkpoint` already avoids O(n²) I/O on large volumes.

Because the concurrent `download_volume_assets_multiworker` path downloads
in worker subprocesses but only reports results back to the single
controller process via a queue (`_worker_download_loop`,
LAC.py:304-331 → `result_queue.put(("SUCCESS", ...))`), the scaffold write —
like the checkpoint write — happens only in that single controller loop,
never inside a worker. No file-locking or concurrent-write concern exists
because of this existing structure.

`LAC.py` currently has no way to know which record type (Parish vs. Scrip)
it's harvesting — `volume`'s `--archival-number` defaults to `RG15` (Scrip)
but nothing labels the `reel` subcommand at all, and neither subcommand
today resolves a `MASTER_DB` path the way Paleographer does. `main()` gains
a `--record-type {parish,scrip}` argument on both subparsers, used to select
which `MASTER_DB_NAME` env var to resolve (`CHURCH_MASTER_DB_NAME` /
`SCRIP_MASTER_DB_NAME`, the same variables Scriptorium.py already defines
per Paleographer's record type — Scriptorium.py:114,131) and which
Commissioner document type to validate against (`"Parish"` / `"Scrip"`).

**Validation.** After building each batch of new scaffold sheets (`LAC.py`)
or the full `build_universal_json` output (`FS.py`), wrap a call to
`Commissioner.record_registry.parse_collection(collection_dict,
"Parish"|"Scrip")` in `try/except Exception`, logging a warning on failure —
identical in shape to the `A.py`/`FS.py` Census wiring from Sub-project 2.
The write to `MASTER_DB` (or, for `FS.py`, its existing output path) proceeds
unchanged regardless of validation outcome.

## Components changed

**`Commissioner/record_registry.py`**
- New `build_empty_sheet(file_name, file_type, page_id=None) -> dict`.

**`Voyageur/LAC.py`**
- `main()`: `--record-type {parish,scrip}` added to both `volume` and `reel`
  subparsers.
- New helper resolving `MASTER_DB` the same way Paleographer.py does
  (`PROGRAM_DIR`/`JSON_DIR`/`CHURCH_MASTER_DB_NAME`|`SCRIP_MASTER_DB_NAME`).
- `download_volume_assets`, `download_volume_assets_multiworker`,
  `download_images`/`_run_reel`: after each successful asset download, build
  scaffold sheets via `build_empty_sheet`, append to the in-memory
  `MASTER_DB` dict, validate via `parse_collection`, rewrite `MASTER_DB`.

**`Voyageur/FS.py`**
- `build_universal_json` (FS.py:447-454): populate `document_metadata`'s
  `file_name`/`file_type` from the image's real moved path instead of `""`.
- After building the return value, validate via
  `Commissioner.record_registry.parse_collection(result, "Parish")`,
  log-only on failure.

**`Paleographer/Paleographer.py`**
- `get_processed_files` (1428-1434): a sheet counts as processed only if any
  of its records has a non-empty `participants` list.
- `merge_sheets` (1437-1442): an incoming sheet replaces an existing
  same-`file_name` sheet if every record in the existing sheet has empty
  `participants`; otherwise appends, unchanged from today.

## Data flow

Before: `LAC.py` downloads images and a checkpoint dict; nothing resembling
a Commissioner `Collection` is ever written for Parish/Scrip from LAC-sourced
images. Paleographer's own run invents the entire sheet/record structure
from scratch by scanning `SOURCE_DIR`. `FS.py` already writes a real
`Collection`-shaped file with full record content, but its `document_metadata`
is always empty, so nothing downstream can locate the source image for a
given sheet without guessing.

After: `LAC.py` writes real `Collection`-shaped scaffold data directly into
`MASTER_DB`, incrementally, as each image downloads. `FS.py`'s existing write
correctly labels each sheet's source image. When Paleographer's `main()` is
later launched by the user (unchanged trigger — still explicit, still
manual), `get_processed_files` correctly identifies scaffold-only images as
not-yet-processed, `list_source_files()`'s existing `SOURCE_DIR` scan still
finds them (no change there), and `merge_sheets` replaces each placeholder
with real content once Paleographer's AI pass fills it in.

## Error handling

No new exception types. `parse_collection` failures are caught and logged at
both `LAC.py` and `FS.py` call sites, same soft-fail posture as Sub-project
2 — a validation gap never blocks a gather or drops downloaded images.
Image download failures in `LAC.py` are already handled by its existing
retry/checkpoint logic (`403_ERROR` backoff, watchdog restart) — untouched.
A `MASTER_DB` write failure (disk full, permissions) is allowed to raise —
same as `save_checkpoint`'s current unguarded write, no new swallow
introduced.

## Testing

- `Commissioner/tests/test_record_registry.py`: `build_empty_sheet` returns a
  dict that round-trips through `Sheet` validation; its single record has
  empty `participants` and every other field `None`.
- `Paleographer/tests/`: `get_processed_files` treats an all-placeholder
  sheet as not-processed and a sheet with a real participant as processed;
  `merge_sheets` replaces a placeholder sheet sharing a `file_name` with an
  incoming real sheet, and appends normally when no placeholder exists for
  that `file_name`.
- `Voyageur/tests/test_fs.py` (or wherever FS tests land after the prior
  cleanup): `build_universal_json`'s `document_metadata.file_name`/`file_type`
  reflect the real moved image path instead of `""`.
- `Voyageur/tests/`: a `LAC.py` test asserting that after a mocked asset
  download, `MASTER_DB` contains one scaffold sheet per asset with the
  correct `file_name`, and that a second run (same PID, already checkpointed)
  does not duplicate it.

## What comes after this sub-project (not part of it)

- **New sub-project (inserted here, before the former Sub-project 4):**
  Fix `rasterize_pdf_to_images`' memory usage — stream pages in
  `chunk_size`-page windows instead of rasterizing an entire PDF into memory
  before chunked processing begins. Unrelated to Voyageur ingestion; grouped
  here only because it surfaced during this brainstorm.
- Sub-project 4: reworking Paleographer to consume the scaffold as pure
  analysis — including actually using whatever partial data Voyageur's index
  path already gathered as AI context, and handling one scaffold image
  splitting into multiple real records.
- Sub-project 5: wiring Commissioner validation at both the Voyageur and
  Paleographer boundaries — hard-fail/blocking mode decision.
- Sub-project 6: cross-script invocation (Paleographer/Voyageur calling into
  each other's real functions).
- Sub-project 7: `Voyageur/A.py` gains a Parish/Scrip gather path (it is
  Census/Ancestry-URL-only today), following whatever pattern this
  sub-project establishes for `FS.py`/`LAC.py` — image-reference scaffold
  writes into the type-resolved `MASTER_DB`, non-blocking Commissioner
  validation. Not scoped further here since Ancestry has no current
  Parish/Scrip source to gather from.
- Census family-linking (`role_name` → `role_semantic` derivation for
  Voyageur-sourced data) — still unscoped, not part of this sub-project.
