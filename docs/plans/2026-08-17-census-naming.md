# Census Directory Naming Implementation Plan

> **For AGY:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** Update the Voyageur gathering pipeline to nest Census media dynamically into `{Provider}/{Country}/` and format both the folder and JSON file identically as `{Provider} - {Year} {Country} Census - {County} - {Township} - {ED} - {RM}`.

**Architecture:** We will modify the core JSON filename builder (`build_detailed_census_filename`) in `_gather_helpers.py` to match the exact string format, dynamically extracting the `Provider` abbreviation (e.g., `ANC`, `FS`) and geographic fields. We'll update the image folder resolver (`resolve_census_image_dir`) to prepend the `{Provider}/{Country}` hierarchy. Finally, the main provider scripts (`A.py`, `FS.py`) will pass their respective Provider tags into this logic.

**Tech Stack:** Python (pathlib, regex, dictionary extraction)

---

### Task 1: Update Filename Builder in `_gather_helpers.py`

**Files:**
- Modify: `Voyageur/_gather_helpers.py`
- Test: `Voyageur/tests/test_gather_helpers.py`

**Step 1: Write the failing test**

```python
# In Voyageur/tests/test_gather_helpers.py
def test_build_detailed_census_filename_matches_new_format():
    normalized_data = {
        "sheets": [{
            "records": [{
                "type_specific_fields": {
                    "country": "USA",
                    "county": "Pembina",
                    "city": "Walhalla",
                    "enumeration_district": "34-36",
                    "rural_municipality": "RM of Springfield"
                }
            }]
        }]
    }
    result = gh.build_detailed_census_filename("1950", normalized_data, "FS")
    assert result == "FS - 1950 US Census - Pembina - Walhalla - 34-36 - RM of Springfield.json"
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest Voyageur/tests/test_gather_helpers.py::test_build_detailed_census_filename_matches_new_format -v`
Expected: FAIL (assertion error due to old naming format)

**Step 3: Write minimal implementation**

```python
# In Voyageur/_gather_helpers.py
def build_detailed_census_filename(year: str, normalized_data: dict, provider: str) -> Optional[str]:
    """Builds a '{Provider} - {Year} {Country} Census - {County} - {City} - {ED} - {RM}.json'
    filename matching the specific request."""
    prov_abbr = "ANC" if provider.lower() == "ancestry" else ("FS" if provider.lower() in ("familysearch", "fs") else provider)

    for sheet in normalized_data.get("sheets", []):
        for record in sheet.get("records", []):
            fields = record.get("type_specific_fields", {}) or {}
            parts = []
            
            if prov_abbr:
                parts.append(prov_abbr)
            
            raw_country = fields.get("country", "")
            country_display = "US" if raw_country.upper() == "USA" else raw_country
            
            census_str = f"{year} {country_display} Census" if country_display else f"{year} Census"
            parts.append(census_str.strip())
            
            for key in ["county", "city", "enumeration_district", "rural_municipality", "roll_number", "microfilm_roll"]:
                if fields.get(key):
                    parts.append(fields[key])
            
            if len(parts) > 1:
                safe = " - ".join(parts)
                safe = re.sub(r'[/\\?%*:|"<>]', "-", safe).strip()
                return f"{safe}.json"
    return None
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest Voyageur/tests/test_gather_helpers.py::test_build_detailed_census_filename_matches_new_format -v`
Expected: PASS

**Step 5: Commit**

```bash
git add Voyageur/_gather_helpers.py Voyageur/tests/test_gather_helpers.py
git commit -m "feat: implement detailed census filename builder with provider and country"
```

---

### Task 2: Update Image Dir Resolver in `_gather_helpers.py`

**Files:**
- Modify: `Voyageur/_gather_helpers.py`
- Test: `Voyageur/tests/test_gather_helpers.py`

**Step 1: Write the failing tests**

