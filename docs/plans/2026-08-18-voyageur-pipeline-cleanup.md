# Voyageur Pipeline Cleanup Implementation Plan

> **For AGY:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** Remove three categories of stale artifacts from the Voyageur gather pipeline: the DOM-era `scrapeCitationAndCatalog()` call inside the FS `image-index` branch (already superseded by API data), the broken `stem.split(' - ', 1)` filename-parsing in both `FS.py` and `A.py` (broken by the ` - ` to `-` separator change), and the resulting arity mismatch on `resolve_census_image_dir` (callers pass 4 args; function takes 5).

**Architecture:** Three independent but related fixes across four files. `resolve_census_image_dir` gains a `census_folder` param (6 params total) and builds a structured `base/census_folder/country/year/location parts` path. All callers drop their stale `stem.split` blocks and supply data directly from the already-available in-memory dicts. `Voyageur.js`'s `buildFsItemData` drops the two lines that call `scrapeCitationAndCatalog()` from the `image-index` branch, since citation text is already built from the API and catalog items are redundant on that path.

**Tech Stack:** Python 3.12, JavaScript (Tampermonkey userscript). No new dependencies.

---

## Global Constraints

- Line length <= 120 chars for all Python files (pycodestyle).
- Never fabricate data: if a field is absent, leave it as `""` or `"Unknown_*"`, never guess.
- JS change must not break the `names` path: `scrapeCitationAndCatalog()` is removed **only** from the `image-index` branch.
- `census_folder` stays computed at every call site; it is now passed explicitly into `resolve_census_image_dir` rather than replacing `year`.
- Tests must not make real HTTP requests or touch real paths: patch `os.makedirs` / `Path.mkdir` where needed.
- Run `python -m pycodestyle --max-line-length=120 Voyageur/FS.py Voyageur/A.py Voyageur/_gather_helpers.py` after every Python task.

---

## Reference: current broken state

### `resolve_census_image_dir` signature vs. callers

Current signature (`_gather_helpers.py:314`):

```python
def resolve_census_image_dir(base_img_setting, genealogy_dir, year, country, location_folder): ...
```

Current callers: **4 args, function takes 5, causes `TypeError` at runtime**:

```python
# FS.py:801 and FS.py:909
resolve_census_image_dir("Census", genealogy_dir, census_folder, location_folder)

# A.py:137 and A.py:271
resolve_census_image_dir(base_img_setting, genealogy_dir, census_folder, location_folder)
```

### Stale `stem.split` blocks

`FS.py:892-895` and `FS.py:792-795`:

```python
stem = re.sub(r' - FS$', '', final_json.stem)   # no-op: suffix is now -FS, not ' - FS'
stem_parts = stem.split(' - ', 1)               # never splits: separator is now '-'
census_year = stem_parts[0].strip() ...          # gets the WHOLE stem, not the year
location_folder = stem_parts[1].strip() ...      # falls back to "Unknown_Location" always
```

`A.py:258-262`:

```python
stem_parts = final_json.stem.split(' - ', 1)
census_year = stem_parts[0].strip() ...
location_folder = re.sub(r'^USA\s*-\s*', '', stem_parts[1].strip() ...)
```

### JS dead call

`Voyageur.js:1811-1812` inside `buildFsItemData()` `image-index` branch:

```js
const catalog = await scrapeCitationAndCatalog();  // clicks DOM tab, scrapes table
catalogItems = catalog.catalogItems;               // only use; citationText discarded
```

Citation is already built from the API at line 1796; catalog items are redundant because
`FS.py`'s `parse_nara_citing_clause()` extracts the same roll/film data from the citation
text when `catalog_items` is empty.

---

## Task 1: Extend `resolve_census_image_dir` to take `census_folder`

**Files:**
- Modify: `Voyageur/_gather_helpers.py:314-335`
- Test: `Voyageur/tests/test_gather_helpers.py` (add new test cases)

### Step 1: Write the failing tests

Add to `Voyageur/tests/test_gather_helpers.py` (or create it if absent):

