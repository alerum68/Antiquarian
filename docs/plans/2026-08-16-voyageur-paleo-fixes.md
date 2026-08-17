# Voyageur & Paleographer Fixes Implementation Plan

> **For AGY:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** Fix three GUI/settings issues: expose Overwrite/Skip for all Voyageur sources, add a third "Gather, Transcribe & Build" pipeline button, and make Paleographer's record-type dropdown use the same multi-tier .pmt search as the runtime engine.

**Architecture:** All changes are in `Antiquarian.py` (GUI), `Voyageur/HBCA.py`, and `Voyageur/LAC.py`. No new files are created; no schema changes are needed except wiring `GATHER_ON_COLLISION` into the two scripts that currently ignore it. The Paleographer fix extracts a helper method to mirror `engine.py`'s `_prompt_search_dirs()` so GUI and runtime always agree on which .pmt files exist.

**Tech Stack:** Python 3.12, CustomTkinter, PyYAML, pathlib — all already in `requirements.txt`.

## Global Constraints

- Branch off `Unify`; do not push directly to `Unify` or `main`.
- Lint: `python -m pycodestyle --max-line-length=120` — zero violations required.
- All tests must pass: `python -m pytest` from repo root.
- Schema-completeness tests must pass: `python -m pytest tests/test_settings_schema_completeness.py tests/test_load_tool_schema.py`
- `GATHER_ON_COLLISION` is already declared in `Voyageur/settings_schema.yaml` — no YAML edits needed.
- `PROMPTS_DIR` stays in `INTERNAL_KEYS` — no Global Settings UI changes needed.
- Never re-run `capture_golden_gedcom.py`.

---

### Task 0: Create feature branch

**Files:** none (git only)

**Step 1: Create and check out branch**

```bash
git checkout -b fix/voyageur-paleo-settings
```

Expected: `Switched to a new branch 'fix/voyageur-paleo-settings'`

---

### Task 1: Expose `GATHER_ON_COLLISION` for all Voyageur sources

**Context:** `_voyageur_visible_sections()` in `Antiquarian.py` (lines ~1761–1779) removes
`GATHER_ON_COLLISION` from any source that isn't Ancestry or FamilySearch. The fix is to
remove that guard entirely so the field shows for all four sources.

**Files:**
- Modify: `Antiquarian.py:1767–1773`

**Step 1: Write the failing test**

`Antiquarian.py` is a GUI module and not directly testable by pytest. Verify manually by
reading the code. The observable correct state: `_voyageur_visible_sections("Keystone Archives")`
must include `"GATHER_ON_COLLISION"` in its returned dict's `"Gather Settings"` section, and
`_voyageur_visible_sections("LAC")` likewise.

Since `_voyageur_visible_sections` is a `@staticmethod`, write a lightweight pytest test
that imports `VOYAGEUR_VARS` and calls the method directly:

In `Voyageur/tests/test_voyageur_dispatcher.py`, add:

```python
import importlib.util, sys
from pathlib import Path


def _load_antiquarian():
    """Load the Antiquarian module without executing its tk mainloop."""
    spec = importlib.util.spec_from_file_location(
        "antiquarian_gui",
        Path(__file__).resolve().parents[2] / "Antiquarian.py",
    )
    mod = importlib.util.module_from_spec(spec)
    # Stub tk so import succeeds in a headless test environment
    import unittest.mock as mock
    sys.modules.setdefault("customtkinter", mock.MagicMock())
    sys.modules.setdefault("tkinter", mock.MagicMock())
    spec.loader.exec_module(mod)
    return mod


def test_gather_on_collision_shown_for_keystone():
    mod = _load_antiquarian()
    sections = mod.AntiquarianApp._voyageur_visible_sections("Keystone Archives")
    gather = sections.get("Gather Settings", {})
    assert "GATHER_ON_COLLISION" in gather, (
        "GATHER_ON_COLLISION must be visible for Keystone Archives"
    )


def test_gather_on_collision_shown_for_lac():
    mod = _load_antiquarian()
    sections = mod.AntiquarianApp._voyageur_visible_sections("LAC")
    gather = sections.get("Gather Settings", {})
    assert "GATHER_ON_COLLISION" in gather, (
        "GATHER_ON_COLLISION must be visible for LAC"
    )
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest Voyageur/tests/test_voyageur_dispatcher.py -v
```

