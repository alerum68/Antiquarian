# Media Directory Restructure Implementation Plan

> **For AGY:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** Reformat the Census media directory structure to follow the exact `Media\Census\Country\Year\State\County\City\` pattern, strip the `3_1_3` prefix from downloaded FamilySearch ARKs, and change the default image save behavior to Skip instead of Overwrite.

**Architecture:** 
1. We will update the schema and scripts to default `GATHER_ON_COLLISION` to `skip`.
2. We will add a regex strip to `move_downloaded_images` to remove any `3_1_3` or `3:1:3` prefix from the start of the final filename.
3. We will modify `resolve_census_image_dir` to accept the specific geographic segments (Country, Year, State, County, City) instead of a pre-combined `location_folder`, and hook `A.py` and `FS.py` up to parse those segments out of the JSON.

**Tech Stack:** Python (pathlib, regex, dictionaries)

---

### Task 1: Change default collision setting to "skip"

**Files:**
- Modify: `Voyageur/settings_schema.yaml`
- Modify: `Voyageur/A.py`
- Modify: `Voyageur/FS.py`

**Step 1: Write the failing test**

*(No test needed for basic YAML/env defaults change, but we'll verify it manually)*

**Step 2: Write minimal implementation**

```yaml
# In Voyageur/settings_schema.yaml:9-13
    GATHER_ON_COLLISION:
      default: "skip"
      tooltip: "When a gathered JSON or image file's destination already exists: overwrite it, or skip and keep the existing file."
      widget: segmented
      options: [["overwrite", "Overwrite"], ["skip", "Skip"]]
```

```python
# In Voyageur/A.py:163
    on_collision = os.getenv("GATHER_ON_COLLISION", "skip").strip().lower()

# In Voyageur/FS.py:822
    on_collision = os.getenv("GATHER_ON_COLLISION", "skip").strip().lower()
```

**Step 3: Commit**

```bash
git add Voyageur/settings_schema.yaml Voyageur/A.py Voyageur/FS.py
git commit -m "chore: change default gather collision resolution to skip"
```

---

### Task 2: Remove 3_1_3 prefix from ARK numbers

**Files:**
- Modify: `Voyageur/_gather_helpers.py`

**Step 1: Write the failing test**

```python
# In Voyageur/tests/test_gather_helpers.py (add to end)
def test_move_downloaded_images_strips_313_prefix_from_ark(tmp_path):
    downloads_dir = tmp_path / "downloads"
    downloads_dir.mkdir()
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    
    (downloads_dir / "TMP_FS_123_Images_3_1_3QHK-SQHW-1BWT.jpg").write_bytes(b"data")
    
    gh.move_downloaded_images(downloads_dir, "TMP_FS_123_Images_", 0.0, target_dir)
    assert (target_dir / "QHK-SQHW-1BWT.jpg").exists()
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest Voyageur/tests/test_gather_helpers.py::test_move_downloaded_images_strips_313_prefix_from_ark -v`
Expected: FAIL (file saved as `3_1_3QHK-SQHW-1BWT.jpg`)

**Step 3: Write minimal implementation**

```python
# In Voyageur/_gather_helpers.py in move_downloaded_images
    def attempt(candidate_path: Path) -> None:
        final_name = candidate_path.name[len(image_prefix):]
        # Strip FamilySearch ARK prefixes
        final_name = re.sub(r'^3[_:]1[_:]3', '', final_name)
        final_img = img_target_dir / final_name
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest Voyageur/tests/test_gather_helpers.py::test_move_downloaded_images_strips_313_prefix_from_ark -v`
Expected: PASS

**Step 5: Commit**

```bash
git add Voyageur/_gather_helpers.py Voyageur/tests/test_gather_helpers.py
git commit -m "feat: strip 3_1_3 prefix from downloaded image arks"
```

---

### Task 3: Update Media Directory Structure for Census

**Files:**
- Modify: `Voyageur/_gather_helpers.py`
- Modify: `Voyageur/tests/test_gather_helpers.py`
- Modify: `Voyageur/A.py`
- Modify: `Voyageur/FS.py`

**Step 1: Write the failing tests**

```python
# In Voyageur/tests/test_gather_helpers.py (replace old resolve_census_image_dir tests)
def test_resolve_census_image_dir_hierarchy(tmp_path):
    abs_base = tmp_path / "AbsCensus"
    result = gh.resolve_census_image_dir(str(abs_base), "", "USA", "1950", "North Dakota", "Pembina", "Walhalla")
    
    # USA mapped to US
    assert result == abs_base / "US" / "1950" / "North Dakota" / "Pembina" / "Walhalla"
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest Voyageur/tests/test_gather_helpers.py::test_resolve_census_image_dir_hierarchy -v`

**Step 3: Write minimal implementation**

```python
# In Voyageur/_gather_helpers.py
def resolve_census_image_dir(base_img_setting: str, genealogy_dir: str, country: str, year: str, state: str, county: str, city: str) -> Path:
    if os.path.isabs(base_img_setting):
        base_img_dir = Path(base_img_setting)
    else:
        media_setting = os.getenv("MEDIA_DIR", "Media")
        base_media_dir = Path(media_setting) if os.path.isabs(media_setting) else (
            Path(genealogy_dir) / media_setting if genealogy_dir else Path(media_setting))
        base_img_dir = base_media_dir / base_img_setting
    
    img_target_dir = base_img_dir
    country_display = "US" if country.upper() == "USA" else country
    
    for segment in [country_display, year, state, county, city]:
        if segment:
            img_target_dir = img_target_dir / segment.strip()
            
    img_target_dir.mkdir(parents=True, exist_ok=True)
    return img_target_dir
```

In `FS.py` and `A.py`, update both `_recover_orphaned_runs` and `main()` to extract the fields directly from the parsed JSON data:
```python
# Replace the clean_stem/location_folder logic with direct extraction
    fields = next(
        (s.get("records", [{}])[0].get("type_specific_fields", {})
         for s in final_data.get("sheets", []) if s.get("records")), {})
    
    year = fields.get("year", "")
    if not year:
        # Fallback to checking citation date or filename string if year field is missing
        # We can extract from collection_name or just rely on the file stem
        pass # Implement proper year fallback logic based on the provider data
    
    img_target_dir = resolve_census_image_dir(
        "Census", genealogy_dir, 
        fields.get("country", ""), 
        year, 
        fields.get("state", ""), 
        fields.get("county", ""), 
        fields.get("city", "")
    )
```
*(Specific data extraction logic will be verified during execution to ensure it correctly identifies the year, etc.)*

**Step 4: Run test to verify it passes**

Run: `python -m pytest Voyageur/tests -v`

**Step 5: Commit**

```bash
git add Voyageur/_gather_helpers.py Voyageur/tests/test_gather_helpers.py Voyageur/A.py Voyageur/FS.py
git commit -m "feat: restructure census media hierarchy to country/year/state/county/city"
```
