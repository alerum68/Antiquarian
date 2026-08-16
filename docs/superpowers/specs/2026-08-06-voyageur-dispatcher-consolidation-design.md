# Make Voyageur.py a Real Thin Dispatcher, Deduplicate A.py/FS.py Gather Boilerplate (Sub-project 5 of the Voyageur-owns-ingestion rework)

## What this is

`Antiquarian.py`'s GUI launches `Voyageur/Voyageur.py` as a subprocess
(`SCRIPT_PATHS["VOYAGEUR_SCRIPT"]`) for every Gather run — it is the only
wiring for the A/FS/LAC buttons. `Voyageur.py` is a ~1300-line frozen fork of
`A.py`/`FS.py`/`LAC.py`/`census_schema.py`, folded in once and never touched
since: no commit since `fa4f1a7` (start of the debt-cleanup initiative)
touches it, it has zero Commissioner references, and it still duplicates the
pre-extraction retry helpers instead of using `_retry_utils.py`. Every recent
sub-project (Commissioner soft-fail wiring, retry/normalization extraction)
improved the split files (`A.py`, `FS.py`, `LAC.py`, `census_schema.py`) but
never reached the copy the GUI actually runs. Its folded-in LAC section even
predates `LAC.py`'s later split into `volume`/`reel` subcommands, so it isn't
just stale — it runs structurally incompatible logic today.

Originally this sub-project was scoped as "cross-script invocation between
Paleographer and Voyageur." That idea is dropped: there's no concrete current
need for Paleographer and Voyageur to call into each other's functions, and
Commissioner already serves as their shared layer. This sub-project instead
makes `Voyageur.py` a real thin dispatcher — matching what its own docstring
already (incorrectly) claims — and, since implementing that surfaced a second,
smaller pocket of duplication, also deduplicates the gather boilerplate
`A.py` and `FS.py` independently copy-pasted from each other.

## Goals

- Every GUI-triggered gather (A/FS/LAC) runs the same maintained, tested code
  the split files already have — no more split-brain between "what's tested"
  and "what's actually run."
- `Voyageur.py` shrinks from ~1300 lines to a dispatcher: a `SOURCES` tuple
  and a `main()` that imports and calls the right provider's real `main()`,
  forwarding the remaining CLI arguments correctly.
- The LAC CLI-argument path (`Antiquarian.py` → `Voyageur.py` → `LAC.py`)
  works end-to-end for both the `volume` and `reel` harvest modes, verified
  by running it, not just read.
- The ~70-90 lines of near-identical logic independently duplicated between
  `A.py`'s and `FS.py`'s `main()` (Tampermonkey download-polling loop,
  browser-launch sequence, downloaded-image move loop, `CENSUS_IMAGE_DIR`
  resolution, Archivist `.env` write-back) collapses into one shared module
  both call into.

## Non-goals

