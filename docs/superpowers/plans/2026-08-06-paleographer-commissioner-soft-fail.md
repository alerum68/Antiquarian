# Paleographer Commissioner Soft-Fail Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire Paleographer's `save_master_db()` into the same soft-fail Commissioner validation Voyageur already runs, and collapse the three existing copy-pasted try/except/log-WARN blocks (`census_schema.py`, `FS.py`, `LAC.py`) plus the new Paleographer one into a single shared `Commissioner.record_registry.validate_soft()` helper.

**Architecture:** Add one new function, `validate_soft(data, document_type, label) -> None`, to `Commissioner/record_registry.py`. It wraps the existing `parse_collection()` call in a try/except that logs `[WARN] Commissioner validation failed for {label!r}: {e}` and never raises. The three existing Voyageur wrapper functions swap their inline `parse_collection` call for a call to `validate_soft`, keeping their own document-type resolution logic and their own outer try/except (which guards the `validate_soft` import itself). Paleographer's `save_master_db()` gets the same guarded call added directly, with no signature change — every one of its ~6 existing call sites is covered automatically.

**Tech Stack:** Python, pytest, Pydantic (via `Commissioner.models`).

## Global Constraints

- Soft-fail only, everywhere: `validate_soft` must never raise once its own import has succeeded — every failure inside `parse_collection` is caught by `Exception` and logged, never propagated.
- No hard-fail/blocking validation mode is introduced anywhere in this plan.
- `save_master_db(master_data)` keeps its exact current signature — `Dict[str, Any] -> None`. No new parameter.
- No changes to `Commissioner.models` or to `parse_collection`'s own behavior — only how many places call it changes.
- The three existing Voyageur wrapper functions (`census_schema.validate_against_commissioner`, `FS.validate_against_commissioner`, `LAC.validate_master_db_against_commissioner`) keep their exact current signatures and their own document-type resolution logic. Only their internal `parse_collection` call is replaced.
- `validate_soft`'s exact signature: `validate_soft(data: dict, document_type: str, label: str) -> None`.
- `validate_soft`'s exact log line: `f"[WARN] Commissioner validation failed for {label!r}: {e}"` — this exact format is asserted by existing tests in `Voyageur/tests/test_census_schema.py`, `Voyageur/tests/test_fs.py`, and `Voyageur/tests/test_lac.py`, and must not change.

---

## Task 1: Add `validate_soft()` to Commissioner/record_registry.py

**Files:**
- Modify: `Commissioner/record_registry.py:161-163` (insert new function after `parse_collection`)
- Test: `Commissioner/tests/test_record_registry.py`

**Interfaces:**
- Consumes: existing `parse_collection(raw_json: dict, document_type: str) -> Collection` (already defined at `Commissioner/record_registry.py:147`).
- Produces: `validate_soft(data: dict, document_type: str, label: str) -> None` — every later task in this plan imports and calls this exact function.

- [x] **Step 1: Write the failing tests**

Open `Commissioner/tests/test_record_registry.py`. Find this existing test (it ends at line 284):

```python
def test_parse_collection_rejects_bad_extra_field_type():
    bad_payload = {
        **SAMPLE_SCRIP_PAYLOAD,
        "sheets": [
            {
                **SAMPLE_SCRIP_PAYLOAD["sheets"][0],
                "records": [
                    {
                        **SAMPLE_SCRIP_PAYLOAD["sheets"][0]["records"][0],
                        "type_specific_fields": {"scrip_type": "Currency"},
                    }
                ],
            }
        ],
    }
    with pytest.raises(ValidationError, match="Land"):
        parse_collection(bad_payload, document_type="Scrip")
```

Immediately after it (before `def test_parse_collection_leaves_type_specific_fields_exactly_as_given():`), insert:

```python
def test_validate_soft_accepts_a_valid_collection_and_prints_nothing(capsys):
    validate_soft(SAMPLE_SCRIP_PAYLOAD, "Scrip", "Test Scrip Collection")

    captured = capsys.readouterr()
    assert "[WARN]" not in captured.out


def test_validate_soft_logs_and_does_not_raise_on_bad_shape(capsys):
    bad_payload = {"collection_title": "Bad Collection", "sheets": [{"records": "not-a-list"}]}

    validate_soft(bad_payload, "Scrip", "Bad Collection")

    captured = capsys.readouterr()
    assert "[WARN] Commissioner validation failed for 'Bad Collection'" in captured.out


def test_validate_soft_logs_and_does_not_raise_on_unknown_document_type(capsys):
    validate_soft({"collection_title": "X", "sheets": []}, "NotARecordType", "X Collection")

    captured = capsys.readouterr()
    assert "[WARN] Commissioner validation failed for 'X Collection'" in captured.out
    assert "NotARecordType" in captured.out
```