```python
from unittest.mock import patch
from pathlib import Path
from _gather_helpers import resolve_census_image_dir


def test_resolve_census_image_dir_builds_structured_path(tmp_path):
    """census_folder is a distinct level between base and country/year."""
    with patch("_gather_helpers.os.getenv", return_value=""):
        result = resolve_census_image_dir(
            str(tmp_path), "", "United States Census 1880",
            "1880", "USA", "North Dakota - Pembina"
        )
    assert result == tmp_path / "United States Census 1880" / "USA" / "1880" / "North Dakota" / "Pembina"


def test_resolve_census_image_dir_no_location_parts(tmp_path):
    """Empty location_folder still produces a valid path."""
    with patch("_gather_helpers.os.getenv", return_value=""):
        result = resolve_census_image_dir(
            str(tmp_path), "", "1880 USA Census", "1880", "USA", ""
        )
    assert result == tmp_path / "1880 USA Census" / "USA" / "1880"


def test_resolve_census_image_dir_omits_empty_segments(tmp_path):
    """Absent country or year are skipped, not added as empty path segments."""
    with patch("_gather_helpers.os.getenv", return_value=""):
        result = resolve_census_image_dir(
            str(tmp_path), "", "Some Collection", "", "", "Pembina"
        )
    assert result == tmp_path / "Some Collection" / "Pembina"
```

### Step 2: Run tests to verify they fail

```
python -m pytest Voyageur/tests/test_gather_helpers.py -k "resolve_census_image_dir" -v
```

Expected: `FAILED` - `TypeError: resolve_census_image_dir() takes 5 positional arguments but 6 were given`

### Step 3: Update `resolve_census_image_dir`

Replace lines 314-335 in `Voyageur/_gather_helpers.py`:

```python
def resolve_census_image_dir(base_img_setting: str, genealogy_dir: str, census_folder: str,
                             year: str, country: str, location_folder: str) -> Path:
    """Resolves the image target directory for a census gather.

    Path structure: <base_img_dir>/<census_folder>/<country>/<year>/<location_parts...>
    census_folder is the sanitised collection-level folder name (from
    census_collection_folder_name()) and forms the first sub-level so all images from one
    collection stay together regardless of state/county. country and year are appended
    next (each skipped when blank), then location_folder is split on ' - ' to form the
    remaining leaf segments.
    """
    if os.path.isabs(base_img_setting):
        base_img_dir = Path(base_img_setting)
    else:
        media_setting = os.getenv("MEDIA_DIR", "Media")
        base_media_dir = Path(media_setting) if os.path.isabs(media_setting) else (
            Path(genealogy_dir) / media_setting if genealogy_dir else Path(media_setting))
        base_img_dir = base_media_dir / base_img_setting

    parts = []
    if census_folder:
        parts.append(census_folder)
    if country:
        parts.append(country)
    if year:
        parts.append(year)

    location_parts = [p.strip() for p in location_folder.split(' - ') if p.strip()]
    parts.extend(location_parts)

    img_target_dir = base_img_dir.joinpath(*parts) if parts else base_img_dir
    img_target_dir.mkdir(parents=True, exist_ok=True)
    return img_target_dir
```

### Step 4: Run tests to verify they pass

```
python -m pytest Voyageur/tests/test_gather_helpers.py -k "resolve_census_image_dir" -v
```

Expected: all 3 new tests `PASSED`.

### Step 5: Lint

```
python -m pycodestyle --max-line-length=120 Voyageur/_gather_helpers.py
```

Expected: zero violations.

### Step 6: Commit

```
git add Voyageur/_gather_helpers.py Voyageur/tests/test_gather_helpers.py
git commit -m "feat(voyageur): add census_folder param to resolve_census_image_dir"
```

---

## Task 2: Fix `FS.py` - replace stale `stem.split` blocks with live data

**Files:**
- Modify: `Voyageur/FS.py:792-801` (`_recover_orphaned_runs`)
- Modify: `Voyageur/FS.py:892-909` (`main`)
- Test: `Voyageur/tests/test_fs.py` (add/update)

### Background: where the data actually lives

For **`main()`**: `final_data` (after `convert_raw_gather_to_final`) carries `census_year`,
`country`, `state`, `county`, `city` in `sheets[0].records[0].type_specific_fields`.
Use `final_data` since it is always in scope when the image-routing block runs.

`location_folder` should be built as `" - ".join(filter(None, [state, county, city]))`
using values from `final_data`'s first record's `type_specific_fields`, matching the
`' - '` split that `resolve_census_image_dir` uses internally.

For **`_recover_orphaned_runs()`**: `final_data` is already in scope (line 781). Same extraction logic applies.

### Step 1: Write the failing tests

Add to `Voyageur/tests/test_fs.py`:

```python
import json

MINIMAL_FINAL_DATA = {
    "citation": {"collection_name": "United States Census, 1880"},
    "sheets": [{
        "records": [{
            "type_specific_fields": {
                "census_year": "1880",
                "country": "USA",
                "state": "North Dakota",
                "county": "Pembina",
                "city": "Walhalla",
                "enumeration_district": "",
            }
        }]
    }]
}


def test_fs_main_image_routing_uses_live_data_not_filename():
    """census_year and location_folder come from final_data, never from stem.split."""
    from FS import _extract_census_image_routing_fields
    year, country, loc_folder, coll_name = _extract_census_image_routing_fields(MINIMAL_FINAL_DATA)
    assert year == "1880"
    assert country == "USA"
    assert loc_folder == "North Dakota - Pembina - Walhalla"
    assert coll_name == "United States Census, 1880"


def test_fs_location_folder_skips_empty_fields():
    """Empty city is omitted from location_folder, no trailing ' - '."""
    data = json.loads(json.dumps(MINIMAL_FINAL_DATA))
    data["sheets"][0]["records"][0]["type_specific_fields"]["city"] = ""
    from FS import _extract_census_image_routing_fields
    _, _, loc_folder, _ = _extract_census_image_routing_fields(data)
    assert loc_folder == "North Dakota - Pembina"
    assert not loc_folder.endswith(" - ")
```

> **Note:** `_extract_census_image_routing_fields` is the new private helper added to `FS.py` in Step 3. The test must fail with `ImportError` before Step 3.

### Step 2: Run tests to verify they fail

```
python -m pytest Voyageur/tests/test_fs.py -k "image_routing" -v
```

Expected: `FAILED` - `ImportError: cannot import name '_extract_census_image_routing_fields'`

### Step 3: Add helper and update both call sites in `FS.py`

**Add this helper** in `FS.py`, near the top of module scope (after imports, before `_recover_orphaned_runs`):

```python
def _extract_census_image_routing_fields(final_data: dict) -> tuple[str, str, str, str]:
    """Extracts (census_year, country, location_folder, collection_name) directly from
    the already-normalised final_data dict. Used by both main() and
    _recover_orphaned_runs() to route images without re-parsing the filename.

    location_folder is built as 'state - county - city' (each segment omitted when
    blank) matching the ' - ' split resolve_census_image_dir uses internally.
    census_year comes from type_specific_fields since the top-level key is only present
    in the raw JS payload, not the normalised output."""
    fields: dict = {}
    for sheet in final_data.get("sheets", []):
        records = sheet.get("records", [])
        if records:
            fields = records[0].get("type_specific_fields", {}) or {}
            break
    census_year = fields.get("census_year", "") or ""
    country = fields.get("country", "") or ""
    location_parts = [
        fields.get("state", ""),
        fields.get("county", ""),
        fields.get("city", ""),
    ]
    location_folder = " - ".join(p for p in location_parts if p)
    collection_name = final_data.get("citation", {}).get("collection_name", "") or ""
    return census_year, country, location_folder, collection_name
```

**Replace `_recover_orphaned_runs` stale block** (lines 792-801):

```python
        # Extract routing fields from the normalised data directly - no filename parsing.
        census_year, country, location_folder, collection_name = \
            _extract_census_image_routing_fields(final_data)
        census_folder = census_collection_folder_name(census_year, country, collection_name)
        img_target_dir = resolve_census_image_dir(
            "Census", genealogy_dir, census_folder, census_year, country, location_folder)
```

**Replace `main()` stale block** (lines 892-909):

```python
    # Extract routing fields from the normalised data directly - no filename parsing.
    census_year, country, location_folder, collection_name = \
        _extract_census_image_routing_fields(final_data)
    census_folder = census_collection_folder_name(census_year, country, collection_name)

    # Matches Antiquarian.py's own default ("Census", resolved against
    # MEDIA_DIR by the GUI before this ever runs).
    base_img_setting = "Census"
    img_target_dir = resolve_census_image_dir(
        base_img_setting, genealogy_dir, census_folder, census_year, country, location_folder)
```

Check whether `import re` is still used elsewhere in `FS.py`. If not, remove it:

```
python -c "import ast; src=open('Voyageur/FS.py').read(); uses=[n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id=='re']; print(len(uses), 're usages')"
```

### Step 4: Run tests to verify they pass

```
python -m pytest Voyageur/tests/test_fs.py -k "image_routing" -v
```

Expected: both new tests `PASSED`.

### Step 5: Run full Voyageur test suite

```
python -m pytest Voyageur/tests -v
```

Expected: all pre-existing tests still `PASSED`.

### Step 6: Lint

```
python -m pycodestyle --max-line-length=120 Voyageur/FS.py
```

Expected: zero violations.

### Step 7: Commit

```
git add Voyageur/FS.py Voyageur/tests/test_fs.py
git commit -m "fix(voyageur/fs): replace stale stem.split with live data for image routing"
```