Expected: FAIL — `AssertionError: GATHER_ON_COLLISION must be visible for Keystone Archives`

**Step 3: Implement the fix**

In `Antiquarian.py`, find `_voyageur_visible_sections` (~line 1767). The current body is:

```python
if "Gather Settings" in VOYAGEUR_VARS:
    gather_settings = dict(VOYAGEUR_VARS["Gather Settings"])
    # GATHER_ON_COLLISION only means anything to A.py/FS.py - LAC.py and the
    # HBCA/Keystone script never read it, so it must not leak into their form.
    if label not in ("Ancestry", "FamilySearch"):
        gather_settings.pop("GATHER_ON_COLLISION", None)
    result["Gather Settings"] = gather_settings
```

Replace with:

```python
if "Gather Settings" in VOYAGEUR_VARS:
    gather_settings = dict(VOYAGEUR_VARS["Gather Settings"])
    result["Gather Settings"] = gather_settings
```

(Remove the pop block and its comment entirely — all four sources now show the setting.)

**Step 4: Run test to verify it passes**

```bash
python -m pytest Voyageur/tests/test_voyageur_dispatcher.py -v
```

Expected: PASS

**Step 5: Lint check**

```bash
python -m pycodestyle --max-line-length=120 Antiquarian.py
```

Expected: no output (zero violations)

**Step 6: Commit**

```bash
git add Antiquarian.py Voyageur/tests/test_voyageur_dispatcher.py
git commit -m "feat: expose GATHER_ON_COLLISION for all Voyageur sources"
```

---

### Task 2: Wire `GATHER_ON_COLLISION` into HBCA.py

**Context:** `download_keystone_media()` in `HBCA.py` (line ~586) uses `if not dest_file.exists():`
to guard writes — this is the "always skip" behavior. It needs to read `GATHER_ON_COLLISION`
and either skip existing files (current behavior, `"skip"`) or overwrite them (`"overwrite"`).

The reference implementation is `A.py` line 157:
`on_collision = os.getenv("GATHER_ON_COLLISION", "overwrite").strip().lower()`

There is also a `target_file` guard at line ~780. Check both.

**Files:**
- Modify: `Voyageur/HBCA.py`

**Step 1: Write the failing test**

In `Voyageur/tests/test_hbca_gather.py`, add at the end:

```python
def test_download_keystone_media_skip_existing(tmp_path, monkeypatch):
    """When GATHER_ON_COLLISION=skip, an existing file must not be re-downloaded."""
    monkeypatch.setenv("GATHER_ON_COLLISION", "skip")

    existing = tmp_path / "file.jpg"
    existing.write_bytes(b"original")

    call_count = {"n": 0}

    class _FakeResp:
        status_code = 200
        content = b"new_data"

    class _FakeClient:
        def get(self, url, headers=None, timeout=None):
            call_count["n"] += 1
            return _FakeResp()

    download_keystone_media(["http://example.com/file.jpg"], tmp_path, _FakeClient())
    assert call_count["n"] == 0, "Should not fetch when file exists and collision=skip"
    assert existing.read_bytes() == b"original"


def test_download_keystone_media_overwrite_existing(tmp_path, monkeypatch):
    """When GATHER_ON_COLLISION=overwrite, an existing file must be re-downloaded."""
    monkeypatch.setenv("GATHER_ON_COLLISION", "overwrite")

    existing = tmp_path / "file.jpg"
    existing.write_bytes(b"original")

    class _FakeResp:
        status_code = 200
        content = b"new_data"

    class _FakeClient:
        def get(self, url, headers=None, timeout=None):
            return _FakeResp()

    download_keystone_media(["http://example.com/file.jpg"], tmp_path, _FakeClient())
    assert existing.read_bytes() == b"new_data"
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest Voyageur/tests/test_hbca_gather.py::test_download_keystone_media_skip_existing Voyageur/tests/test_hbca_gather.py::test_download_keystone_media_overwrite_existing -v
```

