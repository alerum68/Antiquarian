# Antiquarian UI Tab Review & Citation Architecture Implementation Plan

> **For AGY:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** Simplify the Antiquarian UI by consolidating Voyageur gather settings, migrating manual citation entry to Paleographer (so AI gets context and the JSON is fully baked), and updating help documentation.

**Architecture:** 
1. Voyageur uses a single generic `GATHER_URL` instead of `A_URL`, `FS_URL`, `LAC_URL`. The UI hides LAC's manual `LAC_VOLUME`, `LAC_RECORD_TYPE`, `VOLUME_TITLE` and uses URL parsing/extrapolation.
2. Paleographer `.pmt` files add `Citation Overrides` to their `settings_sections`. `Extract.py` reads these environment variables and injects them into the generated Master DB JSON's `collection_metadata`.
3. Archivist removes the manual Citation Override fields from its schema and updates its GEDCOM generator to pull citation data directly from the ingested JSON file.

**Tech Stack:** Python 3.12, CustomTkinter (UI), Pydantic v2 (Commissioner), Pytest.

---

### Task 1: Voyageur Schema Consolidation

**Files:**
- Modify: `Voyageur/settings_schema.yaml`
- Modify: `tests/test_antiquarian_settings_migration.py`
- Modify: `tests/test_load_tool_schema.py`

**Step 1: Write the failing test**
Update `tests/test_antiquarian_settings_migration.py::test_voyageur_schema_matches_expected_shape` to expect the new consolidated structure (a `Gather Settings` section with `VOYAGEUR_SOURCE`, `GATHER_URL`, `GATHER_ON_COLLISION`, plus a simplified `HBCA / Manitoba Archives` section without `HBCA_IMAGE_DIR`/`HBCA_MASTER_DB_NAME`).

**Step 2: Run test to verify it fails**
Run: `pytest tests/test_antiquarian_settings_migration.py::test_voyageur_schema_matches_expected_shape -v`
Expected: FAIL due to missing/mismatched keys.

**Step 3: Write minimal implementation**
Update `Voyageur/settings_schema.yaml`:
- Move `GATHER_ON_COLLISION` to `Gather Settings` (with options: overwrite, skip, append).
- Add `GATHER_URL` to `Gather Settings`.
- Delete the `Ancestry`, `FamilySearch`, `LAC` sections completely.
- Remove `HBCA_IMAGE_DIR` and `HBCA_MASTER_DB_NAME` from the `HBCA / Manitoba Archives` section.
- Update `label_overrides` to reflect the changes (e.g. `GATHER_URL: "Gather URL"`).

**Step 4: Run test to verify it passes**
Run: `pytest tests/test_antiquarian_settings_migration.py tests/test_load_tool_schema.py tests/test_settings_schema_completeness.py -v`
Expected: PASS

**Step 5: Commit**
`git add tests/test_antiquarian_settings_migration.py Voyageur/settings_schema.yaml`
`git commit -m "feat(voyageur): consolidate gather schema and remove legacy provider sections"`

---

### Task 2: Voyageur Python Scripts Refactor

**Files:**
- Modify: `Voyageur/A.py`
- Modify: `Voyageur/FS.py`
- Modify: `Voyageur/LAC.py`
- Modify: `Voyageur/HBCA.py`
- Modify: `Voyageur/tests/test_a.py`
- Modify: `Voyageur/tests/test_fs.py`
- Modify: `Voyageur/tests/test_lac.py`
- Modify: `Voyageur/tests/test_hbca_gather.py`

**Step 1: Write the failing test**
In `test_a.py`, `test_fs.py`, `test_lac.py`, modify tests that rely on `A_URL`, `FS_URL`, `LAC_URL` to set `GATHER_URL` instead. Ensure they fail. 

**Step 2: Run test to verify it fails**
Run: `pytest Voyageur/tests/ -v`
Expected: FAIL

**Step 3: Write minimal implementation**
- `A.py`: Replace `os.getenv("A_URL")` with `os.getenv("GATHER_URL")`.
- `FS.py`: Replace `os.getenv("FS_URL")` with `os.getenv("GATHER_URL")`.
- `LAC.py`: Replace `os.environ.get("LAC_URL")` with `os.environ.get("GATHER_URL")`.
  - Add logic to extrapolate `volume`, `archival_number`, `record_type`, and `volume_title` from the URL or fallback logic, replacing `LAC_VOLUME`, `LAC_RECORD_TYPE`, `VOLUME_TITLE` direct lookups from `.env`.
- `HBCA.py`: Hardcode `HBCA_IMAGE_DIR` to `"HBCA"` and `HBCA_MASTER_DB_NAME` to `"MasterDB_HBCA.json"` directly in the script, removing the `os.environ.get` for them.

**Step 4: Run test to verify it passes**
Run: `pytest Voyageur/tests/ -v`
Expected: PASS

**Step 5: Commit**
`git commit -am "feat(voyageur): update scripts to read consolidated GATHER_URL and auto-generate LAC/HBCA properties"`