Add `validate_soft` to the existing import block at the top of the file:

```python
from Commissioner.record_registry import (
    InvalidRoleError,
    UnknownDocumentTypeError,
    UnknownFieldTypeError,
    _build_registry,
    get_document_types,
    get_valid_roles,
    parse_collection,
    validate_participant_extra_fields,
    validate_record_extra_fields,
    validate_role_name,
    validate_soft,
)
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest Commissioner/tests/test_record_registry.py -k validate_soft -v`
Expected: FAIL with `ImportError: cannot import name 'validate_soft'`

- [x] **Step 3: Implement `validate_soft`**

In `Commissioner/record_registry.py`, immediately after `parse_collection`'s closing `return collection` (line 163), insert:

```python


def validate_soft(data: dict, document_type: str, label: str) -> None:
    """Runs parse_collection() as a visibility check, never a gate: a validation failure is
    logged and swallowed here so a Commissioner-side schema gap can never block a real
    Voyageur gather or a Paleographer MASTER_DB write. Shared by every soft-fail call site -
    see the sub-project 4 design spec
    (docs/superpowers/specs/2026-08-06-paleographer-commissioner-soft-fail-design.md)."""
    try:
        parse_collection(data, document_type)
    except Exception as e:
        print(f"[WARN] Commissioner validation failed for {label!r}: {e}")
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest Commissioner/tests/test_record_registry.py -v`
Expected: PASS (all tests, including the 3 new ones and every pre-existing test in the file)

- [x] **Step 5: Commit**

```bash
git add Commissioner/record_registry.py Commissioner/tests/test_record_registry.py
git commit -m "Add validate_soft() soft-fail wrapper to Commissioner record_registry"
```

---

## Task 2: Delegate census_schema.py's validate_against_commissioner to validate_soft

**Files:**
- Modify: `Voyageur/census_schema.py:296-314`
- Test: `Voyageur/tests/test_census_schema.py` (existing tests only — no new tests)

**Interfaces:**
- Consumes: `validate_soft(data: dict, document_type: str, label: str) -> None` from Task 1.
- Produces: no change to `census_schema.validate_against_commissioner(normalized: dict, collection_title: str) -> None`'s signature or external behavior — later tasks and existing callers are unaffected.

- [ ] **Step 1: Run the existing tests as a baseline**

Run: `pytest Voyageur/tests/test_census_schema.py -k commissioner -v`
Expected: PASS (3 tests: `test_validate_against_commissioner_accepts_valid_normalized_output`, `test_validate_against_commissioner_logs_and_does_not_raise_on_bad_shape`, `test_validate_against_commissioner_survives_broken_commissioner_import`)

- [ ] **Step 2: Replace the internal parse_collection call with validate_soft**

In `Voyageur/census_schema.py`, find:

```python
    try:
        from Commissioner.record_registry import parse_collection
        parse_collection(normalized, "Census")
    except Exception as e:
        print(f"[WARN] Commissioner validation failed for {collection_title!r}: {e}")
```

Replace with:

```python
    try:
        from Commissioner.record_registry import validate_soft
        validate_soft(normalized, "Census", collection_title)
    except Exception as e:
        print(f"[WARN] Commissioner validation failed for {collection_title!r}: {e}")
```

- [ ] **Step 3: Run the existing tests to confirm they still pass unmodified**

Run: `pytest Voyageur/tests/test_census_schema.py -k commissioner -v`
Expected: PASS (same 3 tests, proving the delegation is behavior-neutral — including
`test_validate_against_commissioner_survives_broken_commissioner_import`, which monkeypatches
`sys.modules["Commissioner.record_registry"] = None` so the `from Commissioner.record_registry
import validate_soft` line itself raises `ImportError`, caught by this function's own
outer `except`)

- [ ] **Step 4: Commit**

```bash
git add Voyageur/census_schema.py
git commit -m "Delegate census_schema validate_against_commissioner to shared validate_soft"
```

---

## Task 3: Delegate FS.py's validate_against_commissioner to validate_soft

**Files:**
- Modify: `Voyageur/FS.py:433-446`
- Test: `Voyageur/tests/test_fs.py` (existing tests only — no new tests)