Expected: FAIL — both assertions fail (overwrite always skips, skip always skips)

**Step 3: Implement the fix**

In `HBCA.py`, find `download_keystone_media()`. At the top of the function body (before the
`for url in media_urls:` loop), add:

```python
on_collision = os.getenv("GATHER_ON_COLLISION", "overwrite").strip().lower()
```

Then find the guard `if not dest_file.exists():` (~line 586) and replace the block:

```python
# Before:
if not dest_file.exists():
    try:
        resp = client.get(url, headers=headers, timeout=30)
        ...

# After:
if on_collision == "skip" and dest_file.exists():
    if dest_file.exists():
        downloaded_paths.append(str(dest_file))
    continue
try:
    resp = client.get(url, headers=headers, timeout=30)
    ...
```

Also check line ~780 (`target_file` guard) for any other `if not target_file.exists():` write
guards in the same module and apply the same pattern if present.

**Step 4: Run tests**

```bash
python -m pytest Voyageur/tests/test_hbca_gather.py -v
```

Expected: all PASS

**Step 5: Lint**

```bash
python -m pycodestyle --max-line-length=120 Voyageur/HBCA.py
```

Expected: no output

**Step 6: Commit**

```bash
git add Voyageur/HBCA.py Voyageur/tests/test_hbca_gather.py
git commit -m "feat: honour GATHER_ON_COLLISION in HBCA.py media download"
```

---

### Task 3: Wire `GATHER_ON_COLLISION` into LAC.py

**Context:** In `LAC.py` ~line 318, `if not file_path.exists():` guards whether an asset file
is downloaded. Same fix as HBCA: read `GATHER_ON_COLLISION` and honor it.

**Files:**
- Modify: `Voyageur/LAC.py`

**Step 1: Write the failing test**

In `Voyageur/tests/test_lac.py`, add at the end:

```python
def test_download_asset_skips_on_collision_skip(tmp_path, monkeypatch):
    """When GATHER_ON_COLLISION=skip, LAC must not re-download an existing asset file."""
    import LAC
    import lac_client as lc

    monkeypatch.setenv("GATHER_ON_COLLISION", "skip")
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path))

    pid_dir = tmp_path / "test_pid"
    pid_dir.mkdir()
    existing = pid_dir / "asset123.jpg"
    existing.write_bytes(b"cached")

    download_calls = {"n": 0}

    def _fake_download(asset_id, op):
        download_calls["n"] += 1
        return b"fresh"

    monkeypatch.setattr(lc, "download_asset", _fake_download)

    # Call the internal function that guards the file write
    # (adjust import path if the function is named differently in LAC.py)
    LAC._download_pid_assets(
        pid="test_pid",
        assets=[lc.AssetRef(asset_id="asset123", op="jpg")],  # adjust type as needed
        media_dir=str(tmp_path),
        lac_client=lc,
        document_type_override=None,
    )

    assert download_calls["n"] == 0, "Should not download when file exists and collision=skip"
    assert existing.read_bytes() == b"cached"


def test_download_asset_overwrites_on_collision_overwrite(tmp_path, monkeypatch):
    """When GATHER_ON_COLLISION=overwrite, LAC must re-download an existing asset file."""
    import LAC
    import lac_client as lc

    monkeypatch.setenv("GATHER_ON_COLLISION", "overwrite")
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path))

    pid_dir = tmp_path / "test_pid"
    pid_dir.mkdir()
    existing = pid_dir / "asset456.jpg"
    existing.write_bytes(b"cached")

    def _fake_download(asset_id, op):
        return b"fresh"

    monkeypatch.setattr(lc, "download_asset", _fake_download)

    LAC._download_pid_assets(
        pid="test_pid",
        assets=[lc.AssetRef(asset_id="asset456", op="jpg")],
        media_dir=str(tmp_path),
        lac_client=lc,
        document_type_override=None,
    )

    assert existing.read_bytes() == b"fresh"
```

