# Voyageur Parish/Scrip Scaffold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every Parish/Scrip record Voyageur produces (index-derived via `FS.py` or image-only via `LAC.py`) carries a real `document_metadata.file_name`/`file_type` pointing at its source image, and `LAC.py` seeds Paleographer's own `MASTER_DB` with a Commissioner-shaped scaffold sheet per downloaded image so a later, on-demand Paleographer run finds it already registered.

**Architecture:** `Commissioner/record_registry.py` gains `build_empty_sheet()` (one placeholder `Sheet` dict: real `document_metadata`, one `Record` with `participants: []`) and `get_field_remap()` (exposes a `.pmt` file's `field_remap` table without pulling in Paleographer's heavy `engine.py`). `Paleographer.py`'s `get_processed_files`/`merge_sheets` learn to treat an all-empty-participants sheet as a placeholder rather than a finished record, so scaffold sheets get reprocessed and then replaced in place instead of duplicated. `FS.py` derives its `document_metadata.file_name` deterministically from `item_id` (matching the filename its own image-move step already produces) instead of leaving it blank. `LAC.py` gains a `--record-type {parish,scrip}` flag, `MASTER_DB` path resolution mirroring Paleographer's own `resolve_setting`, and writes one scaffold sheet directly into that `MASTER_DB` after each successfully downloaded image, in both its sequential and concurrent volume-harvest paths and its simpler reel-harvest path.