---

### Task 3: Paleographer Citation Metadata Schema

**Files:**
- Modify: `Paleographer/settings_schema.yaml`
- Modify: `Paleographer/prompts/Parish.pmt`
- Modify: `Paleographer/prompts/Scrip.pmt`
- Modify: `tests/test_antiquarian_settings_migration.py`

**Step 1: Write the failing test**
Update `test_paleographer_schema_matches_expected_shape` to expect the new `Citation Overrides` section containing all citation fields (`PUBLISHER`, `REPOSITORY`, `CALL_NUMBER`, `COLLECTION_URL`, `COLLECTION_NAME`, `PUB_LOC`, `REGISTER_NAME`, `REGISTER_SOURCE_ID`, `CITATION_DETAIL`, `CITATION_TEXT`).

**Step 2: Run test to verify it fails**
Run: `pytest tests/test_antiquarian_settings_migration.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**
- `Paleographer/settings_schema.yaml`: Add the `Citation Overrides` section with the 10 fields moved from Archivist.
- `Parish.pmt` & `Scrip.pmt`: Add `- "Citation Overrides"` to their `settings_sections` lists.

**Step 4: Run test to verify it passes**
Run: `pytest tests/test_antiquarian_settings_migration.py -v`
Expected: PASS

**Step 5: Commit**
`git commit -am "feat(paleographer): add citation overrides section to schema and pmt profiles"`

---

### Task 4: Paleographer Metadata Injection

**Files:**
- Modify: `Paleographer/Extract.py`
- Modify: `Paleographer/tests/test_engine.py` (or relevant test)
- Modify: `Commissioner/models.py` (if needed for `collection_metadata`)

**Step 1: Write the failing test**
Create/update a test in `Paleographer/tests/test_master_db_merge.py` or `test_paleographer_pipeline.py` asserting that citation environment variables (`PUBLISHER`, `REPOSITORY`, etc.) are written into `collection_metadata` when `save_master_db` is called.

**Step 2: Run test to verify it fails**
Run: `pytest Paleographer/tests/ -v`
Expected: FAIL

**Step 3: Write minimal implementation**
- Modify `Paleographer/Extract.py` (in `save_master_db` or similar context-prep) to read the citation variables from `os.getenv` using `resolve_setting` and inject them into the Master DB JSON structure (e.g. `data.setdefault("collection_metadata", {}).update({ ... })`).
- Modify `Commissioner/models.py` `Collection` model if it does not already accept a `collection_metadata` dictionary mapping.

**Step 4: Run test to verify it passes**
Run: `pytest Paleographer/tests/ -v`
Expected: PASS

**Step 5: Commit**
`git commit -am "feat(paleographer): inject citation settings into generated JSON master DB"`

---

### Task 5: Archivist Schema & Dependency Simplification

**Files:**
- Modify: `Archivist/settings_schema.yaml`
- Modify: `Archivist/General.py`
- Modify: `Archivist/Census.py`
- Modify: `tests/test_antiquarian_settings_migration.py`
- Modify: `Archivist/tests/test_general_smoke.py`

**Step 1: Write the failing test**
Update `tests/test_antiquarian_settings_migration.py::test_archivist_schema_matches_expected_shape` to ensure `Citation Overrides` is no longer present.

**Step 2: Run test to verify it fails**
Run: `pytest tests/test_antiquarian_settings_migration.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**
- Remove `Citation Overrides` entirely from `Archivist/settings_schema.yaml`.
- Update `Archivist/General.py` (and `Census.py` if applicable) to stop using `os.getenv("PUBLISHER")`, etc.
- Modify the GEDCOM compilation logic to instead read these properties securely from the loaded JSON's `collection_metadata` or `document_metadata`.

**Step 4: Run test to verify it passes**
Run: `pytest tests/test_antiquarian_settings_migration.py Archivist/tests/ -v`
Expected: PASS

**Step 5: Commit**
`git commit -am "feat(archivist): remove manual citation schema and read dynamically from JSON"`

---

### Task 6: Help & Tooltips Refresh

**Files:**
- Modify: `Antiquarian.py`
- Modify: relevant `settings_schema.yaml` files

**Step 1: Write the failing test**
Not applicable. Run full pycodestyle/pytest suite to ensure no regressions.

**Step 2: Write minimal implementation**
- Update `self.help_texts` in `Antiquarian.py` for Voyageur, Paleographer, and Archivist.
  - *Voyageur:* Explain the consolidated `Gather URL`.
  - *Paleographer:* Explain the new Citation Overrides section and that the UI dynamically swaps.
  - *Archivist:* Explain that citations are now derived directly from the JSON files and do not require manual tuning at this stage.
- Update the `tooltip` properties in the YAML schemas to match the new behavior.

**Step 3: Run test to verify it passes**
Run: `python -m pycodestyle --max-line-length=120 Antiquarian.py`
Expected: PASS

**Step 4: Commit**
`git commit -am "docs: update UI help texts and tooltips to reflect new tab architectures"`

---