> **Note:** Inspect `LAC.py` around line 315-330 to confirm the exact function name and
> `AssetRef` type before writing the test. Adjust the test to match the real API.

**Step 2: Run test to verify it fails**

```bash
python -m pytest Voyageur/tests/test_lac.py::test_download_asset_skips_on_collision_skip Voyageur/tests/test_lac.py::test_download_asset_overwrites_on_collision_overwrite -v
```

Expected: FAIL

**Step 3: Implement the fix**

In `LAC.py`, find the function containing the `if not file_path.exists():` guard (~line 318).
At the top of that function, add:

```python
on_collision = os.getenv("GATHER_ON_COLLISION", "overwrite").strip().lower()
```

Replace the guard block:

```python
# Before:
if not file_path.exists():
    data = lac_client.download_asset(asset.asset_id, asset.op)
    atomic_write_bytes(file_path, data)

# After:
if on_collision == "overwrite" or not file_path.exists():
    data = lac_client.download_asset(asset.asset_id, asset.op)
    atomic_write_bytes(file_path, data)
```

**Step 4: Run tests**

```bash
python -m pytest Voyageur/tests/test_lac.py -v
```

Expected: all PASS

**Step 5: Lint**

```bash
python -m pycodestyle --max-line-length=120 Voyageur/LAC.py
```

Expected: no output

**Step 6: Schema completeness check**

```bash
python -m pytest tests/test_settings_schema_completeness.py tests/test_load_tool_schema.py -v
```

Expected: all PASS — `GATHER_ON_COLLISION` is already in `Voyageur/settings_schema.yaml`.

**Step 7: Commit**

```bash
git add Voyageur/LAC.py Voyageur/tests/test_lac.py
git commit -m "feat: honour GATHER_ON_COLLISION in LAC.py asset download"
```

---

### Task 4: Add third Voyageur button "Gather, Transcribe & Build"

**Context:** `_build_tab_voyageur()` (~line 1825) creates two buttons. `_on_voyageur_source_change()`
(~line 1781) configures them dynamically. The Paleographer script key is `"ANALYSIS_SCRIPT"`
with mode `"paleographer_api"` (line 1661).

**Files:**
- Modify: `Antiquarian.py:1825–1834` (button creation in `_build_tab_voyageur`)
- Modify: `Antiquarian.py:1789–1800` (button configuration in `_on_voyageur_source_change`)

**Step 1: No new pytest test needed**

GUI button wiring is not testable by pytest without a display. The `test_gather_on_collision_shown_*`
tests added in Task 1 already import the module cleanly; verify the module still imports after
this change using the existing dispatcher test suite.

**Step 2: Update `_build_tab_voyageur` — add the third button**

Find the button creation block (~lines 1825–1834):

```python
self.voyageur_gather_btn = ctk.CTkButton(btn_box, text="Gather", fg_color="#3B8ED0", hover_color="#2b7a4b",
                                         text_color=C_TEXT)
self.voyageur_gather_btn.pack(side="left", padx=5)

self.voyageur_send_to_archivist_btn = ctk.CTkButton(
    btn_box, text="Gather and Send to Archivist", fg_color="#2b7a4b", hover_color="#1e5935",
    text_color=C_TEXT)
self.voyageur_send_to_archivist_btn.pack(side="left", padx=5)
```

