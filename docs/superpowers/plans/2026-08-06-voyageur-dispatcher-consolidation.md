# Voyageur Dispatcher Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **SUPERSEDED:** This plan is historical. Its checklist steps marked `- [ ]` were superseded and never executed as written; see the live tracker `docs/plans/task.md` for the actual disposition.

**Goal:** Make `Voyageur/Voyageur.py` a real ~30-line dispatcher that calls the maintained `A.py`/`FS.py`/`LAC.py` provider files instead of running its own 1300-line frozen fork, fix `Scriptorium.py`'s LAC dispatch so it reaches the real `LAC.py`'s `volume`/`reel` subcommands, and deduplicate the ~70-90 lines of gather boilerplate `A.py` and `FS.py` currently copy-paste between each other.

**Architecture:** `Voyageur/_retry_utils.py` is renamed to `Voyageur/_gather_helpers.py` and gains five new shared functions (verbatim extractions of A.py/FS.py's duplicated download-wait/image-move/image-dir-resolution/Archivist-write-back logic). `A.py` and `FS.py` call into these instead of their own inline copies. `Voyageur.py` is rewritten to import and delegate to `A`/`FS`/`LAC`'s real `main()` based on `sys.argv[1]`. `Scriptorium.py`'s LAC dispatch branch gains the `volume`/`reel` subcommand token the real `LAC.py`'s argparse now requires.

**Tech Stack:** Python, pytest, pathlib, argparse (LAC.py, unchanged), CustomTkinter (Scriptorium.py, unchanged).

## Global Constraints

- No behavior change to `A.py`/`FS.py`/`LAC.py`'s actual gather logic — every extracted function is a verbatim lift; same inputs produce the same outputs.
- No change to `Commissioner.normalization`/`record_registry` scope, and no change to `census_schema.py`.
- `FS.py`'s own `_read_text_with_retry`/`_unlink_with_retry` stay in `FS.py` — not duplicated into `_gather_helpers.py`.
- No new LAC features. Only fix: forward `LAC_HARVEST_VOLUME` as `volume --volume X` and `LAC_URL` as `reel --url <url>`.
- No fix to the separate, pre-existing `LAC_MAX_WORKERS`/`LAC_RECORD_TYPE`/`LAC_VOLUME` vs. `Scriptorium.py`'s actual env-var names mismatch — out of scope, already flagged in the spec for a future task.
- No AI attribution, "Co-Authored-By", or Claude stamps in any commit message.
- Full `pytest` suite (run from repo root) must stay green after every task, not just at the end.

---

### Task 1: Rename `_retry_utils.py` to `_gather_helpers.py`, add five shared gather functions

**Files:**
- Rename: `Voyageur/_retry_utils.py` → `Voyageur/_gather_helpers.py`
- Modify: `Voyageur/A.py` (import line only, `_retry_utils` → `_gather_helpers`)
- Modify: `Voyageur/FS.py` (import line only, `_retry_utils` → `_gather_helpers`)
- Test: `Voyageur/tests/test_gather_helpers.py` (new)

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces (used by Tasks 2 and 3):
  - `launch_gather_browser(url: str) -> float`
  - `wait_for_downloaded_json(downloads_dir: Path, prefix: str, start_time: float, label: str) -> Path`
  - `move_downloaded_images(downloads_dir: Path, image_prefix: str, start_time: float, img_target_dir: Path) -> int`
  - `resolve_census_image_dir(base_img_setting: str, program_dir: str, census_folder: str, location_folder: str) -> Path`
  - `write_archivist_json_file(final_json_name: str) -> None`
  - Existing (unchanged): `move_with_retry(src: Path, dst: Path, attempts: int = 5, delay: float = 0.5) -> None`, `cleanup_checkpoint_files(downloads_dir: Path, prefix: str, start_time: float) -> None`

- [ ] **Step 1: Rename the file with git**

```bash
git mv Voyageur/_retry_utils.py Voyageur/_gather_helpers.py
```

- [ ] **Step 2: Write the failing tests for the five new functions**

Create `Voyageur/tests/test_gather_helpers.py`:

```python
import os
import time as time_module

import pytest

import _gather_helpers as gh


def test_launch_gather_browser_opens_url_and_returns_start_time(monkeypatch, capsys):
    opened = {}
    monkeypatch.setattr(gh.webbrowser, "open", lambda url: opened.setdefault("url", url))
    monkeypatch.setattr(gh.time, "time", lambda: 12345.0)

    start_time = gh.launch_gather_browser("https://example.com/record?id=1")

    assert start_time == 12345.0
    assert opened["url"] == "https://example.com/record?id=1&mgs_auto=1"
    captured = capsys.readouterr()
    assert "[System] Launching browser..." in captured.out
    assert "Waiting for Tampermonkey downloads" in captured.out


def test_wait_for_downloaded_json_finds_newest_matching_file(tmp_path, capsys):
    start_time = time_module.time()

    old = tmp_path / "TMP_A_old.json"
    old.write_text("{}")
    os.utime(old, (start_time - 100, start_time - 100))

    checkpoint = tmp_path / "TMP_A_run[checkpoint].json"
    checkpoint.write_text("{}")
    os.utime(checkpoint, (start_time + 1, start_time + 1))

    wrong_prefix = tmp_path / "TMP_FS_other.json"
    wrong_prefix.write_text("{}")
    os.utime(wrong_prefix, (start_time + 1, start_time + 1))

    newest = tmp_path / "TMP_A_final.json"
    newest.write_text("{}")
    os.utime(newest, (start_time + 2, start_time + 2))

    result = gh.wait_for_downloaded_json(tmp_path, "TMP_A_", start_time, "Final JSON")

    assert result == newest
    assert "[System] Detected Final JSON: TMP_A_final.json" in capsys.readouterr().out


def test_wait_for_downloaded_json_keyboard_interrupt_exits(tmp_path, monkeypatch, capsys):
    def raise_interrupt(_):
        raise KeyboardInterrupt

    monkeypatch.setattr(gh.time, "sleep", raise_interrupt)

    with pytest.raises(SystemExit) as exc_info:
        gh.wait_for_downloaded_json(tmp_path, "TMP_A_", time_module.time(), "Final JSON")

    assert exc_info.value.code == 0
    assert "Operation cancelled by user" in capsys.readouterr().out


def test_move_downloaded_images_moves_matches_and_counts(tmp_path):
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    target = tmp_path / "target"
    target.mkdir()
    start_time = time_module.time()

    (downloads / "TMP_A_Images_page1.jpg").write_bytes(b"x")
    (downloads / "TMP_A_Images_page2.jpg").write_bytes(b"x")
    unrelated = downloads / "other.jpg"
    unrelated.write_bytes(b"x")

    count = gh.move_downloaded_images(downloads, "TMP_A_Images_", start_time, target)

    assert count == 2
    assert (target / "page1.jpg").exists()
    assert (target / "page2.jpg").exists()
    assert unrelated.exists()


def test_move_downloaded_images_tolerates_failed_move(tmp_path, monkeypatch, capsys):
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    target = tmp_path / "target"
    target.mkdir()
    start_time = time_module.time()
    (downloads / "TMP_A_Images_bad.jpg").write_bytes(b"x")

    def fail_move(src, dst):
        raise OSError("locked")

    monkeypatch.setattr(gh, "move_with_retry", fail_move)

    count = gh.move_downloaded_images(downloads, "TMP_A_Images_", start_time, target)

    assert count == 0
    assert "[ERROR] Could not move" in capsys.readouterr().out


def test_resolve_census_image_dir_absolute_base(tmp_path):
    abs_base = tmp_path / "AbsCensus"

    result = gh.resolve_census_image_dir(str(abs_base), "", "1900 US Federal Census", "USA - Ohio")

    assert result == abs_base / "1900 US Federal Census" / "USA - Ohio"
    assert result.exists()


def test_resolve_census_image_dir_relative_to_media_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_DIR", "Media")
    program_dir = tmp_path / "program"

    result = gh.resolve_census_image_dir("Census", str(program_dir), "1900 US Federal Census", "Ohio")

    assert result == program_dir / "Media" / "Census" / "1900 US Federal Census" / "Ohio"
    assert result.exists()


def test_write_archivist_json_file_writes_expected_key(monkeypatch):
    calls = []
    monkeypatch.setattr(gh, "set_key", lambda path, key, value: calls.append((path, key, value)))

    gh.write_archivist_json_file("1900 - Ohio.json")

    assert len(calls) == 1
    path, key, value = calls[0]
    assert key == "JSON_FILE"
    assert value == "1900 - Ohio.json"
    assert path.endswith(os.path.join("Archivist", ".env"))
```

- [ ] **Step 3: Run the new tests to verify they fail**

Run: `pytest Voyageur/tests/test_gather_helpers.py -v`
Expected: FAIL — `_gather_helpers` has no attribute `launch_gather_browser` (etc.), since the module doesn't have these functions yet.

- [ ] **Step 4: Add the five functions to `_gather_helpers.py`**

Replace the full contents of `Voyageur/_gather_helpers.py` with:

```python
"""
Shared gather helpers for Voyageur's provider scripts (A.py, FS.py). Chrome (or antivirus
scanning it) can still hold a freshly-downloaded file open for a brief moment after it
appears in the folder listing, so an immediate shutil.move/unlink can lose to a transient
PermissionError/WinError 32 on Windows - these retry helpers ride out that window instead
of letting a gather crash with the file left stranded. The remaining functions here are the
Tampermonkey-download-wait/image-move/image-dir-resolution/Archivist-write-back logic that
used to be duplicated between A.py and FS.py's own main().
"""

import os
import shutil
import sys
import time
import webbrowser
from pathlib import Path

from dotenv import set_key


def move_with_retry(src: Path, dst: Path, attempts: int = 5, delay: float = 0.5) -> None:
    for attempt in range(1, attempts + 1):
        try:
            shutil.move(str(src), str(dst))
            return
        except OSError as e:
            if attempt == attempts:
                print(f"[ERROR] Could not move {src.name} to {dst} after {attempts} attempts: {e}")
                raise
            time.sleep(delay)


def cleanup_checkpoint_files(downloads_dir: Path, prefix: str, start_time: float) -> None:
    """Deletes this run's own leftover periodic checkpoint downloads (see
    downloadCheckpointJson in Voyageur.js) now that the final combined JSON has already
    been moved/written out - they're superseded and, unlike the final JSON, nothing else
    ever cleans them up, so a long gather would otherwise leave several of them sitting in
    the Downloads folder permanently. Best-effort: a checkpoint that can't be deleted (still
    briefly locked, already gone) is left in place rather than raising."""
    for p in downloads_dir.iterdir():
        if (p.is_file() and p.suffix.lower() == '.json' and p.name.startswith(prefix)
                and '[checkpoint' in p.name and p.stat().st_mtime >= start_time):
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass


def launch_gather_browser(url: str) -> float:
    start_time = time.time()
    auto_url = url + ("&mgs_auto=1" if "?" in url else "?mgs_auto=1")
    print("[System] Launching browser...")
    webbrowser.open(auto_url)
    print("\n[System] Waiting for Tampermonkey downloads (Auto-Batch will start automatically)...")
    return start_time


def wait_for_downloaded_json(downloads_dir: Path, prefix: str, start_time: float, label: str) -> Path:
    json_file = None
    try:
        while True:
            # noinspection broad-exception
            try:
                candidates = [
                    p for p in downloads_dir.iterdir()
                    if p.is_file() and p.suffix.lower() == '.json'
                    and p.name.startswith(prefix)
                    and p.stat().st_mtime >= start_time
                    and '[checkpoint' not in p.name
                ]
                if candidates:
                    json_file = max(candidates, key=lambda p: p.stat().st_mtime)
                    print(f"[System] Detected {label}: {json_file.name}")
            except OSError:
                pass

            if json_file:
                break
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[System] Operation cancelled by user.")
        sys.exit(0)
    return json_file


def move_downloaded_images(downloads_dir: Path, image_prefix: str, start_time: float,
                            img_target_dir: Path) -> int:
    img_count = 0
    image_candidates = [
        p for p in downloads_dir.iterdir()
        if p.is_file() and p.suffix.lower() == '.jpg'
        and p.name.startswith(image_prefix) and p.stat().st_mtime >= start_time
    ]
    for file_path in image_candidates:
        # noinspection broad-exception
        try:
            final_img = img_target_dir / file_path.name[len(image_prefix):]
            move_with_retry(file_path, final_img)
            img_count += 1
        except Exception as e:
            print(f"[ERROR] Could not move image {file_path.name}: {e}")
    return img_count


def resolve_census_image_dir(base_img_setting: str, program_dir: str, census_folder: str,
                              location_folder: str) -> Path:
    if os.path.isabs(base_img_setting):
        base_img_dir = Path(base_img_setting)
    else:
        media_setting = os.getenv("MEDIA_DIR", "Media")
        base_media_dir = Path(media_setting) if os.path.isabs(media_setting) else (
            Path(program_dir) / media_setting if program_dir else Path(media_setting))
        base_img_dir = base_media_dir / base_img_setting
    img_target_dir = base_img_dir / census_folder / location_folder
    img_target_dir.mkdir(parents=True, exist_ok=True)
    return img_target_dir


def write_archivist_json_file(final_json_name: str) -> None:
    set_key(str(Path(__file__).resolve().parent.parent / "Archivist" / ".env"), "JSON_FILE", final_json_name)
```

- [ ] **Step 5: Run the new tests to verify they pass**

Run: `pytest Voyageur/tests/test_gather_helpers.py -v`
Expected: PASS (8 tests)

- [ ] **Step 6: Update A.py's and FS.py's import lines so they resolve against the renamed module**

In `Voyageur/A.py`, change:
```python
old_string:
from _retry_utils import cleanup_checkpoint_files, move_with_retry
```
```python
new_string:
from _gather_helpers import cleanup_checkpoint_files, move_with_retry
```

In `Voyageur/FS.py`, change:
```python
old_string:
from _retry_utils import cleanup_checkpoint_files, move_with_retry
```
```python
new_string:
from _gather_helpers import cleanup_checkpoint_files, move_with_retry
```

- [ ] **Step 7: Run the full test suite to confirm nothing broke**

Run: `pytest Voyageur/tests/ -v`
Expected: all tests PASS (existing `test_census_schema.py`, `test_fs.py`, `test_lac.py` unaffected; new `test_gather_helpers.py` passes).

- [ ] **Step 8: Commit**

```bash
git add Voyageur/_gather_helpers.py Voyageur/A.py Voyageur/FS.py Voyageur/tests/test_gather_helpers.py
git commit -m "Rename _retry_utils.py to _gather_helpers.py, add shared gather-boilerplate functions"
```

---

### Task 2: Consolidate A.py's duplicated gather boilerplate into `_gather_helpers`

**Files:**
- Modify: `Voyageur/A.py`

**Interfaces:**
- Consumes: the five functions from Task 1 (`launch_gather_browser`, `wait_for_downloaded_json`, `move_downloaded_images`, `resolve_census_image_dir`, `write_archivist_json_file`), plus existing `cleanup_checkpoint_files`/`move_with_retry`.
- Produces: nothing consumed by later tasks — `A.main()`'s external signature and behavior are unchanged.

This task has no new tests of its own (this refactor doesn't change `A.py`'s untested `main()` in a way Task 1's helper tests don't already cover) — its test cycle is a compile check plus a full-suite regression run.

- [ ] **Step 1: Update the import block**

In `Voyageur/A.py`, replace the full import block (lines 1-13) with:

```python
old_string:
import json
import os
import re
import sys
import time
import urllib.parse
import webbrowser
from pathlib import Path

from dotenv import load_dotenv, set_key

import census_schema
from _gather_helpers import cleanup_checkpoint_files, move_with_retry
```

```python
new_string:
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
    launch_gather_browser,
    move_downloaded_images,
    move_with_retry,
    resolve_census_image_dir,
    wait_for_downloaded_json,
    write_archivist_json_file,
)
```

- [ ] **Step 2: Replace the browser-launch block**

```python
old_string:
    start_time = time.time()
    auto_url = url + ("&mgs_auto=1" if "?" in url else "?mgs_auto=1")
    print("[System] Launching browser...")
    webbrowser.open(auto_url)

    print("\n[System] Waiting for Tampermonkey downloads (Auto-Batch will start automatically)...")
```

```python
new_string:
    start_time = launch_gather_browser(url)
```

- [ ] **Step 3: Replace the download-polling block**

```python
old_string:
    downloads_dir = Path.home() / "Downloads"
    json_prefix = "TMP_A_"
    image_prefix = "TMP_A_Images_"
    json_file = None

    try:
        while True:
            # noinspection broad-exception
            try:
                # image_prefix files are always .jpg (never .json), so the suffix check
                # above already excludes them - no separate "not an image" check needed.
                candidates = [
                    p for p in downloads_dir.iterdir()
                    if p.is_file() and p.suffix.lower() == '.json'
                    and p.name.startswith(json_prefix)
                    and p.stat().st_mtime >= start_time
                    and '[checkpoint' not in p.name
                ]
                if candidates:
                    json_file = max(candidates, key=lambda p: p.stat().st_mtime)
                    print(f"[System] Detected Final JSON: {json_file.name}")
            except OSError:
                pass

            if json_file:
                break
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[System] Operation cancelled by user.")
        sys.exit(0)
```

```python
new_string:
    downloads_dir = Path.home() / "Downloads"
    json_prefix = "TMP_A_"
    image_prefix = "TMP_A_Images_"
    json_file = wait_for_downloaded_json(downloads_dir, json_prefix, start_time, "Final JSON")
```

- [ ] **Step 4: Replace the Archivist `.env` write-back call**

```python
old_string:
    set_key(str(Path(__file__).resolve().parent.parent / "Archivist" / ".env"), "JSON_FILE", final_json.name)
```

```python
new_string:
    write_archivist_json_file(final_json.name)
```

- [ ] **Step 5: Replace the image-directory resolution block**

```python
old_string:
    if os.path.isabs(base_img_setting):
        base_img_dir = Path(base_img_setting)
    else:
        media_setting = os.getenv("MEDIA_DIR", "Media")
        base_media_dir = Path(media_setting) if os.path.isabs(media_setting) else (
            Path(program_dir) / media_setting if program_dir else Path(media_setting))
        base_img_dir = base_media_dir / base_img_setting
    img_target_dir = base_img_dir / census_folder / location_folder
    img_target_dir.mkdir(parents=True, exist_ok=True)
```

```python
new_string:
    img_target_dir = resolve_census_image_dir(base_img_setting, program_dir, census_folder, location_folder)
```

- [ ] **Step 6: Replace the image-move loop**

```python
old_string:
    img_count = 0
    image_candidates = [
        p for p in downloads_dir.iterdir()
        if p.is_file() and p.suffix.lower() == '.jpg'
        and p.name.startswith(image_prefix) and p.stat().st_mtime >= start_time
    ]
    for file_path in image_candidates:
        # noinspection broad-exception
        try:
            final_img = img_target_dir / file_path.name[len(image_prefix):]
            move_with_retry(file_path, final_img)
            img_count += 1
        except Exception as e:
            print(f"[ERROR] Could not move image {file_path.name}: {e}")

    print(f"[System] Moved JSON and {img_count} images to Project folders.")
```

```python
new_string:
    img_count = move_downloaded_images(downloads_dir, image_prefix, start_time, img_target_dir)
    print(f"[System] Moved JSON and {img_count} images to Project folders.")
```

- [ ] **Step 7: Compile-check the file**

Run: `python -m py_compile Voyageur/A.py`
Expected: no output, exit code 0.

- [ ] **Step 8: Run the full test suite to confirm nothing broke**

Run: `pytest Voyageur/tests/ -v`
Expected: all tests PASS.

- [ ] **Step 9: Commit**

```bash
git add Voyageur/A.py
git commit -m "Consolidate A.py's gather boilerplate into _gather_helpers"
```

---

### Task 3: Consolidate FS.py's duplicated gather boilerplate into `_gather_helpers`

**Files:**
- Modify: `Voyageur/FS.py`

**Interfaces:**
- Consumes: the same five functions from Task 1, plus existing `cleanup_checkpoint_files`/`move_with_retry`. `FS.py`'s own `_read_text_with_retry`/`_unlink_with_retry` are untouched local helpers.
- Produces: nothing consumed by later tasks — `FS.main()`'s external signature and behavior are unchanged.

Same test-cycle shape as Task 2: compile check plus full-suite regression (no new tests — `FS.py`'s `main()` has no existing test coverage of this logic, and this is a verbatim-lift refactor).

- [ ] **Step 1: Update the import block**

```python
old_string:
import json
import os
import re
import sys
import time
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import yaml
from dotenv import load_dotenv, set_key
from thefuzz import fuzz

import census_schema
from _gather_helpers import cleanup_checkpoint_files, move_with_retry
```

```python
new_string:
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import yaml
from dotenv import load_dotenv
from thefuzz import fuzz

import census_schema
from _gather_helpers import (
    cleanup_checkpoint_files,
    launch_gather_browser,
    move_downloaded_images,
    move_with_retry,
    resolve_census_image_dir,
    wait_for_downloaded_json,
    write_archivist_json_file,
)
```

Note: `time` stays imported — `_read_text_with_retry`/`_unlink_with_retry` (FS.py's own local retry helpers, not moved) still call `time.sleep(delay)`.

- [ ] **Step 2: Replace the browser-launch block**

```python
old_string:
    start_time = time.time()
    auto_url = url + ("&mgs_auto=1" if "?" in url else "?mgs_auto=1")
    print("[System] Launching browser...")
    webbrowser.open(auto_url)

    print("\n[System] Waiting for Tampermonkey downloads (Auto-Batch will start automatically)...")
```

```python
new_string:
    start_time = launch_gather_browser(url)
```

- [ ] **Step 3: Replace the download-polling block**

```python
old_string:
    downloads_dir = Path.home() / "Downloads"
    json_prefix = "TMP_FS_"
    image_prefix = "TMP_FS_Images_"
    raw_json_file = None

    try:
        while True:
            # noinspection broad-exception
            try:
                candidates = [
                    p for p in downloads_dir.iterdir()
                    if p.is_file() and p.suffix.lower() == '.json'
                    and p.name.startswith(json_prefix)
                    and p.stat().st_mtime >= start_time
                    and '[checkpoint' not in p.name
                ]
                if candidates:
                    raw_json_file = max(candidates, key=lambda p: p.stat().st_mtime)
                    print(f"[System] Detected raw gather JSON: {raw_json_file.name}")
            except OSError:
                pass

            if raw_json_file:
                break
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[System] Operation cancelled by user.")
        sys.exit(0)
```

```python
new_string:
    downloads_dir = Path.home() / "Downloads"
    json_prefix = "TMP_FS_"
    image_prefix = "TMP_FS_Images_"
    raw_json_file = wait_for_downloaded_json(downloads_dir, json_prefix, start_time, "raw gather JSON")
```

- [ ] **Step 4: Replace the Archivist `.env` write-back call**

```python
old_string:
    set_key(str(Path(__file__).resolve().parent.parent / "Archivist" / ".env"), "JSON_FILE", final_json.name)
```

```python
new_string:
    write_archivist_json_file(final_json.name)
```

- [ ] **Step 5: Replace the image-directory resolution block**

```python
old_string:
    base_img_setting = os.getenv("CENSUS_IMAGE_DIR", "Census")
    if os.path.isabs(base_img_setting):
        base_img_dir = Path(base_img_setting)
    else:
        media_setting = os.getenv("MEDIA_DIR", "Media")
        base_media_dir = Path(media_setting) if os.path.isabs(media_setting) else (
            Path(program_dir) / media_setting if program_dir else Path(media_setting))
        base_img_dir = base_media_dir / base_img_setting
    img_target_dir = base_img_dir / census_folder / location_folder
    img_target_dir.mkdir(parents=True, exist_ok=True)
```

```python
new_string:
    base_img_setting = os.getenv("CENSUS_IMAGE_DIR", "Census")
    img_target_dir = resolve_census_image_dir(base_img_setting, program_dir, census_folder, location_folder)
```

- [ ] **Step 6: Replace the image-move loop**

```python
old_string:
    img_count = 0
    image_candidates = [
        p for p in downloads_dir.iterdir()
        if p.is_file() and p.suffix.lower() == '.jpg'
        and p.name.startswith(image_prefix) and p.stat().st_mtime >= start_time
    ]
    for file_path in image_candidates:
        # noinspection broad-exception
        try:
            final_img = img_target_dir / file_path.name[len(image_prefix):]
            move_with_retry(file_path, final_img)
            img_count += 1
        except Exception as e:
            print(f"[ERROR] Could not move image {file_path.name}: {e}")

    print(f"[System] Moved {img_count} image(s) to Project folder.")
```

```python
new_string:
    img_count = move_downloaded_images(downloads_dir, image_prefix, start_time, img_target_dir)
    print(f"[System] Moved {img_count} image(s) to Project folder.")
```

- [ ] **Step 7: Compile-check the file**

Run: `python -m py_compile Voyageur/FS.py`
Expected: no output, exit code 0.

- [ ] **Step 8: Run the full test suite to confirm nothing broke**

Run: `pytest Voyageur/tests/ -v`
Expected: all tests PASS.

- [ ] **Step 9: Commit**

```bash
git add Voyageur/FS.py
git commit -m "Consolidate FS.py's gather boilerplate into _gather_helpers"
```

---

### Task 4: Rewrite Voyageur.py as a thin dispatcher

**Files:**
- Modify: `Voyageur/Voyageur.py` (full rewrite — ~1300 lines → ~25 lines)
- Test: `Voyageur/tests/test_voyageur_dispatcher.py` (new)

**Interfaces:**
- Consumes: `A.main()`, `FS.main()`, `LAC.main()` — no signature requirements, called with no arguments; each reads its own CLI args from `sys.argv`.
- Produces: nothing consumed by later tasks. `Scriptorium.py` (Task 5) already launches `Voyageur/Voyageur.py` as a subprocess with the source code as its first CLI argument — that contract is unchanged, only what happens inside the subprocess changes.

- [ ] **Step 1: Write the failing dispatcher tests**

Create `Voyageur/tests/test_voyageur_dispatcher.py`:

```python
import sys
import types

import pytest

import Voyageur


@pytest.mark.parametrize("source, module_name", [("A", "A"), ("FS", "FS"), ("LAC", "LAC")])
def test_main_dispatches_to_correct_provider_and_strips_mode_token(source, module_name, monkeypatch):
    calls = []
    fake_module = types.ModuleType(module_name)
    fake_module.main = lambda: calls.append(sys.argv[:])
    monkeypatch.setitem(sys.modules, module_name, fake_module)
    monkeypatch.setattr(sys, "argv", ["Voyageur.py", source, "--extra", "value"])

    Voyageur.main()

    assert calls == [["Voyageur.py", "--extra", "value"]]


def test_main_rejects_invalid_source(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["Voyageur.py", "BOGUS"])

    with pytest.raises(SystemExit) as exc_info:
        Voyageur.main()

    assert exc_info.value.code == 1
    assert "[ERROR] Usage: python Voyageur.py <source>" in capsys.readouterr().out


def test_main_rejects_missing_source(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["Voyageur.py"])

    with pytest.raises(SystemExit) as exc_info:
        Voyageur.main()

    assert exc_info.value.code == 1
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `pytest Voyageur/tests/test_voyageur_dispatcher.py -v`
Expected: FAIL — `Voyageur.main()` currently dispatches via `_SOURCE_MAINS` without stripping `sys.argv[1]` first, and the old `Voyageur.py` still contains the full 1300-line fork (importing it directly executes all the folded-in module-level code, which is not itself a failure, but the mode-token-stripping assertion fails since the current `main()` never deletes `sys.argv[1]`).

- [ ] **Step 3: Overwrite Voyageur.py entirely**

This is a full-file replacement (use the Write tool, not a targeted edit) — every
folded-in section of the current ~1297-line file (shared utilities, census schema,
`_a_*`/`_fs_*`/`_lac_*` gather logic, the old `_SOURCE_MAINS` dispatcher) is deleted.
Replace the entire contents of `Voyageur/Voyageur.py` with:

```python
Voyageur - thin dispatcher for the GUI's A/FS/LAC gather buttons.

Scriptorium.py launches this as a subprocess with cwd=Voyageur/ and the source code
(A/FS/LAC) as sys.argv[1], so A/FS/LAC import as plain sibling modules and each
provider's own main() sees exactly the CLI arguments Scriptorium.py meant for it.
"""

import sys

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

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `pytest Voyageur/tests/test_voyageur_dispatcher.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Run the full test suite to confirm nothing broke**

Run: `pytest Voyageur/tests/ -v`
Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add Voyageur/Voyageur.py Voyageur/tests/test_voyageur_dispatcher.py
git commit -m "Rewrite Voyageur.py as a thin dispatcher to A.py/FS.py/LAC.py"
```

---

### Task 5: Fix Scriptorium.py's LAC dispatch to send the required subcommand token

**Files:**
- Modify: `Scriptorium.py:1858-1864`

**Interfaces:**
- Consumes: `LAC.py`'s real `argparse` contract (unchanged, verified in design) — `volume` subcommand takes `--volume`, `reel` subcommand takes `--url`.
- Produces: nothing consumed by later tasks. Task 6's manual verification exercises this.

No existing automated test coverage exists for `Scriptorium.py` (a CustomTkinter GUI class with no test file). This task's test cycle is a compile check and full-suite regression; end-to-end correctness is verified manually in Task 6.

- [ ] **Step 1: Update the LAC dispatch branch**

```python
old_string:
        elif script_key == "VOYAGEUR_SCRIPT":
            # Voyageur.py is a thin dispatcher; the mode IS the source code (A/FS/LAC).
            args.append(mode)
            if mode == "LAC":
                vol = self.string_vars.get("LAC_HARVEST_VOLUME", ctk.StringVar(value="")).get().strip()
                if vol:
                    args.extend(["--volume", vol])
```

```python
new_string:
        elif script_key == "VOYAGEUR_SCRIPT":
            # Voyageur.py is a thin dispatcher; the mode IS the source code (A/FS/LAC).
            args.append(mode)
            if mode == "LAC":
                vol = self.string_vars.get("LAC_HARVEST_VOLUME", ctk.StringVar(value="")).get().strip()
                url = self.string_vars.get("LAC_URL", ctk.StringVar(value="")).get().strip()
                if vol:
                    args.extend(["volume", "--volume", vol])
                elif url:
                    args.extend(["reel", "--url", url])
```

- [ ] **Step 2: Compile-check the file**

Run: `python -m py_compile Scriptorium.py`
Expected: no output, exit code 0.

- [ ] **Step 3: Run the full test suite to confirm nothing broke**

Run: `pytest Voyageur/tests/ -v`
Expected: all tests PASS (Scriptorium.py has no test file of its own to run).

- [ ] **Step 4: Commit**

```bash
git add Scriptorium.py
git commit -m "Fix LAC dispatch to send the volume/reel subcommand token LAC.py requires"
```

---

### Task 6: Manual end-to-end verification

**Files:** none (no code changes — this task documents the manual verification the spec requires before this work is considered done)

**Interfaces:** N/A

This is the first time the GUI's A/FS/LAC buttons will run the maintained code path (Tasks 1-4) in production, and the first time the LAC subcommand fix (Task 5) is exercised against the real `LAC.py`. Per the spec's Testing section, this must be run manually, not automated.

- [ ] **Step 1: Run the full automated suite one more time as a final gate**

Run: `pytest Voyageur/tests/ -v`
Expected: all tests PASS.

- [ ] **Step 2: Launch Scriptorium.py and run an Ancestry (A) gather against a real record**

Set `CENSUS_URL` in the Toolbox settings to a real Ancestry census record URL, click the Ancestry gather button, and confirm: browser opens, JSON and images land in the expected project folders, and Archivist's `JSON_FILE` setting is updated. Confirm console output matches the existing `[System] ...` messages.

- [ ] **Step 3: Run a FamilySearch (FS) gather against a real record**

Same as Step 2, using `FS_URL` and a real FamilySearch record page. Confirm both the census-family and non-census-family code paths still work if you have a record of each available.

- [ ] **Step 4: Run an LAC volume harvest**

Set `LAC_HARVEST_VOLUME` to a real volume number, click the LAC harvest button, and confirm the subprocess receives `LAC volume --volume <number>` and the harvest completes (per the project's existing LAC-network guidance — do not run this if LAC.py/network access is currently blocked per Claude issue #81159; if blocked, defer this step and note it).

- [ ] **Step 5: Run an LAC reel harvest**

Set `LAC_URL` to a real Canadiana IIIF URL (clear `LAC_HARVEST_VOLUME` first, since volume takes priority), click the LAC harvest button, and confirm the subprocess receives `LAC reel --url <url>` and the harvest completes. Same network-access caveat as Step 4.

- [ ] **Step 6: Report results**

No commit for this task. If any manual check fails, stop and fix the regression as a new task before considering this plan complete — do not mark the branch ready to ship with a known-broken manual check.