- No change to `Commissioner.normalization`/`record_registry` scope — they
  stay cross-script-only; this sub-project's shared logic is Voyageur-only
  (LAC.py doesn't participate in it) and doesn't belong there.
- No change to `A.py`/`FS.py`/`LAC.py`'s actual gather *behavior* — this is
  a structural deduplication and re-wiring, not a logic change. Every
  extracted function is a verbatim lift of existing code into a shared
  location, called with the same arguments producing the same results.
- No change to `census_schema.py` — it stays a Voyageur-local sibling module,
  untouched.
- No revival of Paleographer/Voyageur cross-invocation — superseded, per the
  above.
- `FS.py`'s own `_read_text_with_retry`/`_unlink_with_retry` stay in `FS.py`
  — they're not duplicated in `A.py`, so there's nothing to deduplicate.
- No fix to any LAC harvest behavior beyond making the existing `volume` and
  `reel` GUI fields (`LAC_HARVEST_VOLUME`, `LAC_URL`) actually reach
  `LAC.py` correctly. No new LAC features.
- No fix to the separate, pre-existing env-var naming mismatch between what
  `Antiquarian.py` writes (`LAC_HARVEST_ARCHIVAL_NUMBER`, no
  `LAC_MAX_WORKERS`/`LAC_RECORD_TYPE` at all) and what `LAC.py`'s argparse
  defaults for `--workers`/`--record-type`/`--archival-number` read from the
  environment — flagged during design, left for a future task.

## Architecture

### Voyageur.py becomes a thin dispatcher

```python
SOURCES = ("A", "FS", "LAC")

def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in SOURCES:
        print(f"[ERROR] Usage: python Voyageur.py <source>, where <source> is one of: "
              f"{', '.join(SOURCES)}.")
        sys.exit(1)
    source = sys.argv[1]
    del sys.argv[1]
    if source == "A":
        import A
        A.main()
    elif source == "FS":
        import FS
        FS.main()
    elif source == "LAC":
        import LAC
        LAC.main()


if __name__ == "__main__":
    main()
```

`Antiquarian.py` sets `cwd=Voyageur/` for the subprocess (`target_cwd =
os.path.dirname(target_script_path)`), so `import A`/`import FS`/`import LAC`
resolve as plain sibling-module imports — the same pattern `A.py`/`FS.py`
already use for `import census_schema` today. Deleting `sys.argv[1]` (the
mode token) before delegating means each provider's own `sys.argv`-based
parsing (in particular `LAC.py`'s `argparse.ArgumentParser().parse_args()`,
which reads `sys.argv[1:]` implicitly) sees exactly the arguments
`Antiquarian.py` meant for it.

Every folded-in section of the current `Voyageur.py` (shared utilities,
census schema, the `_a_*`/`_fs_*`/`_lac_*` gather logic) is deleted — none of
it is imported or referenced by anything else in the repo (confirmed: no
`import Voyageur`/`from Voyageur import Voyageur` anywhere in the codebase).

### Antiquarian.py's LAC dispatch gets fixed to match the real LAC.py

`LAC.py`'s real `main()` requires a `volume`/`reel` subcommand as its first
positional (`add_subparsers(dest="command", required=True)`) — the folded-in
copy never needed this, since it predates that split. `Antiquarian.py`'s
current LAC branch (`Antiquarian.py:1858-1864`) sends `LAC --volume X`,
missing the subcommand token entirely, and has no handling at all for the
`reel` mode (the `LAC_URL` field exists in the GUI's env vars but nothing
currently forwards it as a CLI argument). Both gaps get fixed in the same
task: `LAC_HARVEST_VOLUME` set → send `LAC volume --volume X`; `LAC_URL` set
→ send `LAC reel --url <url>`. This is a hard blocker — without the
subcommand token, `argparse` rejects the command outright once `Voyageur.py`
delegates to the real `LAC.py`, so the GUI's LAC buttons would go from
"running stale logic" to "not running at all."

Design-time inspection also found `LAC.py`'s argparse defaults for
`--workers`, `--record-type`, and `--archival-number` read
`os.environ.get("LAC_MAX_WORKERS"/"LAC_RECORD_TYPE", ...)` and a
`DEFAULT_ARCHIVAL_NUMBER` constant, while `Antiquarian.py` never sets
`LAC_MAX_WORKERS` or `LAC_RECORD_TYPE` at all (it writes
`LAC_HARVEST_ARCHIVAL_NUMBER`, `LAC_HARVEST_VOLUME`, `LAC_URL`,
`LAC_IMAGE_DIR`, `LAC_COOKIE_FILE` — a different naming scheme). This looks
like a second, pre-existing wiring gap, but auditing and fixing every
LAC.py argument's env-var plumbing is a distinct, larger scope than this
sub-project's dispatcher fix — it's flagged here for a future task, not
fixed as part of this one. The `--volume` value is the only one already
proven to reach `LAC.py` correctly (via the explicit CLI arg
`Antiquarian.py` already sends), so it's the only one this sub-project's
fix depends on.

### A.py/FS.py gather-boilerplate consolidation

`Voyageur/_retry_utils.py` is renamed to `Voyageur/_gather_helpers.py` and
gains five functions, each a verbatim extraction of logic currently
duplicated (with only cosmetic differences — a prefix string, a print label)
between `A.py`'s and `FS.py`'s `main()`:

- `launch_gather_browser(url: str) -> float` — opens the browser on the
  gather URL (appending `mgs_auto=1`), prints the Tampermonkey-wait message,
  returns `start_time`.
- `wait_for_downloaded_json(downloads_dir: Path, prefix: str, start_time: float, label: str) -> Path`
  — polls `downloads_dir` once a second for a `.json` file matching `prefix`,
  newer than `start_time`, not a checkpoint file; prints `f"[System] Detected
  {label}: {name}"` on match; on `KeyboardInterrupt`, prints the cancellation
  message and calls `sys.exit(0)`.
- `move_downloaded_images(downloads_dir: Path, image_prefix: str, start_time: float, img_target_dir: Path) -> int`
  — moves every matching `.jpg` into `img_target_dir` via `move_with_retry`,
  returns the count moved (logging and skipping any that fail).
- `resolve_census_image_dir(base_img_setting: str, program_dir: str, census_folder: str, location_folder: str) -> Path`
  — resolves `CENSUS_IMAGE_DIR` (absolute or relative to `MEDIA_DIR`) and
  creates `.../<census_folder>/<location_folder>`, returning the path.
- `write_archivist_json_file(final_json_name: str) -> None` — writes
  `JSON_FILE=<final_json_name>` into `Archivist/.env` via `set_key`.

`A.py` and `FS.py` both replace their duplicated inline blocks with calls
into these five functions, keeping only what's genuinely source-specific:
their own `.env` var name (`CENSUS_URL` vs. `FS_URL`), print banner text, the
download-prefix strings (`TMP_A_`/`TMP_FS_`), and the record-shape-specific
logic in between (Ancestry's straight census normalization vs.
FamilySearch's census-or-universal branch).

## Components changed

- **`Voyageur/Voyageur.py`**: ~1300 → ~30 lines. Delete every folded-in
  section; keep only the `SOURCES` tuple and the dispatcher `main()`.
- **`Voyageur/_retry_utils.py`** → renamed **`Voyageur/_gather_helpers.py`**:
  keeps `move_with_retry`/`cleanup_checkpoint_files`, gains the five
  functions above.
- **`Voyageur/A.py`**: `main()` shrinks — its duplicated download-polling,
  browser-launch, image-move, image-dir-resolution, and Archivist-`.env`
  write-back blocks become calls into `_gather_helpers`. Its
  `from _retry_utils import ...` becomes `from _gather_helpers import ...`.
- **`Voyageur/FS.py`**: same treatment as `A.py` for its matching duplicated
  blocks. Its own unique `_read_text_with_retry`/`_unlink_with_retry` stay
  as-is.
- **`Antiquarian.py`** (~1858-1864): LAC branch gains the `volume`/`reel`
  subcommand token ahead of the existing `--volume`/new `--url` argument, so
  both harvest modes reach the real `LAC.py` correctly.

## Data flow

Before: the GUI's A/FS/LAC buttons run `Voyageur.py`'s own frozen, duplicated
copy of each provider's logic — untouched by any Commissioner validation,
retry-extraction, or normalization work landed elsewhere. `A.py` and `FS.py`
each independently poll `~/Downloads`, move images, and resolve
`CENSUS_IMAGE_DIR` with their own copy-pasted logic.

After: the GUI's buttons run `Voyageur.py`'s dispatcher, which calls straight
into the real `A.py`/`FS.py`/`LAC.py` — the same code the test suite covers
and every prior sub-project's fixes already reached. `A.py` and `FS.py` share
one implementation of the download-wait/image-move/image-dir-resolution
logic via `_gather_helpers.py`, instead of two independently-maintained
copies that can silently drift (as `Voyageur.py`'s fork already proved
happens).

## Error handling

No new exception types. `wait_for_downloaded_json`'s `KeyboardInterrupt`
handling and `move_downloaded_images`'s per-file `try/except Exception`
logging are verbatim lifts of the current inline behavior — unchanged.
`LAC.py`'s existing `argparse` error behavior (exits with a usage message on
an invalid/missing subcommand) is unchanged; `Antiquarian.py`'s fix ensures
it's never hit by GUI-triggered runs, but a user invoking `Voyageur.py LAC`
by hand with no further arguments still sees the same `argparse` error as
running `LAC.py` directly.

## Testing

- New `Voyageur/tests/test_voyageur_dispatcher.py`: `main()` with
  `sys.argv = ["Voyageur.py", "A"]` calls `A.main` (monkeypatched) with the
  mode token stripped from `sys.argv` first — repeated for `"FS"` and
  `"LAC"`. An invalid/missing source argument prints the usage error and
  exits 1 without importing any provider.
- New tests in `Voyageur/tests/` (new file or added to an existing one) for
  each of `_gather_helpers.py`'s five new functions: `wait_for_downloaded_json`
  finds the newest matching file and ignores older/checkpoint/non-matching
  ones; `move_downloaded_images` moves matches and counts them, tolerating a
  failed move; `resolve_census_image_dir` handles both the absolute and
  `MEDIA_DIR`-relative cases; `write_archivist_json_file` writes the expected
  key to the expected `.env` path. `launch_gather_browser` is covered by
  mocking `webbrowser.open` and asserting the URL/`start_time` handling.
  `Voyageur/tests/test_fs.py` and a prospective `test_a.py` currently have no
  tests targeting `main()`'s download/browser logic at all (confirmed by
  grep — nothing there mocks `webbrowser`, `Downloads`, or the old
  `_retry_utils` functions), so this is net-new coverage, not a retarget of
  existing mocks.