Replace with:

```python
self.voyageur_gather_btn = ctk.CTkButton(btn_box, text="Gather", fg_color="#3B8ED0",
                                         hover_color="#2b7a4b", text_color=C_TEXT)
self.voyageur_gather_btn.pack(side="left", padx=5)

self.voyageur_send_to_archivist_btn = ctk.CTkButton(
    btn_box, text="Gather & Build", fg_color="#2b7a4b", hover_color="#1e5935",
    text_color=C_TEXT)
self.voyageur_send_to_archivist_btn.pack(side="left", padx=5)

self.voyageur_full_pipeline_btn = ctk.CTkButton(
    btn_box, text="Gather, Transcribe & Build", fg_color="#7c5cbf",
    hover_color="#5e3fa3", text_color=C_TEXT)
self.voyageur_full_pipeline_btn.pack(side="left", padx=5)
```

**Step 3: Update `_on_voyageur_source_change` — configure the third button**

Find the section that configures `voyageur_send_to_archivist_btn` (~lines 1793–1800):

```python
if hasattr(self, "voyageur_send_to_archivist_btn"):
    # Chains straight into Generate GEDCOM (the same "gedcom_auto" mode the
    # Archivist tab's own button uses) only once the gather actually finishes
    # cleanly - see execute_script's on_success.
    self.voyageur_send_to_archivist_btn.configure(
        command=lambda: self.execute_script(
            "VOYAGEUR_SCRIPT", code,
            on_success=lambda: self.execute_script("ARCHIVIST_SCRIPT", "gedcom_auto")))
```

After that block, add:

```python
if hasattr(self, "voyageur_full_pipeline_btn"):
    # Full pipeline: Gather -> Paleographer (AI transcription) -> Archivist (GEDCOM).
    # Use for raw-image collections that need transcription before a GEDCOM can be built.
    _code = code  # capture for the nested lambdas
    self.voyageur_full_pipeline_btn.configure(
        command=lambda: self.execute_script(
            "VOYAGEUR_SCRIPT", _code,
            on_success=lambda: self.execute_script(
                "ANALYSIS_SCRIPT", "paleographer_api",
                on_success=lambda: self.execute_script("ARCHIVIST_SCRIPT", "gedcom_auto"))))
```

Also update the `voyageur_send_to_archivist_btn` label in `_on_voyageur_source_change` — the
button text should remain `"Gather & Build"` (it was set at creation time; `configure()` here
only updates the command, which is correct).

**Step 4: Run existing tests to confirm nothing broke**

```bash
python -m pytest Voyageur/tests/test_voyageur_dispatcher.py -v
```

Expected: all PASS (the module still imports cleanly)

**Step 5: Lint**

```bash
python -m pycodestyle --max-line-length=120 Antiquarian.py
```

Expected: no output

**Step 6: Commit**

```bash
git add Antiquarian.py
git commit -m "feat: add 'Gather, Transcribe & Build' pipeline button to Voyageur"
```

---

### Task 5: Fix Paleographer multi-tier .pmt discovery

**Context:** Three methods in `Antiquarian.py` hardcode `Paleographer/prompts` relative to
`__file__`:
- `_list_record_types()` (~line 1547) — populates the Record Type dropdown
- `_read_pmt_front_matter()` (~line 1558) — reads YAML from a specific .pmt
- `_get_pmt_settings_sections()` (~line 1585) — calls `_read_pmt_front_matter()`

`engine.py`'s `_prompt_search_dirs()` uses three tiers (GENEALOGY_DIR, PROGRAM_DIR, sibling).
The GUI must use the same tiers so the dropdown and runtime always agree.

**Files:**
- Modify: `Antiquarian.py:1547–1583`

**Step 1: Write the failing test**

Add to `Voyageur/tests/test_voyageur_dispatcher.py` (or create a new test file
`tests/test_antiquarian_pmt_discovery.py` at repo root level):

