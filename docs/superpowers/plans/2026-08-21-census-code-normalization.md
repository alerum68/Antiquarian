# Census Code Normalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decode the real Census Bureau codes FamilySearch's 1950 index carries
alongside (or instead of) its own transcription - Occupation, Industry, Class of
Worker, Education, Race, and Nationality/Birthplace - and prefer the decoded value
over transcribed text whenever a code is present and resolves.

**Architecture:** A new `Commissioner/census_codes.py` module owns loading and
caching the year-specific `census_<year>_codes.json` dictionaries and exposes two
lookup functions. `Archivist/Census.py` surfaces the previously-unused numeric codes
(currently buried in each participant's `type_specific_fields.unmapped`) into new
DataFrame columns, then consumes the decode functions, code-first, in the five
existing fact-building call sites.

**Tech Stack:** Python 3.12+, `pandas` (existing `pd.Series`/`pd.DataFrame` row
shape), `pytest`.

**Spec:** `docs/superpowers/specs/2026-08-21-census-code-normalization-design.md`

## Global Constraints

- Code-first, not code-fallback: when a code is present and decodes, use it over
  transcribed text - text is the fallback for absent/undecodable codes, not the
  other way around.
- The gather-time JSON shape never changes. All decoding happens in
  `Archivist/Census.py` at GEDCOM-build time.
- `decode()` never raises for missing data (unknown year, unknown item, unknown
  code, falsy code) - always returns `None` gracefully.
- `Occupation Category` (`h`/`wk`/`ot`/`u`) is removed from the occupation fallback
  chain entirely - it is a different, undocumented scheme, not decodable via
  `Item_C_Occupation`.
- A literal `"O"` code normalizes to `"0"` before the Education lookup (confirmed:
  both mean "No schooling").
- `decode_birthplace` returns `(place, is_foreign)` - callers must branch on
  `is_foreign`, not on truthiness alone, since a resolved US hit must actively
  suppress a NATI fact.

---

### Task 1: `Commissioner/census_codes.py` - the decode module

**Files:**
- Create: `Commissioner/census_codes.py`
- Test: `Commissioner/tests/test_census_codes.py`

**Interfaces:**
- Produces: `decode(year: int, item: str, code: str) -> Optional[str]`
- Produces: `decode_birthplace(year: int, code: str) -> Tuple[Optional[str], bool]`

Uses the real, already-committed `Commissioner/census_1950_codes.json` as test
fixture data directly - no synthetic fixtures needed, this file is stable, versioned
project data.

- [ ] **Step 1: Write the failing tests**

Create `Commissioner/tests/test_census_codes.py`:

```python
from Commissioner import census_codes


def test_decode_occupation_code():
    assert census_codes.decode(1950, "Item_C_Occupation", "100") == "Farmers (owners and tenants)"


def test_decode_industry_code():
    assert census_codes.decode(1950, "Item_C_Industry", "105") == "Agriculture"


def test_decode_class_of_worker_code():
    assert census_codes.decode(1950, "Item_C_Class_Of_Worker", "3") == "In own business"


def test_decode_education_code():
    assert census_codes.decode(1950, "Education", "S8") == "8th grade"


def test_decode_race_code():
    assert census_codes.decode(1950, "Race", "W") == "White"


def test_decode_returns_none_for_unknown_code():
    assert census_codes.decode(1950, "Item_C_Occupation", "999999") is None


def test_decode_returns_none_for_unknown_item():
    assert census_codes.decode(1950, "NotARealItem", "100") is None


def test_decode_returns_none_for_unknown_year():
    assert census_codes.decode(1899, "Item_C_Occupation", "100") is None


def test_decode_returns_none_for_falsy_code():
    assert census_codes.decode(1950, "Item_C_Occupation", "") is None
    assert census_codes.decode(1950, "Item_C_Occupation", None) is None


def test_decode_birthplace_us_code_resolves_directly():
    place, is_foreign = census_codes.decode_birthplace(1950, "091")
    assert place == "Washington"
    assert is_foreign is False


def test_decode_birthplace_foreign_code_strips_citizenship_prefix():
    place, is_foreign = census_codes.decode_birthplace(1950, "161")
    assert place == "Canada -- English"
    assert is_foreign is True


def test_decode_birthplace_foreign_code_with_unspecified_citizenship_prefix():
    place, is_foreign = census_codes.decode_birthplace(1950, "V39")
    assert place == "Iceland"
    assert is_foreign is True


def test_decode_birthplace_unresolvable_code_returns_none_not_foreign():
    place, is_foreign = census_codes.decode_birthplace(1950, "999")
    assert place is None
    assert is_foreign is False


def test_decode_birthplace_falsy_code():
    place, is_foreign = census_codes.decode_birthplace(1950, "")
    assert place is None
    assert is_foreign is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest Commissioner/tests/test_census_codes.py -v`
Expected: FAIL - `ModuleNotFoundError: No module named 'Commissioner.census_codes'`

- [ ] **Step 3: Write `Commissioner/census_codes.py`**

```python
"""
Decodes the numeric/letter codes the real Census Bureau enumerator recorded (and
FamilySearch's index carries alongside, or instead of, its own transcription) into
readable text, using the year-specific Commissioner/census_<year>_codes.json
dictionaries. Archivist/Census.py is the consumer - decoding happens at
GEDCOM-build time, never at gather time, so the JSON stays a raw capture and a
dictionary fix never requires re-gathering.
"""

import json
import os
from typing import Dict, Optional, Tuple

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
_CODE_CACHE: Dict[int, Dict[str, Dict[str, str]]] = {}


def _load_year_codes(year: int) -> Dict[str, Dict[str, str]]:
    if year not in _CODE_CACHE:
        path = os.path.join(_MODULE_DIR, f"census_{year}_codes.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                _CODE_CACHE[year] = json.load(f)
        except (OSError, json.JSONDecodeError):
            _CODE_CACHE[year] = {}
    return _CODE_CACHE[year]


def decode(year: int, item: str, code: Optional[str]) -> Optional[str]:
    """Looks up `code` under `item` in that year's census code dictionary. Returns
    None if the year has no dictionary file, the item doesn't exist, the code isn't
    found, or `code` is falsy - never raises for missing data."""
    if not code:
        return None
    return _load_year_codes(year).get(item, {}).get(str(code))


def decode_birthplace(year: int, code: Optional[str]) -> Tuple[Optional[str], bool]:
    """1950-style birthplace codes are either a bare Item_B1 (US) code, or a
    1-character Item_B3 citizenship prefix + Item_B2 (foreign) code. Tries the bare
    code against Item_B1 first; if that misses, strips the first character and
    tries the remainder against Item_B2. Returns (place, is_foreign) - (None, False)
    if neither resolves."""
    if not code:
        return None, False
    us_place = decode(year, "Item_B1_Birthplace_US", code)
    if us_place:
        return us_place, False
    if len(code) >= 2:
        foreign_place = decode(year, "Item_B2_Birthplace_Foreign", code[1:])
        if foreign_place:
            return foreign_place, True
    return None, False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest Commissioner/tests/test_census_codes.py -v`
Expected: PASS, all 14 tests

- [ ] **Step 5: Commit**

```bash
git add Commissioner/census_codes.py Commissioner/tests/test_census_codes.py
git commit -m "feat(commissioner): add census_codes decode module"
```

---

### Task 2: Surface the unused code fields into DataFrame columns

**Files:**
- Modify: `Archivist/Census.py:1887-1910` (`build_census_dataframe_from_unified`,
  the per-participant row-building loop)
- Test: `Archivist/tests/test_census_ingestion.py`

**Interfaces:**
- Consumes: nothing new (pure data plumbing)
- Produces: four new possible DataFrame columns per row - `'Occupation Code'`,
  `'Industry Code'`, `'Class of Worker Code'`, `'Birthplace Code'` - populated only
  when the corresponding `unmapped.MISC_CODE_*_<year>_CENSUS` key is present and
  truthy on that participant.

This task only adds columns; it does not change what consumes them yet (Tasks 3-6
do that). Locate the function by name (`grep -n "def build_census_dataframe_from_unified"`)
since this is a large file and other tasks may shift line numbers around it.

- [ ] **Step 1: Write the failing test**

Add to `Archivist/tests/test_census_ingestion.py`:

```python
def test_build_census_dataframe_from_unified_surfaces_unmapped_codes():
    data = {
        "record_type_name": "Census_1950", "sheets": [{
            "page_id": "1", "document_metadata": {},
            "records": [{
                "type_specific_fields": {},
                "participants": [{
                    "std_given": "William", "std_surname": "Vinctson",
                    "type_specific_fields": {
                        "unmapped": {
                            "MISC_CODE_C_1950_CENSUS": "100",
                            "MISC_CODE_C1_1950_CENSUS": "105",
                            "MISC_CODE_C2_1950_CENSUS": "3",
                            "MISC_CODE_B_1950_CENSUS": "161",
                        },
                    },
                }],
            }],
        }],
    }
    df, year_str, _ = arc.build_census_dataframe_from_unified(data)
    assert year_str == "1950"
    row = df.iloc[0]
    assert row['Occupation Code'] == "100"
    assert row['Industry Code'] == "105"
    assert row['Class of Worker Code'] == "3"
    assert row['Birthplace Code'] == "161"


def test_build_census_dataframe_from_unified_omits_code_columns_when_absent():
    data = {
        "record_type_name": "Census_1950", "sheets": [{
            "page_id": "1", "document_metadata": {},
            "records": [{
                "type_specific_fields": {},
                "participants": [{"std_given": "Jane", "std_surname": "Doe",
                                  "type_specific_fields": {}}],
            }],
        }],
    }
    df, _, _ = arc.build_census_dataframe_from_unified(data)
    row = df.iloc[0]
    for col in ('Occupation Code', 'Industry Code', 'Class of Worker Code', 'Birthplace Code'):
        assert col not in df.columns or not row.get(col)
```

(`arc` is this test file's existing alias for the `Census` module - confirm with
`grep -n "^import Census\|as arc" Archivist/tests/test_census_ingestion.py` and match
whatever alias is already in use there.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd Archivist && python -m pytest tests/test_census_ingestion.py -k unmapped_codes -v`
Expected: FAIL - `KeyError` or `AssertionError`, the new columns don't exist yet.

- [ ] **Step 3: Add the column extraction**

In `Archivist/Census.py`, inside `build_census_dataframe_from_unified`'s
participant loop, immediately after the existing `if p.get('race'): row['Race'] = p['race']`
line (currently line 1890) and before the `# Occupation belongs...` comment, insert:

```python
                unmapped = pts.get('unmapped') or {}
                if unmapped.get(f'MISC_CODE_C_{census_year_str}_CENSUS'):
                    row['Occupation Code'] = unmapped[f'MISC_CODE_C_{census_year_str}_CENSUS']
                if unmapped.get(f'MISC_CODE_C1_{census_year_str}_CENSUS'):
                    row['Industry Code'] = unmapped[f'MISC_CODE_C1_{census_year_str}_CENSUS']
                if unmapped.get(f'MISC_CODE_C2_{census_year_str}_CENSUS'):
                    row['Class of Worker Code'] = unmapped[f'MISC_CODE_C2_{census_year_str}_CENSUS']
                if unmapped.get(f'MISC_CODE_B_{census_year_str}_CENSUS'):
                    row['Birthplace Code'] = unmapped[f'MISC_CODE_B_{census_year_str}_CENSUS']
```

`census_year_str` and `pts` are both already in scope at this point in the function
(confirm via the surrounding code you just read - `census_year_str` is computed once
near the top of the function from `record_type_name`, `pts` is the per-participant
`type_specific_fields` dict already used by every neighboring line).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd Archivist && python -m pytest tests/test_census_ingestion.py -k unmapped_codes -v`
Expected: PASS

- [ ] **Step 5: Run the full Census ingestion test module**

Run: `cd Archivist && python -m pytest tests/test_census_ingestion.py -v`
Expected: all pass, no regressions (this change is purely additive).

- [ ] **Step 6: Commit**

```bash
git add Archivist/Census.py Archivist/tests/test_census_ingestion.py
git commit -m "feat(archivist): surface unmapped census codes into DataFrame columns"
```

---

### Task 3: Code-first Occupation, Industry, Class of Worker

**Files:**
- Modify: `Archivist/Census.py:1043-1090` (`get_occupation_value`)
- Test: `Archivist/tests/test_census_ingestion.py`

**Interfaces:**
- Consumes: `Commissioner.census_codes.decode` (Task 1), `row['Occupation Code']` /
  `row['Industry Code']` / `row['Class of Worker Code']` (Task 2)
- Produces: `get_occupation_value(row: pd.Series) -> Tuple[str, str]` - same
  signature, new priority order internally.

`CENSUS_YEAR` is already a module-level global in `Census.py`, readable directly
from this function without a signature change (confirm: `grep -n "^CENSUS_YEAR"
Archivist/Census.py`).

- [ ] **Step 1: Write the failing tests**

Add to `Archivist/tests/test_census_ingestion.py`:

```python
def test_get_occupation_value_prefers_decoded_code_over_existing_text():
    """Code-first, not code-fallback: even when real occupation text is ALSO
    present, the decoded code wins."""
    arc.CENSUS_YEAR = 1950
    row = pd.Series({'Occupation Code': '100', 'Occupation': 'Some Other Job'})
    occ, _ = arc.get_occupation_value(row)
    assert occ == "Farmers (owners and tenants)"


def test_get_occupation_value_falls_back_to_text_when_code_unknown():
    arc.CENSUS_YEAR = 1950
    row = pd.Series({'Occupation Code': '999999', 'Occupation': 'Blacksmith'})
    occ, _ = arc.get_occupation_value(row)
    assert occ == "Blacksmith"


def test_get_occupation_value_falls_back_to_text_when_no_code():
    arc.CENSUS_YEAR = 1950
    row = pd.Series({'Occupation': 'Blacksmith'})
    occ, _ = arc.get_occupation_value(row)
    assert occ == "Blacksmith"


def test_get_occupation_value_drops_occupation_category_entirely():
    """Occupation Category (h/wk/ot/u) is a different, undecodable scheme - it must
    never appear as the occupation value, even as a last resort."""
    arc.CENSUS_YEAR = 1950
    row = pd.Series({'Occupation Category': 'wk'})
    occ, _ = arc.get_occupation_value(row)
    assert occ == ""


def test_get_occupation_value_decodes_industry_code_first():
    arc.CENSUS_YEAR = 1950
    row = pd.Series({'Occupation Code': '100', 'Industry Code': '105'})
    occ, _ = arc.get_occupation_value(row)
    assert "working in Agriculture" in occ


def test_get_occupation_value_decodes_class_of_worker_code_in_notes():
    arc.CENSUS_YEAR = 1950
    row = pd.Series({'Occupation Code': '100', 'Class of Worker Code': '3'})
    _, notes = arc.get_occupation_value(row)
    assert "Class of Worker: In own business" in notes
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd Archivist && python -m pytest tests/test_census_ingestion.py -k get_occupation_value -v`
Expected: FAIL

- [ ] **Step 3: Rewrite `get_occupation_value`**

Replace lines 1043-1090 in `Archivist/Census.py`:

```python
def get_occupation_value(row: pd.Series) -> Tuple[str, str]:
    from Commissioner import census_codes

    # 1. Primary Selection - code-first: a decoded Item_C_Occupation code wins even
    # when real occupation text is also present, per the code-first constraint.
    # capitalize_text_string (not clean_val alone) on every text-sourced fallback -
    # a real census source can hand back ALL-CAPS or lowercase text, and every other
    # proper-noun-like census field in this module already normalizes to Title Case.
    base_occ = census_codes.decode(CENSUS_YEAR, "Item_C_Occupation", row.get('Occupation Code'))
    if not base_occ:
        base_occ = Utils.capitalize_text_string(row.get('Usual Occupation'))
    if not base_occ:
        base_occ = Utils.capitalize_text_string(row.get('Occupation'))
    if not base_occ:
        base_occ = Utils.capitalize_text_string(row.get('Trade or Profession'))

    employer = Utils.capitalize_text_string(row.get('Employer'))
    industry = census_codes.decode(CENSUS_YEAR, "Item_C_Industry", row.get('Industry Code'))
    if not industry:
        industry = Utils.capitalize_text_string(row.get('Industry'))

    # 2. Unemployment Override
    is_unemployed = (Utils.clean_val(row.get('Out Of Work')) == 'Yes' or
                     Utils.clean_val(row.get('Seeking Work')) == 'Yes' or
                     bool(Utils.clean_val(row.get('Weeks Out of Work'))))

    # 3. Concatenation
    occ_str = ""
    if is_unemployed:
        occ_str = "Unemployed"
        if base_occ:
            occ_str += f" from {base_occ}"
    else:
        occ_str = base_occ if base_occ else ""

    if occ_str and employer:
        occ_str += f" at {employer}"
    if occ_str and industry:
        occ_str += f", working in {industry}"

    # 4. Notes
    class_of_worker = census_codes.decode(CENSUS_YEAR, "Item_C_Class_Of_Worker", row.get('Class of Worker Code'))
    if not class_of_worker:
        class_of_worker = Utils.clean_val(row.get('Class of Worker'))

    notes_parts = []
    if class_of_worker:
        notes_parts.append(f"Class of Worker: {class_of_worker}")
    for field in ['Hours Worked', 'Weeks Worked', 'Weeks Out of Work', 'Months Unemployed Past Year']:
        val = Utils.clean_val(row.get(field))
        if val:
            notes_parts.append(f"{field}: {val}")

    notes_str = "; ".join(notes_parts)

    return occ_str, notes_str
```

Note the `'Occupation Category'` fallback line from the original is gone entirely
(Global Constraints), and the notes loop's old `'Class of Worker'` entry is replaced
by the explicit `class_of_worker` decode-or-text variable computed above it, keeping
the same `"Class of Worker: <value>"` note format the old generic loop produced.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd Archivist && python -m pytest tests/test_census_ingestion.py -k get_occupation_value -v`
Expected: PASS

- [ ] **Step 5: Run the full Census ingestion test module**

Run: `cd Archivist && python -m pytest tests/test_census_ingestion.py -v`
Expected: all pass. Investigate any failure referencing `'Occupation Category'`
before assuming it's expected - the Global Constraint drops it deliberately, but
confirm no other test depended on the old behavior in a way this plan didn't
anticipate.

- [ ] **Step 6: Commit**

```bash
git add Archivist/Census.py Archivist/tests/test_census_ingestion.py
git commit -m "feat(archivist): decode Occupation/Industry/Class of Worker codes, code-first"
```

---

### Task 4: Code-first Education

**Files:**
- Modify: `Archivist/Census.py:1093-1099` (`get_education_value`)
- Test: `Archivist/tests/test_census_ingestion.py`

**Interfaces:**
- Consumes: `Commissioner.census_codes.decode` (Task 1)
- Produces: `get_education_value(row: pd.Series) -> Optional[str]` - same signature.

- [ ] **Step 1: Write the failing tests**

Add to `Archivist/tests/test_census_ingestion.py`:

```python
def test_get_education_value_decodes_grade_code():
    arc.CENSUS_YEAR = 1950
    row = pd.Series({'Highest Grade Completed': 'S8'})
    assert arc.get_education_value(row) == "8th grade"


def test_get_education_value_normalizes_letter_o_to_zero_before_decode():
    arc.CENSUS_YEAR = 1950
    row = pd.Series({'Highest Grade Completed': 'O'})
    assert arc.get_education_value(row) == "No schooling"


def test_get_education_value_falls_back_to_raw_code_when_undecodable():
    arc.CENSUS_YEAR = 1950
    row = pd.Series({'Highest Grade Completed': 'ZZ'})
    assert arc.get_education_value(row) == "ZZ"


def test_get_education_value_still_returns_none_when_nothing_present():
    arc.CENSUS_YEAR = 1950
    row = pd.Series({})
    assert arc.get_education_value(row) is None


def test_get_education_value_still_returns_empty_string_for_attended_only():
    arc.CENSUS_YEAR = 1950
    row = pd.Series({'Attended School': 'Yes'})
    assert arc.get_education_value(row) == ''
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd Archivist && python -m pytest tests/test_census_ingestion.py -k get_education_value -v`
Expected: FAIL

- [ ] **Step 3: Rewrite `get_education_value`**

Replace lines 1093-1099 in `Archivist/Census.py`:

```python
def get_education_value(row: pd.Series) -> Optional[str]:
    from Commissioner import census_codes

    grade = Utils.clean_val(row.get('Highest Grade of School Completed', row.get('Highest Grade Completed', '')))
    if grade:
        code = "0" if grade.upper() == "O" else grade
        return census_codes.decode(CENSUS_YEAR, "Education", code) or grade
    if Utils.clean_val(row.get('Attended School')):
        return ''
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd Archivist && python -m pytest tests/test_census_ingestion.py -k get_education_value -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add Archivist/Census.py Archivist/tests/test_census_ingestion.py
git commit -m "feat(archivist): decode Education grade codes, code-first"
```

---

### Task 5: Code-first Race

**Files:**
- Modify: `Archivist/Census.py:1609-1610` (the `1 FACT ... 2 TYPE Race` line inside
  the per-row GEDCOM-building loop)
- Test: `Archivist/tests/test_census_ingestion.py`

**Interfaces:**
- Consumes: `Commissioner.census_codes.decode` (Task 1)

Locate by content (`grep -n '2 TYPE Race' Archivist/Census.py`) since earlier tasks
may shift this line number.

- [ ] **Step 1: Write the failing tests**

This logic lives inline in a large row-building loop rather than its own function
(unlike Occupation/Education), so cover it by extracting the decode step into a
small named helper first, which is also the cleaner implementation - see Step 3.
Add to `Archivist/tests/test_census_ingestion.py`:

```python
def test_get_race_value_decodes_abbreviation():
    arc.CENSUS_YEAR = 1950
    assert arc.get_race_value(pd.Series({'Race': 'W'})) == "White"


def test_get_race_value_passes_through_already_spelled_out_value():
    arc.CENSUS_YEAR = 1950
    assert arc.get_race_value(pd.Series({'Race': 'White'})) == "White"


def test_get_race_value_falls_back_to_color_column():
    arc.CENSUS_YEAR = 1950
    assert arc.get_race_value(pd.Series({'Color': 'W'})) == "White"


def test_get_race_value_empty_when_nothing_present():
    arc.CENSUS_YEAR = 1950
    assert arc.get_race_value(pd.Series({})) == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd Archivist && python -m pytest tests/test_census_ingestion.py -k get_race_value -v`
Expected: FAIL - `AttributeError: module 'Census' has no attribute 'get_race_value'`

- [ ] **Step 3: Extract a `get_race_value` helper and use it at the call site**

Add this new function in `Archivist/Census.py` near `get_education_value` (same
neighborhood of small per-fact value resolvers):

```python
def get_race_value(row: pd.Series) -> str:
    from Commissioner import census_codes

    raw = row.get('Race', row.get('Color', ''))
    decoded = census_codes.decode(CENSUS_YEAR, "Race", raw)
    return decoded or Utils.capitalize_text_string(raw)
```

Then replace the existing inline line (currently):

```python
        if race := Utils.capitalize_text_string(row.get('Race', row.get('Color', ''))):
```

with:

```python
        if race := get_race_value(row):
```

(The rest of that line - `ged.extend([f"1 FACT {race}", ...])` - is unchanged.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd Archivist && python -m pytest tests/test_census_ingestion.py -k get_race_value -v`
Expected: PASS

- [ ] **Step 5: Run the full Census ingestion test module**

Run: `cd Archivist && python -m pytest tests/test_census_ingestion.py -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add Archivist/Census.py Archivist/tests/test_census_ingestion.py
git commit -m "feat(archivist): decode Race codes, code-first"
```

---

### Task 6: Code-first Nationality/Birthplace

**Files:**
- Modify: `Archivist/Census.py:1612-1616` (the `nat_val` block inside the per-row
  GEDCOM-building loop)
- Test: `Archivist/tests/test_census_ingestion.py`

**Interfaces:**
- Consumes: `Commissioner.census_codes.decode_birthplace` (Task 1), `row['Birthplace Code']` (Task 2)

Locate by content (`grep -n 'nat_val = ' Archivist/Census.py`) since earlier tasks
may shift this line number. `birth_place` (used by the existing fallback) is already
computed a few lines above this block in the same loop - confirm with
`grep -n "birth_place = " Archivist/Census.py`.

- [ ] **Step 1: Write the failing tests**

Same situation as Task 5 - extract a small named helper to make this testable in
isolation. Add to `Archivist/tests/test_census_ingestion.py`:

```python
def test_get_nationality_value_uses_decoded_foreign_code():
    arc.CENSUS_YEAR = 1950
    row = pd.Series({'Birthplace Code': 'V39', 'Birth Place': 'Ireland'})
    assert arc.get_nationality_value(row, birth_place='Ireland') == "Iceland"


def test_get_nationality_value_suppresses_for_resolved_us_code():
    """A resolved US code must win over stale Nationality text or a
    foreign-looking birth_place string - the code can rule a value out, not just
    supply one."""
    arc.CENSUS_YEAR = 1950
    row = pd.Series({'Birthplace Code': '091', 'Nationality': 'Norwegian'})
    assert arc.get_nationality_value(row, birth_place='Norway') == ""


def test_get_nationality_value_falls_back_to_text_when_code_unresolved():
    arc.CENSUS_YEAR = 1950
    row = pd.Series({'Birthplace Code': '999999'})
    assert arc.get_nationality_value(row, birth_place='Norway') == "Norway"


def test_get_nationality_value_falls_back_to_text_when_no_code():
    arc.CENSUS_YEAR = 1950
    row = pd.Series({})
    assert arc.get_nationality_value(row, birth_place='Norway') == "Norway"


def test_get_nationality_value_empty_for_us_birthplace_text_no_code():
    arc.CENSUS_YEAR = 1950
    row = pd.Series({})
    assert arc.get_nationality_value(row, birth_place='Ohio') == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd Archivist && python -m pytest tests/test_census_ingestion.py -k get_nationality_value -v`
Expected: FAIL - `AttributeError`

- [ ] **Step 3: Extract a `get_nationality_value` helper and use it at the call site**

Add this new function in `Archivist/Census.py` near `get_race_value`:

```python
def get_nationality_value(row: pd.Series, birth_place: str) -> str:
    from Commissioner import census_codes

    code = row.get('Birthplace Code')
    if code:
        place, is_foreign = census_codes.decode_birthplace(CENSUS_YEAR, code)
        if place is not None:
            return place if is_foreign else ""

    nat_val = Utils.clean_val(row.get('Nationality'))
    if not nat_val and birth_place and is_foreign_birthplace(birth_place):
        nat_val = birth_place
    return nat_val
```

Then replace the existing inline block (currently):

```python
        nat_val = Utils.clean_val(row.get('Nationality'))
        if not nat_val and birth_place and is_foreign_birthplace(birth_place):
            nat_val = birth_place
        if nat_val:
```

with:

```python
        nat_val = get_nationality_value(row, birth_place)
        if nat_val:
```

(The line after - `ged.extend([f"1 NATI {nat_val}", ...])` - is unchanged.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd Archivist && python -m pytest tests/test_census_ingestion.py -k get_nationality_value -v`
Expected: PASS

- [ ] **Step 5: Run the full Census ingestion test module**

Run: `cd Archivist && python -m pytest tests/test_census_ingestion.py -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add Archivist/Census.py Archivist/tests/test_census_ingestion.py
git commit -m "feat(archivist): decode Nationality/Birthplace codes, code-first"
```

---

### Task 7: Full-suite verification and real-output spot-check

**Files:** none modified - verification only.

- [ ] **Step 1: Run the full Archivist and Commissioner suites**

Run: `cd Archivist && python -m pytest tests/ -v` and
`python -m pytest Commissioner/tests/ -v` (from repo root for the second one).
Expected: both fully green, 0 failures.

- [ ] **Step 2: Regenerate the real GEDCOM from the diagnostic gather**

Run: `cd Archivist && python Archivist.py` with `JSON_FILE` unset (auto-selects the
most recent `*.json` in `JSON_DIR`) - confirm
`JSON/Census-1950-USA-North Dakota-Pembina-Advance-34-1-FS.json` is the only/most
recent file there, or set `JSON_FILE` explicitly to it.

- [ ] **Step 3: Hand-inspect the regenerated output**

Search the output `.ged` file for the Stullangson household (search for
`Stullangson`) and confirm the `1 NATI` line now reads `Iceland`, not `Ireland`.
Search for the farmer household this plan traced throughout (Occupation Code
`100`/Industry Code `105`/Class of Worker Code `3`) and confirm `1 OCCU Farmers
(owners and tenants) at ..., working in Agriculture` (or the equivalent shape given
whatever Employer value that record has) and a `Class of Worker: In own business`
note.

- [ ] **Step 4: Report to the user**

This step is on the user, not the implementer - report the regenerated file's path
and the spot-check results from Step 3, and note that broader verification (spot
checks across more of the 339 individuals, and eventually real RootsMagic import)
is the user's to do, not something this plan's automated steps can confirm.

## Self-Review Notes

- **Spec coverage:** Spec Section 3.1 (`census_codes.py`) → Task 1. Section 3.2
  (DataFrame column surfacing) → Task 2. Section 3.3's five fact-builder bullets →
  Tasks 3 (Occupation/Industry/Class of Worker), 4 (Education), 5 (Race), 6
  (Nationality). Section 4 (Verification) → Task 7 plus the per-task test steps
  throughout.
- **Placeholder scan:** no TBD/TODO; every code step has complete, real code.
- **Type consistency:** `census_codes.decode`/`decode_birthplace` signatures
  identical everywhere they're called (Tasks 3-6). `get_race_value`/
  `get_nationality_value` (new helper functions introduced in Tasks 5-6 purely to
  make inline loop logic testable) have consistent, matching signatures between
  where they're defined and where the plan's own test code calls them.