- Existing `Voyageur/tests/test_census_schema.py`, `test_fs.py`, `test_lac.py`
  continue to pass unmodified — none of them touch `main()` or the extracted
  functions.
- Manual verification step (documented in the plan, not automated): after
  the change, actually run the LAC volume-harvest button, the LAC reel
  harvest, and at least one A/FS gather against real data — this is the
  first time these GUI entry points run the maintained code path in
  production, matching the "untested against real data" caution already
  flagged for the Commissioner soft-fail rollout.

## What comes after this sub-project (not part of it)

- A.py record-type generalization: `A.py` currently only gathers Census
  records (`CENSUS_URL` env var, unconditional `census_schema.normalize_census_pages`
  call) even though nothing about Ancestry itself limits it to Census.
  Unlike `FS.py` — whose browser-side scraper already collects generic
  `items` and branches in Python (`detect_record_family_from_raw`/
  `build_universal_json`) between census and universal handling — Ancestry's
  browser-side scraper (`Voyageur.js`'s `runAncestryGather`) is hardcoded to
  census-index scraping (`{census_year, location, pages}`), with no generic
  scraping path for other Ancestry record layouts. Generalizing `A.py` the
  way `FS.py` already works means designing new Tampermonkey/JS scraping
  logic for other Ancestry collection types first — undesigned work, and a
  different kind of task (browser automation) than this sub-project's Python
  consolidation. The `CENSUS_URL` → `A_URL` env-var rename (raised during
  this sub-project's design, matching the `FS_URL`/`LAC_URL` pattern) belongs
  with this future sub-project rather than as a standalone rename, since
  renaming it alone without generalizing the code it names would be
  cosmetic only.
- Sub-project 6: reworking Paleographer to consume the Sub-project 3
  scaffold as pure analysis, plus the broader structural rebuild
  `Paleographer.py` needs (still four historically separate files stitched
  together behind banner comments).
- Hard-fail/blocking Commissioner validation mode, once the soft-fail
  rollout (now actually reaching GUI-triggered gathers via this sub-project)
  has run against real data and surfaced whatever shape gaps exist.
- Census family-linking and extended-family vocabulary work — still
  unscoped to any currently-planned sub-project.