```python
"""Tests that Antiquarian.py's .pmt discovery matches engine.py's tier order."""
import os
from pathlib import Path


def test_list_record_types_finds_pmt_from_genealogy_dir(tmp_path, monkeypatch):
    """_list_record_types() must discover a .pmt placed in GENEALOGY_DIR/Prompts."""
    prompts_dir = tmp_path / "Prompts"
    prompts_dir.mkdir()
    (prompts_dir / "Custom.pmt").write_text("---\ndocument_type: Custom\n---\n")

    monkeypatch.setenv("GENEALOGY_DIR", str(tmp_path))
    monkeypatch.setenv("PROGRAM_DIR", "")

    # Import the static method without instantiating the GUI
    import importlib, sys, unittest.mock as mock
    sys.modules.setdefault("customtkinter", mock.MagicMock())
    sys.modules.setdefault("tkinter", mock.MagicMock())
    spec = importlib.util.spec_from_file_location(
        "antiquarian_gui", Path(__file__).resolve().parents[1] / "Antiquarian.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    types = mod.AntiquarianApp._list_record_types()
    assert "Custom.pmt" in types, f"Expected Custom.pmt in {types}"
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_antiquarian_pmt_discovery.py -v
```

Expected: FAIL — `Custom.pmt` not found because `_list_record_types()` only looks at
`Paleographer/prompts/` sibling.

**Step 3: Add `_prompt_search_dirs()` helper and fix all three methods**

In `Antiquarian.py`, **before** the `_list_record_types` static method, add a new instance
method (not static — it needs `self.string_vars` for env var values that may have changed
since startup):

```python
def _prompt_search_dirs(self) -> list:
    """Returns .pmt search directories in priority order, mirroring engine.py's
    _prompt_search_dirs() exactly so the GUI dropdown always matches what the runtime
    will find. Reads GENEALOGY_DIR and PROGRAM_DIR from self.string_vars (the
    already-loaded in-memory env values) so live GUI edits are reflected immediately."""
    from pathlib import Path as _Path
    import os as _os
    dirs = []
    genealogy_dir = self.string_vars.get("GENEALOGY_DIR", None)
    genealogy_dir = genealogy_dir.get() if genealogy_dir else _os.getenv("GENEALOGY_DIR", "")
    genealogy_dir = genealogy_dir.strip()
    if genealogy_dir:
        prompts_sub = _os.getenv("PROMPTS_DIR", "").strip() or "Prompts"
        dirs.append(_Path(genealogy_dir) / prompts_sub)
    program_dir = self.string_vars.get("PROGRAM_DIR", None)
    program_dir = program_dir.get() if program_dir else _os.getenv("PROGRAM_DIR", "")
    program_dir = program_dir.strip()
    if program_dir:
        dirs.append(_Path(program_dir) / "Prompts")
    dirs.append(_Path(__file__).resolve().parent / "Paleographer" / "prompts")
    return dirs
```

Then update `_list_record_types` (currently `@staticmethod`) to become an instance method
that uses this helper. Since it's currently called as `self._list_record_types()` in
`_build_tab_paleographer`, the call site does not change.

Replace:

```python
@staticmethod
def _list_record_types() -> List[str]:
    """Lists every .pmt file in Paleographer/prompts, for the record-type dropdown.
    Adding a new record type is exactly this: drop a new .pmt file in that folder,
    nothing else, and it shows up here automatically."""
    prompts_dir = Path(__file__).resolve().parent / "Paleographer" / "prompts"
    if not prompts_dir.is_dir():
        return ["Parish.pmt"]
    found = sorted((p.name for p in prompts_dir.glob("*.pmt")), key=str.lower)
    return found or ["Parish.pmt"]
```

With:

