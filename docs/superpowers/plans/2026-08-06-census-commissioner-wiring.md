# Wire Voyageur's Census Gather to Commissioner Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `Commissioner.record_registry.parse_collection()` run against every real Census gather (Ancestry and FamilySearch), with an open, unenumerated role vocabulary for non-family roles and a validated `unmapped` catch-all field, without ever blocking or corrupting a gather run.

**Architecture:** `Commissioner/record_registry.py` gains a generic, opt-in `role_validation` mode (`"closed"`/`"open"`, default `"closed"`) declared per `.pmt` file, plus a `"dict"` primitive field type. `Census.pmt` sets `role_validation: open` and shrinks its declared roles to the 9 names with real Archivist family-linking semantics; `Parish.pmt`/`Scrip.pmt` declare `role_validation: closed` explicitly (behavior-neutral). `Voyageur/census_schema.py` gains a `validate_against_commissioner()` helper that both `A.py` and `FS.py` call, immediately after `normalize_census_pages()`, catching and logging any Commissioner exception rather than propagating it.

**Tech Stack:** Python, pydantic (Commissioner's validation models), pytest.

## Global Constraints

- New front-matter key `role_validation` accepts exactly `"closed"` or `"open"`; absent key defaults to `"closed"` in code, but every `.pmt` file that exists today (`Parish.pmt`, `Scrip.pmt`, `Census.pmt`) must declare it explicitly — no file relies on the implicit default.
- `Census.pmt`'s `roles` front matter is restricted to exactly these 9 names (matching Archivist's `FAMILY_SEMANTICS` vocabulary): `Head`, `Wife`, `Husband`, `Son`, `Daughter`, `Father`, `Mother`, `Father-In-Law`, `Mother-In-Law`.
- `_PRIMITIVE_TYPE_MAP` gains `"dict"` mapped to `Dict[str, Any]`. `Census.pmt` declares `unmapped: {type: dict}` under `extra_fields.participant`.
- Commissioner validation at the Voyageur call sites is soft-fail only: any exception from `parse_collection()` is caught, logged via `print(f"[WARN] ...")` (matching `A.py`/`FS.py`'s existing print-based logging convention — neither file uses the `logging` module), and the gather's output is written to disk exactly as it would be without validation. No exception from Commissioner validation may ever propagate out of the Census gather path.
- No changes to `Commissioner/models.py`, `Commissioner/fact_registry.py`, or `Voyageur/Voyageur.py` (confirmed dead code — not imported or invoked anywhere).
- Cross-package imports (`Commissioner` from `Voyageur/census_schema.py`) follow the existing repo-root `sys.path` bootstrap precedent already used in `Paleographer/Paleographer.py:47-53` and `Paleographer/engine.py:34-38`.

---

### Task 1: Add open/closed role-validation mode and a `dict` field type to Commissioner's record registry

**Files:**
- Modify: `Commissioner/record_registry.py`
- Test: `Commissioner/tests/test_record_registry.py`

**Interfaces:**
- Consumes: nothing new — extends `_DocumentTypeSchema`, `_build_registry()`, `validate_role_name()`, `_PRIMITIVE_TYPE_MAP`, all already defined in this file.
- Produces: `_DocumentTypeSchema.role_validation_mode: str` (`"closed"` or `"open"`), read from front matter key `role_validation`. `validate_role_name(document_type, role_name)` becomes a no-op (never raises `InvalidRoleError`) when the resolved document type's mode is `"open"`. `_PRIMITIVE_TYPE_MAP["dict"]` resolves to `Dict[str, Any]`, usable as a field `type:` token in any `.pmt` file's `extra_fields`. These are consumed by Task 2 (Census.pmt/Parish.pmt/Scrip.pmt front matter) and Task 3 (indirectly, since Census's `unmapped` field depends on the `dict` type existing).

-x[ ] **Step 1: Write failing tests for the new mechanism**

Add to `Commissioner/tests/test_record_registry.py`, after the existing `test_build_registry_accepts_a_valid_fixture_dir` function (currently ending at line 152) and before the `import pytest` / `from pydantic import ValidationError` block that starts the `parse_collection` tests (currently line 155):

```python
import Commissioner.record_registry as record_registry


OPEN_ROLE_PMT = """---
roles:
  "1": {name: "Head", semantic: primary}
role_validation: open
extra_fields:
  participant:
    - {name: notes, type: dict}
---
Fixture prompt body.
"""


def test_open_role_validation_mode_is_read_from_front_matter(tmp_path):
    (tmp_path / "OpenFixture.pmt").write_text(OPEN_ROLE_PMT, encoding="utf-8")
    registry = _build_registry(tmp_path)
    assert registry["OpenFixture"].role_validation_mode == "open"


def test_closed_is_the_default_role_validation_mode_when_key_absent(tmp_path):
    (tmp_path / "Fixture.pmt").write_text(
        UNKNOWN_TYPE_PMT.replace("type: nonsense", "type: string"), encoding="utf-8"
    )
    registry = _build_registry(tmp_path)
    assert registry["Fixture"].role_validation_mode == "closed"


def test_validate_role_name_is_a_noop_for_open_mode_document_types(tmp_path, monkeypatch):
    (tmp_path / "OpenFixture.pmt").write_text(OPEN_ROLE_PMT, encoding="utf-8")
    fixture_registry = _build_registry(tmp_path)
    monkeypatch.setattr(record_registry, "_REGISTRY", fixture_registry)

    validate_role_name("OpenFixture", "TotallyUnknownRole")
    validate_role_name("OpenFixture", "Head")


def test_validate_role_name_still_rejects_unknown_role_for_closed_mode_document_types(
    tmp_path, monkeypatch
):
    (tmp_path / "Fixture.pmt").write_text(
        UNKNOWN_TYPE_PMT.replace("type: nonsense", "type: string"), encoding="utf-8"
    )
    fixture_registry = _build_registry(tmp_path)
    monkeypatch.setattr(record_registry, "_REGISTRY", fixture_registry)

    with pytest.raises(InvalidRoleError, match="Coordinator"):
        validate_role_name("Fixture", "Coordinator")


def test_dict_field_type_accepts_a_nested_dict_value(tmp_path):
    (tmp_path / "OpenFixture.pmt").write_text(OPEN_ROLE_PMT, encoding="utf-8")
    registry = _build_registry(tmp_path)
    extra = registry["OpenFixture"].participant_extra_model(
        notes={"Race": "W", "Column_9": "Yes"}
    )
    assert extra.notes == {"Race": "W", "Column_9": "Yes"}
```

Note: `UNKNOWN_TYPE_PMT` and `_build_registry`/`InvalidRoleError`/`validate_role_name`/`pytest` are already defined/imported earlier in this file — do not re-import or redefine them.

-x[ ] **Step 2: Run the new tests to verify they fail**

Run: `pytest Commissioner/tests/test_record_registry.py -v -k "open_role_validation or closed_is_the_default or noop_for_open_mode or still_rejects_unknown_role_for_closed or dict_field_type"`
Expected: FAIL — `AttributeError: 'OpenFixture' has no attribute 'role_validation_mode'` (or similar) for the first three; the `dict` field type test fails with `UnknownFieldTypeError: ... unrecognized field type 'dict'`.

-x[ ] **Step 3: Implement `role_validation_mode` on `_DocumentTypeSchema`**

In `Commissioner/record_registry.py`, modify the `_DocumentTypeSchema.__init__` (currently lines 32-40):

```python
class _DocumentTypeSchema:
    def __init__(
        self,
        record_extra_model: Type[BaseModel],
        participant_extra_model: Type[BaseModel],
        valid_roles: FrozenSet[str],
        role_validation_mode: str,
    ):
        self.record_extra_model = record_extra_model
        self.participant_extra_model = participant_extra_model
        self.valid_roles = valid_roles
        self.role_validation_mode = role_validation_mode
```

-x[ ] **Step 4: Pass the mode through `_build_registry()`**

Modify `_build_registry()` (currently lines 75-94): after the existing `valid_roles = frozenset(role["name"] for role in roles.values())` line (currently line 91), add:

```python
        role_validation_mode = front_matter.get("role_validation", "closed")
```

Then update the `_DocumentTypeSchema(...)` construction (currently line 93) to pass it through:

```python
        registry[document_type] = _DocumentTypeSchema(
            record_extra_model, participant_extra_model, valid_roles, role_validation_mode
        )
```

-x[ ] **Step 5: Make `validate_role_name()` a no-op in open mode**

Replace `validate_role_name()` (currently lines 125-133):

```python
def validate_role_name(document_type: str, role_name: Optional[str]) -> None:
    if role_name is None:
        return
    schema = _get_schema(document_type)
    if schema.role_validation_mode == "open":
        return
    if role_name not in schema.valid_roles:
        raise InvalidRoleError(
            f"{role_name!r} is not a valid role for document_type {document_type!r} "
            f"(valid roles: {sorted(schema.valid_roles)})"
        )
```

-x[ ] **Step 6: Add the `dict` primitive type**

Modify `_PRIMITIVE_TYPE_MAP` (currently lines 10-16):

```python
_PRIMITIVE_TYPE_MAP: Dict[str, Any] = {
    "string": str,
    "int": int,
    "float": float,
    "bool": bool,
    "date": date,
    "dict": Dict[str, Any],
}
```

(`Any` and `Dict` are already imported at the top of the file — no new imports needed.)

-x[ ] **Step 7: Run the new tests to verify they pass, then the full Commissioner suite**

Run: `pytest Commissioner/tests/test_record_registry.py -v`
Expected: all tests pass, including the 5 new ones and every pre-existing test in the file (Parish/Scrip/Census tests are unaffected — none of their `.pmt` files have a `role_validation` key yet, so they still resolve to `"closed"`, identical to today's behavior).

Run: `pytest Commissioner/ -v`
Expected: full Commissioner suite passes.

-x[ ] **Step 8: Commit**

```bash
git add Commissioner/record_registry.py Commissioner/tests/test_record_registry.py
git commit -m "Add opt-in open role-validation mode and dict field type to record_registry"
```

---

### Task 2: Apply open role validation to Census.pmt and declare the mode explicitly on every .pmt file

**Files:**
- Modify: `Paleographer/prompts/Census.pmt`
- Modify: `Paleographer/prompts/Parish.pmt`
- Modify: `Paleographer/prompts/Scrip.pmt`
- Modify: `Commissioner/tests/test_record_registry.py`

**Interfaces:**
- Consumes: `role_validation_mode`/`"dict"` type from Task 1 (must be complete first — this task's tests exercise real `.pmt` files through the mechanism Task 1 built).
- Produces: `Census` document type now resolves to `role_validation_mode == "open"` with a 9-name `valid_roles` set and a `dict`-typed `unmapped` participant field, consumed by Task 3's `A.py`/`FS.py` wiring (which relies on Census accepting any `role_name` and any `unmapped` shape `normalize_census_pages()` produces).

-x[ ] **Step 1: Update the two now-stale Census tests and add coverage for the new behavior**

In `Commissioner/tests/test_record_registry.py`, replace `test_census_roles_cover_standard_household_relationships` (currently lines 96-102):

```python
def test_census_roles_are_restricted_to_family_relationships():
    roles = get_valid_roles("Census")
    assert roles == {
        "Head", "Wife", "Husband", "Son", "Daughter",
        "Father", "Mother", "Father-In-Law", "Mother-In-Law",
    }


def test_census_role_validation_is_open():
    validate_role_name("Census", "Boarder")
    validate_role_name("Census", "Roomer")
    validate_role_name("Census", "Coordinator")
```

Replace `test_parse_collection_rejects_invalid_role_for_census` (currently lines 413-434) — Census no longer rejects any role, so this becomes a positive test:

```python
def test_parse_collection_accepts_any_role_for_census():
    payload = {
        **SAMPLE_CENSUS_PAYLOAD,
        "sheets": [
            {
                **SAMPLE_CENSUS_PAYLOAD["sheets"][0],
                "records": [
                    {
                        **SAMPLE_CENSUS_PAYLOAD["sheets"][0]["records"][0],
                        "participants": [
                            {
                                **SAMPLE_CENSUS_PAYLOAD["sheets"][0]["records"][0]["participants"][0],
                                "role_name": "Boarder",
                            }
                        ],
                    }
                ],
            }
        ],
    }
    collection = parse_collection(payload, document_type="Census")
    assert collection.sheets[0].records[0].participants[0].role_name == "Boarder"


def test_parse_collection_validates_census_unmapped_dict_field():
    payload = {
        **SAMPLE_CENSUS_PAYLOAD,
        "sheets": [
            {
                **SAMPLE_CENSUS_PAYLOAD["sheets"][0],
                "records": [
                    {
                        **SAMPLE_CENSUS_PAYLOAD["sheets"][0]["records"][0],
                        "participants": [
                            {
                                **SAMPLE_CENSUS_PAYLOAD["sheets"][0]["records"][0]["participants"][0],
                                "type_specific_fields": {
                                    "line_number": "17",
                                    "pid": "MXHY-ABC",
                                    "unmapped": {"Race": "W", "Column_9": "Yes"},
                                },
                            }
                        ],
                    }
                ],
            }
        ],
    }
    collection = parse_collection(payload, document_type="Census")
    participant = collection.sheets[0].records[0].participants[0]
    assert participant.type_specific_fields["unmapped"] == {"Race": "W", "Column_9": "Yes"}
```

-x[ ] **Step 2: Run the updated/new tests to verify they fail**

Run: `pytest Commissioner/tests/test_record_registry.py -v -k "census"`
Expected: FAIL — `test_census_roles_are_restricted_to_family_relationships` fails because `Census.pmt` still declares all 20 original roles; `test_census_role_validation_is_open` fails with `InvalidRoleError` (mode still closed); `test_parse_collection_accepts_any_role_for_census` fails with `InvalidRoleError`; `test_parse_collection_validates_census_unmapped_dict_field` fails with a `ValidationError` (`unmapped` not declared).

-x[ ] **Step 3: Rewrite Census.pmt's front matter**

Replace `Paleographer/prompts/Census.pmt` lines 1-44 (the entire front-matter block) with:

```
---
roles:
  "1": {name: "Head", semantic: primary, context: "The householder on whose row the family/dwelling entry begins; the person to whom every other household member's relationship is recorded."}
  "2": {name: "Wife", semantic: spouse}
  "3": {name: "Husband", semantic: spouse}
  "4": {name: "Son", semantic: child}
  "5": {name: "Daughter", semantic: child}
  "6": {name: "Father", semantic: father}
  "7": {name: "Mother", semantic: mother}
  "8": {name: "Father-In-Law", semantic: father_in_law}
  "9": {name: "Mother-In-Law", semantic: mother_in_law}
role_validation: open
defaults:
  record:
    event_type: "Census (family)"
extra_fields:
  record:
    - {name: family_number, type: string}
    - {name: enumeration_district, type: string}
    - {name: roll_number, type: string}
    - {name: film_number, type: string}
    - {name: state, type: string}
    - {name: county, type: string}
    - {name: city, type: string}
    - {name: country, type: string}
    - {name: apid_db, type: string}
  participant:
    - {name: line_number, type: string}
    - {name: pid, type: string}
    - {name: extracted_url, type: string}
    - {name: fsftid, type: string}
    - {name: person_ark, type: string}
    - {name: familysearch_url, type: string}
    - {name: unmapped, type: dict}
---
```

-x[ ] **Step 4: Update Census.pmt's prose to match the open vocabulary**

The prose body (after the front matter) still describes the old closed-list-plus-"Other" fallback. Replace this paragraph (currently lines 73-75):

```
- Relationship to head: use the role vocabulary declared above. If the image
  shows a relationship term not on that list, use "Other" and record the literal
  term in that participant's type_specific_fields so a human can review it.
```

with:

```
- Relationship to head: if the image shows one of the family relationships
  declared above (Head, Wife, Husband, Son, Daughter, Father, Mother,
  Father-In-Law, Mother-In-Law), use that exact term. For any other household
  relationship the image shows (Boarder, Servant, Roomer, Lodger, Grandson,
  Aunt, Cousin, or anything else) record the term exactly as it appears on the
  image - it is not restricted to a fixed list, and is used for association
  only, not family-tree linking.
```

-x[ ] **Step 5: Add `role_validation: closed` to Parish.pmt and Scrip.pmt**

In `Paleographer/prompts/Parish.pmt`, insert a new line directly after the last `roles` entry (currently line 12, `"0": {name: "Other", ...}`) and before `defaults:` (currently line 13):

```yaml
role_validation: closed
```

In `Paleographer/prompts/Scrip.pmt`, insert the same line directly after the last `roles` entry (currently line 11, `"0": {name: "Other", ...}`) and before `defaults:` (currently line 12):

```yaml
role_validation: closed
```

-x[ ] **Step 6: Run the tests to verify they pass, then the full Commissioner suite**

Run: `pytest Commissioner/tests/test_record_registry.py -v`
Expected: all tests pass, including every pre-existing Parish/Scrip test (now with an explicit `role_validation: closed` — behavior-neutral, so no assertions change).

Run: `pytest Commissioner/ -v`
Expected: full Commissioner suite passes.

-x[ ] **Step 7: Commit**

```bash
git add Paleographer/prompts/Census.pmt Paleographer/prompts/Parish.pmt Paleographer/prompts/Scrip.pmt Commissioner/tests/test_record_registry.py
git commit -m "Give Census an open role vocabulary restricted to 9 family relationships; declare role_validation explicitly on every .pmt file"
```

---

### Task 3: Wire Commissioner validation into Voyageur's Census gather path

**Files:**
- Modify: `Voyageur/census_schema.py`
- Modify: `Voyageur/A.py`
- Modify: `Voyageur/FS.py`
- Test: `Voyageur/tests/test_census_schema.py`

**Interfaces:**
- Consumes: `Commissioner.record_registry.parse_collection(raw_json: dict, document_type: str) -> Collection` (existing signature, unchanged). Relies on Task 2's Census.pmt changes being in place (open role validation, `unmapped` declared as `dict`) — without Task 2, real gather output would trip `[WARN]` logs constantly.
- Produces: `census_schema.validate_against_commissioner(normalized: dict, collection_title: str) -> None` — never raises; logs via `print(f"[WARN] ...")` on any Commissioner exception. Called from `A.py` and `FS.py` immediately after `normalize_census_pages()`.

-x[ ] **Step 1: Write failing tests for the new helper**

Add to `Voyageur/tests/test_census_schema.py`, after the existing `_page()` helper (currently lines 5-13):

```python
def test_validate_against_commissioner_accepts_valid_normalized_output(capsys):
    raw = {
        "census_year": "1900", "location": "Minnesota",
        "pages": [_page([
            {"columns": {"Given Name": "Jean", "Surname": "Gagnon", "Gender": "M", "Age": "40",
                        "Relationship to Head": "Head", "Family Number": "5"}, "pid": "p1"},
        ])],
    }
    doc = census_schema.normalize_census_pages(raw, "ancestry_census", "1900 US Census", "Census_1900")

    census_schema.validate_against_commissioner(doc, "1900 US Census")

    captured = capsys.readouterr()
    assert "[WARN]" not in captured.out


def test_validate_against_commissioner_logs_and_does_not_raise_on_bad_shape(capsys):
    bad_doc = {"collection_title": "Bad Collection", "sheets": [{"records": "not-a-list"}]}

    census_schema.validate_against_commissioner(bad_doc, "Bad Collection")

    captured = capsys.readouterr()
    assert "[WARN]" in captured.out
    assert "Bad Collection" in captured.out
```

-x[ ] **Step 2: Run the new tests to verify they fail**

Run: `pytest Voyageur/tests/test_census_schema.py -v -k "validate_against_commissioner"`
Expected: FAIL — `AttributeError: module 'census_schema' has no attribute 'validate_against_commissioner'`.

-x[ ] **Step 3: Add the Commissioner import bootstrap and the helper function to `census_schema.py`**

Add `import sys` to the existing import block (currently lines 21-25):

```python
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from titlecase import titlecase
import yaml
```

Immediately after that import block, add:

```python
# Commissioner lives in a sibling tool folder, not an installed package - add the repo
# root to sys.path so it can be imported by absolute path, matching Paleographer.py's own
# precedent for cross-package imports (Paleographer/Paleographer.py:47-53).
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from Commissioner.record_registry import parse_collection  # noqa: E402
```

At the end of the file, after `normalize_census_pages()` (currently ending at line 272 with `return {...}`), add:

```python


def validate_against_commissioner(normalized: dict, collection_title: str) -> None:
    """Runs a normalize_census_pages() result through Commissioner's schema validation as
    a visibility check, never a gate: a failure is logged and swallowed here so a
    Commissioner-side gap can never block a real gather or corrupt its output. This is
    Commissioner validation's first production call site - see the sub-project 2 design
    spec (docs/superpowers/specs/2026-08-06-census-commissioner-wiring-design.md)."""
    try:
        parse_collection(normalized, "Census")
    except Exception as e:
        print(f"[WARN] Commissioner validation failed for {collection_title!r}: {e}")
```

-x[ ] **Step 4: Run the new tests to verify they pass, then the full census_schema test file**

Run: `pytest Voyageur/tests/test_census_schema.py -v`
Expected: all tests pass, including the 2 new ones and every pre-existing normalization test (unaffected — `normalize_census_pages()` itself is unchanged).

-x[ ] **Step 5: Call the helper from `A.py`'s Census gather path**

In `Voyageur/A.py`, modify the block around the existing `normalize_census_pages()` call (currently lines 163-166):

```python
    normalized = census_schema.normalize_census_pages(
        raw_gather, "ancestry_census", collection_title, f"Census_{census_year_raw}")
    census_schema.validate_against_commissioner(normalized, collection_title)
    with open(final_json, "w", encoding="utf-8") as f:
        json.dump(normalized, f, indent=2, ensure_ascii=False)
```

-x[ ] **Step 6: Call the helper from `FS.py`'s Census gather path**

In `Voyageur/FS.py`, modify the block around the existing `normalize_census_pages()` call (currently lines 898-901):

```python
        final_data = census_schema.normalize_census_pages(
            raw_census, "familysearch_census", collection_title,
            f"Census_{raw_census.get('census_year', '')}")
        census_schema.validate_against_commissioner(final_data, collection_title)
        clean_name = build_clean_census_filename(raw_census.get("census_year", ""), final_data)
```

-x[ ] **Step 7: Run the full Voyageur and Commissioner test suites**

Run: `pytest Voyageur/ -v`
Expected: all tests pass, including `test_fs.py` and `test_census_schema.py` (no test in either file calls `A.py`'s or `FS.py`'s top-level gather functions directly, so the new one-line call sites don't require new mocks — confirm this holds; if a test does exercise the full gather path, it must still pass since `validate_against_commissioner()` never raises).

Run: `pytest Commissioner/ -v`
Expected: full Commissioner suite still passes (unaffected by Voyageur changes).

-x[ ] **Step 8: Commit**

```bash
git add Voyageur/census_schema.py Voyageur/A.py Voyageur/FS.py Voyageur/tests/test_census_schema.py
git commit -m "Wire Commissioner validation into Voyageur's Ancestry and FamilySearch Census gather paths"
```
