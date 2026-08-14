# PyCharm Inspection Fixes Part 2

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** Resolve the remaining PyCharm inspection errors that were skipped in Part 1 and update the automated lint suite.


### Task 1: Fix Remaining Issues in Archivist, Commissioner
**Files:**
- Modify: `Archivist/Census.py`
- Modify: `Archivist/General.py`
- Modify: `Archivist/HBCA.py`
- Modify: `Archivist/Scrip.py`
- Modify: `Archivist/Utils.py`
- Modify: `Archivist/tests/golden/capture_golden_gedcom.py`
- Modify: `Archivist/tests/test_archivist.py`
- Modify: `Archivist/tests/test_archivist_dispatcher.py`
- Modify: `Archivist/tests/test_general_smoke.py`
- Modify: `Commissioner/normalization.py`
- Modify: `Commissioner/tests/test_models.py`
- Modify: `Archivist/tests/test_census_ingestion.py`
- Modify: `Archivist/tests/test_hbca_profile.py`
- Modify: `Archivist/tests/test_census_module_smoke.py`
- Modify: `Archivist/tests/test_profile_parity.py`
- Modify: `Archivist/tests/test_scrip_profile_smoke.py`
- Modify: `Archivist/tests/test_utils.py`
- Modify: `Commissioner/tests/test_hbca_registry.py`
- Modify: `Commissioner/tests/test_record_registry.py`

**Step 1:** Read brief at `C:\Users\Jason Cole\Documents\Genealogy\Scriptorium\.superpowers\sdd\2026-08-14-pycharm-inspection-fixes-part-2\task-1-brief.md` and implement fixes.
**Step 2:** Run `python -m pytest`
**Step 3:** Commit changes.

### Task 2: Fix Remaining Issues in Paleographer, PDFix
**Files:**
- Modify: `PDFix/PDFix.py`
- Modify: `Paleographer/Extract.py`
- Modify: `Paleographer/ScripTools.py`
- Modify: `Paleographer/agy_engine.py`
- Modify: `Paleographer/tests/test_agy_engine.py`
- Modify: `Paleographer/tests/test_crosscheck.py`
- Modify: `Paleographer/tests/test_engine.py`
- Modify: `Paleographer/tests/test_master_db_merge.py`
- Modify: `Paleographer/tests/test_paleographer_pipeline.py`
- Modify: `Paleographer/tests/test_settings_standalone.py`
- Modify: `Paleographer/engine.py`
- Modify: `PDFix/tests/test_pdfix.py`
- Modify: `Paleographer/CacheCleanup.py`
- Modify: `Paleographer/tests/test_extract_dispatch.py`
- Modify: `Paleographer/tests/test_paleographer_dispatcher.py`
- Modify: `Paleographer/tests/test_schema.py`
- Modify: `Paleographer/tests/test_scriptools_dispatch.py`

**Step 1:** Read brief at `C:\Users\Jason Cole\Documents\Genealogy\Scriptorium\.superpowers\sdd\2026-08-14-pycharm-inspection-fixes-part-2\task-2-brief.md` and implement fixes.
**Step 2:** Run `python -m pytest`
**Step 3:** Commit changes.

### Task 3: Fix Remaining Issues in Registrar, Gazetteer, ScriptoriumMCP
**Files:**
- Modify: `Gazetteer/Gazetteer.py`
- Modify: `Registrar/tests/test_registrar.py`
- Modify: `ScriptoriumMCP/agy_client.py`
- Modify: `ScriptoriumMCP/tests/test_agy_client.py`

**Step 1:** Read brief at `C:\Users\Jason Cole\Documents\Genealogy\Scriptorium\.superpowers\sdd\2026-08-14-pycharm-inspection-fixes-part-2\task-3-brief.md` and implement fixes.
**Step 2:** Run `python -m pytest`
**Step 3:** Commit changes.

### Task 4: Fix Remaining Issues in Voyageur
**Files:**
- Modify: `Voyageur/A.py`
- Modify: `Voyageur/FS.py`
- Modify: `Voyageur/LAC.py`
- Modify: `Voyageur/census_schema.py`
- Modify: `Voyageur/lac_client.py`
- Modify: `Voyageur/tests/test_hbca_gather.py`
- Modify: `Voyageur/tests/test_hbca_keystone.py`
- Modify: `Voyageur/tests/test_lac.py`
- Modify: `Voyageur/tests/js/harness.js`
- Modify: `Voyageur/HBCA.py`
- Modify: `Voyageur/_gather_helpers.py`
- Modify: `Voyageur/tests/test_a.py`
- Modify: `Voyageur/tests/test_census_schema.py`
- Modify: `Voyageur/tests/test_fs.py`
- Modify: `Voyageur/tests/test_gather_helpers.py`
- Modify: `Voyageur/tests/test_hbca_regex.py`
- Modify: `Voyageur/tests/test_voyageur_dispatcher.py`

**Step 1:** Read brief at `C:\Users\Jason Cole\Documents\Genealogy\Scriptorium\.superpowers\sdd\2026-08-14-pycharm-inspection-fixes-part-2\task-4-brief.md` and implement fixes.
**Step 2:** Run `python -m pytest`
**Step 3:** Commit changes.

### Task 5: Fix Remaining Issues in Scriptorium.py, tests, Working
**Files:**
- Modify: `Scriptorium.py`
- Modify: `tests/test_scriptorium_voyageur_settings_ui.py`
- Modify: `tests/test_scriptorium_settings_migration.py`

**Step 1:** Read brief at `C:\Users\Jason Cole\Documents\Genealogy\Scriptorium\.superpowers\sdd\2026-08-14-pycharm-inspection-fixes-part-2\task-5-brief.md` and implement fixes.
**Step 2:** Run `python -m pytest`
**Step 3:** Commit changes.

### Task 6: Update Lint Test Suite
**Step 1:** Update `tests/test_code_quality.py` to enforce these checks (e.g., using `pylint` or matching flake8 plugins) to ensure nothing is missing from what PyCharm checks for.
**Step 2:** Run `python -m pytest tests/test_code_quality.py -v`.
**Step 3:** Commit.