**Interfaces:**
- Consumes: `validate_soft(data: dict, document_type: str, label: str) -> None` from Task 1.
- Produces: no change to `FS.validate_against_commissioner(final_data: dict, record_family: str, collection_title: str) -> None`'s signature, its `RECORD_FAMILY_TO_DOCUMENT_TYPE` lookup, or its early-return for unmapped families.

- [ ] **Step 1: Run the existing tests as a baseline**

Run: `pytest Voyageur/tests/test_fs.py -k commissioner -v`
Expected: PASS

- [ ] **Step 2: Replace the internal parse_collection call with validate_soft**

In `Voyageur/FS.py`, find:

```python
    document_type = RECORD_FAMILY_TO_DOCUMENT_TYPE.get(record_family)
    if document_type is None:
        return
    try:
        from Commissioner.record_registry import parse_collection
        parse_collection(final_data, document_type)
    except Exception as e:
        print(f"[WARN] Commissioner validation failed for {collection_title!r}: {e}")
```

Replace with:

```python
    document_type = RECORD_FAMILY_TO_DOCUMENT_TYPE.get(record_family)
    if document_type is None:
        return
    try:
        from Commissioner.record_registry import validate_soft
        validate_soft(final_data, document_type, collection_title)
    except Exception as e:
        print(f"[WARN] Commissioner validation failed for {collection_title!r}: {e}")
```

- [ ] **Step 3: Run the existing tests to confirm they still pass unmodified**

Run: `pytest Voyageur/tests/test_fs.py -k commissioner -v`
Expected: PASS (same tests, proving the delegation is behavior-neutral)

- [ ] **Step 4: Commit**

```bash
git add Voyageur/FS.py
git commit -m "Delegate FS validate_against_commissioner to shared validate_soft"
```

---

## Task 4: Delegate LAC.py's validate_master_db_against_commissioner to validate_soft

**Files:**
- Modify: `Voyageur/LAC.py:118-127`
- Test: `Voyageur/tests/test_lac.py` (existing tests only — no new tests)

**Interfaces:**
- Consumes: `validate_soft(data: dict, document_type: str, label: str) -> None` from Task 1.
- Produces: no change to `LAC.validate_master_db_against_commissioner(master_data: Dict[str, Any], document_type: str, collection_title: str) -> None`'s signature or external behavior.

- [ ] **Step 1: Run the existing tests as a baseline**

Run: `pytest Voyageur/tests/test_lac.py -k commissioner -v`
Expected: PASS (`test_validate_master_db_against_commissioner_warns_and_does_not_raise`)

- [ ] **Step 2: Replace the internal parse_collection call with validate_soft**

In `Voyageur/LAC.py`, find:

```python
    try:
        from Commissioner.record_registry import parse_collection
        parse_collection(master_data, document_type)
    except Exception as e:
        print(f"[WARN] Commissioner validation failed for {collection_title!r}: {e}")
```

Replace with:

```python
    try:
        from Commissioner.record_registry import validate_soft
        validate_soft(master_data, document_type, collection_title)
    except Exception as e:
        print(f"[WARN] Commissioner validation failed for {collection_title!r}: {e}")
```

- [ ] **Step 3: Run the existing tests to confirm they still pass unmodified**

Run: `pytest Voyageur/tests/test_lac.py -k commissioner -v`
Expected: PASS (same test, proving the delegation is behavior-neutral)

- [ ] **Step 4: Commit**

```bash
git add Voyageur/LAC.py
git commit -m "Delegate LAC validate_master_db_against_commissioner to shared validate_soft"
```

---

## Task 5: Wire validate_soft into Paleographer's save_master_db

**Files:**
- Modify: `Paleographer/Paleographer.py:1422-1425`
- Test: `Paleographer/tests/test_master_db_merge.py`

**Interfaces:**
- Consumes: `validate_soft(data: dict, document_type: str, label: str) -> None` from Task 1. Also consumes module globals already defined earlier in `Paleographer.py`: `TYPE_CFG` (a `parse_type_config(...)` result with a `.name` attribute, `Paleographer/Paleographer.py:1312`), `COLLECTION_TITLE` (`Paleographer/Paleographer.py:1309`), and `MASTER_DB` (`Paleographer/Paleographer.py:1340`).
- Produces: `save_master_db(master_data: Dict[str, Any]) -> None` keeps its exact existing signature; every existing call site (live-extraction loop, batch-job merge loop, quota-exhaustion fallback, batch-job submission) is covered with zero changes to those call sites.

- [ ] **Step 1: Write the failing tests**

Open `Paleographer/tests/test_master_db_merge.py`. Add `import os` to the top imports (currently just `import importlib` / `import sys` / `import pytest`):