**Tech Stack:** Python, pydantic (Commissioner models), pytest, argparse, multiprocessing (LAC.py's existing worker pool - untouched by this plan beyond passing new read-only params through).

## Global Constraints

- Non-blocking Commissioner validation only: every `parse_collection(...)` call this plan adds is wrapped in `try/except Exception`, logs `[WARN] Commissioner validation failed for {collection_title!r}: {e}"`, and never raises - identical in shape to `Voyageur/census_schema.py::validate_against_commissioner` (Sub-project 2's established pattern). A validation gap must never block a gather or drop a downloaded image.
- No new fields on `Commissioner.models.Sheet`/`Record`/`DocumentMetadata`. A placeholder record is expressed with fields the model already has (`participants: []`, everything else `None`/default) - no "is this a placeholder" marker field.
- No change to `Voyageur/A.py` and no change to `FS.py`'s `build_census_json`/Census path - both explicitly out of scope for this sub-project.
- `Commissioner.record_registry` imports that are validation-only (`parse_collection`) go inside the enclosing function's `try` block, never at module scope - a malformed `.pmt` file must never crash a gather script at import time. Imports of `build_empty_sheet`/`get_field_remap` (structural, not validation) are plain local imports inside the functions that use them, not module-scope, for the same reason.
- `LAC.py` stays free of Paleographer's heavy dependency chain (`google.genai`, `pdfplumber`, `PIL`, `PDFix`, `agy_client`) - `field_remap` resolution goes through `Commissioner.record_registry.get_field_remap()`, never `Paleographer/engine.py`.
- A `MASTER_DB` write failure (disk full, permissions) is allowed to raise, same unguarded-write posture as `save_checkpoint` today - no new swallow introduced for that failure mode.

---

## File Structure

- `Commissioner/record_registry.py` - add `build_empty_sheet()`, `get_field_remap()`.
- `Commissioner/tests/test_record_registry.py` - tests for both new functions.
- `Paleographer/Paleographer.py` - fix `get_processed_files()`, `merge_sheets()`.
- `Paleographer/tests/test_master_db_merge.py` (new) - tests for both fixes.
- `Voyageur/FS.py` - add `sanitize_item_id_filename()`, fix `build_universal_json()`'s `document_metadata`, add `validate_against_commissioner()`, wire it into `main()`.
- `Voyageur/tests/test_fs.py` (new) - tests for all three.
- `Voyageur/LAC.py` - add repo-root `sys.path` insertion, `resolve_generic_setting()`, `resolve_master_db_path()`, `load_master_db()`/`save_master_db()`, `append_scaffold_sheets()`, `validate_master_db_against_commissioner()`, `--record-type` CLI flag, `_resolve_record_type()`; wire scaffold writing into `download_volume_assets()`, `download_volume_assets_multiworker()`, `retrieve_volume()`, `_run_volume()`, `download_images()`, `_run_reel()`.
- `Voyageur/tests/test_lac.py` (new) - tests for all of the above.

---

### Task 1: Commissioner scaffold-building helpers

**Files:**
- Modify: `Commissioner/record_registry.py`
- Test: `Commissioner/tests/test_record_registry.py`

**Interfaces:**
- Produces: `build_empty_sheet(file_name: str, file_type: str, page_id: Optional[str] = None) -> dict` - a `Sheet`-shaped dict with real `document_metadata` and one placeholder `Record` (`participants: []`, every other field its model default).
- Produces: `get_field_remap(document_type: str) -> Dict[str, str]` - a `.pmt` file's `field_remap` table (e.g. `{"CHURCH_MASTER_DB_NAME": "MASTER_DB_NAME", ...}`). Raises `UnknownDocumentTypeError` for an unrecognized `document_type`.

- [ ] **Step 1: Write the failing tests**

Append to `Commissioner/tests/test_record_registry.py`:

```python
def test_build_empty_sheet_shape():
    sheet = record_registry.build_empty_sheet("abc123.jpg", "jpg")
    assert sheet["page_id"] == "abc123.jpg"
    assert sheet["document_metadata"] == {
        "file_name": "abc123.jpg", "file_type": "jpg", "volume": None,
        "pages": None, "source_name": None, "source_location": None,
    }
    assert len(sheet["records"]) == 1
    assert sheet["records"][0]["participants"] == []
    assert sheet["records"][0]["event_type"] is None


def test_build_empty_sheet_explicit_page_id():
    sheet = record_registry.build_empty_sheet("abc123.jpg", "jpg", page_id="p1")
    assert sheet["page_id"] == "p1"


def test_build_empty_sheet_defaults_page_id_to_file_name():
    sheet = record_registry.build_empty_sheet("abc123.jpg", "jpg")
    assert sheet["page_id"] == "abc123.jpg"


def test_build_empty_sheet_round_trips_through_sheet_validation():
    from Commissioner.models import Sheet
    sheet = Sheet.model_validate(record_registry.build_empty_sheet("abc123.jpg", "jpg"))
    assert sheet.document_metadata.file_name == "abc123.jpg"
    assert sheet.records[0].participants == []


def test_build_empty_sheet_validates_against_commissioner_schema():
    collection = {
        "collection_title": "Test",
        "sheets": [record_registry.build_empty_sheet("abc123.jpg", "jpg")],
    }
    result = parse_collection(collection, "Parish")
    assert result.sheets[0].records[0].participants == []


def test_get_field_remap_parish():
    remap = record_registry.get_field_remap("Parish")
    assert remap["CHURCH_MASTER_DB_NAME"] == "MASTER_DB_NAME"
    assert remap["CHURCH_IMAGE_DIR"] == "IMAGE_DIR"


def test_get_field_remap_scrip():
    remap = record_registry.get_field_remap("Scrip")
    assert remap["SCRIP_MASTER_DB_NAME"] == "MASTER_DB_NAME"
    assert remap["SCRIP_IMAGE_DIR"] == "IMAGE_DIR"


def test_get_field_remap_unknown_document_type_raises():
    with pytest.raises(UnknownDocumentTypeError, match="NotARecordType"):
        record_registry.get_field_remap("NotARecordType")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest Commissioner/tests/test_record_registry.py -k "build_empty_sheet or get_field_remap" -v`
Expected: FAIL with `AttributeError: module 'Commissioner.record_registry' has no attribute 'build_empty_sheet'` (and similarly for `get_field_remap`).

- [ ] **Step 3: Implement `build_empty_sheet` and `get_field_remap`**

In `Commissioner/record_registry.py`, add after `parse_collection` (end of file):

```python
def build_empty_sheet(file_name: str, file_type: str, page_id: Optional[str] = None) -> dict:
    """Builds a Commissioner-shaped placeholder sheet dict: a real document_metadata (the
    image reference) wrapping exactly one empty-content Record (participants: [], every
    other field its model default). Paleographer's own get_processed_files treats a sheet
    with no record carrying non-empty participants as unprocessed, so this placeholder gets
    picked up and replaced by a real AI pass rather than silently skipped forever."""
    return {
        "page_id": page_id if page_id is not None else file_name,
        "document_metadata": {
            "file_name": file_name,
            "file_type": file_type,
            "volume": None,
            "pages": None,
            "source_name": None,
            "source_location": None,
        },
        "records": [{
            "record_id": None,
            "page": None,
            "record_number": None,
            "event_type": None,
            "year": None,
            "event_date": None,
            "event_place": None,
            "citation_details": None,
            "citation_text": None,
            "review": False,
            "review_reason": None,
            "continues_on_next_image": False,
            "continues_from_previous_image": False,
            "type_specific_fields": {},
            "participants": [],
        }],
    }


def get_field_remap(document_type: str) -> Dict[str, str]:
    """Returns document_type's own .pmt front matter field_remap table (e.g.
    {"CHURCH_MASTER_DB_NAME": "MASTER_DB_NAME", ...}). Reuses the same lightweight
    _load_pmt_front_matter() the rest of this module already uses, rather than
    Paleographer/engine.py's own TYPE_CFG - engine.py transitively imports google.genai,
    pdfplumber, PIL, PDFix, and ScriptoriumMCP.agy_client, a dependency chain LAC.py (a
    standalone, light-dependency script) must not be forced to pull in."""
    _get_schema(document_type)  # raises UnknownDocumentTypeError early if unrecognized
    front_matter = _load_pmt_front_matter(PMT_DIR / f"{document_type}.pmt")
    return front_matter.get("field_remap") or {}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest Commissioner/tests/test_record_registry.py -v`
Expected: PASS (all tests, including the pre-existing ones).

- [ ] **Step 5: Commit**

```bash
git add Commissioner/record_registry.py Commissioner/tests/test_record_registry.py
git commit -m "feat(commissioner): add build_empty_sheet and get_field_remap"
```

---

### Task 2: Paleographer MASTER_DB placeholder-awareness

**Files:**
- Modify: `Paleographer/Paleographer.py:1428-1442`
- Test: `Paleographer/tests/test_master_db_merge.py` (new)

**Interfaces:**
- Consumes: nothing new from Task 1 (these are pure dict functions; the placeholder shape they must recognize is the same shape `build_empty_sheet` produces, but they don't import it).
- Produces: `get_processed_files(master_data: Dict[str, Any]) -> set` - unchanged signature, now excludes all-placeholder sheets. `merge_sheets(master_data: Dict[str, Any], new_sheets: List[Dict[str, Any]]) -> None` - unchanged signature, now replaces a same-`file_name` placeholder sheet in place instead of appending a duplicate.

- [ ] **Step 1: Write the failing tests**

Create `Paleographer/tests/test_master_db_merge.py`:

```python
"""
Confirms get_processed_files/merge_sheets correctly treat Voyageur-written scaffold sheets
(document_metadata present, every record's participants empty) as unprocessed, and that
merge_sheets replaces a placeholder sheet with Paleographer's own real AI-filled sheet for
the same file_name in place, instead of appending a duplicate - see the
Voyageur-Parish-Scrip-scaffold design spec's Architecture section (Fix 1a/1b).
"""
import importlib
import sys

import pytest


@pytest.fixture
def minimal_paleographer_env(monkeypatch, tmp_path):
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


def _placeholder_sheet(file_name):
    return {
        "page_id": file_name,
        "document_metadata": {"file_name": file_name, "file_type": "jpg"},
        "records": [{"event_type": None, "participants": []}],
    }


def _real_sheet(file_name):
    return {
        "page_id": file_name,
        "document_metadata": {"file_name": file_name, "file_type": "jpg"},
        "records": [{
            "event_type": "Baptism",
            "participants": [{"role_name": "Child", "full_name": "Jean Gagnon", "sex": "M", "is_priest": False}],
        }],
    }


def test_get_processed_files_excludes_placeholder_scaffold_sheet(minimal_paleographer_env):
    module = minimal_paleographer_env
    master_data = {"sheets": [_placeholder_sheet("abc123.jpg")]}
    assert module.get_processed_files(master_data) == set()


def test_get_processed_files_includes_real_sheet(minimal_paleographer_env):
    module = minimal_paleographer_env
    master_data = {"sheets": [_real_sheet("abc123.jpg")]}
    assert module.get_processed_files(master_data) == {"abc123.jpg"}


def test_get_processed_files_ignores_sheet_with_no_records(minimal_paleographer_env):
    module = minimal_paleographer_env
    sheet = {"page_id": "abc123.jpg", "document_metadata": {"file_name": "abc123.jpg"}, "records": []}
    master_data = {"sheets": [sheet]}
    assert module.get_processed_files(master_data) == set()


def test_merge_sheets_replaces_placeholder_with_real_sheet_same_file_name(minimal_paleographer_env):
    module = minimal_paleographer_env
    master_data = {"sheets": [_placeholder_sheet("abc123.jpg")]}
    real_sheet = _real_sheet("abc123.jpg")

    module.merge_sheets(master_data, [real_sheet])

    assert len(master_data["sheets"]) == 1
    assert master_data["sheets"][0] is real_sheet


def test_merge_sheets_appends_when_no_matching_placeholder(minimal_paleographer_env):
    module = minimal_paleographer_env
    master_data = {"sheets": [_real_sheet("abc123.jpg")]}
    other_sheet = _real_sheet("def456.jpg")

    module.merge_sheets(master_data, [other_sheet])

    assert len(master_data["sheets"]) == 2
    assert master_data["sheets"][1] is other_sheet


def test_merge_sheets_appends_when_master_sheets_missing(minimal_paleographer_env):
    module = minimal_paleographer_env
    master_data = {}
    new_sheet = _real_sheet("abc123.jpg")

    module.merge_sheets(master_data, [new_sheet])

    assert master_data["sheets"] == [new_sheet]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest Paleographer/tests/test_master_db_merge.py -v`
Expected: FAIL - `test_get_processed_files_excludes_placeholder_scaffold_sheet` and
`test_merge_sheets_replaces_placeholder_with_real_sheet_same_file_name` fail (current code
treats any `file_name` as processed, and `merge_sheets` always appends). The other tests
pass already against unfixed code - that's expected, they document unchanged behavior.

- [ ] **Step 3: Implement the fixes**

In `Paleographer/Paleographer.py`, replace lines 1428-1442:

```python
def get_processed_files(master_data: Dict[str, Any]) -> set:
    processed = set()
    for sheet in master_data.get("sheets", []):
        metadata = sheet.get("document_metadata", {})
        if isinstance(metadata, dict) and "file_name" in metadata:
            processed.add(metadata["file_name"])
    return processed


def merge_sheets(master_data: Dict[str, Any], new_sheets: List[Dict[str, Any]]) -> None:
    master_sheets = master_data.get("sheets")
    if isinstance(master_sheets, list):
        master_sheets.extend(new_sheets)
    else:
        master_data["sheets"] = new_sheets
```

with:

```python
def _sheet_is_placeholder(sheet: Dict[str, Any]) -> bool:
    """A sheet counts as a real, already-processed sheet only if at least one of its
    records has a non-empty participants list - a scaffold sheet Voyageur wrote
    (Commissioner.record_registry.build_empty_sheet) has no such record, and must be
    reprocessed rather than skipped forever."""
    return not any(record.get("participants") for record in sheet.get("records", []))


def get_processed_files(master_data: Dict[str, Any]) -> set:
    processed = set()
    for sheet in master_data.get("sheets", []):
        metadata = sheet.get("document_metadata", {})
        if not isinstance(metadata, dict) or "file_name" not in metadata:
            continue
        if not _sheet_is_placeholder(sheet):
            processed.add(metadata["file_name"])
    return processed


def merge_sheets(master_data: Dict[str, Any], new_sheets: List[Dict[str, Any]]) -> None:
    master_sheets = master_data.get("sheets")
    if not isinstance(master_sheets, list):
        master_data["sheets"] = new_sheets
        return

    by_file_name = {
        sheet.get("document_metadata", {}).get("file_name"): idx
        for idx, sheet in enumerate(master_sheets)
    }

    for new_sheet in new_sheets:
        file_name = new_sheet.get("document_metadata", {}).get("file_name")
        existing_idx = by_file_name.get(file_name) if file_name is not None else None
        if existing_idx is not None and _sheet_is_placeholder(master_sheets[existing_idx]):
            master_sheets[existing_idx] = new_sheet
            continue
        master_sheets.append(new_sheet)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest Paleographer/tests/test_master_db_merge.py Paleographer/tests/test_settings_standalone.py -v`
Expected: PASS (both files - confirms the fix doesn't disturb existing settings-resolution behavior).

- [ ] **Step 5: Commit**

```bash
git add Paleographer/Paleographer.py Paleographer/tests/test_master_db_merge.py
git commit -m "fix(paleographer): treat all-empty-participants sheets as unprocessed scaffolds"
```

---

### Task 3: FS.py real document_metadata + Commissioner validation

**Files:**
- Modify: `Voyageur/FS.py`
- Test: `Voyageur/tests/test_fs.py` (new)

**Interfaces:**
- Produces: `sanitize_item_id_filename(item_id: str) -> str` - mirrors `Voyageur.js`'s own
  `itemId.replace(/[^a-zA-Z0-9_-]/g, '_')` + `'.jpg'` (Voyageur.js:93), so
  `document_metadata.file_name` always matches the real filename `main()`'s image-move loop
  already produces for that item.
- Produces: `validate_against_commissioner(final_data: dict, record_family: str, collection_title: str) -> None` - non-blocking; looks up `record_family` (`"church"`/`"scrip"`/other) against a `Parish`/`Scrip` Commissioner document type and skips silently for families with no Commissioner counterpart (e.g. `"wills"`, `"other"`).
- Modifies: `build_universal_json`'s sheet dict now sets real `file_name`/`file_type` instead of `""`.

- [ ] **Step 1: Write the failing tests**

Create `Voyageur/tests/test_fs.py`:

```python
"""Tests for FS.py's build_universal_json() document_metadata fix and Commissioner
validation wiring - see the Voyageur-Parish-Scrip-scaffold design spec."""
import FS


def test_sanitize_item_id_filename_replaces_unsafe_characters():
    assert FS.sanitize_item_id_filename("abc 123/def") == "abc_123_def.jpg"


def test_sanitize_item_id_filename_preserves_safe_characters():
    assert FS.sanitize_item_id_filename("abc-123_DEF") == "abc-123_DEF.jpg"


def test_build_universal_json_sets_real_document_metadata_from_item_id():
    raw = {"collection_title": "Test Parish Register"}
    items_raw = [{"item_id": "abc 123/def", "rows": [], "citation_text": ""}]
    result = FS.build_universal_json(raw, items_raw, {}, "church")

    metadata = result["sheets"][0]["document_metadata"]
    assert metadata["file_name"] == "abc_123_def.jpg"
    assert metadata["file_type"] == "jpg"


def test_build_universal_json_empty_item_id_yields_empty_file_name():
    raw = {"collection_title": "Test"}
    items_raw = [{"item_id": "", "rows": []}]
    result = FS.build_universal_json(raw, items_raw, {}, "church")

    assert result["sheets"][0]["document_metadata"]["file_name"] == ""


def test_validate_against_commissioner_accepts_valid_church_sheet(capsys):
    final_data = {
        "collection_title": "Test Parish",
        "sheets": [{
            "page_id": "abc123.jpg",
            "document_metadata": {"file_name": "abc123.jpg", "file_type": "jpg"},
            "records": [],
        }],
    }
    FS.validate_against_commissioner(final_data, "church", "Test Parish")
    assert "[WARN]" not in capsys.readouterr().out


def test_validate_against_commissioner_skipped_for_unmapped_family(capsys):
    FS.validate_against_commissioner({"sheets": []}, "wills", "Test")
    assert capsys.readouterr().out == ""


def test_validate_against_commissioner_warns_and_does_not_raise_on_bad_shape(capsys):
    bad_data = {"collection_title": "Bad", "sheets": [{"records": "not-a-list"}]}
    FS.validate_against_commissioner(bad_data, "church", "Bad Collection")
    captured = capsys.readouterr()
    assert "[WARN]" in captured.out
    assert "Bad Collection" in captured.out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest Voyageur/tests/test_fs.py -v`
Expected: FAIL with `AttributeError: module 'FS' has no attribute 'sanitize_item_id_filename'`
(and similarly for `validate_against_commissioner`); the `document_metadata` tests fail
because `file_name`/`file_type` are still `""`.

- [ ] **Step 3: Implement the fix**

In `Voyageur/FS.py`, add before `build_universal_json` (currently line 421):

```python
def sanitize_item_id_filename(item_id: str) -> str:
    """Mirrors Voyageur.js's own image-filename sanitization (line 93:
    itemId.replace(/[^a-zA-Z0-9_-]/g, '_') + '.jpg') so document_metadata.file_name always
    matches the real filename main()'s image-move loop already produces for this item -
    both are derived independently from the same item_id rather than one scanning the
    filesystem to match the other."""
    return re.sub(r'[^a-zA-Z0-9_-]', '_', item_id) + ".jpg" if item_id else ""


RECORD_FAMILY_TO_DOCUMENT_TYPE = {"church": "Parish", "scrip": "Scrip"}


def validate_against_commissioner(final_data: dict, record_family: str, collection_title: str) -> None:
    """Non-blocking Commissioner schema check for Parish/Scrip gathers, mirroring
    census_schema.py's validate_against_commissioner() (Sub-project 2) - a failure here is
    logged and swallowed, never raised. record_family values with no matching Commissioner
    document type (e.g. "wills", "other") are silently skipped - only "church" (-> Parish)
    and "scrip" (-> Scrip) are currently recognized document types."""
    document_type = RECORD_FAMILY_TO_DOCUMENT_TYPE.get(record_family)
    if document_type is None:
        return
    try:
        from Commissioner.record_registry import parse_collection
        parse_collection(final_data, document_type)
    except Exception as e:
        print(f"[WARN] Commissioner validation failed for {collection_title!r}: {e}")
```

Then replace the `sheets.append({...})` block inside `build_universal_json` (currently lines 447-454):

```python
        sheets.append({
            "page_id": item_id,
            "document_metadata": {
                "file_name": "", "file_type": "", "volume": "", "pages": "",
                "source_name": "", "source_location": "",
            },
            "records": records,
        })
```

with:

```python
        sheets.append({
            "page_id": item_id,
            "document_metadata": {
                "file_name": sanitize_item_id_filename(item_id), "file_type": "jpg" if item_id else "",
                "volume": "", "pages": "", "source_name": "", "source_location": "",
            },
            "records": records,
        })
```

Finally, wire validation into `main()`. Replace:

```python
    else:
        print("\n[System] Converting raw scrape into the universal Gather JSON...")
        final_data = build_universal_json(raw_data, items_raw, catalog_items, record_family)
```

with:

```python
    else:
        print("\n[System] Converting raw scrape into the universal Gather JSON...")
        final_data = build_universal_json(raw_data, items_raw, catalog_items, record_family)
        validate_against_commissioner(final_data, record_family, raw_data.get("collection_title", ""))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest Voyageur/tests/test_fs.py Voyageur/tests/test_census_schema.py -v`
Expected: PASS (both files - confirms the Census path, which doesn't touch
`build_universal_json`, is unaffected).

- [ ] **Step 5: Commit**

```bash
git add Voyageur/FS.py Voyageur/tests/test_fs.py
git commit -m "fix(fs): populate document_metadata from item_id, validate against Commissioner"
```

---

### Task 4: LAC.py MASTER_DB building blocks

**Files:**
- Modify: `Voyageur/LAC.py`
- Test: `Voyageur/tests/test_lac.py` (new)

**Interfaces:**
- Consumes: `Commissioner.record_registry.get_field_remap(document_type)` (Task 1), `Commissioner.record_registry.parse_collection(raw_json, document_type)` (pre-existing).
- Produces: `resolve_generic_setting(document_type: str, generic_key: str, default: str = "") -> str`; `resolve_master_db_path(document_type: str, program_dir: str) -> str`; `load_master_db(master_db_path: str, collection_title: str, record_type_name: str) -> Dict[str, Any]`; `save_master_db(master_db_path: str, master_data: Dict[str, Any]) -> None`; `append_scaffold_sheets(master_data: Dict[str, Any], new_sheets: List[Dict[str, Any]]) -> None`; `validate_master_db_against_commissioner(master_data: Dict[str, Any], document_type: str, collection_title: str) -> None`; `RECORD_TYPE_ARG_TO_DOCUMENT_TYPE: Dict[str, str]`; `_resolve_record_type(record_type_arg: str) -> str` (calls `sys.exit(1)` on an unrecognized/empty arg).

- [ ] **Step 1: Write the failing tests**

Create `Voyageur/tests/test_lac.py`:

```python
"""Tests for LAC.py's Commissioner-scaffold building blocks: MASTER_DB path resolution
(mirroring Paleographer.py's own resolve_setting), load/save, and scaffold-sheet
deduplicated append. See the Voyageur-Parish-Scrip-scaffold design spec."""
import os

import pytest

import LAC


def test_resolve_generic_setting_prefers_prefixed_key(monkeypatch):
    monkeypatch.setenv("CHURCH_MASTER_DB_NAME", "parish_register.json")
    monkeypatch.delenv("MASTER_DB_NAME", raising=False)
    assert LAC.resolve_generic_setting("Parish", "MASTER_DB_NAME") == "parish_register.json"


def test_resolve_generic_setting_falls_back_to_generic_key(monkeypatch):
    monkeypatch.delenv("CHURCH_MASTER_DB_NAME", raising=False)
    monkeypatch.setenv("MASTER_DB_NAME", "fallback.json")
    assert LAC.resolve_generic_setting("Parish", "MASTER_DB_NAME") == "fallback.json"


def test_resolve_master_db_path_matches_paleographer_convention(monkeypatch, tmp_path):
    monkeypatch.setenv("CHURCH_MASTER_DB_NAME", "parish_register.json")
    monkeypatch.setenv("JSON_DIR", "JSON")
    path = LAC.resolve_master_db_path("Parish", str(tmp_path))
    assert path == str(tmp_path / "JSON" / "parish_register.json")


def test_resolve_master_db_path_raises_on_empty_master_db_name(monkeypatch, tmp_path):
    monkeypatch.delenv("CHURCH_MASTER_DB_NAME", raising=False)
    monkeypatch.delenv("MASTER_DB_NAME", raising=False)
    with pytest.raises(RuntimeError, match="MASTER_DB_NAME"):
        LAC.resolve_master_db_path("Parish", str(tmp_path))


def test_load_master_db_returns_default_shape_when_missing(tmp_path):
    master_db_path = str(tmp_path / "does_not_exist.json")
    data = LAC.load_master_db(master_db_path, "Test Collection", "Parish")
    assert data == {
        "collection_title": "Test Collection", "record_type_name": "Parish", "sheets": [],
        "total_spent": 0.0, "total_pages_processed": 0, "pending_batch_jobs": [],
    }


def test_save_and_load_master_db_round_trip(tmp_path):
    master_db_path = str(tmp_path / "JSON" / "parish_register.json")
    data = {"collection_title": "Test", "record_type_name": "Parish", "sheets": [{"page_id": "p1"}]}
    LAC.save_master_db(master_db_path, data)
    assert LAC.load_master_db(master_db_path, "Test", "Parish") == data


def test_append_scaffold_sheets_adds_new_sheets():
    master_data = {"sheets": []}
    new_sheets = [
        {"page_id": "p1", "document_metadata": {"file_name": "abc.jpg"}, "records": []},
        {"page_id": "p2", "document_metadata": {"file_name": "def.jpg"}, "records": []},
    ]
    LAC.append_scaffold_sheets(master_data, new_sheets)
    assert len(master_data["sheets"]) == 2


def test_append_scaffold_sheets_dedups_by_file_name():
    existing_sheet = {"page_id": "p1", "document_metadata": {"file_name": "abc.jpg"}, "records": []}
    master_data = {"sheets": [existing_sheet]}
    duplicate_sheet = {"page_id": "p1-retry", "document_metadata": {"file_name": "abc.jpg"}, "records": []}
    LAC.append_scaffold_sheets(master_data, [duplicate_sheet])
    assert master_data["sheets"] == [existing_sheet]


def test_validate_master_db_against_commissioner_warns_and_does_not_raise(capsys):
    bad_data = {"collection_title": "Bad", "sheets": [{"records": "not-a-list"}]}
    LAC.validate_master_db_against_commissioner(bad_data, "Parish", "Bad Collection")
    captured = capsys.readouterr()
    assert "[WARN]" in captured.out
    assert "Bad Collection" in captured.out


def test_resolve_record_type_maps_parish_and_scrip():
    assert LAC._resolve_record_type("parish") == "Parish"
    assert LAC._resolve_record_type("scrip") == "Scrip"


def test_resolve_record_type_exits_on_empty(capsys):
    with pytest.raises(SystemExit):
        LAC._resolve_record_type("")
    assert "[ERROR]" in capsys.readouterr().out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest Voyageur/tests/test_lac.py -v`
Expected: FAIL with `AttributeError: module 'LAC' has no attribute 'resolve_generic_setting'`
(and similarly down the list, as each referenced name doesn't exist yet).

- [ ] **Step 3: Implement the building blocks**

In `Voyageur/LAC.py`, add the repo-root `sys.path` insertion right after the existing
`load_dotenv` calls (currently lines 17-18), before the `try: from . import lac_client`
block:

```python
# Commissioner lives in a sibling tool folder, not an installed package - add the repo root
# to sys.path so it can be imported by absolute path, matching census_schema.py's own
# precedent for cross-package imports (Voyageur/census_schema.py:28-35).
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
```

Add after the `CDP_PORT` constant (currently line 44), before `load_cookies`:

```python
def resolve_generic_setting(document_type: str, generic_key: str, default: str = "") -> str:
    """Mirrors Paleographer.py's own resolve_setting(): resolves a generic runtime setting
    (e.g. "MASTER_DB_NAME") via document_type's own field_remap table (e.g. Parish.pmt's
    CHURCH_MASTER_DB_NAME -> MASTER_DB_NAME), falling back to reading generic_key directly.
    Uses Commissioner.record_registry.get_field_remap() rather than Paleographer/engine.py's
    own TYPE_CFG - see this plan's Global Constraints on LAC.py's dependency footprint."""
    from Commissioner.record_registry import get_field_remap
    field_remap = get_field_remap(document_type)
    for prefixed_key, target in field_remap.items():
        if target == generic_key:
            val = os.environ.get(prefixed_key, "")
            if val:
                return val
    return os.environ.get(generic_key, default)


def resolve_master_db_path(document_type: str, program_dir: str) -> str:
    """Resolves the absolute path to Paleographer's own MASTER_DB for document_type,
    matching Paleographer.py's own MASTER_DB derivation (PROGRAM_DIR / JSON_DIR /
    MASTER_DB_NAME) exactly, so scaffold sheets Voyageur writes land in the same file
    Paleographer itself reads/writes."""
    master_db_name = resolve_generic_setting(document_type, "MASTER_DB_NAME")
    if not master_db_name:
        raise RuntimeError(
            f"MASTER_DB_NAME resolved to an empty value for document_type {document_type!r} "
            f"(check the active record type's own MASTER_DB_NAME setting, e.g. "
            f"CHURCH_MASTER_DB_NAME for Parish).")
    json_dir = os.environ.get("JSON_DIR", "")
    return str(Path(program_dir) / json_dir / master_db_name)


def load_master_db(master_db_path: str, collection_title: str, record_type_name: str) -> Dict[str, Any]:
    if os.path.exists(master_db_path):
        with open(master_db_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "collection_title": collection_title, "record_type_name": record_type_name, "sheets": [],
        "total_spent": 0.0, "total_pages_processed": 0, "pending_batch_jobs": [],
    }


def save_master_db(master_db_path: str, master_data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(master_db_path) or ".", exist_ok=True)
    with open(master_db_path, "w", encoding="utf-8") as f:
        json.dump(master_data, f, indent=2, ensure_ascii=False)


def append_scaffold_sheets(master_data: Dict[str, Any], new_sheets: List[Dict[str, Any]]) -> None:
    """Appends Voyageur-built placeholder sheets into master_data["sheets"], deduplicating
    by document_metadata.file_name against sheets already present. Guards a crash-and-resume
    scenario: download_pid_bundle skips the actual file download when it already exists on
    disk, but is not itself responsible for skipping the caller's own scaffold-sheet append,
    so a resumed run that re-touches an already-checkpointed PID must not write a duplicate
    placeholder for the same file_name."""
    master_sheets = master_data.setdefault("sheets", [])
    existing_file_names = {sheet.get("document_metadata", {}).get("file_name") for sheet in master_sheets}
    for sheet in new_sheets:
        file_name = sheet.get("document_metadata", {}).get("file_name")
        if file_name is not None and file_name in existing_file_names:
            continue
        master_sheets.append(sheet)
        existing_file_names.add(file_name)


def validate_master_db_against_commissioner(master_data: Dict[str, Any], document_type: str,
                                            collection_title: str) -> None:
    """Non-blocking Commissioner schema check, identical in shape to
    census_schema.py's validate_against_commissioner() (Sub-project 2) - a failure here is
    logged and swallowed, never raised, and the MASTER_DB write proceeds regardless."""
    try:
        from Commissioner.record_registry import parse_collection
        parse_collection(master_data, document_type)
    except Exception as e:
        print(f"[WARN] Commissioner validation failed for {collection_title!r}: {e}")


RECORD_TYPE_ARG_TO_DOCUMENT_TYPE = {"parish": "Parish", "scrip": "Scrip"}


def _resolve_record_type(record_type_arg: str) -> str:
    document_type = RECORD_TYPE_ARG_TO_DOCUMENT_TYPE.get(record_type_arg)
    if document_type is None:
        print("[ERROR] --record-type is required (parish or scrip) - or set LAC_RECORD_TYPE in .env.")
        sys.exit(1)
    return document_type
```

Add the `--record-type` flag to both subparsers in `main()`. Replace:

```python
    volume_parser.add_argument("--workers", type=int, default=int(os.environ.get("LAC_MAX_WORKERS", "1")),
                               help="Number of concurrent workers for volume downloading (default 1).")
    volume_parser.set_defaults(func=_run_volume)
```

with:

```python
    volume_parser.add_argument("--workers", type=int, default=int(os.environ.get("LAC_MAX_WORKERS", "1")),
                               help="Number of concurrent workers for volume downloading (default 1).")
    volume_parser.add_argument("--record-type", default=os.environ.get("LAC_RECORD_TYPE", ""),
                               help="Commissioner record type this volume harvest is for: parish or scrip.")
    volume_parser.set_defaults(func=_run_volume)
```

and replace:

```python
    reel_parser.add_argument("--media-dir", default=MEDIA_DIR,
                             help="Base output media directory.")
    reel_parser.set_defaults(func=_run_reel)
```

with:

```python
    reel_parser.add_argument("--media-dir", default=MEDIA_DIR,
                             help="Base output media directory.")
    reel_parser.add_argument("--record-type", default=os.environ.get("LAC_RECORD_TYPE", ""),
                             help="Commissioner record type this reel harvest is for: parish or scrip.")
    reel_parser.set_defaults(func=_run_reel)
```

(`choices=` is deliberately not used here: an invalid value should fail with the plain
`[ERROR]` message `_resolve_record_type` already prints, not argparse's own less-actionable
`invalid choice` error, and an empty default from an unset `LAC_RECORD_TYPE` must reach
`_resolve_record_type` rather than being rejected by argparse before `_run_volume`/`_run_reel`
even runs.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest Voyageur/tests/test_lac.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add Voyageur/LAC.py Voyageur/tests/test_lac.py
git commit -m "feat(lac): add MASTER_DB path resolution and scaffold-sheet building blocks"
```

---

### Task 5: Wire scaffold writing into LAC.py's volume harvest path

**Files:**
- Modify: `Voyageur/LAC.py`
- Test: `Voyageur/tests/test_lac.py`

**Interfaces:**
- Consumes: `load_master_db`, `save_master_db`, `append_scaffold_sheets`, `validate_master_db_against_commissioner`, `resolve_master_db_path`, `_resolve_record_type`, `RECORD_TYPE_ARG_TO_DOCUMENT_TYPE` (Task 4); `Commissioner.record_registry.build_empty_sheet` (Task 1).
- Produces: `download_volume_assets(pids, media_dir, checkpoint_path, master_db_path, document_type, collection_title) -> Dict[str, Any]`; `download_volume_assets_multiworker(pids, media_dir, checkpoint_path, master_db_path, document_type, collection_title, max_workers=4, base_delay=0.3, timeout_seconds=45) -> Dict[str, Any]`; `retrieve_volume(vol, cookies, media_dir, checkpoint_path, master_db_path, document_type, collection_title, archival_number=DEFAULT_ARCHIVAL_NUMBER, max_workers=1) -> Dict[str, Any]` (signatures gain three new required params, inserted after `checkpoint_path`).

- [ ] **Step 1: Write the failing tests**

Append to `Voyageur/tests/test_lac.py`:

```python
import lac_client


def test_download_volume_assets_writes_one_scaffold_sheet_per_asset(monkeypatch, tmp_path):
    def fake_download_pid_bundle(pid, media_dir):
        return {
            "pid": pid, "lac_catalog_title": "Test", "reel_numbers": [], "series_code": "RG15-D-II-8-b",
            "source_documents": [
                {"document_type": "Affidavit", "media_path": str(tmp_path / pid / "asset1.jpg"),
                 "lac_pid": pid, "lac_asset_id": "asset1", "source": "LAC"},
            ],
        }
    monkeypatch.setattr(LAC, "download_pid_bundle", fake_download_pid_bundle)

    checkpoint_path = str(tmp_path / "checkpoint.json")
    master_db_path = str(tmp_path / "scrip_records.json")

    result = LAC.download_volume_assets(["pid1"], str(tmp_path), checkpoint_path,
                                        master_db_path, "Scrip", "Test Collection")

    assert result["downloaded_pids"] == ["pid1"]
    master_data = LAC.load_master_db(master_db_path, "Test Collection", "Scrip")
    assert len(master_data["sheets"]) == 1
    assert master_data["sheets"][0]["document_metadata"]["file_name"] == "asset1.jpg"
    assert master_data["sheets"][0]["records"][0]["participants"] == []


def test_download_volume_assets_skips_already_downloaded_pid(monkeypatch, tmp_path):
    calls = []
    def fake_download_pid_bundle(pid, media_dir):
        calls.append(pid)
        return {"source_documents": []}
    monkeypatch.setattr(LAC, "download_pid_bundle", fake_download_pid_bundle)

    checkpoint_path = str(tmp_path / "checkpoint.json")
    LAC.save_checkpoint(checkpoint_path, {"pids": ["pid1"], "downloaded_pids": ["pid1"], "failed_pids": {}})
    master_db_path = str(tmp_path / "scrip_records.json")

    LAC.download_volume_assets(["pid1"], str(tmp_path), checkpoint_path, master_db_path, "Scrip", "Test")

    assert calls == []


def test_download_volume_assets_records_failure_without_writing_scaffold(monkeypatch, tmp_path):
    def fake_download_pid_bundle(pid, media_dir):
        raise lac_client.LacCallError("boom")
    monkeypatch.setattr(LAC, "download_pid_bundle", fake_download_pid_bundle)

    checkpoint_path = str(tmp_path / "checkpoint.json")
    master_db_path = str(tmp_path / "scrip_records.json")

    result = LAC.download_volume_assets(["pid1"], str(tmp_path), checkpoint_path, master_db_path, "Scrip", "Test")

    assert result["failed_pids"] == {"pid1": "boom"}
    assert not os.path.exists(master_db_path)


def test_download_volume_assets_multiworker_no_op_when_all_downloaded(tmp_path):
    checkpoint_path = str(tmp_path / "checkpoint.json")
    LAC.save_checkpoint(checkpoint_path, {"pids": ["pid1"], "downloaded_pids": ["pid1"], "failed_pids": {}})
    master_db_path = str(tmp_path / "scrip_records.json")

    result = LAC.download_volume_assets_multiworker(["pid1"], str(tmp_path), checkpoint_path,
                                                     master_db_path, "Scrip", "Test", max_workers=2)

    assert result["downloaded_pids"] == ["pid1"]


def test_retrieve_volume_threads_master_db_params_to_sequential_path(monkeypatch, tmp_path):
    monkeypatch.setattr(LAC, "retrieve_volume_pids",
                        lambda vol, cookies, checkpoint_path, archival_number: ["pid1"])
    monkeypatch.setattr(LAC, "download_pid_bundle", lambda pid, media_dir: {
        "source_documents": [{"media_path": str(tmp_path / "asset1.jpg"), "lac_asset_id": "asset1"}],
    })
    checkpoint_path = str(tmp_path / "checkpoint.json")
    master_db_path = str(tmp_path / "scrip_records.json")

    LAC.retrieve_volume("1325", {}, str(tmp_path), checkpoint_path, master_db_path, "Scrip", "Test Collection")

    master_data = LAC.load_master_db(master_db_path, "Test Collection", "Scrip")
    assert len(master_data["sheets"]) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest Voyageur/tests/test_lac.py -v`
Expected: FAIL with `TypeError: download_volume_assets() takes 3 positional arguments but 6
were given` (and similarly for `download_volume_assets_multiworker`/`retrieve_volume`) - the
new params don't exist on these functions yet.

- [ ] **Step 3: Wire the scaffold writes**

In `Voyageur/LAC.py`, replace `download_volume_assets` (currently lines 281-301):

```python
def download_volume_assets(pids: List[str], media_dir: str, checkpoint_path: str) -> Dict[str, Any]:
    """Sequential bulk download for a list of PIDs with checkpointing."""
    checkpoint = load_checkpoint(checkpoint_path)
    downloaded = set(checkpoint.get("downloaded_pids", []))
    failed = checkpoint.get("failed_pids", {})

    for pid in pids:
        if pid in downloaded:
            continue
        try:
            download_pid_bundle(pid, media_dir)
            downloaded.add(pid)
            failed.pop(pid, None)
        except lac_client.LacCallError as e:
            failed[pid] = str(e)

        checkpoint["downloaded_pids"] = sorted(downloaded)
        checkpoint["failed_pids"] = failed
        save_checkpoint(checkpoint_path, checkpoint)

    return checkpoint
```

with:

```python
def download_volume_assets(pids: List[str], media_dir: str, checkpoint_path: str,
                           master_db_path: str, document_type: str, collection_title: str) -> Dict[str, Any]:
    """Sequential bulk download for a list of PIDs with checkpointing. Also seeds
    Paleographer's own MASTER_DB with one Commissioner-shaped scaffold sheet per
    downloaded asset, incrementally - see the Voyageur-Parish-Scrip-scaffold design spec."""
    from Commissioner.record_registry import build_empty_sheet

    checkpoint = load_checkpoint(checkpoint_path)
    downloaded = set(checkpoint.get("downloaded_pids", []))
    failed = checkpoint.get("failed_pids", {})
    master_data = load_master_db(master_db_path, collection_title, document_type)

    for pid in pids:
        if pid in downloaded:
            continue
        try:
            bundle = download_pid_bundle(pid, media_dir)
            downloaded.add(pid)
            failed.pop(pid, None)

            new_sheets = [
                build_empty_sheet(Path(entry["media_path"]).name,
                                  Path(entry["media_path"]).suffix.lstrip("."),
                                  page_id=entry.get("lac_asset_id"))
                for entry in bundle.get("source_documents", [])
            ]
            append_scaffold_sheets(master_data, new_sheets)
            validate_master_db_against_commissioner(master_data, document_type, collection_title)
            save_master_db(master_db_path, master_data)
        except lac_client.LacCallError as e:
            failed[pid] = str(e)

        checkpoint["downloaded_pids"] = sorted(downloaded)
        checkpoint["failed_pids"] = failed
        save_checkpoint(checkpoint_path, checkpoint)

    return checkpoint
```

Replace `download_volume_assets_multiworker`'s signature and body (currently lines
334-417) - only the changed lines are shown, everything else (the watchdog loop, `START`/
`403_ERROR`/`FAIL` branches) is unchanged:

```python
def download_volume_assets_multiworker(pids: List[str], media_dir: str, checkpoint_path: str,
                                       max_workers: int = 4, base_delay: float = 0.3,
                                       timeout_seconds: int = 45) -> Dict[str, Any]:
    """Concurrent multi-worker PID downloading with watchdog timeout."""
    checkpoint = load_checkpoint(checkpoint_path)
    downloaded = set(checkpoint.get("downloaded_pids", []))
    failed = checkpoint.get("failed_pids", {})

    pids_to_process = [p for p in pids if p not in downloaded]
```

becomes:

```python
def download_volume_assets_multiworker(pids: List[str], media_dir: str, checkpoint_path: str,
                                       master_db_path: str, document_type: str, collection_title: str,
                                       max_workers: int = 4, base_delay: float = 0.3,
                                       timeout_seconds: int = 45) -> Dict[str, Any]:
    """Concurrent multi-worker PID downloading with watchdog timeout. Scaffold-sheet writes
    happen only in this controller loop (never inside a worker subprocess) after a SUCCESS
    message, mirroring the existing single-writer checkpoint pattern - see the
    Voyageur-Parish-Scrip-scaffold design spec."""
    from Commissioner.record_registry import build_empty_sheet

    checkpoint = load_checkpoint(checkpoint_path)
    downloaded = set(checkpoint.get("downloaded_pids", []))
    failed = checkpoint.get("failed_pids", {})
    master_data = load_master_db(master_db_path, collection_title, document_type)

    pids_to_process = [p for p in pids if p not in downloaded]
```

and the `SUCCESS` branch:

```python
        elif msg_type == "SUCCESS":
            active_workers[wid]["pid"] = None
            downloaded.add(pid)
            failed.pop(pid, None)
            processed_count += 1
            checkpoint["downloaded_pids"] = sorted(downloaded)
            checkpoint["failed_pids"] = failed
            save_checkpoint(checkpoint_path, checkpoint)
            print(f"\rDownloaded PID {pid} [{processed_count}/{total_target}]", end="", flush=True)
```

becomes:

```python
        elif msg_type == "SUCCESS":
            active_workers[wid]["pid"] = None
            downloaded.add(pid)
            failed.pop(pid, None)
            processed_count += 1
            bundle = msg[3]
            new_sheets = [
                build_empty_sheet(Path(entry["media_path"]).name,
                                  Path(entry["media_path"]).suffix.lstrip("."),
                                  page_id=entry.get("lac_asset_id"))
                for entry in bundle.get("source_documents", [])
            ]
            append_scaffold_sheets(master_data, new_sheets)
            validate_master_db_against_commissioner(master_data, document_type, collection_title)
            save_master_db(master_db_path, master_data)
            checkpoint["downloaded_pids"] = sorted(downloaded)
            checkpoint["failed_pids"] = failed
            save_checkpoint(checkpoint_path, checkpoint)
            print(f"\rDownloaded PID {pid} [{processed_count}/{total_target}]", end="", flush=True)
```

Replace `retrieve_volume` (currently lines 420-426):

```python
def retrieve_volume(vol: str, cookies: Dict[str, str], media_dir: str, checkpoint_path: str,
                    archival_number: str = DEFAULT_ARCHIVAL_NUMBER, max_workers: int = 1) -> Dict[str, Any]:
    """High-level volume retrieval: gathers PIDs and downloads all associated assets."""
    pids = retrieve_volume_pids(vol, cookies, checkpoint_path, archival_number=archival_number)
    if max_workers > 1:
        return download_volume_assets_multiworker(pids, media_dir, checkpoint_path, max_workers=max_workers)
    return download_volume_assets(pids, media_dir, checkpoint_path)
```

with:

```python
def retrieve_volume(vol: str, cookies: Dict[str, str], media_dir: str, checkpoint_path: str,
                    master_db_path: str, document_type: str, collection_title: str,
                    archival_number: str = DEFAULT_ARCHIVAL_NUMBER, max_workers: int = 1) -> Dict[str, Any]:
    """High-level volume retrieval: gathers PIDs and downloads all associated assets."""
    pids = retrieve_volume_pids(vol, cookies, checkpoint_path, archival_number=archival_number)
    if max_workers > 1:
        return download_volume_assets_multiworker(pids, media_dir, checkpoint_path, master_db_path,
                                                   document_type, collection_title, max_workers=max_workers)
    return download_volume_assets(pids, media_dir, checkpoint_path, master_db_path, document_type, collection_title)
```

Replace `_run_volume` (currently lines 432-453):

```python
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
```

with:

```python
def _run_volume(args: argparse.Namespace) -> None:
    print(f"[System] Starting LAC Volume retrieval for Volume {args.volume}...")
    document_type = _resolve_record_type(args.record_type)
    master_db_path = resolve_master_db_path(document_type, PROGRAM_DIR)
    collection_title = os.environ.get("VOLUME_TITLE") or f"LAC Volume {args.volume}"

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
                                 master_db_path, document_type, collection_title,
                                 archival_number=args.archival_number, max_workers=args.workers)
    except lac_client.LacSearchAuthError as e:
        print(f"[FATAL ERROR] {e} Opening the search page now.")
        lac_client.open_search_browser_for_refresh()
        return

    print(f"[System] Harvested volume {args.volume}: {len(result.get('pids', []))} PID(s), "
          f"{len(result.get('downloaded_pids', []))} downloaded, "
          f"{len(result.get('failed_pids', {}))} failed.")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest Voyageur/tests/test_lac.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add Voyageur/LAC.py Voyageur/tests/test_lac.py
git commit -m "feat(lac): write Commissioner scaffold sheets during volume harvest"
```

---

### Task 6: Wire scaffold writing into LAC.py's reel harvest path

**Files:**
- Modify: `Voyageur/LAC.py`
- Test: `Voyageur/tests/test_lac.py`

**Interfaces:**
- Consumes: `load_master_db`, `save_master_db`, `append_scaffold_sheets`,
  `validate_master_db_against_commissioner`, `resolve_master_db_path`, `_resolve_record_type`
  (Task 4); `Commissioner.record_registry.build_empty_sheet` (Task 1).
- Produces: `download_images(manifest_data, out_dir, roll_num, master_db_path, document_type, collection_title) -> None` (signature gains three new required params, inserted after `roll_num`).

- [ ] **Step 1: Write the failing tests**

Append to `Voyageur/tests/test_lac.py`:

```python
from pathlib import Path


def test_download_images_writes_scaffold_sheet_per_canvas(monkeypatch, tmp_path):
    manifest_data = {
        "sequences": [{"canvases": [
            {"images": [{"resource": {"@id": "https://example.com/img1.jpg"}}]},
        ]}],
    }

    class FakeResponse:
        content = b"fake-image-bytes"
        def raise_for_status(self):
            pass

    class FakeSession:
        def get(self, url, timeout=None):
            return FakeResponse()

    monkeypatch.setattr(LAC.requests, "Session", lambda: FakeSession())

    out_dir = str(tmp_path / "images")
    os.makedirs(out_dir, exist_ok=True)
    master_db_path = str(tmp_path / "parish_register.json")

    LAC.download_images(manifest_data, out_dir, "roll1", master_db_path, "Parish", "Test Collection")

    master_data = LAC.load_master_db(master_db_path, "Test Collection", "Parish")
    assert len(master_data["sheets"]) == 1
    assert master_data["sheets"][0]["document_metadata"]["file_name"] == "roll1_0001.jpg"
    assert master_data["sheets"][0]["page_id"] == "roll1_0001"


def test_download_images_dedups_scaffold_when_image_already_on_disk(monkeypatch, tmp_path):
    manifest_data = {
        "sequences": [{"canvases": [
            {"images": [{"resource": {"@id": "https://example.com/img1.jpg"}}]},
        ]}],
    }
    out_dir = str(tmp_path / "images")
    os.makedirs(out_dir, exist_ok=True)
    (Path(out_dir) / "roll1_0001.jpg").write_bytes(b"already-downloaded")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("should not re-download an existing image")
    monkeypatch.setattr(LAC.requests, "Session", lambda: type("FakeSession", (), {"get": fail_if_called})())

    master_db_path = str(tmp_path / "parish_register.json")

    LAC.download_images(manifest_data, out_dir, "roll1", master_db_path, "Parish", "Test Collection")

    master_data = LAC.load_master_db(master_db_path, "Test Collection", "Parish")
    assert len(master_data["sheets"]) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest Voyageur/tests/test_lac.py -k download_images -v`
Expected: FAIL with `TypeError: download_images() takes 3 positional arguments but 6 were
given`.

- [ ] **Step 3: Wire the scaffold write**

In `Voyageur/LAC.py`, replace `download_images` (currently lines 105-165):

```python
def download_images(manifest_data: Dict[str, Any], out_dir: str, roll_num: str) -> None:
    """Loops through the manifest canvases and downloads max-resolution files."""
    if "sequences" in manifest_data and manifest_data["sequences"]:
        canvases = manifest_data["sequences"][0].get("canvases", [])
    elif "items" in manifest_data:
        canvases = manifest_data.get("items", [])
    else:
        print("[Error] No valid sequences or items found in the manifest.")
        print(f"[Debug] Manifest Keys returned: {list(manifest_data.keys())}")
        sys.exit(1)

    total = len(canvases)
    if total == 0:
        print("[Error] No images found in the manifest.")
        sys.exit(1)

    print(f"[Info] Found {total} images to download.")
    session = requests.Session()

    for i, canvas in enumerate(canvases, 1):
        try:
            img_id = ""
            if "images" in canvas:
                images = canvas.get("images", [])
                if images:
                    resource = images[0].get("resource", {})
                    img_id = resource.get("@id", "")
            elif "items" in canvas:
                items = canvas.get("items", [])
                if items:
                    annotations = items[0].get("items", [])
                    if annotations:
                        body = annotations[0].get("body", {})
                        if isinstance(body, dict):
                            img_id = body.get("id", "")
                        elif isinstance(body, list) and body:
                            img_id = body[0].get("id", "")

            if not img_id:
                print(f"\n[Warning] Could not extract image URL for canvas {i}")
                continue

            filename = f"{roll_num}_{i:04d}.jpg"
            filepath = os.path.join(out_dir, filename)

            if os.path.exists(filepath):
                print(f"\rDownloading [{i}/{total}]...", end="", flush=True)
                continue

            print(f"\rDownloading [{i}/{total}]...", end="", flush=True)

            img_resp = session.get(img_id, timeout=20)
            img_resp.raise_for_status()

            with open(filepath, 'wb') as f:
                f.write(img_resp.content)

        except Exception as e:
            print(f"\n[Warning] Failed to download image {i}: {e}")

    print(f"\n\n[System] LAC Download for {roll_num} completed successfully!")
```

with:

```python
def download_images(manifest_data: Dict[str, Any], out_dir: str, roll_num: str,
                    master_db_path: str, document_type: str, collection_title: str) -> None:
    """Loops through the manifest canvases, downloads max-resolution files, and seeds
    Paleographer's own MASTER_DB with one Commissioner-shaped scaffold sheet per canvas -
    for both a freshly downloaded image and one already on disk from a prior run, so a
    MASTER_DB reset/first-time run still ends up fully seeded. See the
    Voyageur-Parish-Scrip-scaffold design spec."""
    from Commissioner.record_registry import build_empty_sheet

    if "sequences" in manifest_data and manifest_data["sequences"]:
        canvases = manifest_data["sequences"][0].get("canvases", [])
    elif "items" in manifest_data:
        canvases = manifest_data.get("items", [])
    else:
        print("[Error] No valid sequences or items found in the manifest.")
        print(f"[Debug] Manifest Keys returned: {list(manifest_data.keys())}")
        sys.exit(1)

    total = len(canvases)
    if total == 0:
        print("[Error] No images found in the manifest.")
        sys.exit(1)

    print(f"[Info] Found {total} images to download.")
    session = requests.Session()
    master_data = load_master_db(master_db_path, collection_title, document_type)

    for i, canvas in enumerate(canvases, 1):
        try:
            img_id = ""
            if "images" in canvas:
                images = canvas.get("images", [])
                if images:
                    resource = images[0].get("resource", {})
                    img_id = resource.get("@id", "")
            elif "items" in canvas:
                items = canvas.get("items", [])
                if items:
                    annotations = items[0].get("items", [])
                    if annotations:
                        body = annotations[0].get("body", {})
                        if isinstance(body, dict):
                            img_id = body.get("id", "")
                        elif isinstance(body, list) and body:
                            img_id = body[0].get("id", "")

            if not img_id:
                print(f"\n[Warning] Could not extract image URL for canvas {i}")
                continue

            filename = f"{roll_num}_{i:04d}.jpg"
            filepath = os.path.join(out_dir, filename)
            page_id = f"{roll_num}_{i:04d}"

            print(f"\rDownloading [{i}/{total}]...", end="", flush=True)

            if not os.path.exists(filepath):
                img_resp = session.get(img_id, timeout=20)
                img_resp.raise_for_status()
                with open(filepath, 'wb') as f:
                    f.write(img_resp.content)

            new_sheet = build_empty_sheet(filename, "jpg", page_id=page_id)
            append_scaffold_sheets(master_data, [new_sheet])
            validate_master_db_against_commissioner(master_data, document_type, collection_title)
            save_master_db(master_db_path, master_data)

        except Exception as e:
            print(f"\n[Warning] Failed to download image {i}: {e}")

    print(f"\n\n[System] LAC Download for {roll_num} completed successfully!")
```

Replace `_run_reel` (currently lines 456-465):

```python
def _run_reel(args: argparse.Namespace) -> None:
    if not args.url:
        print("[Error] --url is required for the reel subcommand.")
        sys.exit(1)

    program_dir = os.environ.get("PROGRAM_DIR", "").strip()
    roll, manifest = parse_url(args.url)
    output_directory = setup_directories(program_dir, args.media_dir, roll)
    manifest_json = download_manifest(manifest)
    download_images(manifest_json, output_directory, roll)
```

with:

```python
def _run_reel(args: argparse.Namespace) -> None:
    if not args.url:
        print("[Error] --url is required for the reel subcommand.")
        sys.exit(1)

    document_type = _resolve_record_type(args.record_type)
    program_dir = os.environ.get("PROGRAM_DIR", "").strip()
    master_db_path = resolve_master_db_path(document_type, PROGRAM_DIR)

    roll, manifest = parse_url(args.url)
    collection_title = os.environ.get("VOLUME_TITLE") or f"LAC Reel {roll}"
    output_directory = setup_directories(program_dir, args.media_dir, roll)
    manifest_json = download_manifest(manifest)
    download_images(manifest_json, output_directory, roll, master_db_path, document_type, collection_title)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest Voyageur/tests/ Commissioner/tests/ Paleographer/tests/ -v`
Expected: PASS (full suite across all three packages this plan touched).

- [ ] **Step 5: Commit**

```bash
git add Voyageur/LAC.py Voyageur/tests/test_lac.py
git commit -m "feat(lac): write Commissioner scaffold sheets during reel harvest"
```

---

## Self-Review

**Spec coverage:**
- Real `document_metadata` for `FS.py` (Goals bullet 2) -> Task 3.
- `LAC.py` gains a real JSON/`MASTER_DB` output step with one scaffold `Sheet` per asset
  (Goals bullet 3) -> Tasks 4-6.
- Written directly into Paleographer's own `MASTER_DB`, resolved the same way Paleographer
  resolves it (Goals bullet 4) -> Task 4 (`resolve_master_db_path`/`resolve_generic_setting`).
- `get_processed_files`/`merge_sheets` fixes (Goals bullet 5) -> Task 2.
- Non-blocking `parse_collection` validation at both `LAC.py` and `FS.py` (Goals bullet 6)
  -> Task 3 (`validate_against_commissioner`), Task 4/5/6
  (`validate_master_db_against_commissioner`).
- No AI-filling triggered automatically (Goals bullet 7) - satisfied by construction: no
  task calls anything in Paleographer's extraction path.
- `--record-type {parish,scrip}` on both subparsers (Architecture) -> Task 4.
- Scaffold write happens only in the controller loop for the concurrent path, never inside
  a worker (Architecture) -> Task 5 (`SUCCESS` branch only).
- `build_empty_sheet` shape (`document_metadata` + one empty `Record`) -> Task 1.
- Testing section's four bullets -> Task 1 (Commissioner), Task 2 (Paleographer), Task 3
  (FS.py), Tasks 4-6 (LAC.py, including the "second run doesn't duplicate" case via
  `test_download_volume_assets_skips_already_downloaded_pid` and
  `test_append_scaffold_sheets_dedups_by_file_name`).

**Placeholder scan:** no "TBD"/"add appropriate error handling"/"similar to Task N" found -
every step above has complete, copy-pasteable code, and every test asserts a concrete value.

**Type/signature consistency:** `build_empty_sheet(file_name, file_type, page_id=None)`
(Task 1) is called identically in Tasks 5 and 6. `load_master_db`/`save_master_db`/
`append_scaffold_sheets`/`validate_master_db_against_commissioner`/`resolve_master_db_path`
(Task 4) are called with the same parameter order and types everywhere they're used in Tasks
5-6. `download_volume_assets`/`download_volume_assets_multiworker`/`retrieve_volume`/
`download_images` all insert their three new params (`master_db_path`, `document_type`,
`collection_title`) in the same relative position and order at every call site touched.

**Design refinement flagged for the user:** `append_scaffold_sheets`'s dedup-by-`file_name`
check (Task 4) goes slightly beyond the committed spec's literal text, which describes the
scaffold write but doesn't call out deduplication explicitly. It's needed because a crash
between a `save_master_db` call and the following `save_checkpoint` call (sequential path)
or `save_checkpoint` call (multiworker path) could leave a PID undercounted as downloaded;
a resumed run would then re-process that PID through `download_pid_bundle` (itself
idempotent about the actual file download) and, without this guard, append a second
placeholder sheet for the same `file_name`. This is a robustness addition, not a scope
change - flagging it here per this plan's own transparency norm rather than presenting it
silently.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-06-voyageur-parish-scrip-scaffold.md`. Two execution options:

1. **Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
