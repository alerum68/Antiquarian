# Voyageur Downloads Handling Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Downloads-folder polling/filename-collision handoff between `Voyageur.js` and `A.py`/`FS.py` with unique per-run filenames, a real filesystem-event wait (no `time.sleep()` polling), and a startup recovery sweep for files a previous run's missing watcher left stranded.

**Architecture:** `A.py`/`FS.py` generate an 8-character run ID and pass it to the browser via a new `mgs_run` URL param; `Voyageur.js` reads it and embeds it in every filename it downloads, making every run's filenames collision-proof. The Python side's `time.sleep(1)` polling loop is replaced with a `watchdog`-based filesystem-event wait. A startup sweep in `A.py`/`FS.py` recovers any previous run's orphaned files before generating a new run ID.

**Tech Stack:** Python (`watchdog` — new dependency), plain JS (Tampermonkey userscript, no build step).

**Spec:** `docs/superpowers/specs/2026-08-13-voyageur-downloads-handling-design.md`

## Global Constraints

- No hard page-count/item-count caps in shipped code (unrelated to this plan, but a standing project rule — don't reintroduce one while touching this code).
- Timer-based waiting (`time.sleep()` polling, `setTimeout` fallback ceilings) must not be used unless there is genuinely no event/state-based alternative — this is the core requirement this plan implements for the Downloads handoff specifically.
- `LAC.py` and `HBCA.py` are out of scope — they already download directly over HTTP from Python and never touch the Downloads folder.
- The in-browser "Start Auto-Batch" manual button stays available but is not the documented entry point; `A.py`/`FS.py` (which already launch the browser themselves) remain the only supported way to start a real gather. The recovery sweep (Task 4/5) is the safety net for when the button is used anyway.

---

### Task 1: State-based final-JSON wait in `_gather_helpers.py`

**Files:**
- Modify: `Voyageur/_gather_helpers.py`
- Modify: `Voyageur/tests/test_gather_helpers.py`
- Modify: `requirements.txt`

**Interfaces:**
- Produces: `wait_for_final_json_event(downloads_dir: Path, json_prefix: str, label: str) -> Path` — blocks (no timeout) until a file matching `json_prefix` + `.json` suffix + not containing `'[checkpoint'` is created in `downloads_dir`, then returns its path. Replaces `wait_for_downloaded_json` (removed in this task).
- Produces: `_block_until_ready(ready: threading.Event) -> None` — thin, separately-patchable wrapper around `ready.wait()`, used so tests can simulate `KeyboardInterrupt` without touching global `threading.Event` behavior.

- [ ] **Step 1: Add the `watchdog` dependency**

In `requirements.txt`, add this line near the other "w"-prefixed dependency:

```
watchdog==6.0.0
```

- [ ] **Step 2: Write the failing tests**

Remove these two existing tests from `Voyageur/tests/test_gather_helpers.py` (they test the function this task removes):
- `test_wait_for_downloaded_json_finds_newest_matching_file`
- `test_wait_for_downloaded_json_keyboard_interrupt_exits`

Add these in their place:

```python
def test_wait_for_final_json_event_finds_already_existing_file(tmp_path, capsys):
    (tmp_path / "TMP_A_abc123_final.json").write_text("{}")

    result = gh.wait_for_final_json_event(tmp_path, "TMP_A_abc123_", "Final JSON")

    assert result.name == "TMP_A_abc123_final.json"
    assert "[System] Detected Final JSON: TMP_A_abc123_final.json" in capsys.readouterr().out


def test_wait_for_final_json_event_detects_file_created_after_call(tmp_path):
    import threading as _threading
    import time as _time

    def create_after_delay():
        _time.sleep(0.2)
        (tmp_path / "TMP_A_abc123_checkpoint_1.json").write_text("{}")
        _time.sleep(0.1)
        (tmp_path / "TMP_A_abc123_final.json").write_text("{}")

    _threading.Thread(target=create_after_delay, daemon=True).start()

    result = gh.wait_for_final_json_event(tmp_path, "TMP_A_abc123_", "Final JSON")

    assert result.name == "TMP_A_abc123_final.json"


def test_wait_for_final_json_event_ignores_checkpoint_and_other_prefix_files(tmp_path):
    import threading as _threading
    import time as _time

    (tmp_path / "TMP_A_abc123_checkpoint_1.json").write_text("{}")
    (tmp_path / "TMP_FS_xyz789_final.json").write_text("{}")

    def create_real_final():
        _time.sleep(0.2)
        (tmp_path / "TMP_A_abc123_final.json").write_text("{}")

    _threading.Thread(target=create_real_final, daemon=True).start()

    result = gh.wait_for_final_json_event(tmp_path, "TMP_A_abc123_", "Final JSON")

    assert result.name == "TMP_A_abc123_final.json"


def test_wait_for_final_json_event_keyboard_interrupt_exits(tmp_path, monkeypatch, capsys):
    def raise_interrupt(_ready):
        raise KeyboardInterrupt

    monkeypatch.setattr(gh, "_block_until_ready", raise_interrupt)

    with pytest.raises(SystemExit) as exc_info:
        gh.wait_for_final_json_event(tmp_path, "TMP_A_abc123_", "Final JSON")

    assert exc_info.value.code == 0
    assert "Operation cancelled by user" in capsys.readouterr().out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest Voyageur/tests/test_gather_helpers.py -v -k final_json_event`
Expected: FAIL with `AttributeError: module '_gather_helpers' has no attribute 'wait_for_final_json_event'`

- [ ] **Step 3: Implement**

In `Voyageur/_gather_helpers.py`, add these imports at the top (alongside the existing ones):

```python
import threading
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
```

Remove the entire `wait_for_downloaded_json` function, and add in its place:

```python
def _block_until_ready(ready: threading.Event) -> None:
    ready.wait()


def wait_for_final_json_event(downloads_dir: Path, json_prefix: str, label: str) -> Path:
    """State-based replacement for the old time.sleep(1) polling loop: blocks on a real
    filesystem "file created" event for this run's own final JSON instead of waking up
    once a second to re-scan the directory. No timeout, matching the polling loop's own
    previous behavior (it never gave up on its own either) - just event-driven instead of
    poll-driven, per project direction (prefer state-based waiting over timers wherever a
    real event exists)."""
    ready = threading.Event()
    found: dict = {}

    def matches(p: Path) -> bool:
        return (p.suffix.lower() == '.json' and p.name.startswith(json_prefix)
                and '[checkpoint' not in p.name)

    class _FinalJsonHandler(FileSystemEventHandler):
        def on_created(self, event):
            if event.is_directory:
                return
            p = Path(event.src_path)
            if matches(p):
                found['path'] = p
                ready.set()

    observer = Observer()
    observer.schedule(_FinalJsonHandler(), str(downloads_dir), recursive=False)
    observer.start()
    try:
        # A file matching this run's own final-JSON pattern may already exist by the time
        # the observer is attached (e.g. a very fast gather) - its on_created event would
        # never fire since it already happened, so check directly before waiting.
        existing = [p for p in downloads_dir.iterdir() if p.is_file() and matches(p)]
        if existing:
            found['path'] = max(existing, key=lambda p: p.stat().st_mtime)
            ready.set()

        _block_until_ready(ready)
    except KeyboardInterrupt:
        print("\n[System] Operation cancelled by user.")
        sys.exit(0)
    finally:
        observer.stop()
        observer.join()

    print(f"[System] Detected {label}: {found['path'].name}")
    return found['path']
```

- [ ] **Step 4: Install the dependency and run tests to verify they pass**

Run: `pip install -r requirements.txt && python -m pytest Voyageur/tests/test_gather_helpers.py -v -k final_json_event`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add Voyageur/_gather_helpers.py Voyageur/tests/test_gather_helpers.py requirements.txt
git commit -m "feat(voyageur): replace Downloads polling wait with watchdog filesystem event"
```

---

### Task 2: Run-ID-aware launch URL in `_gather_helpers.py`

**Files:**
- Modify: `Voyageur/_gather_helpers.py`
- Modify: `Voyageur/tests/test_gather_helpers.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `build_gather_launch_url(url: str, run_id: str) -> str` — pure function. `launch_gather_browser(url: str, run_id: str) -> float` — signature changes (adds `run_id` param); return type unchanged.

- [ ] **Step 1: Write the failing tests**

In `Voyageur/tests/test_gather_helpers.py`, replace the existing `test_launch_gather_browser_opens_url_and_returns_start_time` with:

```python
def test_build_gather_launch_url_appends_auto_and_run_id_with_existing_query():
    result = gh.build_gather_launch_url("https://example.com/record?id=1", "abc123")
    assert result == "https://example.com/record?id=1&mgs_auto=1&mgs_run=abc123"


def test_build_gather_launch_url_appends_auto_and_run_id_with_no_existing_query():
    result = gh.build_gather_launch_url("https://example.com/record", "abc123")
    assert result == "https://example.com/record?mgs_auto=1&mgs_run=abc123"


def test_launch_gather_browser_opens_url_and_returns_start_time(monkeypatch, capsys):
    opened = {}
    monkeypatch.setattr(gh.webbrowser, "open", lambda url: opened.setdefault("url", url))
    monkeypatch.setattr(gh.time, "time", lambda: 12345.0)

    start_time = gh.launch_gather_browser("https://example.com/record?id=1", "abc123")

    assert start_time == 12345.0
    assert opened["url"] == "https://example.com/record?id=1&mgs_auto=1&mgs_run=abc123"
    captured = capsys.readouterr()
    assert "[System] Launching browser..." in captured.out
    assert "Waiting for Tampermonkey downloads" in captured.out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest Voyageur/tests/test_gather_helpers.py -v -k "launch_url or launch_gather_browser"`
Expected: FAIL — `build_gather_launch_url` doesn't exist yet, and the existing test fails on the new call signature/expected URL.

- [ ] **Step 3: Implement**

In `Voyageur/_gather_helpers.py`, replace `launch_gather_browser` with:

```python
def build_gather_launch_url(url: str, run_id: str) -> str:
    """Appends the auto-start flag and this run's own unique ID to the gather URL so
    Voyageur.js can read both from window.location.href: mgs_auto=1 starts the batch
    automatically, mgs_run=<id> is embedded into every filename this run downloads so two
    runs (even of the identical record) never produce colliding Downloads filenames - see
    the Voyageur Downloads Handling Redesign spec."""
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}mgs_auto=1&mgs_run={run_id}"


def launch_gather_browser(url: str, run_id: str) -> float:
    start_time = time.time()
    auto_url = build_gather_launch_url(url, run_id)
    print("[System] Launching browser...")
    webbrowser.open(auto_url)
    print("\n[System] Waiting for Tampermonkey downloads (Auto-Batch will start automatically)...")
    return start_time
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest Voyageur/tests/test_gather_helpers.py -v -k "launch_url or launch_gather_browser"`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add Voyageur/_gather_helpers.py Voyageur/tests/test_gather_helpers.py
git commit -m "feat(voyageur): thread a per-run ID into the gather launch URL"
```

---

### Task 3: Orphaned-run detection in `_gather_helpers.py`

**Files:**
- Modify: `Voyageur/_gather_helpers.py`
- Modify: `Voyageur/tests/test_gather_helpers.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `find_orphaned_gather_runs(downloads_dir: Path, source_prefix: str, current_run_id: str) -> dict` — returns `{run_id: {"final": Path | None, "checkpoints": [Path, ...], "images": [Path, ...]}}` for every run ID found under `source_prefix` other than `current_run_id`.

Also removes `cleanup_stale_gather_files` (dead once every run's filenames are unique — see Task 4/5) and its test.

- [ ] **Step 1: Write the failing tests**

Remove `test_cleanup_stale_gather_files_*` tests (whatever their exact names are — search `test_gather_helpers.py` for `cleanup_stale_gather_files` and delete every test referencing it) from `Voyageur/tests/test_gather_helpers.py`.

Add:

```python
def test_find_orphaned_gather_runs_groups_by_run_id_and_finds_complete_run(tmp_path):
    (tmp_path / "TMP_A_stale1_final.json").write_text("{}")
    (tmp_path / "TMP_A_stale1_Images_00130.jpg").write_text("x")
    (tmp_path / "TMP_A_stale1_Images_00131.jpg").write_text("x")
    (tmp_path / "TMP_A_stale2_checkpoint_20.json").write_text("{}")
    (tmp_path / "TMP_A_current_final.json").write_text("{}")
    (tmp_path / "TMP_FS_other_final.json").write_text("{}")

    result = gh.find_orphaned_gather_runs(tmp_path, "TMP_A_", "current")

    assert set(result.keys()) == {"stale1", "stale2"}
    assert result["stale1"]["final"] == tmp_path / "TMP_A_stale1_final.json"
    assert sorted(p.name for p in result["stale1"]["images"]) == [
        "TMP_A_stale1_Images_00130.jpg", "TMP_A_stale1_Images_00131.jpg"]
    assert result["stale2"]["final"] is None
    assert len(result["stale2"]["checkpoints"]) == 1


def test_find_orphaned_gather_runs_returns_empty_dict_when_nothing_stale(tmp_path):
    (tmp_path / "TMP_A_current_final.json").write_text("{}")

    result = gh.find_orphaned_gather_runs(tmp_path, "TMP_A_", "current")

    assert result == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest Voyageur/tests/test_gather_helpers.py -v -k find_orphaned`
Expected: FAIL with `AttributeError: module '_gather_helpers' has no attribute 'find_orphaned_gather_runs'`

- [ ] **Step 3: Implement**

In `Voyageur/_gather_helpers.py`, remove the entire `cleanup_stale_gather_files` function, and add in its place:

```python
def find_orphaned_gather_runs(downloads_dir: Path, source_prefix: str, current_run_id: str) -> dict:
    """Groups leftover TMP_<source>_<runId>_* files in Downloads by their embedded run ID,
    excluding current_run_id (the run about to start) - these are runs whose files
    downloaded successfully but were never collected, because nothing was watching Downloads
    at the time (e.g. a gather started via Voyageur.js's own manual "Start Auto-Batch"
    button instead of through A.py/FS.py). source_prefix is the source's own fixed prefix
    ("TMP_A_" or "TMP_FS_") - the run ID is whatever comes between it and the next "_"
    (run IDs are plain hex, so they never contain one themselves). A run_id with "final" set
    is a complete, recoverable gather; one with only checkpoints/images and no final JSON
    never finished and is reported as-is by the caller rather than guessed at."""
    groups: dict = {}
    for p in downloads_dir.iterdir():
        if not p.is_file() or not p.name.startswith(source_prefix):
            continue
        rest = p.name[len(source_prefix):]
        run_id = rest.split('_', 1)[0]
        if not run_id or run_id == current_run_id:
            continue
        group = groups.setdefault(run_id, {"final": None, "checkpoints": [], "images": []})
        if p.suffix.lower() == '.json':
            if '[checkpoint' in p.name:
                group["checkpoints"].append(p)
            else:
                group["final"] = p
        elif p.suffix.lower() == '.jpg':
            group["images"].append(p)
    return groups
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest Voyageur/tests/test_gather_helpers.py -v -k find_orphaned`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add Voyageur/_gather_helpers.py Voyageur/tests/test_gather_helpers.py
git commit -m "feat(voyageur): detect orphaned gather runs left behind by a missing watcher"
```

---

### Task 4: Wire `A.py` — run ID, event wait, recovery sweep

**Files:**
- Modify: `Voyageur/A.py`

**Interfaces:**
- Consumes: `wait_for_final_json_event`, `build_gather_launch_url` (via `launch_gather_browser`'s new signature), `find_orphaned_gather_runs` (Tasks 1-3).
- Produces: `_recover_orphaned_runs(downloads_dir: Path, current_run_id: str, json_target_dir: Path, genealogy_dir: str) -> None` (module-private, no other module calls it).

No new automated test for this task: `main()` is not currently under test (it does real browser/filesystem orchestration), and `_recover_orphaned_runs` is a thin wrapper composing already-tested pieces (`find_orphaned_gather_runs`, `move_with_retry`, `move_downloaded_images`, `resolve_census_image_dir` — all covered by existing/Task-1-3 tests). Verify this task via Task 8's live check instead.

- [ ] **Step 1: Update imports**

In `Voyageur/A.py`, replace the import block:

```python
import json
import os
import re
import sys
import urllib.parse
from pathlib import Path

from dotenv import load_dotenv

import census_schema
from _gather_helpers import (
    cleanup_checkpoint_files,
    cleanup_stale_gather_files,
    launch_gather_browser,
    move_downloaded_images,
    move_with_retry,
    resolve_census_image_dir,
    wait_for_downloaded_json,
    write_archivist_json_file,
)
```

with:

```python
import json
import os
import re
import sys
import urllib.parse
import uuid
from pathlib import Path

from dotenv import load_dotenv

import census_schema
from _gather_helpers import (
    cleanup_checkpoint_files,
    find_orphaned_gather_runs,
    launch_gather_browser,
    move_downloaded_images,
    move_with_retry,
    resolve_census_image_dir,
    wait_for_final_json_event,
    write_archivist_json_file,
)
```

- [ ] **Step 2: Add the recovery-sweep function**

Add this function after `normalize_ancestry_census_gather` and before the `MAIN EXECUTION` section:

```python
def _recover_orphaned_runs(downloads_dir: Path, current_run_id: str, json_target_dir: Path,
                           genealogy_dir: str) -> None:
    """Recovers gather output left behind by a previous run that had no watcher present to
    collect it (e.g. a gather started via Voyageur.js's own manual "Start Auto-Batch" button
    instead of through this script) - moves the JSON and images into their normal project
    locations. The Ancestry-specific header-normalization/apid_db-tagging pass is skipped
    for recovered runs: it needs the originating record's dbid, parsed from A_URL, which
    isn't reliably known for a run this script didn't itself launch. An incomplete stale run
    (checkpoints only, no final JSON - the browser gather itself never finished) is reported,
    not guessed at."""
    orphans = find_orphaned_gather_runs(downloads_dir, "TMP_A_", current_run_id)
    if not orphans:
        return

    for run_id, group in orphans.items():
        if group["final"] is None:
            names = ", ".join(p.name for p in group["checkpoints"] + group["images"])
            print(f"[WARN] Found an incomplete stale gather (run {run_id}) with no final JSON - "
                  f"left in place for manual review: {names}")
            continue

        final_name = group["final"].name[len(f"TMP_A_{run_id}_"):]
        recovered_json = json_target_dir / final_name
        json_status = move_with_retry(group["final"], recovered_json, on_collision="skip")
        if json_status == "skipped":
            print(f"[System] Recovered run {run_id}: {final_name} already exists in Project folder, "
                  f"discarding the stale copy (images below are still recovered).")

        stem_parts = recovered_json.stem.split(' - ', 1)
        census_year = stem_parts[0].strip() if stem_parts and stem_parts[0].strip() else "Unknown_Year"
        raw_location = stem_parts[1].strip() if len(stem_parts) > 1 else "Unknown_Location"
        location_folder = re.sub(r'^USA\s*-\s*', '', raw_location)
        census_folder = f"{census_year} US Federal Census"
        img_target_dir = resolve_census_image_dir("Census", genealogy_dir, census_folder, location_folder)

        img_moved, img_skipped, img_failed = move_downloaded_images(
            downloads_dir, f"TMP_A_{run_id}_Images_", 0, img_target_dir, on_collision="skip")
        print(f"[System] Recovered stale run {run_id}: moved {final_name} and {img_moved} image(s) "
              f"to Project folders. NOTE: header normalization was skipped for this recovered run - "
              f"verify column names before relying on it.")
```

- [ ] **Step 3: Rewire `main()`**

Replace:

```python
    # Voyageur.js downloads via plain <a download> rather than GM_download (see CHANGELOG -
    # GM_download's permission grant proved unreliable). Chrome replaces "/" in a download
    # attribute with "_" instead of creating subfolders, so these land flat in the Downloads
    # root with a "TMP_A_"/"TMP_A_Images_" filename prefix instead of a real subfolder -
    # that prefix is also what lets this scan pick its own files out from whatever else
    # happens to be in the Downloads root.
    downloads_dir = Path.home() / "Downloads"
    json_prefix = "TMP_A_"
    image_prefix = "TMP_A_Images_"
    # A previous run that crashed/was killed mid-gather can leave same-named TMP_A_* files
    # behind; if still present when the new download lands, Chrome renames it to
    # "foo (1).json"/"foo (1).jpg" instead of overwriting, and that (1) survives into the
    # final output name. Clearing them first removes the actual cause, not just a symptom.
    cleanup_stale_gather_files(downloads_dir, json_prefix, image_prefix)

    start_time = launch_gather_browser(url)

    json_file = wait_for_downloaded_json(downloads_dir, json_prefix, start_time, "Final JSON")
```

with:

```python
    downloads_dir = Path.home() / "Downloads"
    json_target_dir = Path(program_dir) / json_dir if program_dir else Path(json_dir)
    json_target_dir.mkdir(parents=True, exist_ok=True)

    run_id = uuid.uuid4().hex[:8]
    json_prefix = f"TMP_A_{run_id}_"
    image_prefix = f"TMP_A_{run_id}_Images_"

    # Recover anything a previous run left stranded before this run's own files - which use
    # a fresh, guaranteed-unique run_id - are even downloaded. See the Downloads Handling
    # Redesign spec (docs/superpowers/specs/2026-08-13-voyageur-downloads-handling-design.md).
    _recover_orphaned_runs(downloads_dir, run_id, json_target_dir, genealogy_dir)

    start_time = launch_gather_browser(url, run_id)

    json_file = wait_for_final_json_event(downloads_dir, json_prefix, "Final JSON")
```

Then, further down, replace:

```python
    print("\n[System] Processing extracted files...")

    json_target_dir = Path(program_dir) / json_dir if program_dir else Path(json_dir)
    json_target_dir.mkdir(parents=True, exist_ok=True)

    final_json = json_target_dir / json_file.name[len(json_prefix):]
```

with:

```python
    print("\n[System] Processing extracted files...")

    final_json = json_target_dir / json_file.name[len(json_prefix):]
```

(only the two now-redundant `json_target_dir` lines are removed — it's already built above, before the recovery sweep).

- [ ] **Step 4: Verify by reading the full function**

Read `Voyageur/A.py`'s `main()` top to bottom and confirm: `cleanup_stale_gather_files` no longer appears anywhere in the file, `json_prefix`/`image_prefix` are both built from `run_id` before first use, and `json_target_dir` is computed exactly once.

- [ ] **Step 5: Run the existing test suite**

Run: `python -m pytest Voyageur/tests/test_a.py -v`
Expected: PASS (unchanged — this task doesn't touch any function `test_a.py` covers)

- [ ] **Step 6: Commit**

```bash
git add Voyageur/A.py
git commit -m "feat(voyageur): give A.py unique run IDs, event-driven wait, and a recovery sweep"
```

---

### Task 5: Wire `FS.py` — run ID, event wait, full recovery sweep

**Files:**
- Modify: `Voyageur/FS.py`

**Interfaces:**
- Consumes: `wait_for_final_json_event`, `find_orphaned_gather_runs` (Tasks 1, 3).
- Produces: `convert_raw_gather_to_final(raw_data: dict) -> Tuple[dict, Optional[str]]` — extracted from `main()`'s existing conversion logic so the recovery sweep can reuse it. `_recover_orphaned_runs(downloads_dir: Path, current_run_id: str, json_target_dir: Path, genealogy_dir: str, on_collision: str) -> None` (module-private).

- [ ] **Step 1: Write the failing test for the extracted conversion function**

Add to `Voyageur/tests/test_fs.py` (check the file's existing imports/fixtures first and match its style — it already imports the module as e.g. `import FS`):

```python
def test_convert_raw_gather_to_final_routes_census_collections_through_census_path():
    raw = {
        "collection_title": "United States, Census, 1880",
        "items": [
            {
                "item_id": "abc",
                "citation_text": (
                    '"1880 Census," database with images, FamilySearch '
                    '(https://familysearch.org/x : accessed 1 Jan 2026), Alabama > Autauga > '
                    'image 1 of 1; citing NARA microfilm publication T9 (Washington D.C.: '
                    'National Archives and Records Administration, n.d.).'
                ),
                "rows": [{"columns": {"Name": "John Smith"}, "person_ark": "ARK1"}],
            }
        ],
    }

    final_data, clean_name = FS.convert_raw_gather_to_final(raw)

    assert "pages" in final_data
    assert clean_name is None or clean_name.endswith(".json")


def test_convert_raw_gather_to_final_routes_non_census_collections_through_universal_path():
    raw = {
        "collection_title": "Quebec, Catholic Parish Registers",
        "items": [{"item_id": "abc", "citation_text": "", "rows": []}],
    }

    final_data, clean_name = FS.convert_raw_gather_to_final(raw)

    assert "sheets" in final_data
    assert clean_name is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest Voyageur/tests/test_fs.py -v -k convert_raw_gather_to_final`
Expected: FAIL with `AttributeError: module 'FS' has no attribute 'convert_raw_gather_to_final'`

- [ ] **Step 3: Extract the conversion function**

In `Voyageur/FS.py`, add this function directly above `main()`:

```python
def convert_raw_gather_to_final(raw_data: dict) -> Tuple[dict, Optional[str]]:
    """Converts a raw FamilySearch scrape dict into (final_data, clean_name) - clean_name is
    None when no sheet/record carried enough location info to build one (see
    build_clean_census_filename), in which case the caller falls back to a name derived from
    the raw download's own filename instead. Pulled out of main() so the startup recovery
    sweep can run the exact same conversion on a stale run's raw JSON, rather than
    duplicating this logic."""
    items_raw = raw_data.get("items", [])
    catalog_items = dedup_catalog_items(items_raw)
    record_family = detect_record_family_from_raw(raw_data, catalog_items)

    if record_family == "census":
        raw_census = build_census_json(raw_data, items_raw, catalog_items)
        final_data = normalize_familysearch_census_gather(raw_census, raw_data.get("collection_title", ""))
        clean_name = build_clean_census_filename(raw_census.get("census_year", ""), final_data)
    else:
        final_data = build_universal_json(raw_data, items_raw, catalog_items, record_family)
        validate_against_commissioner(final_data, record_family, raw_data.get("collection_title", ""))
        clean_name = None

    return final_data, clean_name
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest Voyageur/tests/test_fs.py -v -k convert_raw_gather_to_final`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add Voyageur/FS.py Voyageur/tests/test_fs.py
git commit -m "refactor(voyageur): extract FS.py's raw-to-final conversion into its own function"
```

- [ ] **Step 6: Update imports**

Replace the `_gather_helpers` import block in `Voyageur/FS.py`:

```python
from _gather_helpers import (
    cleanup_checkpoint_files,
    cleanup_stale_gather_files,
    launch_gather_browser,
    move_downloaded_images,
    resolve_census_image_dir,
    wait_for_downloaded_json,
    write_archivist_json_file,
)
```

with:

```python
from _gather_helpers import (
    cleanup_checkpoint_files,
    find_orphaned_gather_runs,
    launch_gather_browser,
    move_downloaded_images,
    move_with_retry,
    resolve_census_image_dir,
    wait_for_final_json_event,
    write_archivist_json_file,
)
```

Add `import uuid` alongside the other stdlib imports at the top of the file.

- [ ] **Step 7: Add the recovery-sweep function**

Add this function directly above `main()` (after `convert_raw_gather_to_final`):

```python
def _recover_orphaned_runs(downloads_dir: Path, current_run_id: str, json_target_dir: Path,
                           genealogy_dir: str, on_collision: str) -> None:
    """Recovers gather output left behind by a previous run that had no watcher present to
    collect it. Unlike A.py's recovery, this completes the FULL pipeline (including the
    raw-to-final conversion) since FS's conversion needs nothing beyond the raw JSON itself -
    no external context like A.py's dbid is required."""
    orphans = find_orphaned_gather_runs(downloads_dir, "TMP_FS_", current_run_id)
    if not orphans:
        return

    for run_id, group in orphans.items():
        if group["final"] is None:
            names = ", ".join(p.name for p in group["checkpoints"] + group["images"])
            print(f"[WARN] Found an incomplete stale gather (run {run_id}) with no final JSON - "
                  f"left in place for manual review: {names}")
            continue

        raw_data = json.loads(_read_text_with_retry(group["final"]))
        final_data, clean_name = convert_raw_gather_to_final(raw_data)
        out_name = clean_name or group["final"].name[len(f"TMP_FS_{run_id}_"):]
        recovered_json = json_target_dir / out_name

        if on_collision == "skip" and recovered_json.exists():
            print(f"[System] Recovered run {run_id}: {out_name} already exists in Project folder, "
                  f"discarding the stale copy (images below are still recovered).")
        else:
            recovered_json.write_text(json.dumps(final_data, indent=2, ensure_ascii=False), encoding="utf-8")
        _unlink_with_retry(group["final"])

        stem = re.sub(r' - FS$', '', recovered_json.stem)
        stem_parts = stem.split(' - ', 1)
        census_year = stem_parts[0].strip() if stem_parts and stem_parts[0].strip() else "Unknown_Year"
        location_folder = stem_parts[1].strip() if len(stem_parts) > 1 else "Unknown_Location"
        census_folder = f"{census_year} US Federal Census"
        img_target_dir = resolve_census_image_dir("Census", genealogy_dir, census_folder, location_folder)

        img_moved, img_skipped, img_failed = move_downloaded_images(
            downloads_dir, f"TMP_FS_{run_id}_Images_", 0, img_target_dir, on_collision="skip")
        print(f"[System] Recovered stale run {run_id}: wrote {out_name} and moved {img_moved} image(s) "
              f"to Project folders.")
```

- [ ] **Step 8: Rewire `main()`**

Replace:

```python
    downloads_dir = Path.home() / "Downloads"
    json_prefix = "TMP_FS_"
    image_prefix = "TMP_FS_Images_"
    # A previous run that crashed/was killed mid-gather can leave same-named TMP_FS_* files
    # behind; if still present when the new download lands, Chrome renames it to
    # "foo (1).json"/"foo (1).jpg" instead of overwriting, and that (1) survives into the
    # final output name. Clearing them first removes the actual cause, not just a symptom.
    cleanup_stale_gather_files(downloads_dir, json_prefix, image_prefix)

    start_time = launch_gather_browser(url)

    raw_json_file = wait_for_downloaded_json(downloads_dir, json_prefix, start_time, "raw gather JSON")

    raw_data = json.loads(_read_text_with_retry(raw_json_file))
    items_raw = raw_data.get("items", [])
    catalog_items = dedup_catalog_items(items_raw)
    record_family = detect_record_family_from_raw(raw_data, catalog_items)

    clean_name = None
    if record_family == "census":
        print("\n[System] Converting raw scrape into census Gather JSON...")
        raw_census = build_census_json(raw_data, items_raw, catalog_items)
        final_data = normalize_familysearch_census_gather(raw_census, raw_data.get("collection_title", ""))
        clean_name = build_clean_census_filename(raw_census.get("census_year", ""), final_data)
    else:
        print("\n[System] Converting raw scrape into the universal Gather JSON...")
        final_data = build_universal_json(raw_data, items_raw, catalog_items, record_family)
        validate_against_commissioner(final_data, record_family, raw_data.get("collection_title", ""))

    json_target_dir = Path(program_dir) / json_dir if program_dir else Path(json_dir)
    json_target_dir.mkdir(parents=True, exist_ok=True)
```

with:

```python
    downloads_dir = Path.home() / "Downloads"
    json_target_dir = Path(program_dir) / json_dir if program_dir else Path(json_dir)
    json_target_dir.mkdir(parents=True, exist_ok=True)

    run_id = uuid.uuid4().hex[:8]
    json_prefix = f"TMP_FS_{run_id}_"
    image_prefix = f"TMP_FS_{run_id}_Images_"

    # Recover anything a previous run left stranded before this run's own files - which use
    # a fresh, guaranteed-unique run_id - are even downloaded. See the Downloads Handling
    # Redesign spec (docs/superpowers/specs/2026-08-13-voyageur-downloads-handling-design.md).
    _recover_orphaned_runs(downloads_dir, run_id, json_target_dir, genealogy_dir, on_collision)

    start_time = launch_gather_browser(url, run_id)

    raw_json_file = wait_for_final_json_event(downloads_dir, json_prefix, "raw gather JSON")

    raw_data = json.loads(_read_text_with_retry(raw_json_file))
    print("\n[System] Converting raw scrape into Gather JSON...")
    final_data, clean_name = convert_raw_gather_to_final(raw_data)
```

- [ ] **Step 9: Run the existing test suite**

Run: `python -m pytest Voyageur/tests/test_fs.py -v`
Expected: PASS (unchanged behavior for everything `test_fs.py` already covers, since `convert_raw_gather_to_final` reproduces the prior inline logic exactly)

- [ ] **Step 10: Commit**

```bash
git add Voyageur/FS.py
git commit -m "feat(voyageur): give FS.py unique run IDs, event-driven wait, and a full recovery sweep"
```

---

### Task 6: Wire `Voyageur.js` — Ancestry section run-ID filenames

**Files:**
- Modify: `Voyageur/Voyageur.js`

**Interfaces:**
- Consumes: `mgs_run` URL query parameter (produced by Task 4's `build_gather_launch_url`).
- Produces: nothing new for other tasks — pure filename-construction wiring.

No new automated test: the change is two one-line edits to string arguments passed into an already-DOM-heavy download function (`triggerBlobDownload`, which takes a real `Blob` and manipulates real `<a>` elements). Extracting these into pure functions solely to unit-test a template-literal change would be over-engineering for what it tests. Verify via Task 8's live check.

- [ ] **Step 1: Add the run ID constant**

In `runAncestryGather()`, immediately after the existing `const shouldAutoStart = window.location.href.includes('mgs_auto=1');` line, add:

```js
const runId = new URLSearchParams(window.location.search).get('mgs_run') || 'norun';
```

- [ ] **Step 2: Thread it into the image download**

In `downloadCurrentImage()`, find:

```js
                        if (response.status === 200) {
                            triggerBlobDownload(response.response, imgFileName, 'A/Images');
```

Change to:

```js
                        if (response.status === 200) {
                            triggerBlobDownload(response.response, imgFileName, `A_${runId}/Images`);
```

- [ ] **Step 3: Thread it into the JSON download**

In `triggerJsonDownload`, find:

```js
        function triggerJsonDownload(jsonString, jsonFileName) {
            triggerBlobDownload(new Blob([jsonString], {type: 'application/json;charset=utf-8;'}), jsonFileName, 'A');
        }
```

Change to:

```js
        function triggerJsonDownload(jsonString, jsonFileName) {
            triggerBlobDownload(new Blob([jsonString], {type: 'application/json;charset=utf-8;'}), jsonFileName, `A_${runId}`);
        }
```

- [ ] **Step 4: Verify syntax**

Run: `node --check Voyageur/Voyageur.js`
Expected: no output (clean parse)

- [ ] **Step 5: Run the JS test suite**

Run: `cd Voyageur/tests/js && node --test test_stop_conditions.mjs`
Expected: PASS (unchanged — this task doesn't touch any function the harness covers)

- [ ] **Step 6: Commit**

```bash
git add Voyageur/Voyageur.js
git commit -m "feat(voyageur): tag Ancestry gather downloads with the run ID"
```

---

### Task 7: Wire `Voyageur.js` — FamilySearch section run-ID filenames

**Files:**
- Modify: `Voyageur/Voyageur.js`

**Interfaces:**
- Consumes: `mgs_run` URL query parameter (produced by Task 5's `launch_gather_browser`/`build_gather_launch_url`).
- Produces: nothing new — pure filename-construction wiring, same reasoning as Task 6 for why no new automated test is added.

- [ ] **Step 1: Add the run ID constant**

In `runFamilySearchGather()`, immediately after the existing `const shouldAutoStart = window.location.href.includes('mgs_auto=1');` line, add:

```js
const runId = new URLSearchParams(window.location.search).get('mgs_run') || 'norun';
```

- [ ] **Step 2: Thread it into the JSON download**

In `triggerFsJsonDownload`, find:

```js
            link.setAttribute('download', `TMP_FS_${jsonFileName}`);
```

Change to:

```js
            link.setAttribute('download', `TMP_FS_${runId}_${jsonFileName}`);
```

- [ ] **Step 3: Thread it into the image download**

In `downloadFsImage`'s `onMessage` handler, find:

```js
                        link.setAttribute('download', `TMP_FS_Images_${event.data.fileName}`);
```

Change to:

```js
                        link.setAttribute('download', `TMP_FS_${runId}_Images_${event.data.fileName}`);
```

- [ ] **Step 4: Verify syntax**

Run: `node --check Voyageur/Voyageur.js`
Expected: no output (clean parse)

- [ ] **Step 5: Run the JS test suite**

Run: `cd Voyageur/tests/js && node --test test_stop_conditions.mjs`
Expected: PASS (unchanged)

- [ ] **Step 6: Commit**

```bash
git add Voyageur/Voyageur.js
git commit -m "feat(voyageur): tag FamilySearch gather downloads with the run ID"
```

---

### Task 8: Live verification

**Files:** none (manual verification only)

- [ ] **Step 1: Bump the userscript version**

In `Voyageur/Voyageur.js`, increment `// @version` (currently `0.3.7`) to `0.3.8` so Tampermonkey's disk-tracking picks up every change from Tasks 6-7.

- [ ] **Step 2: Confirm the full Python test suite is green**

Run: `python -m pytest Voyageur/ -v`
Expected: PASS, no failures, no collection errors (confirms Tasks 1-5 didn't break anything outside their own test files)

- [ ] **Step 3: Re-run the same record twice in a row (collision check)**

With the Ancestry tab kept in focus throughout (per the project's standing note on Chrome background-tab timer throttling), run `A.py` against the same test record twice back to back. Confirm: no `(1)`/`(2)`-suffixed files ever appear in Downloads, and both runs produce correctly-named final output files in the project JSON folder.

- [ ] **Step 4: Recovery sweep check**

Start a gather via `Voyageur.js`'s own "Start Auto-Batch" button directly in the browser (bypassing `A.py`), let a few pages download, then stop it. Run `A.py` fresh against a *different* URL. Confirm the console output reports recovering the first run's stranded files into the project folders before the new gather begins.

- [ ] **Step 5: Commit the version bump**

```bash
git add Voyageur/Voyageur.js
git commit -m "chore(voyageur): bump userscript version for Downloads handling redesign"
```
