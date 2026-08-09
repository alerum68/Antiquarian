# Task Tracking

| Stage | Agent | Status | Notes |
|-------|-------|--------|-------|
| 1 | ArchDev | ⏭️ | Skip (no new folders/files) |
| 2 | LogicDev | ✅ | Auto image dirs, hardcoded IMAGE_EXTENSION, removed env lookups |
| 3 | UIFormDev | ✅ | Removed CENSUS_IMAGE_DIR/IMAGE_EXTENSION from globals, separated Parish/Scrip settings |
| 4 | Tester | ✅ | py_compile pass, YAML validation pass, A.py docstring fix applied |
| 5 | BugFixer | ✅ | Fixed escaped triple-quote docstring in Voyageur/A.py |
| 6 | DocBot | ⏳ | — |

## Current Task: UI Cleanup - Auto Image Dirs & Tab Separation
* ✅ Removed `CENSUS_IMAGE_DIR` and `IMAGE_EXTENSION` from Global Settings (`Scriptorium.py`).
* ✅ Removed `*_IMAGE_DIR` (e.g. `CHURCH_IMAGE_DIR`, `SCRIP_IMAGE_DIR`) from `Paleographer/settings_schema.yaml` and `.pmt` field_remaps.
* ✅ Automated Image Dir resolution: `Media/<Prompt_Name>` via `TYPE_CFG.name` in `Extract.py`.
* ✅ Separated Paleographer settings: Scrip now has its own `SCRIP_GEDCOM_NAME`; Parish keeps `CHURCH_GEDCOM_NAME`/`CHURCH_MASTER_DB_NAME`.