```python
def _list_record_types(self) -> List[str]:
    """Lists every .pmt file discoverable via the three-tier prompt search path
    (GENEALOGY_DIR/Prompts, PROGRAM_DIR/Prompts, Paleographer/prompts sibling),
    mirroring engine.py's _prompt_search_dirs() so the dropdown always matches
    what the runtime will actually find. Higher-priority tiers shadow the same
    filename from lower-priority tiers. Adding a new record type is exactly this:
    drop a .pmt in any tier directory; nothing else changes."""
    available: dict = {}
    for prompts_dir in reversed(self._prompt_search_dirs()):
        if prompts_dir.is_dir():
            for p in prompts_dir.glob("*.pmt"):
                available[p.name.lower()] = p.name  # higher-priority tiers win (reversed)
    found = sorted(available.values(), key=str.lower)
    return found or ["Parish.pmt"]
```

Replace `_read_pmt_front_matter` (currently `@staticmethod`):

```python
@staticmethod
def _read_pmt_front_matter(record_type_value: str) -> dict:
    ...
    pmt_path = Path(__file__).resolve().parent / "Paleographer" / "prompts" / name
    ...
```

With an instance method:

```python
def _read_pmt_front_matter(self, record_type_value: str) -> dict:
    """Reads a .pmt file's own YAML front matter using the same three-tier search
    as _list_record_types(), so settings sections and field remaps are read from
    whichever tier actually owns the active .pmt. Returns {} for a .pmt that
    doesn't exist or can't be parsed."""
    name = record_type_value.strip() or "Parish.pmt"
    if not name.endswith(".pmt"):
        name += ".pmt"
    pmt_path = None
    for prompts_dir in self._prompt_search_dirs():
        candidate = prompts_dir / name
        if candidate.is_file():
            pmt_path = candidate
            break
    if pmt_path is None:
        return {}
    try:
        raw = pmt_path.read_text(encoding="utf-8")
    except OSError:
        return {}
    stripped = raw.lstrip()
    if not stripped.startswith("---"):
        return {}
    parts = stripped.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        return yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {}
```

> `_get_pmt_settings_sections` and `_get_pmt_field_remap` both call
> `self._read_pmt_front_matter(...)` — they remain unchanged and inherit the fix.
> `_get_pmt_settings_sections` is also currently an instance method so no signature change needed.
> `_get_pmt_field_remap` is also an instance method — same.

**Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_antiquarian_pmt_discovery.py -v
```

Expected: PASS

**Step 5: Run full test suite**

```bash
python -m pytest -v
```

Expected: all PASS

**Step 6: Lint**

```bash
python -m pycodestyle --max-line-length=120 Antiquarian.py
```

Expected: no output

**Step 7: Commit**

```bash
git add Antiquarian.py tests/test_antiquarian_pmt_discovery.py
git commit -m "fix: Paleographer record-type dropdown uses multi-tier .pmt discovery"
```

---

### Task 6: Final verification & PR

**Step 1: Full test suite**

```bash
python -m pytest -v
```

Expected: all PASS

**Step 2: Schema completeness**

```bash
python -m pytest tests/test_settings_schema_completeness.py tests/test_load_tool_schema.py -v
```

Expected: all PASS

**Step 3: Lint all touched files**

```bash
python -m pycodestyle --max-line-length=120 Antiquarian.py Voyageur/HBCA.py Voyageur/LAC.py
```

Expected: no output

**Step 4: Push branch and open PR**

```bash
git push -u origin fix/voyageur-paleo-settings
```

Then open a PR on GitHub targeting `Unify`. PR title:
`fix: Voyageur collision/buttons + Paleographer .pmt discovery`

PR description should reference the three changes:
1. Expose `GATHER_ON_COLLISION` for all Voyageur sources (HBCA + LAC wired)
2. Add "Gather, Transcribe & Build" button (three-button pipeline)
3. Fix Paleographer record-type dropdown to use multi-tier .pmt search

**Step 5: Update task tracker**

Edit `docs/plans/task.md` to record this task as complete.
