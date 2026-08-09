# Task Tracking

| Stage | Agent | Status | Notes |
|-------|-------|--------|-------|
| 1 | ArchDev | ⏳ | Decompose Commissioner root requirements into folder/file structural spec |
| 2 | LogicDev | ⏳ | — |
| 3 | UIFormDev | ⏳ | — |
| 4 | Tester | ⏳ | — |
| 5 | BugFixer | ⏳ | — |
| 6 | DocBot | ⏳ | — |

## Completed Task: Commissioner SubAgent Rules
* ✅ Required ArchDev and LogicDev to use `Commissioner` as the conceptual root for how everything is built.
* ✅ Added constraints to `.opencode/` and `.claude/` subagent profiles (and `AGENTS.md`) so Commissioner dictates the core structure of JSON and GEDCOMs going forward.

## Task Definition
Update directory logic across the project:
1. `PROGRAM_DIR` is currently being used as the genealogy root. We need to rename its concept in the UI/settings to `GENEALOGY_DIR`.
2. `PROGRAM_DIR` should be redefined as the directory where the Scriptorium codebase resides.
3. The following directories should default as subdirectories of `GENEALOGY_DIR`:
   - Media Dir (`MEDIA_DIR`)
   - Gedcom Output Dir (`GEDCOM_OUTPUT_PATH`)
   - Roots Magic Dir (`RM_DIR`)
   - Family Tree Maker Dir (`FTM_DIR`)
4. The following directories should default as subdirectories of `PROGRAM_DIR`:
   - JSON Dir (`JSON_DIR`)
   - Working Dir (any other working/temp dirs)

## Files to touch
- `Scriptorium.py`
- `Archivist/Utils.py`
- `Voyageur/A.py`
- `Voyageur/FS.py`
- `Voyageur/LAC.py`
- `Paleographer/Extract.py`
- `Gazetteer/Gazetteer.py`
- `Registrar/Registrar.py`
- `PDFix/PDFix.py`
- Any related schema or utility files where `PROGRAM_DIR` is used as the base for Genealogy files.
