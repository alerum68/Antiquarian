# Antiquarian Project Rename Design

## 1. Scope & Strategy
We will execute a project-wide renaming from "Antiquarian" (along with legacy names "Antiquarian" and "Antiquarian") to "Antiquarian". Because the name is heavily embedded in class names, file names, documentation, and module imports, we will use a systematic approach across all file types on the `Unify` branch.

## 2. Execution Steps

**Phase A: File & Directory Renames**
- Rename `Antiquarian.py` to `Antiquarian.py`.
- Rename the `AntiquarianMCP/` directory to `AntiquarianMCP/`.
- Rename tests, e.g., `tests/test_antiquarian_settings_migration.py` to `tests/test_antiquarian_settings_migration.py`.

**Phase B: Global String Replacements**
- Run case-sensitive replacements across all source files (`.py`, `.md`, `.yaml`, `.js`, `.iss`, `.json`):
  - `Antiquarian` -> `Antiquarian`
  - `antiquarian` -> `antiquarian`
  - `Antiquarian` -> `Antiquarian`
  - `Antiquarian` -> `Antiquarian`

**Phase C: Build & Config Updates**
- Update module imports (e.g., `from AntiquarianMCP import ...`).
- Update Inno Setup (`installer.iss`), PyInstaller (`build.py`), and GitHub action workflows to point to the new binary and directory names.
- Update `AGENTS.md` to reflect the new project name.

## 3. Verification
- Run the full test suite (`python -m pytest`) to ensure all module imports resolve correctly and no schemas are broken.
- Commit all changes incrementally to the `Unify` branch.