---

## Task 3: Fix `A.py` - same stem.split removal, helper promoted to `_gather_helpers.py`

**Files:**
- Modify: `Voyageur/_gather_helpers.py` (add public helper)
- Modify: `Voyageur/FS.py` (replace private helper with import)
- Modify: `Voyageur/A.py:116-137` (`_recover_orphaned_runs`)
- Modify: `Voyageur/A.py:258-271` (`main`)
- Test: `Voyageur/tests/test_a.py` (add/update)

### Background: where the data lives in A.py

For **`main()`**: `raw_gather` is already loaded (line 230). `normalized` (output of
`normalize_ancestry_census_gather`) has the same `type_specific_fields` shape as FS's
`final_data`. Pass `normalized` to the shared helper.

For **`_recover_orphaned_runs()`**: `recovered_data` is loaded from the JSON file inside
the existing `try/except` block (lines 127-135). Pass it to the shared helper after that block.

### Step 1: Write the failing tests

Add to `Voyageur/tests/test_a.py`:

```python
MINIMAL_NORMALIZED = {
    "citation": {"collection_name": "United States Federal Census, 1860"},
    "sheets": [{
        "records": [{
            "type_specific_fields": {
                "census_year": "1860",
                "country": "USA",
                "state": "Minnesota",
                "county": "Ramsey",
                "city": "St Paul",
                "enumeration_district": "",
            }
        }]
    }]
}


def test_a_main_image_routing_uses_live_data_not_filename():
    """A.py image routing reads census_year/location from data, not the filename stem."""
    from _gather_helpers import extract_census_image_routing_fields
    year, country, loc_folder, coll_name = extract_census_image_routing_fields(MINIMAL_NORMALIZED)
    assert year == "1860"
    assert country == "USA"
    assert loc_folder == "Minnesota - Ramsey - St Paul"
    assert coll_name == "United States Federal Census, 1860"
```

> The helper is named `extract_census_image_routing_fields` (no leading underscore) in `_gather_helpers.py`.

### Step 2: Run tests to verify they fail

```
python -m pytest Voyageur/tests/test_a.py -k "image_routing" -v
```

Expected: `FAILED` - `ImportError`

### Step 3: Promote helper to `_gather_helpers.py`, update both callers

**In `_gather_helpers.py`**, add the public version of the helper (no leading underscore):

```python
def extract_census_image_routing_fields(final_data: dict) -> tuple[str, str, str, str]:
    """Extracts (census_year, country, location_folder, collection_name) from a normalised
    gather dict (output of normalize_*_census_gather). Used by both FS.py and A.py to
    route images without re-parsing the filename.

    location_folder is built as 'state - county - city' (each segment omitted when blank)
    matching the ' - ' split resolve_census_image_dir uses internally."""
    fields: dict = {}
    for sheet in final_data.get("sheets", []):
        records = sheet.get("records", [])
        if records:
            fields = records[0].get("type_specific_fields", {}) or {}
            break
    census_year = fields.get("census_year", "") or ""
    country = fields.get("country", "") or ""
    location_parts = [
        fields.get("state", ""),
        fields.get("county", ""),
        fields.get("city", ""),
    ]
    location_folder = " - ".join(p for p in location_parts if p)
    collection_name = final_data.get("citation", {}).get("collection_name", "") or ""
    return census_year, country, location_folder, collection_name
```

**Update `FS.py`**: remove the private `_extract_census_image_routing_fields` body added
in Task 2 and replace it with an import from `_gather_helpers`. Update the two call sites
to use `extract_census_image_routing_fields` (no underscore prefix):

```python
from _gather_helpers import (
    # ... existing imports ...,
    extract_census_image_routing_fields,
)
```

**Update `A.py`**: add to the `_gather_helpers` import block:

```python
from _gather_helpers import (
    # ... existing imports ...,
    extract_census_image_routing_fields,
)
```

**Replace `_recover_orphaned_runs` stale block** (`A.py:116-137`):

```python
        census_year, country, location_folder, collection_name = \
            extract_census_image_routing_fields(recovered_data)
        census_folder = census_collection_folder_name(census_year, country, collection_name)
        img_target_dir = resolve_census_image_dir(
            "Census", genealogy_dir, census_folder, census_year, country, location_folder)
```

> The existing `try/except` block loading `recovered_data` (A.py:127-135) stays in place.
> `extract_census_image_routing_fields` is called after it, using `recovered_data` already in scope.

**Replace `main()` stale block** (`A.py:258-271`):

