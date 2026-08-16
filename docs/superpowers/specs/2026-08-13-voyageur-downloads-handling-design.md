# Voyageur Downloads Handling Redesign — Design

## Goal

Replace the current Downloads-folder-scanning handoff between `Voyageur.js`
(the Tampermonkey userscript driving Ancestry/FamilySearch gathers) and
`A.py`/`FS.py` with a design that eliminates the concrete, repeated failure
modes it has caused: Chrome's silent filename-collision renaming, ambiguous
file-detection heuristics, and — worst — silent, permanent data loss when
the Python watcher isn't running to catch what the browser downloads.
Applies only to `A.py`/`FS.py`; `LAC.py` and `HBCA.py` already download
directly over HTTP from Python and never touch the Downloads folder.

## Background

A browser userscript cannot write to an arbitrary filesystem path — the
only filesystem-writing capability available to it is triggering a
download, which always lands in the browser's configured Downloads folder.
Today's flow: `Voyageur.js` downloads images and JSON via `<a download>`;
`A.py`/`FS.py` scans `Path.home() / "Downloads"` for files matching a
fixed prefix (`TMP_A_`/`TMP_A_Images_`) whose mtime is at or after the
run's start time, polling on a `time.sleep(1)` loop
(`_gather_helpers.wait_for_downloaded_json`) until a match with no
`[checkpoint...]` in its name appears.

This has been the source of most of this project's file-handling bugs:

- **Collision renaming.** Re-running the same record (or re-testing the
  same page range) reuses identical filenames. If a stale file from a
  prior run is still present, Chrome renames the new one `foo (1).json`,
  and that suffix survives into the final output name.
- **Silent orphaning.** If `A.py`/`FS.py` isn't running — confirmed live
  this session: driving a gather via `Voyageur.js`'s own "Start
  Auto-Batch" button, or a stale `mgs_auto=1` tab, works completely
  independently of the Python side — the browser downloads everything
  successfully and nothing is ever collected. No error, no signal,
  files just sit in Downloads indefinitely.
- **Timer-based waiting.** `wait_for_downloaded_json`'s `time.sleep(1)`
  polling loop is a standing anti-pattern per project direction: prefer
  state-based waiting (a real event/signal) over timer-based waiting
  (sleep-and-recheck) everywhere a state-based alternative exists. This
  session separately found `Voyageur.js`'s own `waitForCondition()`
  `setTimeout` fallback inflate from a configured 5000ms to an observed
  115895ms under Chrome's background-tab timer throttling — a related
  but out-of-scope bug (browser-side, no filesystem-watch equivalent
  exists in JS; see "Out of scope" below).

## Alternatives considered and rejected

- **Local HTTP server** (`Voyageur.js` `POST`s directly to
  `127.0.0.1:<port>` via the already-granted `GM_xmlhttpRequest`/
  `@connect *`, server writes straight to the project folders). Rejected
  as overkill for a single-user, one-gather-at-a-time tool — real
  benefits (no Downloads folder at all, immediate failure feedback) but
  adds a new component to reason about for a problem the existing
  architecture can be fixed to solve directly.
- **File System Access API** (`window.showDirectoryPicker()`, direct
  browser-to-disk writes, no companion process needed during a gather at
  all). Rejected: permissions are granted per-origin, so Ancestry and
  FamilySearch would each need a separate one-time grant, and the
  durability of that grant across browser restarts was never verified
  (not spiked) — real, un-resolved friction for a two-click reason to
  reject outright rather than adopt on faith.
- **Custom URL protocol handler** (`voyageur://start-watcher`, letting
  the "Start Auto-Batch" button launch `A.py`/`FS.py` directly via an
  OS-registered handler). Rejected: requires a one-time OS-level
  registry/handler registration, which breaks the project's zip-and-run
  portability model — this tool must work when unzipped onto a fresh PC
  with no installer step.

These are recorded here so a future reader doesn't re-propose them without
knowing why each was already ruled out.

## Chosen design

### 1. Unique per-run filenames

`A.py` generates a run ID (`uuid.uuid4().hex[:8]` — an 8-character hex
token, short enough to keep filenames readable, random enough that
collision odds are negligible for this use case) before launching the
browser, and appends it to the gather URL as a new query parameter
alongside the existing `mgs_auto=1` — e.g. `&mgs_run=<runId>`. `FS.py`
does the same for its own launch URL. `Voyageur.js` reads `mgs_run` from
`window.location.href` the same way it already reads `mgs_auto=1`, and
embeds it in every filename the run produces:

- `TMP_A_<runId>_Images_<imageId>.jpg`
- `TMP_A_<runId>_checkpoint_<n>.json`
- `TMP_A_<runId>_final.json`

(equivalent `TMP_FS_<runId>_*` naming on the FamilySearch side). Because
the run ID is unique per launch, no two runs — including a re-run of the
exact same record — ever produce colliding filenames, so Chrome never
needs to rename anything. `A.py`/`FS.py` already know their own run ID
(they generated it), so file-matching becomes an exact prefix match
against a known, unambiguous value — no mtime-based heuristics needed for
disambiguation (mtime may still be used as a cheap sanity check, but is no
longer load-bearing for correctness).