```python
import importlib
import os
import sys

import pytest
```

Add these two fixture-building helpers and two tests at the end of the file (after `test_merge_sheets_appends_when_master_sheets_missing`):

```python
def _valid_parish_master_db():
    return {
        "collection_title": "Test Volume",
        "record_type_name": "Parish",
        "sheets": [
            {
                "page_id": "abc123.jpg",
                "document_metadata": {"file_name": "abc123.jpg", "file_type": "jpg"},
                "records": [
                    {
                        "event_type": "Baptism",
                        "participants": [
                            {
                                "role_name": "Primary",
                                "std_given": "Jean",
                                "std_surname": "Gagnon",
                                "sex": "M",
                                "is_priest": False,
                            }
                        ],
                    }
                ],
            }
        ],
    }


def test_save_master_db_valid_shape_writes_file_and_prints_no_warning(minimal_paleographer_env, capsys):
    module = minimal_paleographer_env
    master_data = _valid_parish_master_db()

    module.save_master_db(master_data)

    captured = capsys.readouterr()
    assert "[WARN]" not in captured.out
    assert os.path.exists(module.MASTER_DB)


def test_save_master_db_bad_shape_still_writes_file_and_logs_warning(minimal_paleographer_env, capsys):
    module = minimal_paleographer_env
    master_data = {
        "collection_title": "Bad",
        "record_type_name": "Parish",
        "sheets": [{"records": "not-a-list"}],
    }

    module.save_master_db(master_data)

    captured = capsys.readouterr()
    # The warning label is save_master_db's own COLLECTION_TITLE global (derived from the
    # VOLUME_TITLE env var the minimal_paleographer_env fixture sets to "Test Volume"), not
    # master_data's own "collection_title" key - the two are independent.
    assert "[WARN] Commissioner validation failed for 'Test Volume'" in captured.out
    assert os.path.exists(module.MASTER_DB)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest Paleographer/tests/test_master_db_merge.py -k save_master_db -v`
Expected: FAIL — `test_save_master_db_bad_shape_still_writes_file_and_logs_warning` fails because
no `[WARN]` is printed yet; `test_save_master_db_valid_shape_writes_file_and_prints_no_warning`
may pass by coincidence (nothing to warn about yet) but must be re-checked in Step 4 once the
call actually runs.

- [ ] **Step 3: Implement the wiring**

In `Paleographer/Paleographer.py`, find:

```python
def save_master_db(master_data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(MASTER_DB), exist_ok=True)
    with open(MASTER_DB, "w", encoding="utf-8") as f:
        json.dump(master_data, f, indent=2, ensure_ascii=False)
```

Replace with:

```python
def save_master_db(master_data: Dict[str, Any]) -> None:
    try:
        from Commissioner.record_registry import validate_soft
        validate_soft(master_data, master_data.get("record_type_name", TYPE_CFG.name), COLLECTION_TITLE)
    except Exception as e:
        print(f"[WARN] Commissioner validation failed for {COLLECTION_TITLE!r}: {e}")

    os.makedirs(os.path.dirname(MASTER_DB), exist_ok=True)
    with open(MASTER_DB, "w", encoding="utf-8") as f:
        json.dump(master_data, f, indent=2, ensure_ascii=False)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest Paleographer/tests/test_master_db_merge.py -v`
Expected: PASS (all tests, including the 2 new ones and every pre-existing test in the file)

- [ ] **Step 5: Run the full Paleographer and Commissioner test suites**

Run: `pytest Paleographer/tests Commissioner/tests Voyageur/tests -v`
Expected: PASS (confirms Task 5's change hasn't broken anything Tasks 1-4 already touched)

- [ ] **Step 6: Commit**

```bash
git add Paleographer/Paleographer.py Paleographer/tests/test_master_db_merge.py
git commit -m "Wire save_master_db into Commissioner soft-fail validation via validate_soft"
```

---

## What comes after this plan (not part of it)

- Sub-project 5: cross-script invocation (Paleographer/Voyageur calling into each other's real
  functions when one needs what the other gathers).
- Sub-project 6: reworking Paleographer to consume the Voyageur scaffold as pure analysis, plus
  the broader structural rebuild `Paleographer.py` needs (still four historically separate files
  stitched together behind banner comments).
- Hard-fail/blocking Commissioner validation mode for any of the four now-wired sites, once this
  plan's soft-fail rollout has run against real data and surfaced whatever shape gaps exist.
- Census family-linking and extended-family vocabulary work — unscoped to any currently-planned
  sub-project.
