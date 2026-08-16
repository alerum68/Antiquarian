# Antiquarian Project Rename Implementation Plan

> **For AGY:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** Execute a project-wide rename from "Antiquarian", "Antiquarian", and "Antiquarian" to "Antiquarian" across all files, directories, and documentation on the `Unify` branch.

**Architecture:** We will systematically rename files and directories first to establish the new structure, followed by text replacement inside all source files, and finally test and verify the module imports.

**Tech Stack:** Python, bash (or powershell equivalents), pytest

---

### Task 1: Rename the root application file

**Files:**
- Rename: `Antiquarian.py` -> `Antiquarian.py`

**Step 1: Rename the file**
Run: `mv Antiquarian.py Antiquarian.py` (or Windows equivalent `Rename-Item Antiquarian.py Antiquarian.py`)

**Step 2: Commit**
```bash
git add Antiquarian.py Antiquarian.py
git commit -m "refactor: rename root application file to Antiquarian.py"
```

---

### Task 2: Rename the MCP directory

**Files:**
- Rename: `AntiquarianMCP/` -> `AntiquarianMCP/`

**Step 1: Rename the directory**
Run: `mv AntiquarianMCP AntiquarianMCP` (or Windows `Rename-Item AntiquarianMCP AntiquarianMCP`)

**Step 2: Commit**
```bash
git add AntiquarianMCP AntiquarianMCP
git commit -m "refactor: rename AntiquarianMCP to AntiquarianMCP"
```

---

### Task 3: Global String Replacements (Case-Sensitive)

**Files:**
- Modify: All `.py`, `.md`, `.yaml`, `.js`, `.iss`, `.json` files in the repository.

**Step 1: Replace 'Antiquarian' with 'Antiquarian'**
Using your replacement tools or a targeted script, find and replace all instances of the exact string `Antiquarian` with `Antiquarian`. Be sure to catch `AGENTS.md`, `README.md`, `CHANGELOG.md`, `installer.iss`, `build.py`, and all python modules.

**Step 2: Replace 'antiquarian' with 'antiquarian'**
Find and replace all instances of the lowercase string `antiquarian` with `antiquarian` (important for paths, URLs, or lowercase variables).

**Step 3: Replace 'Antiquarian' and 'Antiquarian' with 'Antiquarian'**
Find and replace any lingering instances of `Antiquarian` or `Antiquarian` with `Antiquarian`.

**Step 4: Commit**
```bash
git add -u
git commit -m "refactor: global text replacement of Antiquarian and Antiquarian to Antiquarian"
```

---

### Task 4: Rename test files and specific references

**Files:**
- Rename: `tests/test_antiquarian_settings_migration.py` -> `tests/test_antiquarian_settings_migration.py`

**Step 1: Rename the file**
Run: `mv tests/test_antiquarian_settings_migration.py tests/test_antiquarian_settings_migration.py`

**Step 2: Update contents of the renamed test**
Ensure the internal test function names inside `test_antiquarian_settings_migration.py` reflect the new name (e.g., `test_antiquarian_migration` -> `test_antiquarian_migration`).

**Step 3: Commit**
```bash
git add tests/
git commit -m "test: rename antiquarian settings test to antiquarian"
```

---

### Task 5: Verification and Testing

**Step 1: Run the full test suite**
Run: `python -m pytest -v`
Expected: PASS (All tests should execute properly, indicating that internal imports like `from AntiquarianMCP import ...` are resolving correctly).

**Step 2: Verify Linting**
Run: `python -m pycodestyle --max-line-length=120`
Expected: No violations.

**Step 3: Final validation commit**
If any final tweaks were needed to fix broken imports, commit them.
```bash
git add .
git commit -m "chore: fix remaining Antiquarian import resolution issues"
```
