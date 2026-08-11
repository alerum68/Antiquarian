# Paleographer / Voyageur Debt Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Model selection note (overrides the subagent-driven-development skill's own Model Selection section): never select Opus for any task in this plan — default to Sonnet everywhere, including the final whole-branch review and any fix-loop escalation round.**

> **SUPERSEDED:** This plan is historical. Its checklist steps marked `- [ ]` were superseded and never executed as written; see the live tracker `docs/plans/task.md` for the actual disposition.

**Goal:** Remove verified dead code, fix the broken `crosscheck` CLI mode, and consolidate duplicated logic across `Paleographer/Paleographer.py` and `Voyageur/` (`LAC.py`, `A.py`, `FS.py`) — a self-contained branch that merges before sub-project 3 begins. No new features, no behavior change except the one explicit bug fix.

**Architecture:** Single branch off `Unify`. Reuses Paleographer.py's existing `from Voyageur import LAC as voyageur_lac` cross-import for the `COLLECTIONS` consolidation. Two new shared modules: `Voyageur/_retry_utils.py` (retry helpers, A.py + FS.py) and `Commissioner/normalization.py` (normalization helpers, Paleographer.py + FS.py).

**Tech Stack:** Python, pytest, pycodestyle.

## Global Constraints

- Full `pytest` suite and `pycodestyle --max-line-length=120` must stay green after every task, not just at the end.
- No behavior change anywhere except the `crosscheck` CLI mode fix (Task 6).
- Deletions/consolidations (pure code moves) get no new tests — existing tests for moved/deleted code must still pass, or be deleted alongside (postprocess.py's own tests).
- Do not run `Voyageur/LAC.py` or `Voyageur/BACLAC.py` against the real network, and do not open a browser to LAC/Canadiana — blocked pending Claude issue #81159. The `crosscheck` unit test (Task 6) mocks `lac_client.search` and `voyageur_lac.download_pid_bundle`; it must never make a real network call.
- No AI attribution, "Co-Authored-By", or Claude stamps in any commit message.
- Do not touch `Voyageur/Voyageur.py` (confirmed-dead pre-split monolith) or `Commissioner/models.py` — both explicitly out of scope.
- Do not add a `scaffold` LAC.py subcommand — that belongs to sub-project 3.

---

### Task 1: Delete dead code in Paleographer.py + orphaned postprocess.py

**Files:**
- Delete: `Paleographer/postprocess.py`
- Delete: `Paleographer/tests/test_postprocess.py`
- Modify: `Paleographer/Paleographer.py`
- Test: existing `Paleographer/tests/` suite (no new file)

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: nothing consumed by later tasks — `clean_race`/`clean_date_and_place`/`MONTHS_REGEX`/`DATE_PATTERN`/`NARRATIVE_JUNK_REGEX` are gone; no other task references them.

- [ ] **Step 1: Confirm zero remaining references before deleting**

Run:
```
grep -rn "clean_race\|clean_date_and_place\|MONTHS_REGEX\|DATE_PATTERN\|NARRATIVE_JUNK_REGEX" Paleographer/ --include=*.py
```
Expected: matches only inside `Paleographer/Paleographer.py` itself (the definitions) — `DATE_PATTERN`/`NARRATIVE_JUNK_REGEX` are used only inside `clean_date_and_place`, `MONTHS_REGEX` only inside `DATE_PATTERN`'s own definition. If any match appears outside `Paleographer.py`, stop and report it — do not delete.

- [ ] **Step 2: Delete the orphaned module and its test file**

```bash
git rm Paleographer/postprocess.py Paleographer/tests/test_postprocess.py
```

- [ ] **Step 3: Delete the four dead functions/constants from Paleographer.py**

In `Paleographer/Paleographer.py`, delete this exact block (currently lines 327-340):

```python
old_string:
# ==========================================
# SCRIP DATA CLEANING & REPAIR
# ==========================================
MONTHS_REGEX = (
    r'(?:january|february|march|april|may|june|july|august|september|october|november|december|'
    r'jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)'
)
DATE_PATTERN = re.compile(
    rf'\b(?:(?:\d{{1,2}}(?:st|nd|rd|th)?\s+)?{MONTHS_REGEX}\.?\s+'
    rf'\d{{1,2}}(?:st|nd|rd|th)?,?\s*(?:17\d\d|18\d\d|19\d\d)?|'
    rf'\d{{1,2}}(?:st|nd|rd|th)?\s+{MONTHS_REGEX}\.?,?\s*(?:17\d\d|18\d\d|19\d\d)?|'
    rf'{MONTHS_REGEX}\.?,?\s*(?:17\d\d|18\d\d|19\d\d)|(?:17\d\d|18\d\d|19\d\d)(?:/(?:17\d\d|18\d\d|19\d\d))?)\b',
    re.I)
NARRATIVE_JUNK_REGEX = re.compile(
    r'\b(?:settler|settled|grandchild|descendant|resided|surviving|heir|entitled|deceased|father|mother|daughter|son|'
    r'brother|sister|wife|husband|married|leaving|claim|who\b|born\b|died\b)\b',
    re.I)

_MOJIBAKE_MAP = {
```

Replace with (drops the four dead names, keeps `_MOJIBAKE_MAP` and everything after it unchanged — note the comment block header goes with it since nothing else follows in that section):

```python
new_string:
_MOJIBAKE_MAP = {
```

Then delete `clean_race` and `clean_date_and_place` in full (currently lines 381-437, immediately after `fix_mojibake`'s closing and before `COMPOUND_SURNAME_PREFIXES_2`). Exact block to remove:

```python
old_string:
def clean_race(val: Any) -> str:
    if val is None:
        return ""
    text = str(val).strip()
    if not text:
        return ""
    cleaned = re.sub(r'^(?:the\s+)?(?:present\s+)?d(?:e)?pon(?:ent|end)\s*(?:and|&)?\s*', '', text, flags=re.I)
    cleaned = re.sub(
        r'[,;]?\s*(?:(?:and|&|an)\s+)?(?:the\s+)?(?:present\s+)?d(?:e)?pon(?:ent|end)\b.*$',
        '', cleaned, flags=re.I)
    cleaned = re.sub(r'[,;&\s]+$', '', cleaned).strip()
    cleaned = re.sub(r'^[,;&\s]+', '', cleaned).strip()
    if cleaned.lower() in ("deponent", "the deponent", "mother", "father", "wife", "husband", "widow", "as heir", ""):
        return ""
    if re.match(r'^(?:who|heir|file ref|was entitled|her brother)\b', cleaned, flags=re.I):
        return ""
    return cap_case(cleaned)


def clean_date_and_place(raw_date: str, raw_place: str) -> Tuple[str, str]:
    def strip_prefixes(s: str) -> str:
        if not s:
            return ""
        t = str(s).strip()
        t = re.sub(r'^(?:born|died|married|address)\s*,\s*', '', t, flags=re.I)
        t = re.sub(r'^(?:born|died|married|address)\s+', '', t, flags=re.I)
        t = re.sub(r'^(?:who\s+died|who\s+was\s+born|mother\s+married|father\s+married)\s*', '', t, flags=re.I)
        return re.sub(r'^[,\s\-:]+|[,\s\-:]+$', '', t).strip()

    d_clean = strip_prefixes(raw_date)
    p_clean = strip_prefixes(raw_place)
    found_date, candidate_place = "", ""
    d_match = DATE_PATTERN.search(d_clean)
    p_match = DATE_PATTERN.search(p_clean)

    if d_match:
        found_date = d_match.group(0).strip()
        d_rem = (d_clean[:d_match.start()] + " " + d_clean[d_match.end():]).strip()
        d_rem = re.sub(r'^[,\s\-:]+|[,\s\-:]+$', '', d_rem).strip()
        if d_rem and not NARRATIVE_JUNK_REGEX.search(d_rem):
            candidate_place = d_rem
    elif d_clean and not NARRATIVE_JUNK_REGEX.search(d_clean):
        candidate_place = d_clean

    if p_match:
        if not found_date:
            found_date = p_match.group(0).strip()
        p_rem = (p_clean[:p_match.start()] + " " + p_clean[p_match.end():]).strip()
        p_rem = re.sub(r'^[,\s\-:]+|[,\s\-:]+$', '', p_rem).strip()
        p_rem = re.sub(r'\s*\bor\s*$', '', p_rem, flags=re.I).strip()
        if p_rem and not candidate_place and not NARRATIVE_JUNK_REGEX.search(p_rem):
            candidate_place = p_rem
    elif p_clean and not candidate_place and not NARRATIVE_JUNK_REGEX.search(p_clean):
        candidate_place = p_clean

    candidate_place = re.sub(r'\s*\bor\s*$', '', candidate_place, flags=re.I).strip()
    return found_date, cap_case(candidate_place)


COMPOUND_SURNAME_PREFIXES_2 = {
```

```python
new_string:
COMPOUND_SURNAME_PREFIXES_2 = {
```

- [ ] **Step 4: Run pycodestyle and the full test suite**

```
pycodestyle --max-line-length=120 Paleographer/Paleographer.py
pytest Paleographer/tests/ -v
```
Expected: no pycodestyle violations; all tests pass (test_postprocess.py's 25 tests are gone with the file, nothing else references the deleted names).

- [ ] **Step 5: Commit**

```bash
git add -A -- Paleographer/postprocess.py Paleographer/tests/test_postprocess.py Paleographer/Paleographer.py
git commit -m "Remove orphaned postprocess.py and dead clean_race/clean_date_and_place from Paleographer.py"
```

---

### Task 2: Delete dead code in Voyageur/LAC.py

**Files:**
- Modify: `Voyageur/LAC.py`
- Test: existing `Voyageur/tests/` suite (no new file)

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: nothing later tasks depend on — `get_env_paths()` and the module-level `resolve_pid_from_filename()`/`_PID_FROM_FILENAME_RE` are gone. Task 4 restructures `main()` in this same file — sequenced after this task so its own edits land on the already-shrunk file.

- [ ] **Step 1: Confirm zero remaining references before deleting**

Run:
```
grep -rn "get_env_paths\b" Voyageur/ Paleographer/ Archivist/ --include=*.py
grep -rn "resolve_pid_from_filename\b" Voyageur/LAC.py Voyageur/tests/
```
Expected: `get_env_paths` matches only its own definition in `LAC.py`. `resolve_pid_from_filename` inside `LAC.py`/`Voyageur/tests/` matches only its own definition — Paleographer.py has a separate, actually-used copy of the same name at `Paleographer.py:1893`, which is a different file and stays untouched.

- [ ] **Step 2: Delete `resolve_pid_from_filename` and its regex**

In `Voyageur/LAC.py`, exact block to remove (currently lines 46, 49-56 with the blank line between):

```python
old_string:
_PID_FROM_FILENAME_RE = re.compile(r"_(\d+)\.pdf$", re.IGNORECASE)


def resolve_pid_from_filename(file_name: str) -> Optional[str]:
    """Returns the PID embedded in a locally-chosen filename (e.g. BAC-LAC_fonandcol_1502188.pdf),
    or None if the filename doesn't follow that convention."""
    if not file_name:
        return None
    match = _PID_FROM_FILENAME_RE.search(file_name)
    return match.group(1) if match else None


def load_cookies(cookie_file: str = COOKIE_FILE, cdp_port: int = CDP_PORT) -> Dict[str, str]:
```

```python
new_string:
def load_cookies(cookie_file: str = COOKIE_FILE, cdp_port: int = CDP_PORT) -> Dict[str, str]:
```

- [ ] **Step 3: Delete `get_env_paths`**

Exact block to remove (currently lines 74-83, the section header plus the function):

```python
old_string:
# ==========================================
# CANADIANA IIIF MANIFEST & DOWNLOAD
# ==========================================
def get_env_paths() -> Tuple[str, str, str]:
    """Reads the necessary foundational directories mapped by the Toolbox."""
    program_dir = os.environ.get("PROGRAM_DIR", "").strip()
    media_dir = os.environ.get("MEDIA_DIR", "Media").strip()
    raw_url = os.environ.get("LAC_URL", "").strip()
    return program_dir, media_dir, raw_url


def parse_url(raw_url: str) -> Tuple[str, str]:
```

```python
new_string:
# ==========================================
# CANADIANA IIIF MANIFEST & DOWNLOAD
# ==========================================
def parse_url(raw_url: str) -> Tuple[str, str]:
```

- [ ] **Step 4: Run pycodestyle and the full test suite**

```
pycodestyle --max-line-length=120 Voyageur/LAC.py
pytest Voyageur/tests/ -v
```
Expected: no violations; all tests pass.

- [ ] **Step 5: Commit**

```bash
git add Voyageur/LAC.py
git commit -m "Remove dead get_env_paths and duplicate resolve_pid_from_filename from LAC.py"
```

---

### Task 3: Extract retry helpers into Voyageur/_retry_utils.py

**Files:**
- Create: `Voyageur/_retry_utils.py`
- Modify: `Voyageur/A.py`
- Modify: `Voyageur/FS.py`
- Test: existing `Voyageur/tests/` suite (no new file — neither function had dedicated unit tests before this move)

**Interfaces:**
- Consumes: nothing from Tasks 1-2.
- Produces: `_retry_utils.move_with_retry(src: Path, dst: Path, attempts: int = 5, delay: float = 0.5) -> None` and `_retry_utils.cleanup_checkpoint_files(downloads_dir: Path, prefix: str, start_time: float) -> None`. No later task calls these directly, but Task 8 edits code in the same two files (the downloads-dir polling loops and image-move loops) — sequenced after this task so its edits land on the already-refactored files. Note the public names drop the leading underscore since they're now a real shared module's public API, not a private same-file helper — every call site is updated accordingly.

- [ ] **Step 1: Create the new shared module**

Write `Voyageur/_retry_utils.py`:

```python
"""
Shared retry helpers for Voyageur's gather scripts (A.py, FS.py). Chrome (or antivirus
scanning it) can still hold a freshly-downloaded file open for a brief moment after it
appears in the folder listing, so an immediate shutil.move/unlink can lose to a transient
PermissionError/WinError 32 on Windows - these retry helpers ride out that window instead
of letting a gather crash with the file left stranded.
"""

import shutil
import time
from pathlib import Path


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
```

- [ ] **Step 2: Update A.py to import from the new module**

In `Voyageur/A.py`, remove the two function definitions and add the import. Exact block to remove (currently lines 16-46, including the blank lines around them):

```python
old_string:
def _move_with_retry(src: Path, dst: Path, attempts: int = 5, delay: float = 0.5) -> None:
    """Chrome (or antivirus scanning it) can still hold a freshly-downloaded file open for
    a brief moment after it appears in the folder listing, so an immediate shutil.move can
    lose to a transient PermissionError/WinError 32 on Windows. Retries ride out that
    window instead of letting the whole gather crash with the file left stranded."""
    for attempt in range(1, attempts + 1):
        try:
            shutil.move(str(src), str(dst))
            return
        except OSError as e:
            if attempt == attempts:
                print(f"[ERROR] Could not move {src.name} to {dst} after {attempts} attempts: {e}")
                raise
            time.sleep(delay)


def _cleanup_checkpoint_files(downloads_dir: Path, prefix: str, start_time: float) -> None:
    """Deletes this run's own leftover periodic checkpoint downloads (see
    downloadCheckpointJson in Voyageur.js) now that the final combined JSON has already
    been moved out - they're superseded and, unlike the final JSON, nothing else ever
    cleans them up, so a long gather would otherwise leave several of them sitting in the
    Downloads folder permanently. Best-effort: a checkpoint that can't be deleted (still
    briefly locked, already gone) is left in place rather than raising."""
    for p in downloads_dir.iterdir():
        if (p.is_file() and p.suffix.lower() == '.json' and p.name.startswith(prefix)
                and '[checkpoint' in p.name and p.stat().st_mtime >= start_time):
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass


# ==========================================
# URL PARSING
# ==========================================
```

```python
new_string:
# ==========================================
# URL PARSING
# ==========================================
```

Update the import block (currently lines 1-13):

```python
old_string:
import json
import os
import re
import shutil
import sys
import time
import urllib.parse
import webbrowser
from pathlib import Path

from dotenv import load_dotenv, set_key

import census_schema
```

```python
new_string:
import json
import os
import re
import sys
import urllib.parse
import webbrowser
from pathlib import Path

from dotenv import load_dotenv, set_key

import census_schema
from _retry_utils import cleanup_checkpoint_files, move_with_retry
```

(`shutil`/`time` are no longer used directly in A.py once the two functions move out — confirm with Step 4's pycodestyle run, which flags unused imports.)

Update the two call sites in `main()`:

```python
old_string:
    final_json = json_target_dir / json_file.name[len(json_prefix):]
    _move_with_retry(json_file, final_json)
    _cleanup_checkpoint_files(downloads_dir, json_prefix, start_time)
```

```python
new_string:
    final_json = json_target_dir / json_file.name[len(json_prefix):]
    move_with_retry(json_file, final_json)
    cleanup_checkpoint_files(downloads_dir, json_prefix, start_time)
```

```python
old_string:
            final_img = img_target_dir / file_path.name[len(image_prefix):]
            _move_with_retry(file_path, final_img)
            img_count += 1
```

```python
new_string:
            final_img = img_target_dir / file_path.name[len(image_prefix):]
            move_with_retry(file_path, final_img)
            img_count += 1
```

- [ ] **Step 3: Update FS.py to import from the new module**

In `Voyageur/FS.py`, remove `_move_with_retry`/`_cleanup_checkpoint_files` (currently lines 772-801, keeping `_read_text_with_retry`/`_unlink_with_retry` in place — those are FS.py-only, not duplicated):

```python
old_string:
def _move_with_retry(src: Path, dst: Path, attempts: int = 5, delay: float = 0.5) -> None:
    """Same reasoning as A.py's own _move_with_retry: Chrome (or antivirus scanning it) can
    still hold a freshly-downloaded file open for a brief moment after it appears in the
    folder listing."""
    for attempt in range(1, attempts + 1):
        try:
            shutil.move(str(src), str(dst))
            return
        except OSError as e:
            if attempt == attempts:
                print(f"[ERROR] Could not move {src.name} to {dst} after {attempts} attempts: {e}")
                raise
            time.sleep(delay)


def _cleanup_checkpoint_files(downloads_dir: Path, prefix: str, start_time: float) -> None:
    """Deletes this run's own leftover periodic checkpoint downloads (see
    downloadCheckpointJson in Voyageur.js) now that the final combined JSON has already
    been written out - they're superseded and, unlike the final JSON, nothing else ever cleans
    them up, so a long gather would otherwise leave several of them sitting in the
    Downloads folder permanently. Best-effort: a checkpoint that can't be deleted (still
    briefly locked, already gone) is left in place rather than raising."""
    for p in downloads_dir.iterdir():
        if (p.is_file() and p.suffix.lower() == '.json' and p.name.startswith(prefix)
                and '[checkpoint' in p.name and p.stat().st_mtime >= start_time):
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass


def build_clean_census_filename(year: str, normalized_data: dict) -> Optional[str]:
```

```python
new_string:
def build_clean_census_filename(year: str, normalized_data: dict) -> Optional[str]:
```

Add the import (FS.py's own import block, currently lines 23-39):

```python
old_string:
import json
import os
import re
import shutil
import sys
import time
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import yaml
from dotenv import load_dotenv, set_key
from thefuzz import fuzz
from titlecase import titlecase

import census_schema
```

```python
new_string:
import json
import os
import re
import shutil
import sys
import time
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import yaml
from dotenv import load_dotenv, set_key
from thefuzz import fuzz
from titlecase import titlecase

import census_schema
from _retry_utils import cleanup_checkpoint_files, move_with_retry
```

(`shutil`/`time` stay in FS.py's imports — `_read_text_with_retry`/`_unlink_with_retry` still use `time.sleep`, and both remaining functions still live in this file.)

Update the three call sites:

```python
old_string:
    final_json.write_text(json.dumps(final_data, indent=2, ensure_ascii=False), encoding="utf-8")
    _unlink_with_retry(raw_json_file)
    _cleanup_checkpoint_files(downloads_dir, json_prefix, start_time)
```

```python
new_string:
    final_json.write_text(json.dumps(final_data, indent=2, ensure_ascii=False), encoding="utf-8")
    _unlink_with_retry(raw_json_file)
    cleanup_checkpoint_files(downloads_dir, json_prefix, start_time)
```

```python
old_string:
            final_img = img_target_dir / file_path.name[len(image_prefix):]
            _move_with_retry(file_path, final_img)
            img_count += 1
```

```python
new_string:
            final_img = img_target_dir / file_path.name[len(image_prefix):]
            move_with_retry(file_path, final_img)
            img_count += 1
```

- [ ] **Step 4: Run pycodestyle and the full test suite**

```
pycodestyle --max-line-length=120 Voyageur/A.py Voyageur/FS.py Voyageur/_retry_utils.py
pytest Voyageur/tests/ -v
```
Expected: no violations (including no unused-import warnings — remove any `shutil`/`time` import pycodestyle flags as unused in A.py); all tests pass.

- [ ] **Step 5: Commit**

```bash
git add Voyageur/_retry_utils.py Voyageur/A.py Voyageur/FS.py
git commit -m "Extract duplicated move_with_retry/cleanup_checkpoint_files into Voyageur/_retry_utils.py"
```

---

### Task 4: Restructure LAC.py's CLI and fix load_cookies/RG15 duplication

**Files:**
- Modify: `Voyageur/LAC.py`
- Test: existing `Voyageur/tests/` suite (no new file — `LAC.py`'s `main()` has no existing unit tests; this is a routing-only change with unchanged internal logic)

**Interfaces:**
- Consumes: the shrunk `LAC.py` from Task 2 (this task's line numbers/exact text assume Task 2 already landed).
- Produces: `LAC.py main()` now dispatches via explicit `volume`/`reel` subcommands instead of implicit `if args.volume`. `load_cookies()` now raises `FileNotFoundError`/`ValueError` instead of calling `sys.exit(1)`. No later task calls `load_cookies()` or `main()` directly, but Task 6 mirrors this same cookie-loading pattern in `Paleographer.py`'s new `crosscheck` dispatch — read this task's Step 3 before writing that one.

- [ ] **Step 1: Fix load_cookies to raise instead of exit**

In `Voyageur/LAC.py`, `load_cookies()` already raises `FileNotFoundError`/`ValueError` for its own two failure paths — the fix is removing the *earlier*, unreachable-in-context `sys.exit` pattern implied by the spec is actually not present in this function's current body (it already only raises). Re-read: the current body is:

```python
def load_cookies(cookie_file: str = COOKIE_FILE, cdp_port: int = CDP_PORT) -> Dict[str, str]:
    """Loads search cookies from a debuggable browser or a cookie file."""
    try:
        return lac_client.load_cookies_from_cdp(port=cdp_port)
    except lac_client.LacCallError:
        pass

    path = Path(cookie_file)
    if not path.is_file():
        raise FileNotFoundError(f"No cookie file at {path}.")
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        raise ValueError(f"Cookie file {path} is empty.")
    return lac_client.parse_cookie_header(raw)
```

This function already raises rather than exiting — no change needed here. Skip to Step 2. (This step exists so the implementer verifies this before assuming work is needed, rather than guessing at a diff that doesn't apply.)

- [ ] **Step 2: Replace RG15 magic-string defaults with DEFAULT_ARCHIVAL_NUMBER**

```python
old_string:
def retrieve_volume_pids(vol: str, cookies: Dict[str, str], checkpoint_path: str,
                         archival_number: str = "RG15") -> List[str]:
```

```python
new_string:
def retrieve_volume_pids(vol: str, cookies: Dict[str, str], checkpoint_path: str,
                         archival_number: str = DEFAULT_ARCHIVAL_NUMBER) -> List[str]:
```

```python
old_string:
def retrieve_volume(vol: str, cookies: Dict[str, str], media_dir: str, checkpoint_path: str,
                    archival_number: str = "RG15", max_workers: int = 1) -> Dict[str, Any]:
```

```python
new_string:
def retrieve_volume(vol: str, cookies: Dict[str, str], media_dir: str, checkpoint_path: str,
                    archival_number: str = DEFAULT_ARCHIVAL_NUMBER, max_workers: int = 1) -> Dict[str, Any]:
```

- [ ] **Step 3: Restructure main() into explicit volume/reel subcommands**

Replace the entire `main()` function:

```python
old_string:
def main() -> None:
    parser = argparse.ArgumentParser(description="Voyageur LAC Gatherer: Canadiana IIIF and LAC Volume Harvester")
    parser.add_argument("--url", default=os.environ.get("LAC_URL", ""),
                        help="Canadiana IIIF URL (e.g., https://heritage.canadiana.ca/view/oocihm.lac_reel_c2170).")
    parser.add_argument("--volume", default=os.environ.get("LAC_VOLUME", ""),
                        help="LAC Volume number to harvest (e.g., 1325).")
    parser.add_argument("--archival-number", default=DEFAULT_ARCHIVAL_NUMBER,
                        help="Archival series number (default: RG15).")
    parser.add_argument("--cookie-file", default=COOKIE_FILE,
                        help="Path to browser cookies file for LAC search.")
    parser.add_argument("--media-dir", default=MEDIA_DIR,
                        help="Base output media directory.")
    parser.add_argument("--workers", type=int, default=int(os.environ.get("LAC_MAX_WORKERS", "1")),
                        help="Number of concurrent workers for volume downloading (default 1).")
    args = parser.parse_args()

    # Route 1: Volume harvesting
    if args.volume:
        print(f"[System] Starting LAC Volume retrieval for Volume {args.volume}...")
        try:
            cookies = load_cookies(args.cookie_file)
        except (FileNotFoundError, ValueError) as e:
            print(f"[FATAL ERROR] {e} Search LAC once in a real browser, then paste its Cookie header "
                  f"into that file. Opening search browser...")
            lac_client.open_search_browser_for_refresh()
            return

        checkpoint_path = str(Path(CHECKPOINT_DIR) / f"volume_{args.volume}.json")
        try:
            result = retrieve_volume(args.volume, cookies, args.media_dir, checkpoint_path,
                                     archival_number=args.archival_number, max_workers=args.workers)
        except lac_client.LacSearchAuthError as e:
            print(f"[FATAL ERROR] {e} Opening the search page now.")
            lac_client.open_search_browser_for_refresh()
            return

        print(f"[System] Harvested volume {args.volume}: {len(result.get('pids', []))} PID(s), "
              f"{len(result.get('downloaded_pids', []))} downloaded, "
              f"{len(result.get('failed_pids', {}))} failed.")
        return

    # Route 2: Canadiana IIIF Reel URL
    url = args.url
    if not url:
        print("[Error] Either LAC_URL or LAC_VOLUME must be provided.")
        sys.exit(1)

    program_dir = os.environ.get("PROGRAM_DIR", "").strip()
    roll, manifest = parse_url(url)
    output_directory = setup_directories(program_dir, args.media_dir, roll)
    manifest_json = download_manifest(manifest)
    download_images(manifest_json, output_directory, roll)
```

```python
new_string:
def _run_volume(args: argparse.Namespace) -> None:
    print(f"[System] Starting LAC Volume retrieval for Volume {args.volume}...")
    try:
        cookies = load_cookies(args.cookie_file)
    except (FileNotFoundError, ValueError) as e:
        print(f"[FATAL ERROR] {e} Search LAC once in a real browser, then paste its Cookie header "
              f"into that file. Opening search browser...")
        lac_client.open_search_browser_for_refresh()
        return

    checkpoint_path = str(Path(CHECKPOINT_DIR) / f"volume_{args.volume}.json")
    try:
        result = retrieve_volume(args.volume, cookies, args.media_dir, checkpoint_path,
                                 archival_number=args.archival_number, max_workers=args.workers)
    except lac_client.LacSearchAuthError as e:
        print(f"[FATAL ERROR] {e} Opening the search page now.")
        lac_client.open_search_browser_for_refresh()
        return

    print(f"[System] Harvested volume {args.volume}: {len(result.get('pids', []))} PID(s), "
          f"{len(result.get('downloaded_pids', []))} downloaded, "
          f"{len(result.get('failed_pids', {}))} failed.")


def _run_reel(args: argparse.Namespace) -> None:
    if not args.url:
        print("[Error] --url is required for the reel subcommand.")
        sys.exit(1)

    program_dir = os.environ.get("PROGRAM_DIR", "").strip()
    roll, manifest = parse_url(args.url)
    output_directory = setup_directories(program_dir, args.media_dir, roll)
    manifest_json = download_manifest(manifest)
    download_images(manifest_json, output_directory, roll)


def main() -> None:
    parser = argparse.ArgumentParser(description="Voyageur LAC Gatherer: Canadiana IIIF and LAC Volume Harvester")
    subparsers = parser.add_subparsers(dest="command", required=True)

    volume_parser = subparsers.add_parser("volume", help="Harvest an LAC archival volume by number.")
    volume_parser.add_argument("--volume", default=os.environ.get("LAC_VOLUME", ""),
                               help="LAC Volume number to harvest (e.g., 1325).")
    volume_parser.add_argument("--archival-number", default=DEFAULT_ARCHIVAL_NUMBER,
                               help="Archival series number (default: RG15).")
    volume_parser.add_argument("--cookie-file", default=COOKIE_FILE,
                               help="Path to browser cookies file for LAC search.")
    volume_parser.add_argument("--media-dir", default=MEDIA_DIR,
                               help="Base output media directory.")
    volume_parser.add_argument("--workers", type=int, default=int(os.environ.get("LAC_MAX_WORKERS", "1")),
                               help="Number of concurrent workers for volume downloading (default 1).")
    volume_parser.set_defaults(func=_run_volume)

    reel_parser = subparsers.add_parser("reel", help="Download a Canadiana IIIF reel by URL.")
    reel_parser.add_argument("--url", default=os.environ.get("LAC_URL", ""),
                             help="Canadiana IIIF URL (e.g., https://heritage.canadiana.ca/view/oocihm.lac_reel_c2170).")
    reel_parser.add_argument("--media-dir", default=MEDIA_DIR,
                             help="Base output media directory.")
    reel_parser.set_defaults(func=_run_reel)

    args = parser.parse_args()
    args.func(args)
```

- [ ] **Step 4: Run pycodestyle and the full test suite**

```
pycodestyle --max-line-length=120 Voyageur/LAC.py
pytest Voyageur/tests/ -v
```
Expected: no violations; all tests pass (no existing test exercises `LAC.py main()` directly, so nothing to update).

- [ ] **Step 5: Manual CLI smoke check (argparse wiring only — no network)**

```
python -m Voyageur.LAC volume --help
python -m Voyageur.LAC reel --help
python -m Voyageur.LAC --help
```
Expected: each prints its own help text with the right flags (`volume` shows `--volume`/`--archival-number`/`--cookie-file`/`--media-dir`/`--workers`; `reel` shows `--url`/`--media-dir`); the bare `--help` lists both subcommands. Do not invoke either subcommand without `--help` — that would hit the network, which is blocked per Global Constraints.

- [ ] **Step 6: Commit**

```bash
git add Voyageur/LAC.py
git commit -m "Restructure LAC.py main() into explicit volume/reel subcommands, use DEFAULT_ARCHIVAL_NUMBER"
```

---

### Task 5: Consolidate COLLECTIONS table into voyageur_lac

**Files:**
- Modify: `Paleographer/Paleographer.py`
- Test: existing `Paleographer/tests/` suite (no new file — neither copy had test coverage before this move)

**Interfaces:**
- Consumes: `Voyageur/LAC.py`'s existing `COLLECTIONS` (line 44, untouched by this plan) and `collection_for_series_code`/`collection_for_volume` — **these two functions do not exist yet in LAC.py** (they currently only exist as Paleographer.py's duplicate copy). This task creates them in `LAC.py` as part of the move, not just Paleographer.py's own deletion.
- Produces: `voyageur_lac.COLLECTIONS`, `voyageur_lac.collection_for_series_code(code) -> Optional[Tuple[str,str,str,str]]`, `voyageur_lac.collection_for_volume(volume, volume_range) -> Optional[Tuple[str,str,str,str]]`. No later task depends on these.

- [ ] **Step 1: Add COLLECTIONS + both functions to LAC.py**

The spec's Background says "keep `LAC.py`'s table canonical," but `LAC.py:44` currently holds only `DEFAULT_ARCHIVAL_NUMBER`, not a `COLLECTIONS` table — the actual `COLLECTIONS` list with its lookup functions exists only in Paleographer.py today. Move that real definition into `LAC.py` (this is the "keep canonical" outcome the spec describes, phrased from the end state rather than today's actual location).

In `Voyageur/LAC.py`, after `download_pid_bundle` and before `load_checkpoint` (currently lines 226-229, the blank lines between them), insert:

```python
old_string:
    return {
        "pid": pid,
        "lac_catalog_title": metadata.title,
        "reel_numbers": metadata.reel_numbers,
        "series_code": metadata.series_code,
        "source_documents": entries,
    }


def load_checkpoint(checkpoint_path: str) -> Dict[str, Any]:
```

```python
new_string:
    return {
        "pid": pid,
        "lac_catalog_title": metadata.title,
        "reel_numbers": metadata.reel_numbers,
        "series_code": metadata.series_code,
        "source_documents": entries,
    }


# ==========================================
# COLLECTION CLASSIFICATION
# ==========================================
COLLECTIONS = [
    ("RG15-D-II-8-a", "Affidavits, 1870-1885", "Finding Aid 15-19", 1319, 1324),
    ("RG15-D-II-8-b", "Applications, 1885", "Finding Aid 15-20", 1325, 1330),
    ("RG15-D-II-8-c", "Applications, 1886-1906", "Finding Aid 15-21", 1331, 1372),
]


def collection_for_series_code(code: Optional[str]) -> Optional[Tuple[str, str, str, str]]:
    if not code:
        return None
    for series_code, title, finding_aid, _lo, _hi in COLLECTIONS:
        if code.startswith(series_code):
            return series_code, title, finding_aid, "confirmed"
    return None


def collection_for_volume(volume: Any, volume_range: Any) -> Optional[Tuple[str, str, str, str]]:
    def in_range(v):
        try:
            v_int = int(v)
            for series_code, title, finding_aid, lo, hi in COLLECTIONS:
                if lo <= v_int <= hi:
                    return series_code, title, finding_aid, "inferred"
        except (ValueError, TypeError):
            pass
        return None

    if volume and str(volume).isdigit():
        res = in_range(volume)
        if res:
            return res
    if volume_range:
        parts = str(volume_range).split("-")
        if len(parts) == 2 and all(p.strip().isdigit() for p in parts):
            lo_res = in_range(parts[0].strip())
            hi_res = in_range(parts[1].strip())
            if lo_res and hi_res and lo_res[0] == hi_res[0]:
                return lo_res
    return None


def load_checkpoint(checkpoint_path: str) -> Dict[str, Any]:
```

- [ ] **Step 2: Remove Paleographer.py's duplicate table and functions, redirect call sites**

In `Paleographer/Paleographer.py`, remove the duplicate definitions:

```python
old_string:
COLLECTIONS = [
    ("RG15-D-II-8-a", "Affidavits, 1870-1885", "Finding Aid 15-19", 1319, 1324),
    ("RG15-D-II-8-b", "Applications, 1885", "Finding Aid 15-20", 1325, 1330),
    ("RG15-D-II-8-c", "Applications, 1886-1906", "Finding Aid 15-21", 1331, 1372),
]
UNKNOWN_COLLECTION_LABEL = "Unclassified (no rg_series_code or inferable volume yet)"


def collection_for_series_code(code: Optional[str]) -> Optional[Tuple[str, str, str, str]]:
    if not code:
        return None
    for series_code, title, finding_aid, _lo, _hi in COLLECTIONS:
        if code.startswith(series_code):
            return series_code, title, finding_aid, "confirmed"
    return None


def collection_for_volume(volume: Any, volume_range: Any) -> Optional[Tuple[str, str, str, str]]:
    def in_range(v):
        try:
            v_int = int(v)
            for series_code, title, finding_aid, lo, hi in COLLECTIONS:
                if lo <= v_int <= hi:
                    return series_code, title, finding_aid, "inferred"
        except (ValueError, TypeError):
            pass
        return None

    if volume and str(volume).isdigit():
        res = in_range(volume)
        if res:
            return res
    if volume_range:
        parts = str(volume_range).split("-")
        if len(parts) == 2 and all(p.strip().isdigit() for p in parts):
            lo_res = in_range(parts[0].strip())
            hi_res = in_range(parts[1].strip())
            if lo_res and hi_res and lo_res[0] == hi_res[0]:
                return lo_res
    return None


def classify_sheet_collection(sheet: Dict[str, Any]) -> Tuple[Optional[str], str, Optional[str], str]:
    """Determines collection for a sheet."""
    records = sheet.get("records", [])
    if records:
        record = records[0]
        series_code = (record.get("type_specific_fields") or {}).get("rg_series_code")
        res = collection_for_series_code(series_code)
        if res:
            return res

    meta = sheet.get("document_metadata", {})
    res = collection_for_volume(meta.get("volume"), meta.get("volume_range"))
    if res:
        return res

    return None, UNKNOWN_COLLECTION_LABEL, None, "unclassified"
```

```python
new_string:
UNKNOWN_COLLECTION_LABEL = "Unclassified (no rg_series_code or inferable volume yet)"


def classify_sheet_collection(sheet: Dict[str, Any]) -> Tuple[Optional[str], str, Optional[str], str]:
    """Determines collection for a sheet."""
    records = sheet.get("records", [])
    if records:
        record = records[0]
        series_code = (record.get("type_specific_fields") or {}).get("rg_series_code")
        res = voyageur_lac.collection_for_series_code(series_code)
        if res:
            return res

    meta = sheet.get("document_metadata", {})
    res = voyageur_lac.collection_for_volume(meta.get("volume"), meta.get("volume_range"))
    if res:
        return res

    return None, UNKNOWN_COLLECTION_LABEL, None, "unclassified"
```

- [ ] **Step 3: Run pycodestyle and the full test suite**

```
pycodestyle --max-line-length=120 Paleographer/Paleographer.py Voyageur/LAC.py
pytest Paleographer/tests/ Voyageur/tests/ -v
```
Expected: no violations; all tests pass, including any test exercising `partition_json_by_collection`/`classify_sheet_collection` (these now resolve through `voyageur_lac`, same return values as before).

- [ ] **Step 4: Commit**

```bash
git add Paleographer/Paleographer.py Voyageur/LAC.py
git commit -m "Consolidate COLLECTIONS table into voyageur_lac, remove Paleographer.py's duplicate"
```

---

### Task 6: Wire up the crosscheck CLI mode with a mocked unit test

**Files:**
- Modify: `Paleographer/Paleographer.py`
- Create: `Paleographer/tests/test_crosscheck.py`

**Interfaces:**
- Consumes: `cross_check_claim_record(record, cookies, media_dir)` (already implemented, `Paleographer.py:2050-2104`, unchanged by this task), `resolve_json_input(json_file, json_dir) -> Path` (already implemented, unchanged), `voyageur_lac.MEDIA_DIR` (module-level constant on `Voyageur/LAC.py`, unchanged).
- Produces: `main()`'s `crosscheck` mode now actually runs. No later task depends on this.

- [ ] **Step 1: Add the crosscheck dispatch branch**

In `Paleographer/Paleographer.py`, `main()`'s argparse setup needs a `--cookie-file` argument (only `crosscheck` uses it), and a new dispatch branch following the same load/process/save shape as `enrich`/`resolve-names`.

```python
old_string:
        parser.add_argument("--json", dest="json_path", default=None,
                            help="Path to JSON dataset (for enrich, crosscheck, partition, resolve-names)")
        parser.add_argument("--delay", type=float, default=0.4, help="Delay in seconds between requests (for enrich)")
        parser.add_argument("--limit", type=int, default=None, help="Limit number of records to process (for enrich)")
        parser.add_argument("--output-dir", default=None, help="Output directory for partitioned datasets")
        args, _ = parser.parse_known_args()

        if args.mode == "enrich":
```

```python
new_string:
        parser.add_argument("--json", dest="json_path", default=None,
                            help="Path to JSON dataset (for enrich, crosscheck, partition, resolve-names)")
        parser.add_argument("--delay", type=float, default=0.4, help="Delay in seconds between requests (for enrich)")
        parser.add_argument("--limit", type=int, default=None, help="Limit number of records to process (for enrich)")
        parser.add_argument("--output-dir", default=None, help="Output directory for partitioned datasets")
        parser.add_argument("--cookie-file", default=voyageur_lac.COOKIE_FILE,
                            help="Path to browser cookies file for LAC search (for crosscheck)")
        args, _ = parser.parse_known_args()

        if args.mode == "crosscheck":
            target = resolve_json_input(args.json_path or os.getenv("MASTER_DB", "master_database.json"),
                                        os.getenv("OUTPUT_DIR", str(Path(__file__).resolve().parent / "output")))
            print(f"Cross-checking claims in dataset: {target}...")
            try:
                cookies = voyageur_lac.load_cookies(args.cookie_file)
            except (FileNotFoundError, ValueError) as e:
                print(f"[FATAL ERROR] {e} Search LAC once in a real browser, then paste its Cookie header "
                      f"into that file.")
                return
            with open(target, "r", encoding="utf-8") as f:
                data = json.load(f)
            for sheet in data.get("sheets", []):
                for record in sheet.get("records", []):
                    cross_check_claim_record(record, cookies, voyageur_lac.MEDIA_DIR)
            with open(target, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"Cross-check complete: {target}")
            return

        if args.mode == "enrich":
```

- [ ] **Step 2: Write the failing test**

Create `Paleographer/tests/test_crosscheck.py`:

```python
"""
Unit tests for Paleographer.py's cross_check_claim_record - wired into the crosscheck CLI
mode by this same cleanup pass (see Paleographer.py main()'s "crosscheck" dispatch branch).
No real network call is ever made: lac_client.search and voyageur_lac.download_pid_bundle
are monkeypatched on the imported module's own attributes.
"""
import importlib
import sys

import pytest


@pytest.fixture
def paleographer_module(monkeypatch, tmp_path):
    program_dir = tmp_path / "program"
    (program_dir / "Parish").mkdir(parents=True)
    (program_dir / "JSON").mkdir(parents=True)

    env = {
        "PROGRAM_DIR": str(program_dir),
        "JSON_DIR": "JSON",
        "PALEOGRAPHER_RECORD_TYPE": "Parish",
        "MODEL_NAME": "gemini-test-model",
        "GEMINI_API_KEY": "fake-key-not-used",
        "API_BUDGET": "5.00",
        "COST_PER_1M_INPUT": "0.075",
        "COST_PER_1M_OUTPUT": "0.30",
        "CACHE_DISCOUNT_MULTIPLIER": "0.10",
        "VOLUME_TITLE": "Test Volume",
        "VOLUME_NUM": "1",
        "EXTRACTION_ENGINE": "api",
        "CHURCH_IMAGE_DIR": "Parish",
        "CHURCH_MASTER_DB_NAME": "parish_register.json",
    }
    for key in ("IMAGE_DIR", "MASTER_DB_NAME"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(sys, "argv", ["Paleographer.py"])
    monkeypatch.setattr("google.genai.Client", lambda *a, **k: object())

    sys.modules.pop("Paleographer", None)
    return importlib.import_module("Paleographer")


def _record(file_name="", **overrides):
    record = {
        "document_metadata": {"file_name": file_name},
        "claim_number": "1234",
        "participants": [],
    }
    record.update(overrides)
    return record


def test_own_pid_resolution_succeeds_and_merges(paleographer_module, monkeypatch):
    module = paleographer_module

    def fake_download(pid, media_dir, document_type_override=None):
        assert pid == "1502188"
        return {
            "pid": pid,
            "lac_catalog_title": "Test Claim Title",
            "reel_numbers": ["C-1234"],
            "series_code": "RG15-D-II-8-a",
            "source_documents": [],
        }

    monkeypatch.setattr(module.voyageur_lac, "download_pid_bundle", fake_download)
    monkeypatch.setattr(module.lac_client, "search", lambda query, cookies: [])

    record = _record(file_name="BAC-LAC_fonandcol_1502188.pdf")
    result = module.cross_check_claim_record(record, {"cookie": "value"}, "media")

    assert result["lac_pid"] == "1502188"
    assert result["lac_catalog_title"] == "Test Claim Title"
    assert result["type_specific_fields"]["reel_numbers"] == "C-1234"
    assert result["type_specific_fields"]["rg_series_code"] == "RG15-D-II-8-a"
    assert "review_reason" not in result


def test_own_pid_resolution_fails_appends_review_reason(paleographer_module, monkeypatch):
    module = paleographer_module

    def fake_download(pid, media_dir, document_type_override=None):
        raise module.lac_client.LacCallError(f"404 for {pid}")

    monkeypatch.setattr(module.voyageur_lac, "download_pid_bundle", fake_download)
    monkeypatch.setattr(module.lac_client, "search", lambda query, cookies: [])

    record = _record(file_name="BAC-LAC_fonandcol_1502188.pdf")
    result = module.cross_check_claim_record(record, {"cookie": "value"}, "media")

    assert result["lac_pid"] == "1502188"
    assert any("failed to fetch own PID 1502188" in r for r in result["review_reason"])


def test_related_pid_search_finds_results_and_appends_source_documents(paleographer_module, monkeypatch):
    module = paleographer_module

    related_entry = {"document_type": "Affidavit", "media_path": "media/999/asset1.pdf",
                      "lac_pid": "999", "lac_asset_id": "asset1", "source": "LAC"}

    def fake_download(pid, media_dir, document_type_override=None):
        assert pid == "999"
        return {"pid": pid, "lac_catalog_title": "Related", "reel_numbers": [],
                "series_code": None, "source_documents": [related_entry]}

    monkeypatch.setattr(module.voyageur_lac, "download_pid_bundle", fake_download)
    monkeypatch.setattr(module.lac_client, "search", lambda query, cookies: ["999"])

    record = _record(file_name="")  # no own PID - file_name doesn't match the PID convention
    result = module.cross_check_claim_record(record, {"cookie": "value"}, "media")

    assert result["source_documents"] == [related_entry]
    assert "review_reason" not in result


def test_search_auth_error_breaks_loop_with_review_reason(paleographer_module, monkeypatch):
    module = paleographer_module
    call_count = {"n": 0}

    def fake_search(query, cookies):
        call_count["n"] += 1
        raise module.lac_client.LacSearchAuthError("cookie expired")

    monkeypatch.setattr(module.lac_client, "search", fake_search)

    record = _record(file_name="", scrip_number="1 to 2")  # two queries if the loop doesn't break
    result = module.cross_check_claim_record(record, {"cookie": "value"}, "media")

    assert call_count["n"] == 1
    assert any("search cookie expired/invalid" in r for r in result["review_reason"])
```

- [ ] **Step 3: Run the new test to verify it exercises real code**

```
pytest Paleographer/tests/test_crosscheck.py -v
```
Expected: all four tests pass against the existing, already-correct `cross_check_claim_record` implementation. If any fails, the failure is in this task's own dispatch/test wiring, not in `cross_check_claim_record` itself (spec confirms that implementation is already correct) — debug the test fixture/mocking before assuming the production code is wrong.

- [ ] **Step 4: Run pycodestyle and the full test suite**

```
pycodestyle --max-line-length=120 Paleographer/Paleographer.py Paleographer/tests/test_crosscheck.py
pytest Paleographer/tests/ -v
```
Expected: no violations; all tests pass.

- [ ] **Step 5: Commit**

```bash
git add Paleographer/Paleographer.py Paleographer/tests/test_crosscheck.py
git commit -m "Wire up crosscheck CLI mode dispatch, add mocked unit tests"
```

---

### Task 7: Extract normalization helpers into Commissioner/normalization.py

**Files:**
- Create: `Commissioner/normalization.py`
- Create: `Commissioner/tests/test_normalization.py`
- Modify: `Paleographer/Paleographer.py`
- Modify: `Voyageur/FS.py`
- Modify: `Voyageur/tests/test_fs.py` (remove the 3 migrated tests)

**Interfaces:**
- Consumes: nothing from other tasks (independent of Tasks 1-6's edits to different regions of these files, but run this task after Task 1 since Task 1 also edits Paleographer.py's lines 77-450 region — sequencing avoids the two tasks' diffs colliding).
- Produces: `normalization.cap_case(text) -> str`, `normalization.parse_to_iso(reading) -> Optional[str]`, `normalization.derive_record_identity(record, event_types_table, set_type_code=False) -> None`, `normalization.derive_role_number(role_name, roles_table) -> Optional[str]`, `normalization.derive_role_semantic(role_number, roles_table) -> Optional[str]`. No later task in this plan consumes these.

**Behavioral divergence found and resolved (do not silently pick one — this is the resolution):**
`FS.py`'s `derive_record_identity` additionally sets `record["record_type_code"] = entry.get("code")`; `Paleographer.py`'s does not (deliberately — the now-deleted `Paleographer/postprocess.py` documented that this was intentionally dropped once Archivist started deriving event/family-bucket handling directly from `event_type` via `FactTypes.json`, no longer needing `record_type_code`). The shared function gets a `set_type_code: bool = False` parameter: `FS.py`'s call site passes `set_type_code=True` (preserving its exact existing behavior), `Paleographer.py`'s call site uses the default (preserving its exact existing behavior). Neither file's behavior changes.

`Paleographer.py`'s `derive_role_numbers`/`derive_role_semantics` (plural) are record-level batch mutators with extra logic (role_name cap_case normalization, skip-if-already-set) that `FS.py`'s singular `derive_role_number`/`derive_role_semantic` don't have — these are not the same abstraction level, so only the shared single-value lookup primitive moves to `Commissioner/normalization.py` (matching `FS.py`'s existing singular shape). `Paleographer.py` keeps its own plural batch-mutator functions locally, but their internal lookup now delegates to the shared primitive instead of reimplementing the `name_to_number`/`roles_table` dict-building logic inline.

- [ ] **Step 1: Write the failing tests (migrated from Voyageur/tests/test_fs.py, plus new coverage for the set_type_code divergence)**

Create `Commissioner/tests/test_normalization.py`:

```python
from Commissioner import normalization

ROLES = {
    "1": {"name": "Primary", "semantic": "primary"},
    "2": {"name": "Father", "semantic": "father"},
    "7": {"name": "Godfather/Witness 1"},
}

EVENT_TYPES = {
    "Baptism": {"code": "7", "id_prefix": "BAPM-"},
}


def test_derive_role_semantic_matches_by_role_number():
    assert normalization.derive_role_semantic("1", ROLES) == "primary"
    assert normalization.derive_role_semantic("2", ROLES) == "father"


def test_derive_role_semantic_none_for_role_without_semantic():
    assert normalization.derive_role_semantic("7", ROLES) is None


def test_derive_role_semantic_none_for_missing_role_number():
    assert normalization.derive_role_semantic(None, ROLES) is None


def test_derive_record_identity_default_does_not_set_type_code():
    record = {"event_type": "Baptism", "record_number": "45"}
    normalization.derive_record_identity(record, EVENT_TYPES)
    assert record["record_id"] == "BAPM-45"
    assert "record_type_code" not in record


def test_derive_record_identity_set_type_code_true_sets_it():
    record = {"event_type": "Baptism", "record_number": "45"}
    normalization.derive_record_identity(record, EVENT_TYPES, set_type_code=True)
    assert record["record_id"] == "BAPM-45"
    assert record["record_type_code"] == "7"


def test_cap_case_preserves_known_acronym():
    assert normalization.cap_case("hbc trading post") == "HBC Trading Post"


def test_parse_to_iso_full_date():
    assert normalization.parse_to_iso("December 12, 1850") == "1850-12-12"
```

- [ ] **Step 2: Run the new test to verify it fails (module doesn't exist yet)**

```
pytest Commissioner/tests/test_normalization.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'Commissioner.normalization'` (or ImportError).

- [ ] **Step 3: Create Commissioner/normalization.py**

```python
"""
Shared record-normalization helpers used by both Paleographer.py (AI-transcribed records)
and Voyageur/FS.py (FamilySearch-indexed records) - text casing, date parsing, and
record/role identity derivation that both sources need applied the same way so Archivist
sees one consistent shape regardless of provenance.
"""

import re
from typing import Any, Dict, Optional

from titlecase import titlecase

PRESERVED_ACRONYMS = {"HBC", "NWT", "USA", "NWMP", "RCMP", "UK", "US", "ED", "PID", "RM", "FTM"}


def _titlecase_callback(word: str, **kwargs) -> Optional[str]:
    w_clean = re.sub(r'^[^\w]+|[^\w]+$', '', word)
    if w_clean.upper() in PRESERVED_ACRONYMS:
        return word.replace(w_clean, w_clean.upper())
    if "-" in word:
        parts = word.split("-")
        return "-".join(
            (p.upper() if re.sub(r'^[^\w]+|[^\w]+$', '', p).upper() in PRESERVED_ACRONYMS
             else titlecase(p, callback=_titlecase_callback).capitalize())
            for p in parts
        )
    return None


def cap_case(text: str) -> str:
    if not text:
        return ""
    val = str(text).strip()
    if not val:
        return ""
    return titlecase(val, callback=_titlecase_callback)


MONTH_NAMES = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sept": 9, "sep": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}

_ISO_DATE_PATTERN = re.compile(r"^\s*(\d{4})-(\d{2})-(\d{2})\s*$")
_ISO_YEAR_MONTH_PATTERN = re.compile(r"^\s*(\d{4})-(\d{2})\s*$")

_DATE_PATTERNS = [
    re.compile(r"^\s*([A-Za-z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{3,4})\s*$"),  # "December 12, 1850"
    re.compile(r"^\s*(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\.?,?\s+(\d{3,4})\s*$"),  # "12 December 1850"
    re.compile(r"^\s*([A-Za-z]+)\.?\s+(\d{3,4})\s*$"),                                # "December 1850"
    re.compile(r"^\s*(\d{3,4})\s*$"),                                                  # bare year "1850"
]


def parse_to_iso(reading: Optional[str]) -> Optional[str]:
    """Parses a plain English-language date reading into YYYY-MM-DD (or a coarser YYYY-MM /
    YYYY if day/month aren't stated). Passes through a date already given in ISO form
    unchanged. Returns None if the reading can't be confidently parsed, rather than
    guessing."""
    if not reading:
        return None
    text = reading.strip()

    if _ISO_DATE_PATTERN.match(text) or _ISO_YEAR_MONTH_PATTERN.match(text):
        return text

    m = _DATE_PATTERNS[0].match(text)
    if m:
        month = MONTH_NAMES.get(m.group(1).lower())
        if month:
            return f"{int(m.group(3)):04d}-{month:02d}-{int(m.group(2)):02d}"

    m = _DATE_PATTERNS[1].match(text)
    if m:
        month = MONTH_NAMES.get(m.group(2).lower())
        if month:
            return f"{int(m.group(3)):04d}-{month:02d}-{int(m.group(1)):02d}"

    m = _DATE_PATTERNS[2].match(text)
    if m:
        month = MONTH_NAMES.get(m.group(1).lower())
        if month:
            return f"{int(m.group(2)):04d}-{month:02d}"

    m = _DATE_PATTERNS[3].match(text)
    if m:
        return f"{int(m.group(1)):04d}"

    return None


def derive_record_identity(record: Dict[str, Any], event_types_table: Dict[str, Dict[str, str]],
                           set_type_code: bool = False) -> None:
    """Sets record_id (id_prefix + record_number) from event_type, looked up in
    event_types_table. When set_type_code is True, also sets record_type_code=entry['code']
    - needed by Voyageur/FS.py's callers; Paleographer.py's callers derive event/family-
    bucket handling directly from event_type via FactTypes.json and don't set
    record_type_code (a deliberate prior decision, not an oversight)."""
    event_type = record.get("event_type")
    entry: Optional[Dict[str, str]] = event_types_table.get(event_type) if event_type else None
    if not entry:
        return

    if set_type_code:
        record["record_type_code"] = entry.get("code")

    record_number: Optional[str] = record.get("record_number")
    if record_number:
        record["record_id"] = f"{entry.get('id_prefix', '')}{record_number}"


def derive_role_number(role_name: str, roles_table: Dict[str, Dict[str, Optional[str]]]) -> Optional[str]:
    """Looks up a participant's role_number from their plain-word role_name (case-insensitive
    match on the role's display name)."""
    name_to_number = {(role.get("name") or "").strip().lower(): number for number, role in roles_table.items()}
    return name_to_number.get((role_name or "").strip().lower())


def derive_role_semantic(role_number: Optional[str],
                         roles_table: Dict[str, Dict[str, Optional[str]]]) -> Optional[str]:
    """Looks up a participant's role_semantic from their already-resolved role_number."""
    role = roles_table.get(role_number) if role_number else None
    return role.get("semantic") if role else None
```

- [ ] **Step 4: Run the new test to verify it passes**

```
pytest Commissioner/tests/test_normalization.py -v
```
Expected: PASS (all 7 tests).

- [ ] **Step 5: Update Paleographer.py to import and use the shared module**

Add the import (after the existing `voyageur_lac` cross-import block, before the `.env` loading):

```python
old_string:
try:
    from Voyageur import lac_client
    from Voyageur import LAC as voyageur_lac
except (ImportError, ValueError):
    try:
        from . import lac_client
        from . import LAC as voyageur_lac
    except (ImportError, ValueError):
        import lac_client
        import LAC as voyageur_lac

# Global settings come from the project root's .env; this tool's own settings come from
# its own subfolder's .env, so Paleographer stays runnable standalone.
```

```python
new_string:
try:
    from Voyageur import lac_client
    from Voyageur import LAC as voyageur_lac
except (ImportError, ValueError):
    try:
        from . import lac_client
        from . import LAC as voyageur_lac
    except (ImportError, ValueError):
        import lac_client
        import LAC as voyageur_lac

from Commissioner import normalization

# Global settings come from the project root's .env; this tool's own settings come from
# its own subfolder's .env, so Paleographer stays runnable standalone.
```

Remove the now-duplicated definitions (`_titlecase_callback`/`cap_case`/`MONTH_NAMES`/date patterns/`parse_to_iso`/`derive_record_identity`, currently lines 77-178, keeping `strip_diacritics` and everything from `derive_role_numbers` onward):

```python
old_string:
PRESERVED_ACRONYMS = {"HBC", "NWT", "USA", "NWMP", "RCMP", "UK", "US", "ED", "PID", "RM", "FTM"}


def _titlecase_callback(word: str, **kwargs) -> str | None:
    w_clean = re.sub(r'^[^\w]+|[^\w]+$', '', word)
    if w_clean.upper() in PRESERVED_ACRONYMS:
        return word.replace(w_clean, w_clean.upper())
    if "-" in word:
        parts = word.split("-")
        return "-".join(
            (p.upper() if re.sub(r'^[^\w]+|[^\w]+$', '', p).upper() in PRESERVED_ACRONYMS
             else titlecase(p, callback=_titlecase_callback).capitalize())
            for p in parts
        )
    return None


def cap_case(text: str) -> str:
    if not text:
        return ""
    val = str(text).strip()
    if not val:
        return ""
    return titlecase(val, callback=_titlecase_callback)


MONTH_NAMES = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sept": 9, "sep": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}

_ISO_DATE_PATTERN = re.compile(r"^\s*(\d{4})-(\d{2})-(\d{2})\s*$")
_ISO_YEAR_MONTH_PATTERN = re.compile(r"^\s*(\d{4})-(\d{2})\s*$")

_DATE_PATTERNS = [
    re.compile(r"^\s*([A-Za-z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{3,4})\s*$"),  # "December 12, 1850"
    re.compile(r"^\s*(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\.?,?\s+(\d{3,4})\s*$"),  # "12 December 1850"
    re.compile(r"^\s*([A-Za-z]+)\.?\s+(\d{3,4})\s*$"),                                # "December 1850"
    re.compile(r"^\s*(\d{3,4})\s*$"),                                                  # bare year "1850"
]


def strip_diacritics(text: Optional[str]) -> Optional[str]:
    """Mechanically strips diacritics/accents, keeping only plain ASCII letters/numbers/
    punctuation. Applies to any std_* field regardless of record type."""
    if text is None:
        return None
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c))


def parse_to_iso(reading: Optional[str]) -> Optional[str]:
    """Parses the LLM's best English-language date reading into YYYY-MM-DD (or a
    coarser YYYY-MM / YYYY if day/month aren't stated). Also passes through a date the
    LLM already gave in ISO form unchanged. Returns None if the reading can't be
    confidently parsed, rather than guessing."""
    if not reading:
        return None
    text = reading.strip()

    if _ISO_DATE_PATTERN.match(text) or _ISO_YEAR_MONTH_PATTERN.match(text):
        return text

    m = _DATE_PATTERNS[0].match(text)
    if m:
        month = MONTH_NAMES.get(m.group(1).lower())
        if month:
            return f"{int(m.group(3)):04d}-{month:02d}-{int(m.group(2)):02d}"

    m = _DATE_PATTERNS[1].match(text)
    if m:
        month = MONTH_NAMES.get(m.group(2).lower())
        if month:
            return f"{int(m.group(3)):04d}-{month:02d}-{int(m.group(1)):02d}"

    m = _DATE_PATTERNS[2].match(text)
    if m:
        month = MONTH_NAMES.get(m.group(1).lower())
        if month:
            return f"{int(m.group(2)):04d}-{month:02d}"

    m = _DATE_PATTERNS[3].match(text)
    if m:
        return f"{int(m.group(1)):04d}"

    return None


def derive_record_identity(record: Dict[str, Any], event_types_table: Dict[str, Dict[str, str]]) -> None:
    """Sets record_id (id_prefix + record_number) from the LLM's plain word event_type,
    looked up in the active type's event_types table."""
    event_type = record.get("event_type")
    entry: Optional[Dict[str, str]] = event_types_table.get(event_type) if event_type else None
    if not entry:
        return

    record_number: Optional[str] = record.get("record_number")
    if record_number:
        record["record_id"] = f"{entry.get('id_prefix', '')}{record_number}"


def derive_role_numbers(record: Dict[str, Any], roles_table: Dict[str, Dict[str, Optional[str]]]) -> None:
    """Sets each participant's role_number from their plain-word role_name."""
    name_to_number = {(role.get("name") or "").strip().lower(): number for number, role in roles_table.items()}
    for participant in record.get("participants", []):
        raw_role_name = participant.get("role_name")
        if raw_role_name:
            participant["role_name"] = cap_case(raw_role_name)
        if participant.get("role_number"):
            continue
        role_name = (raw_role_name or "").strip().lower()
        role_number = name_to_number.get(role_name)
        if role_number is not None:
            participant["role_number"] = role_number
```

```python
new_string:
def strip_diacritics(text: Optional[str]) -> Optional[str]:
    """Mechanically strips diacritics/accents, keeping only plain ASCII letters/numbers/
    punctuation. Applies to any std_* field regardless of record type."""
    if text is None:
        return None
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c))


def derive_role_numbers(record: Dict[str, Any], roles_table: Dict[str, Dict[str, Optional[str]]]) -> None:
    """Sets each participant's role_number from their plain-word role_name."""
    for participant in record.get("participants", []):
        raw_role_name = participant.get("role_name")
        if raw_role_name:
            participant["role_name"] = normalization.cap_case(raw_role_name)
        if participant.get("role_number"):
            continue
        role_number = normalization.derive_role_number(raw_role_name or "", roles_table)
        if role_number is not None:
            participant["role_number"] = role_number
```

Update the remaining references to the moved names within `Paleographer.py`:

```python
old_string:
def derive_role_semantics(record: Dict[str, Any], roles_table: Dict[str, Dict[str, Optional[str]]]) -> None:
    """Sets each participant's role_semantic from their already-resolved role_number."""
    for participant in record.get("participants", []):
        role_number = participant.get("role_number")
        role = roles_table.get(role_number) if role_number else None
        semantic = role.get("semantic") if role else None
        if semantic:
            participant["role_semantic"] = semantic
```

```python
new_string:
def derive_role_semantics(record: Dict[str, Any], roles_table: Dict[str, Dict[str, Optional[str]]]) -> None:
    """Sets each participant's role_semantic from their already-resolved role_number."""
    for participant in record.get("participants", []):
        role_number = participant.get("role_number")
        semantic = normalization.derive_role_semantic(role_number, roles_table)
        if semantic:
            participant["role_semantic"] = semantic
```

```python
old_string:
def finalize_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Applies every generic mechanical post-processing step to one extracted record."""
    derive_role_numbers(record, TYPE_CFG.roles)
    derive_role_semantics(record, TYPE_CFG.roles)
    derive_record_identity(record, TYPE_CFG.event_types)
    derive_suffixes(record, TYPE_CFG.roles)
```

```python
new_string:
def finalize_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Applies every generic mechanical post-processing step to one extracted record."""
    derive_role_numbers(record, TYPE_CFG.roles)
    derive_role_semantics(record, TYPE_CFG.roles)
    normalization.derive_record_identity(record, TYPE_CFG.event_types)
    derive_suffixes(record, TYPE_CFG.roles)
```

Now find every remaining call site of the module-level `cap_case`/`parse_to_iso` names throughout `Paleographer.py` (they are used well beyond the deleted block — e.g. `_label_for` at line 246, `clean_race`/`clean_date_and_place` already removed in Task 1, plus many more downstream) and prefix each with `normalization.`:

```
grep -n "\bcap_case(\|\bparse_to_iso(" Paleographer/Paleographer.py
```

For every match where `cap_case(`/`parse_to_iso(` is a **call**, not a definition (the definitions are already gone from Step 5 above), change it to `normalization.cap_case(`/`normalization.parse_to_iso(`. Do this with a project-wide-safe scoped replace within `Paleographer.py` only — do not touch `FS.py` in this step (Step 6 handles it separately, since `FS.py`'s callers need the same treatment but are edited independently):

```
sed -i 's/\bcap_case(/normalization.cap_case(/g; s/\bparse_to_iso(/normalization.parse_to_iso(/g' Paleographer/Paleographer.py
```

This sed pass is safe because Step 5 already removed the only two definitions (`def cap_case` / `def parse_to_iso`) from this file, so every remaining `cap_case(`/`parse_to_iso(` token is a call site. Run `grep -n "\bcap_case(\|\bparse_to_iso(" Paleographer/Paleographer.py` again afterward and confirm every match now reads `normalization.cap_case(`/`normalization.parse_to_iso(`.

- [ ] **Step 6: Update FS.py to import and use the shared module**

Add the repo-root sys.path insertion (mirroring `census_schema.py`'s own precedent) and the import:

```python
old_string:
import json
import os
import re
import shutil
import sys
import time
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import yaml
from dotenv import load_dotenv, set_key
from thefuzz import fuzz
from titlecase import titlecase

import census_schema
from _retry_utils import cleanup_checkpoint_files, move_with_retry

PRESERVED_ACRONYMS = {"HBC", "NWT", "USA", "NWMP", "RCMP", "UK", "US", "ED", "PID", "RM", "FTM"}


def _titlecase_callback(word: str, **kwargs) -> str | None:
    w_clean = re.sub(r'^[^\w]+|[^\w]+$', '', word)
    if w_clean.upper() in PRESERVED_ACRONYMS:
        return word.replace(w_clean, w_clean.upper())
    if "-" in word:
        parts = word.split("-")
        return "-".join(
            (
                p.upper() if re.sub(r'^[^\w]+|[^\w]+$', '', p).upper() in PRESERVED_ACRONYMS
                else titlecase(p, callback=_titlecase_callback).capitalize()
            )
            for p in parts
        )
    return None


def cap_case(text: str) -> str:
    if not text:
        return ""
    val = str(text).strip()
    if not val:
        return ""
    return titlecase(val, callback=_titlecase_callback)


SCRIPTORIUM_DIR = Path(__file__).resolve().parent.parent
```

```python
new_string:
import json
import os
import re
import shutil
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
from _retry_utils import cleanup_checkpoint_files, move_with_retry

# Commissioner lives in a sibling tool folder, not an installed package - add the repo
# root to sys.path so it can be imported by absolute path, matching census_schema.py's own
# precedent for cross-package imports.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from Commissioner import normalization  # noqa: E402

SCRIPTORIUM_DIR = Path(__file__).resolve().parent.parent
```

(`titlecase` import is dropped since `_titlecase_callback`/`cap_case` move out; `re` stays — still used elsewhere in `FS.py` beyond the deleted block.)

Remove the now-duplicated `MONTH_NAMES`/date-pattern constants/`parse_to_iso`/`derive_record_identity`/`derive_role_number`/`derive_role_semantic` block:

```python
old_string:
MONTH_NAMES = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sept": 9, "sep": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}
_ISO_DATE_PATTERN = re.compile(r"^\s*(\d{4})-(\d{2})-(\d{2})\s*$")
_ISO_YEAR_MONTH_PATTERN = re.compile(r"^\s*(\d{4})-(\d{2})\s*$")
_DATE_PATTERNS = [
    re.compile(r"^\s*([A-Za-z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{3,4})\s*$"),  # "December 12, 1850"
    re.compile(r"^\s*(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\.?,?\s+(\d{3,4})\s*$"),  # "12 December 1850"
    re.compile(r"^\s*([A-Za-z]+)\.?\s+(\d{3,4})\s*$"),                                # "December 1850"
    re.compile(r"^\s*(\d{3,4})\s*$"),                                                 # bare year "1850"
]


def parse_to_iso(reading: Optional[str]) -> Optional[str]:
    """Parses a plain English-language date reading into YYYY-MM-DD (or a coarser YYYY-MM /
    YYYY if day/month aren't stated). Mirrors Paleographer/postprocess.py's parse_to_iso -
    duplicated locally rather than imported, per this project's convention of every tool
    folder staying self-contained (see module docstring)."""
    if not reading:
        return None
    text = reading.strip()

    if _ISO_DATE_PATTERN.match(text) or _ISO_YEAR_MONTH_PATTERN.match(text):
        return text

    m = _DATE_PATTERNS[0].match(text)
    if m:
        month = MONTH_NAMES.get(m.group(1).lower())
        if month:
            return f"{int(m.group(3)):04d}-{month:02d}-{int(m.group(2)):02d}"

    m = _DATE_PATTERNS[1].match(text)
    if m:
        month = MONTH_NAMES.get(m.group(2).lower())
        if month:
            return f"{int(m.group(3)):04d}-{month:02d}-{int(m.group(1)):02d}"

    m = _DATE_PATTERNS[2].match(text)
    if m:
        month = MONTH_NAMES.get(m.group(1).lower())
        if month:
            return f"{int(m.group(2)):04d}-{month:02d}"

    m = _DATE_PATTERNS[3].match(text)
    if m:
        return f"{int(m.group(1)):04d}"

    return None


def derive_record_identity(record: Dict[str, Any], event_types_table: Dict[str, Dict[str, str]]) -> None:
    """Sets record_type_code and record_id (prefix + record_number) from event_type, looked
    up in the shared FactTypes.json table. No-ops if event_type isn't recognized."""
    event_type = record.get("event_type")
    entry = event_types_table.get(event_type) if event_type else None
    if not entry:
        return
    record["record_type_code"] = entry.get("code")
    record_number = record.get("record_number")
    if record_number:
        record["record_id"] = f"{entry.get('id_prefix', '')}{record_number}"


def derive_role_number(role_name: str, roles_table: Dict[str, Dict[str, Optional[str]]]) -> Optional[str]:
    """Looks up a participant's role_number from their plain-word role_name (case-insensitive
    match on the role's display name), same convention as Paleographer/postprocess.py."""
    name_to_number = {(role.get("name") or "").strip().lower(): number for number, role in roles_table.items()}
    return name_to_number.get((role_name or "").strip().lower())


def derive_role_semantic(role_number: Optional[str],
                         roles_table: Dict[str, Dict[str, Optional[str]]]) -> Optional[str]:
    """Looks up a participant's role_semantic from their already-resolved role_number, same
    convention as Paleographer/postprocess.py.derive_role_semantics - this is the field
    Archivist actually reads to build FAMC/FAMS/associations, so an indexed row's plain
    'Relationship'/'Role' column value has to reach it the same way an AI-read role_name
    does, not just role_number (which Archivist no longer uses for family linking)."""
    role = roles_table.get(role_number) if role_number else None
    return role.get("semantic") if role else None
```

```python
new_string:
```

(This block is deleted entirely — nothing replaces it; the next function in the file, `split_name_and_dit`, follows directly after the section-header comment that precedes it.)

Update the four call sites within `row_to_record`/the record-building loop:

```python
old_string:
        primary["birth_date"] = parse_to_iso(birth_date) or (birth_date or None)
```

```python
new_string:
        primary["birth_date"] = normalization.parse_to_iso(birth_date) or (birth_date or None)
```

```python
old_string:
        primary["death_date"] = parse_to_iso(death_date) or (death_date or None)
```

```python
new_string:
        primary["death_date"] = normalization.parse_to_iso(death_date) or (death_date or None)
```

```python
old_string:
    event_type = cap_case(EVENT_TYPE_ALIASES.get(raw_event_type, raw_event_type))
```

```python
new_string:
    event_type = normalization.cap_case(EVENT_TYPE_ALIASES.get(raw_event_type, raw_event_type))
```

```python
old_string:
        "year": (parse_to_iso(event_date_raw) or "")[:4] or None,
        "event_date": parse_to_iso(event_date_raw) or event_date_raw or None,
        "event_place": cap_case((columns.get("Event Place") or "").strip()) or None,
```

```python
new_string:
        "year": (normalization.parse_to_iso(event_date_raw) or "")[:4] or None,
        "event_date": normalization.parse_to_iso(event_date_raw) or event_date_raw or None,
        "event_place": normalization.cap_case((columns.get("Event Place") or "").strip()) or None,
```

```python
old_string:
        "role_name": cap_case(role_name),
```

```python
new_string:
        "role_name": normalization.cap_case(role_name),
```

Update the batch-processing loop that calls `derive_record_identity`/`derive_role_number`/`derive_role_semantic`:

```python
old_string:
        for record in records:
            derive_record_identity(record, event_types_table)
            for participant in record["participants"]:
                role_number = derive_role_number(participant["role_name"], roles_table)
                if role_number is not None:
                    participant["role_number"] = role_number
                    role_semantic = derive_role_semantic(role_number, roles_table)
                    if role_semantic is not None:
                        participant["role_semantic"] = role_semantic
```

```python
new_string:
        for record in records:
            normalization.derive_record_identity(record, event_types_table, set_type_code=True)
            for participant in record["participants"]:
                role_number = normalization.derive_role_number(participant["role_name"], roles_table)
                if role_number is not None:
                    participant["role_number"] = role_number
                    role_semantic = normalization.derive_role_semantic(role_number, roles_table)
                    if role_semantic is not None:
                        participant["role_semantic"] = role_semantic
```

Run `grep -n "\bcap_case(\|\bparse_to_iso(" Voyageur/FS.py` and confirm every remaining match is prefixed `normalization.` — the six call sites above are every one found during plan-writing, but re-grep to be certain none were missed.

- [ ] **Step 7: Remove the three migrated tests from Voyageur/tests/test_fs.py**

```python
old_string:
import FS

ROLES = {
    "1": {"name": "Primary", "semantic": "primary"},
    "2": {"name": "Father", "semantic": "father"},
    "7": {"name": "Godfather/Witness 1"},
}


def test_derive_role_semantic_matches_by_role_number():
    assert FS.derive_role_semantic("1", ROLES) == "primary"
    assert FS.derive_role_semantic("2", ROLES) == "father"


def test_derive_role_semantic_none_for_role_without_semantic():
    assert FS.derive_role_semantic("7", ROLES) is None


def test_derive_role_semantic_none_for_missing_role_number():
    assert FS.derive_role_semantic(None, ROLES) is None
```

```python
new_string:
```

`Voyageur/tests/test_fs.py` is now empty of content — delete the file entirely rather than leaving a zero-test file:

```bash
git rm Voyageur/tests/test_fs.py
```

- [ ] **Step 8: Run pycodestyle and the full test suite**

```
pycodestyle --max-line-length=120 Paleographer/Paleographer.py Voyageur/FS.py Commissioner/normalization.py Commissioner/tests/test_normalization.py
pytest Paleographer/tests/ Voyageur/tests/ Commissioner/tests/ -v
```
Expected: no violations; all tests pass, including `Paleographer/tests/test_paleographer_pipeline.py` (exercises `finalize_record`/`derive_role_numbers`/`derive_role_semantics`/`normalization.derive_record_identity` end-to-end) and the new `Commissioner/tests/test_normalization.py`.

- [ ] **Step 9: Commit**

```bash
git add -A -- Commissioner/normalization.py Commissioner/tests/test_normalization.py Paleographer/Paleographer.py Voyageur/FS.py Voyageur/tests/test_fs.py
git commit -m "Extract cap_case/parse_to_iso/derive_record_identity/derive_role_number(s)/derive_role_semantic(s) into Commissioner/normalization.py"
```

---

### Task 8: Harden error handling in A.py, FS.py, Paleographer.py

**Files:**
- Modify: `Voyageur/A.py`
- Modify: `Voyageur/FS.py`
- Modify: `Paleographer/Paleographer.py`
- Test: existing suites (no new file — pure error-handling narrowing, no new branch to cover)

**Interfaces:**
- Consumes: the post-Task-3 versions of `A.py`/`FS.py` (this task's edits are in the polling/image-move loops, a different region than Task 3's retry-helper extraction, but sequenced after it to land on the final file shape).
- Produces: nothing later tasks depend on.

- [ ] **Step 1: Narrow the downloads-dir polling loop's except clause in A.py**

```python
old_string:
                if candidates:
                    json_file = max(candidates, key=lambda p: p.stat().st_mtime)
                    print(f"[System] Detected Final JSON: {json_file.name}")
            except Exception:
                pass
```

```python
new_string:
                if candidates:
                    json_file = max(candidates, key=lambda p: p.stat().st_mtime)
                    print(f"[System] Detected Final JSON: {json_file.name}")
            except OSError:
                pass
```

- [ ] **Step 2: Log the image-move loop's failure in A.py instead of swallowing it**

```python
old_string:
    for file_path in image_candidates:
        # noinspection broad-exception
        try:
            final_img = img_target_dir / file_path.name[len(image_prefix):]
            move_with_retry(file_path, final_img)
            img_count += 1
        except Exception:
            pass
```

```python
new_string:
    for file_path in image_candidates:
        # noinspection broad-exception
        try:
            final_img = img_target_dir / file_path.name[len(image_prefix):]
            move_with_retry(file_path, final_img)
            img_count += 1
        except Exception as e:
            print(f"[ERROR] Could not move image {file_path.name}: {e}")
```

- [ ] **Step 3: Narrow the downloads-dir polling loop's except clause in FS.py**

```python
old_string:
                if candidates:
                    raw_json_file = max(candidates, key=lambda p: p.stat().st_mtime)
                    print(f"[System] Detected raw gather JSON: {raw_json_file.name}")
            except Exception:
                pass
```

```python
new_string:
                if candidates:
                    raw_json_file = max(candidates, key=lambda p: p.stat().st_mtime)
                    print(f"[System] Detected raw gather JSON: {raw_json_file.name}")
            except OSError:
                pass
```

- [ ] **Step 4: Log the image-move loop's failure in FS.py instead of swallowing it**

```python
old_string:
    for file_path in image_candidates:
        # noinspection broad-exception
        try:
            final_img = img_target_dir / file_path.name[len(image_prefix):]
            move_with_retry(file_path, final_img)
            img_count += 1
        except Exception:
            pass
```

```python
new_string:
    for file_path in image_candidates:
        # noinspection broad-exception
        try:
            final_img = img_target_dir / file_path.name[len(image_prefix):]
            move_with_retry(file_path, final_img)
            img_count += 1
        except Exception as e:
            print(f"[ERROR] Could not move image {file_path.name}: {e}")
```

- [ ] **Step 5: Log has_usable_text_layer's failure in Paleographer.py instead of swallowing it**

```python
old_string:
def has_usable_text_layer(pdf_path: Union[str, Path], sample_pages: int = 3,
                          min_alpha_ratio: float = 0.5, min_chars: int = 40) -> bool:
    """Probes a PDF's first few pages for a genuine, non-garbage text layer."""
    # noinspection broad-exception
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            sampled = "".join((page.extract_text() or "") for page in pdf.pages[:sample_pages])
    except Exception:
        return False
```

```python
new_string:
def has_usable_text_layer(pdf_path: Union[str, Path], sample_pages: int = 3,
                          min_alpha_ratio: float = 0.5, min_chars: int = 40) -> bool:
    """Probes a PDF's first few pages for a genuine, non-garbage text layer."""
    # noinspection broad-exception
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            sampled = "".join((page.extract_text() or "") for page in pdf.pages[:sample_pages])
    except Exception as e:
        print(f"[ERROR] Could not probe text layer for {pdf_path}: {e}")
        return False
```

- [ ] **Step 6: Log optimize_pdf_for_upload's failure in Paleographer.py instead of silently forcing the fallback path**

```python
old_string:
def optimize_pdf_for_upload(file_path: Path, compression_level: int = 2) -> Path:
    """Runs PDFix's lossless structural optimization against a throwaway temp copy."""
    tmp_fd, tmp_path_str = tempfile.mkstemp(suffix=".pdf", prefix="pdfix_upload_")
    os.close(tmp_fd)
    tmp_path = Path(tmp_path_str)
    try:
        shutil.copy2(file_path, tmp_path)
        params = COMPRESSION_PARAMS.get(compression_level, COMPRESSION_PARAMS[2])
        optimize_pdf(str(tmp_path), params)
        return tmp_path
    except Exception:
        tmp_path.unlink(missing_ok=True)
        return file_path
```

```python
new_string:
def optimize_pdf_for_upload(file_path: Path, compression_level: int = 2) -> Path:
    """Runs PDFix's lossless structural optimization against a throwaway temp copy."""
    tmp_fd, tmp_path_str = tempfile.mkstemp(suffix=".pdf", prefix="pdfix_upload_")
    os.close(tmp_fd)
    tmp_path = Path(tmp_path_str)
    try:
        shutil.copy2(file_path, tmp_path)
        params = COMPRESSION_PARAMS.get(compression_level, COMPRESSION_PARAMS[2])
        optimize_pdf(str(tmp_path), params)
        return tmp_path
    except Exception as e:
        print(f"[ERROR] PDF optimization failed for {file_path}: {e}")
        tmp_path.unlink(missing_ok=True)
        return file_path
```

- [ ] **Step 7: Run pycodestyle and the full test suite**

```
pycodestyle --max-line-length=120 Voyageur/A.py Voyageur/FS.py Paleographer/Paleographer.py
pytest Voyageur/tests/ Paleographer/tests/ Commissioner/tests/ -v
```
Expected: no violations; all tests pass. If any test asserted on the old silent-swallow behavior (e.g. captured stdout expecting no output), update its assertion to expect the new `[ERROR]` line rather than removing the assertion.

- [ ] **Step 8: Commit**

```bash
git add Voyageur/A.py Voyageur/FS.py Paleographer/Paleographer.py
git commit -m "Narrow bare except Exception to OSError in polling loops, log swallowed failures elsewhere"
```

---

## Final Verification

After all 8 tasks:

```
pycodestyle --max-line-length=120 Paleographer/ Voyageur/ Commissioner/
pytest -v
```

Expected: zero pycodestyle violations across the whole branch; full suite green. Then proceed to `superpowers:finishing-a-development-branch`.