```python
    census_year, country, location_folder, collection_name = \
        extract_census_image_routing_fields(normalized)
    census_folder = census_collection_folder_name(census_year, country, collection_name)
    img_target_dir = resolve_census_image_dir(
        base_img_setting, genealogy_dir, census_folder, census_year, country, location_folder)
```

> `country` (line 245) and `collection_name` (line 244) that were set earlier can be
> removed only if they are not referenced by any other line between their definition and
> the image routing block. Verify with a quick grep before deleting.

Check and remove `import re` from `A.py` if now unused.

### Step 4: Run tests to verify they pass

```
python -m pytest Voyageur/tests/test_a.py Voyageur/tests/test_fs.py Voyageur/tests/test_gather_helpers.py -v
```

Expected: all pass.

### Step 5: Lint

```
python -m pycodestyle --max-line-length=120 Voyageur/A.py Voyageur/FS.py Voyageur/_gather_helpers.py
```

Expected: zero violations.

### Step 6: Commit

```
git add Voyageur/A.py Voyageur/FS.py Voyageur/_gather_helpers.py Voyageur/tests/test_a.py
git commit -m "fix(voyageur/a): replace stale stem.split with live data for image routing"
```

---

## Task 4: Remove dead `scrapeCitationAndCatalog()` call from JS `image-index` branch

**Files:**
- Modify: `Voyageur/Voyageur.js:1811-1812` (inside `buildFsItemData`, `image-index` branch)

> There are no JS unit tests for `buildFsItemData` itself (async/DOM-dependent), but the
> existing Node test harness (`Voyageur/tests/js/`) covers the pure helpers. Run those
> to confirm nothing broke.

### Step 1: Locate the two lines to remove

`Voyageur/Voyageur.js` lines 1811-1812 (inside `if (pageType === 'image-index')` block):

```js
                const catalog = await scrapeCitationAndCatalog();
                catalogItems = catalog.catalogItems;
```

At this point in the `image-index` branch, the following have already been computed from the API:
- `rows` via `fsBuildRowsFromImageIndexResponse`
- `citationText` via `fsBuildCitationTextFromImageIndexResponse`
- `locationInfo` via `fsImageIndexBrowsePathSegments`

The `citationText` returned by `scrapeCitationAndCatalog()` is discarded on this path.
`catalogItems` being `[]` is acceptable: `FS.py`'s `parse_nara_citing_clause()` already
extracts roll/film info from the API-built citation text when `catalog_items` is `[]`.

### Step 2: Replace the two lines with an explanatory comment

```js
                // catalogItems intentionally empty on the image-index path: the API
                // already supplies the full citation text via
                // fsBuildCitationTextFromImageIndexResponse above, and FS.py's
                // parse_nara_citing_clause() extracts roll/film data from that text
                // when catalog_items is []. scrapeCitationAndCatalog() is not called
                // here because it clicks the Information tab and scrapes a DOM table
                // that does not reliably exist on Image Browser pages - confirmed to
                // produce "No index data received" and "Unrecognized page" toast errors
                // on every image-index gather.
```

### Step 3: Run the JS test harness

```
node Voyageur/tests/js/run_tests.js
```

Expected: all tests pass (the removed lines are not exercised by the pure-helper tests).

### Step 4: Manual smoke-check note

> After deploying the updated `Voyageur.js` to Tampermonkey, run one real image-index
> gather and confirm:
> - No "No index data received for this image." or "Unrecognized page." toasts appear
> - Downloaded JSON still contains `citation_text` (built from API)
> - `catalog_items` is `[]` in the JSON - confirmed acceptable, FS.py still produces correct output

### Step 5: Commit

```
git add Voyageur/Voyageur.js
git commit -m "fix(voyageur/js): remove dead DOM scrape from image-index gather branch"
```

---

## Task 5: Full regression suite + final lint

### Step 1: Full test suite

```
python -m pytest Voyageur/tests Commissioner/tests -v
```

Expected: all pass, no regressions.

### Step 2: Compile check all modified Python files

```
python -m py_compile Voyageur/FS.py Voyageur/A.py Voyageur/_gather_helpers.py
```

Expected: silent (no syntax errors).

### Step 3: Full lint

```
python -m pycodestyle --max-line-length=120 Voyageur/FS.py Voyageur/A.py Voyageur/_gather_helpers.py
```

Expected: zero violations.

### Step 4: Update task tracker

Update `docs/plans/task.md` to mark this plan complete.

### Step 5: Final commit

```
git add docs/plans/task.md
git commit -m "chore: mark voyageur pipeline cleanup complete"
```