### 2. Explicit completion signal

The `_final.json` name (distinct from `_checkpoint_<n>.json`) is the
unambiguous "this run is complete" marker — replacing today's implicit
"a JSON exists whose name doesn't contain `[checkpoint`" inference. No
separate manifest file is introduced; the final JSON already carries this
role, just made explicit and collision-proof by the run-ID naming above.

### 3. State-based waiting via `watchdog`

`wait_for_downloaded_json`'s `time.sleep(1)` polling loop is replaced with
a real filesystem-event watch, using the `watchdog` package (new
dependency, added to `requirements.txt` — pure-Python-installable,
cross-platform: inotify on Linux, FSEvents on Mac, `ReadDirectoryChangesW`
on Windows, so this doesn't compromise the any-PC portability goal). An
`Observer` watches the Downloads folder; its event handler sets a
`threading.Event` the instant a file matching `TMP_A_<runId>_final.json`
is created. The waiting function blocks on `event.wait()` with **no
timeout** — this preserves today's already-correct behavior (the function
currently loops forever with no premature-exit bug; confirmed by reading
`_gather_helpers.py` directly), it just reacts immediately to the real
filesystem event instead of polling on a fixed interval.

`move_downloaded_images` and `cleanup_checkpoint_files` are one-shot scans
(not wait loops) and need no change under this design — noted here so the
"eliminate timers" pass over this code doesn't second-guess them later.

### 4. Startup recovery sweep

At the top of `A.py`/`FS.py`'s `main()`, before generating a new run ID or
launching a browser, scan Downloads for any `TMP_A_*`/`TMP_FS_*` files
that don't belong to the run about to start (i.e., leftovers from a
previous run where nothing was present to collect them — exactly what
happened this session: real gathered data sat abandoned in Downloads
because the browser's manual "Start Auto-Batch" button was used without
`A.py` running).

- If a stale run's files include a `_final.json`: treat it as a complete,
  recoverable gather — move its images and JSON into the project folders
  through the same move/normalize path a normal run uses, and log what
  was recovered.
- If a stale run has only `_checkpoint_*.json` files and no `_final.json`
  (the browser gather itself never finished, not just "watcher wasn't
  present"): do **not** guess. Log a clear warning listing what was found
  and leave it in place for manual review — silently promoting a partial
  checkpoint as if it were the complete gather risks feeding incomplete
  data into Archivist unnoticed.

This turns "forgot to start the watcher" from silent, permanent data loss
into "recovered automatically the next time the tool actually runs" for
the common case, without needing anything to be pre-running, installed, or
polling in the background.

### 5. What stays the same

`move_with_retry`, `atomic_write_bytes`, `cleanup_stale_gather_files`,
image target-directory resolution, and the post-move field-remap
normalization step are reused as-is — this design only changes how files
are *named* and *detected*, not how they're written to their final
location once found.

## Out of scope

- `Voyageur.js`'s own `waitForCondition()` `setTimeout` ceiling (index
  detection, alternate-name settle waits, reload-retry). This is a
  browser-side constraint: `MutationObserver` already provides the
  state-based fast path for "did the thing I'm waiting for appear," but
  detecting genuine, permanent *absence* has no negative-event to listen
  for and inherently requires some bounded wait to conclude "this will
  never appear." That bounded ceiling is the one place in this codebase
  a timer is a "100% no other option" case, not something this Downloads-
  handling redesign changes. The background-tab throttling bug found
  this session (5000ms configured, 115895ms observed) is a separate,
  already-diagnosed issue (keep the gather tab focused/foregrounded)
  tracked outside this document.
- `LAC.py`, `HBCA.py` — already direct-download, unaffected by any part
  of this design.
- The in-browser "Start Auto-Batch" manual button remains available for
  manual/dev testing but is not the documented entry point; `A.py`/
  `FS.py` (which already launches the browser itself) remains the only
  supported way to start a real gather. The recovery sweep (Section 4)
  is the safety net for when the button is used anyway.

## Testing plan

- **Python side:** the `watchdog`-based wait function and the recovery
  sweep are both genuinely unit-testable without a real browser — create
  files in a temp directory standing in for Downloads, verify the
  event-driven wait fires promptly on a matching `_final.json` creation
  and does not fire on unrelated files or checkpoints, and verify the
  sweep correctly separates complete (recoverable) from incomplete
  (left-alone, warned-about) stale runs. Follows existing patterns in
  `Voyageur/tests/`.
- **JS side:** run-ID-tagged filename generation is a pure function,
  testable via the existing `Voyageur/tests/js/` Node harness (same
  pattern already established for `placesMatch`/`saveReloadState`).
- **Live verification:** one real end-to-end gather confirming no
  Downloads collisions across a re-run of the same record, and one
  deliberate test of the recovery sweep (start a gather via the manual
  button with no watcher running, then run `A.py` fresh and confirm it
  recovers the orphaned files correctly).