```python
# In Voyageur/tests/test_gather_helpers.py
def test_resolve_census_image_dir_absolute_base(tmp_path):
    abs_base = tmp_path / "AbsCensus"
    result = gh.resolve_census_image_dir(str(abs_base), "", "FS - 1950 US Census - Ohio", provider="FS", country="USA")
    assert result == abs_base / "FS" / "US" / "FS - 1950 US Census - Ohio"

def test_resolve_census_image_dir_relative_to_media_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_DIR", "Media")
    program_dir = tmp_path / "program"
    result = gh.resolve_census_image_dir("Census", str(program_dir), "ANC - 1950 US Census - Ohio", provider="ANC", country="US")
    assert result == program_dir / "Media" / "Census" / "ANC" / "US" / "ANC - 1950 US Census - Ohio"
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest Voyageur/tests/test_gather_helpers.py -k test_resolve_census_image_dir -v`
Expected: FAIL (TypeError: takes 3 positional arguments but 4/5 were given)

**Step 3: Write minimal implementation**

```python
# In Voyageur/_gather_helpers.py
def resolve_census_image_dir(base_img_setting: str, genealogy_dir: str, folder_name: str, provider: str = "", country: str = "") -> Path:
    if os.path.isabs(base_img_setting):
        base_img_dir = Path(base_img_setting)
    else:
        media_setting = os.getenv("MEDIA_DIR", "Media")
        base_media_dir = Path(media_setting) if os.path.isabs(media_setting) else (
            Path(genealogy_dir) / media_setting if genealogy_dir else Path(media_setting))
        base_img_dir = base_media_dir / base_img_setting
    
    img_target_dir = base_img_dir
    if provider:
        img_target_dir = img_target_dir / provider
    
    country_display = "US" if country.upper() == "USA" else country
    if country_display:
        img_target_dir = img_target_dir / country_display
        
    img_target_dir = img_target_dir / folder_name
    img_target_dir.mkdir(parents=True, exist_ok=True)
    return img_target_dir
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest Voyageur/tests/test_gather_helpers.py -k test_resolve_census_image_dir -v`
Expected: PASS

**Step 5: Commit**

```bash
git add Voyageur/_gather_helpers.py Voyageur/tests/test_gather_helpers.py
git commit -m "feat: resolve census image directory with provider and country nesting"
```

---

### Task 3: Hook up `A.py` and `FS.py` 

**Files:**
- Modify: `Voyageur/A.py`
- Modify: `Voyageur/FS.py`

**Step 1: Write the failing tests**

```bash
# Tests covering the main dispatch logic integration
python -m pytest Voyageur/tests/test_voyageur_dispatcher.py -v
```

**Step 2: Run test to verify it fails**

(Wait until implementation since `A.py` and `FS.py` logic changes might break full integrations if missing kwargs)

**Step 3: Write minimal implementation**

In `A.py` `_recover_orphaned_runs`:
```python
        country = ""
        try:
            with open(recovered_json, "r", encoding="utf-8") as f:
                recovered_data = json.load(f)
            country = next(
                (s.get("records", [{}])[0].get("type_specific_fields", {}).get("country", "")
                 for s in recovered_data.get("sheets", []) if s.get("records")), "")
        except (OSError, json.JSONDecodeError, IndexError, AttributeError):
            pass

        clean_stem = recovered_json.stem
        img_target_dir = resolve_census_image_dir("Census", genealogy_dir, clean_stem, provider="ANC", country=country)
```

In `A.py` `main()`:
```python
    clean_stem = final_json.stem
    img_target_dir = resolve_census_image_dir(base_img_setting, genealogy_dir, clean_stem, provider="ANC", country=country)
```

In `FS.py` `_recover_orphaned_runs`:
```python
        country = next(
            (s.get("records", [{}])[0].get("type_specific_fields", {}).get("country", "")
             for s in final_data.get("sheets", []) if s.get("records")), "")
        clean_stem = recovered_json.stem
        img_target_dir = resolve_census_image_dir("Census", genealogy_dir, clean_stem, provider="FS", country=country)
```

In `FS.py` `main()`:
```python
    country = next(
        (s.get("records", [{}])[0].get("type_specific_fields", {}).get("country", "")
         for s in final_data.get("sheets", []) if s.get("records")), "")
    clean_stem = final_json.stem
    img_target_dir = resolve_census_image_dir(base_img_setting, genealogy_dir, clean_stem, provider="FS", country=country)
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest Voyageur/tests -v`
Expected: PASS

**Step 5: Commit**

```bash
git add Voyageur/A.py Voyageur/FS.py
git commit -m "feat: hook up ancestry and familysearch to new census naming strategy"
```
