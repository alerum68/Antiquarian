# Complex Field Integration Implementation Plan

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** Implement complex mapping rules for advanced census fields (Income, dynamic Occupation, 1935 Residence) across Ancestry and FamilySearch pipelines, without structural `Commissioner` changes.

**Architecture:** We will map generic data (Income, Property, Nationality) directly via `ancestry_census.yaml` and `familysearch_census.yaml`. For the dynamic Occupation sentence and Foreign Birthplace logic, we will modify `Archivist/Census.py` to construct facts dynamically during GEDCOM assembly.

**Tech Stack:** Python, pytest, YAML.

---

### Task 1: Unified Standard Mappings (Voyageur)

**Files:**
- Modify: `Voyageur/field_maps/ancestry_census.yaml`
- Modify: `Voyageur/field_maps/familysearch_census.yaml`
- Modify: `Voyageur/tests/test_census_schema.py`

**Step 1: Write the failing test**

```python
# In Voyageur/tests/test_census_schema.py
def test_complex_field_integration_standard_mappings():
    raw = {
        "census_year": "1940", "location": "USA",
        "pages": [{"columns": {
            "Income": "500",
            "Tribe": "Cherokee",
            "EducationCost": "50",
            "CauseOfDeath": "Fever",
            "CannotRead1": "Yes"
        }, "pid": "p1"}]
    }
    doc = census_schema.normalize_census_pages(raw, "ancestry_census", "1940 Census", "C1940")
    facts = doc.sheets[0].records[0].participants[0].facts
    fact_types = [f.fact_type for f in facts]
    
    assert "Property" in fact_types
    assert "Nationality" in fact_types
    assert "Education" in fact_types
    assert "Death" in fact_types
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest Voyageur/tests/test_census_schema.py::test_complex_field_integration_standard_mappings -v`
Expected: FAIL (assertion error on facts)

**Step 3: Write minimal implementation**

Add the following to `participant_facts` in both `ancestry_census.yaml` and `familysearch_census.yaml`:
```yaml
  # Complex Field Integration Mappings
  "Income": Property
  "IncomeOtherSources": Property
  "InsuranceCost": Property
  "LifeInsuranceCost": Property
  "MonthlyRental": Property
  "AmountOfLand": Property
  "NumberOfHorses": Property
  "ValueOfLivestock": Property
  "Tribe": Nationality
  "Clan": Nationality
  "IndianBlood": Nationality
  "EducationCost": Education
  "CauseOfDeath": Death
  "Widowed1": Marital Status
  "CannotRead1": Education
  "ResidenceCityInNineteenThirtyFive": Residence
  "VesselVisitedNumber": Residence
  "ShantyVisitedNumber": Residence
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest Voyageur/tests/test_census_schema.py::test_complex_field_integration_standard_mappings -v`
Expected: PASS

**Step 5: Commit**

```bash
git add Voyageur/field_maps Voyageur/tests
git commit -m "feat(voyageur): map complex fields to standard facts in YAML schemas"
```

### Task 2: Dynamic Occupation Template (Archivist)

**Files:**
- Modify: `Archivist/Census.py`
- Modify: `Archivist/tests/test_census_ingestion.py`

**Step 1: Write the failing test**

```python
# In Archivist/tests/test_census_ingestion.py
def test_dynamic_occupation_template():
    from Archivist.Census import get_occupation_value
    import pandas as pd
    
    # Test Employed
    row1 = pd.Series({
        "Occupation": "Farmer", 
        "Employer": "Smith Farm", 
        "Industry": "Agriculture",
        "Class of Worker": "W",
        "Hours Worked": "40"
    })
    occ1, notes1 = get_occupation_value(row1)
    assert occ1 == "Farmer at Smith Farm, working in Agriculture"
    assert "Class of Worker: W" in notes1
    assert "Hours Worked: 40" in notes1

    # Test Unemployed override
    row2 = pd.Series({
        "Occupation": "Clerk", 
        "Employer": "Bank", 
        "Out Of Work": "Yes"
    })
    occ2, notes2 = get_occupation_value(row2)
    assert occ2 == "Unemployed from Clerk at Bank"
    
    # Test Usual Occupation priority
    row3 = pd.Series({
        "Occupation": "Laborer",
        "Usual Occupation": "Carpenter"
    })
    occ3, notes3 = get_occupation_value(row3)
    assert occ3 == "Carpenter"
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest Archivist/tests/test_census_ingestion.py::test_dynamic_occupation_template -v`
Expected: FAIL (get_occupation_value currently only returns a string, not a tuple, and doesn't build the sentence).

**Step 3: Write minimal implementation**

Modify `Archivist/Census.py`:
Change `get_occupation_value` to return `(str, str)` (occupation_string, notes_string).
```python
def get_occupation_value(row: pd.Series) -> tuple[str, str]:
    from Archivist.Utils import Utils
    
    # 1. Primary Selection
    base_occ = Utils.clean_val(row.get('Usual Occupation'))
    if not base_occ:
        base_occ = Utils.clean_val(row.get('Occupation'))
    if not base_occ:
        base_occ = Utils.clean_val(row.get('Occupation Category'))
    if not base_occ:
        base_occ = Utils.clean_val(row.get('Trade or Profession'))
        
    employer = Utils.clean_val(row.get('Employer'))
    industry = Utils.clean_val(row.get('Industry'))
    
    # 2. Unemployment Override
    is_unemployed = Utils.clean_val(row.get('Out Of Work')) == 'Yes' or Utils.clean_val(row.get('Seeking Work')) == 'Yes'
    
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
    notes_parts = []
    for field in ['Class of Worker', 'Hours Worked', 'Weeks Worked', 'Months Unemployed Past Year']:
        val = Utils.clean_val(row.get(field))
        if val:
            notes_parts.append(f"{field}: {val}")
            
    notes_str = "; ".join(notes_parts)
    
    return occ_str, notes_str
```
Update all callers of `get_occupation_value` in `Archivist/Census.py` to handle the tuple return and map the notes to the generated `Occupation` fact.

**Step 4: Run test to verify it passes**

Run: `python -m pytest Archivist/tests/test_census_ingestion.py::test_dynamic_occupation_template -v`
Expected: PASS

**Step 5: Commit**

```bash
git add Archivist/Census.py Archivist/tests/test_census_ingestion.py
git commit -m "feat(archivist): implement dynamic occupation sentence template and notes"
```

### Task 3: Foreign Birthplace as Nationality (Archivist)

**Files:**
- Modify: `Archivist/Census.py`
- Modify: `Archivist/tests/test_census_ingestion.py`

**Step 1: Write the failing test**

```python
# In Archivist/tests/test_census_ingestion.py
def test_foreign_birthplace_as_nationality():
    # Write a test that passes a row with Birthplace='Ireland' and no Nationality
    # Ensure a Nationality fact is produced.
    pass
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest Archivist/tests/test_census_ingestion.py::test_foreign_birthplace_as_nationality -v`

**Step 3: Write minimal implementation**

In `Archivist/Census.py`, where facts are extracted, if `row['Birthplace']` is a known foreign country (or simply not matching state abbreviations) and `row['Nationality']` is empty, emit a `Nationality` fact.

**Step 4: Run test to verify it passes**

Run: `python -m pytest Archivist/tests/test_census_ingestion.py::test_foreign_birthplace_as_nationality -v`

**Step 5: Commit**

```bash
git add Archivist/Census.py Archivist/tests/test_census_ingestion.py
git commit -m "feat(archivist): map foreign birthplace to nationality if empty"
```
