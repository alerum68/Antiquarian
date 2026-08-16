# PyCharm Inspection Fixes & Automated Lint Suite Implementation Plan

> **For AGY:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** Resolve all 504 PyCharm inspection errors (across 24 XML inspection types in `DEV/Issues`, ignoring Proofreading) and update the project's automated lint suite (`flake8`/`pyflakes`/`pycodestyle` integration in pytest) to enforce zero inspection violations on future commits.

**Architecture:** Group and resolve code quality findings across all Antiquarian modules (`Archivist`, `Paleographer`, `Voyageur`, `Commissioner`, `PDFix`, `Registrar`, `Gazetteer`, `AntiquarianMCP`, and `Antiquarian.py`). Enhance the automated lint test runner (`tests/test_code_quality.py`) to run `flake8` / `pyflakes` / `pycodestyle` with strict checks matching PyCharm's inspection rules.

**Tech Stack:** Python 3.12, Pytest, Flake8 / Pyflakes / Pycodestyle, Pydantic v2, CustomTkinter.

---

### Task 1: Clean Up Unused Imports, Unused Local Variables, Redundant Parentheses, and Duplicate Dict Keys

**Files:**
- Modify: `Archivist/HBCA.py` (Remove unused `Dict` import and redundant parentheses)
- Modify: `Archivist/General.py` (Remove redundant parentheses line 265, unused variable `rec_id`)
- Modify: `Archivist/Scrip.py` (Remove redundant parentheses line 467)
- Modify: `Voyageur/HBCA.py` (Remove unused import `quote`)
- Modify: `Voyageur/tests/test_hbca_gather.py` (Remove unused imports `json`, `pytest`)
- Modify: `Voyageur/tests/test_hbca_regex.py` (Remove unused import `pytest`)
- Modify: `Archivist/tests/test_archivist_dispatcher.py` (Remove unused import `os`)
- Modify: `Archivist/tests/test_census_ingestion.py` (Remove unused import `pandas as pd`)
- Modify: `Commissioner/tests/test_hbca_registry.py` (Remove unused import `pytest`)
- Modify: `Paleographer/tests/test_paleographer_pipeline.py` (Remove unused import `pytest`)
- Modify: `Archivist/tests/test_archivist.py` (Remove unused local `joined`)
- Modify: `Antiquarian.py` (Remove unused local `status_msg`)

**Step 1: Write failing lint test targeting unused imports/variables**

Run: `python -m flake8 --select=F401,F841 Archivist/ Voyageur/ Commissioner/ Paleographer/ Antiquarian.py`
Expected output: Reports unused imports and variables in target files.

**Step 2: Remove unused imports, unused variables, redundant parentheses, and duplicate keys**

Edit the specified files to remove unused `import` statements, drop unused variable assignments, and strip unnecessary parentheses surrounding conditional expressions.

**Step 3: Run flake8 check to verify clean output**

Run: `python -m flake8 --select=F401,F841 Archivist/ Voyageur/ Commissioner/ Paleographer/ Antiquarian.py`
Expected output: Exit code 0 (no violations reported).

**Step 4: Run test suite to verify no regressions**

Run: `python -m pytest Paleographer/tests Commissioner/tests Voyageur/tests Archivist/tests -v`
Expected output: All tests PASS.

**Step 5: Commit**

```bash
git add Archivist/ Voyageur/ Commissioner/ Paleographer/ Antiquarian.py
git commit -m "fix(lint): remove unused imports, unused variables, and redundant parentheses"
```

---

### Task 2: Fix Relative Imports, Unhashable Types, Unbound Local Variables, Unreachable Code, and TypedDict Keys

**Files:**
- Modify: `Paleographer/ScripTools.py:34-35` (Replace relative imports `from . import ...` with absolute imports)
- Modify: `Voyageur/HBCA.py:31,522` (Fix relative import; wrap dict key lookup to handle `AttributeValueList | str`)
- Modify: `Voyageur/LAC.py:28,33` (Replace relative imports with absolute imports)
- Modify: `PDFix/PDFix.py:387` (Initialize `temp_file = None` before conditional try block to prevent unbound variable error)
- Modify: `Archivist/Census.py:516-518` (Fix string key for TypedDict and remove unreachable return statement)

**Step 1: Run test suite on affected modules to capture baseline**

Run: `python -m pytest Paleographer/tests Voyageur/tests PDFix/tests Archivist/tests -v`
Expected output: Tests run.

**Step 2: Implement relative import fixes, variable initialization, unhashable key fix, and TypedDict cleanup**

- In `Paleographer/ScripTools.py`, `Voyageur/HBCA.py`, `Voyageur/LAC.py`, convert relative imports (`from . import ...`) to explicit absolute imports (`from Paleographer import ...`, `from Voyageur import ...`).
- In `PDFix/PDFix.py`, initialize `temp_file = None` before line 387.
- In `Archivist/Census.py`, ensure TypedDict dictionary keys are standard strings and eliminate unreachable statements after `return`/`raise`.
- In `Voyageur/HBCA.py`, cast unhashable key types to `str(key)` or extract string values before indexing dicts.

**Step 3: Run targeted module tests to verify fix**

Run: `python -m pytest Paleographer/tests Voyageur/tests PDFix/tests Archivist/tests -v`
Expected output: All tests PASS.

**Step 4: Commit**

```bash
git add Paleographer/ Voyageur/ PDFix/ Archivist/
git commit -m "fix(core): correct relative imports, unbound variables, unhashable keys, and unreachable code"
```

---

### Task 3: Fix Type Annotations, String Format Specifiers, and Function Call Signatures

**Files:**
- Modify: `Commissioner/record_registry.py:61,76` (Fix `Literal` type hint parameterization)
- Modify: `PDFix/PDFix.py:163-164,411-413` (Fix format specifiers for floats/ints in string formatting)
- Modify: `Archivist/Census.py` (Fix non-callable invocation and default argument mutability issues)
- Modify: `Archivist/General.py` (Fix default argument mutability `[]` -> `None` pattern)

**Step 1: Write/run type hint & format string check**

Run: `python -m pyflakes Commissioner/record_registry.py PDFix/PDFix.py`
Expected output: Identifies typing and formatting issues.

**Step 2: Implement type hint and string formatting fixes**

- In `Commissioner/record_registry.py`, fix `Literal` type arguments to use valid literal types (strings/ints/enums/None).
- In `PDFix/PDFix.py`, fix format strings like `f"{val:.2f}"` by ensuring numeric values are explicitly cast `float(val)` or removing invalid format specs on general `Any`/`object` types.
- Replace mutable default arguments (`def func(arg=[])`) with `def func(arg=None)` in `Archivist/General.py` and `Archivist/Census.py`.

**Step 3: Verify with pyflakes and pytest**

Run: `python -m pyflakes Commissioner/record_registry.py PDFix/PDFix.py`
Run: `python -m pytest Commissioner/tests PDFix/tests Archivist/tests -v`
Expected output: PASS.

**Step 4: Commit**

```bash
git add Commissioner/record_registry.py PDFix/PDFix.py Archivist/
git commit -m "fix(typing): fix literal type hints, string format specifiers, and mutable default args"
```

---

### Task 4: Remediate High-Frequency Unused Parameters and Method May Be Static Issues

**Files:**
- Modify: `Archivist/General.py` (Prefix unused parameters with `_` or apply `@staticmethod` where methods don't access `self`)
- Modify: `Archivist/HBCA.py` (Fix static method declarations)
- Modify: `Archivist/Scrip.py` (Fix static method declarations)
- Modify: `Paleographer/tests/test_agy_engine.py` (Clean up unused test parameters and static helper methods)
- Modify: `Voyageur/tests/` (Clean up unused test fixture parameters and helper methods)

**Step 1: Run flake8 checks for unused parameters and static methods**

Run: `python -m flake8 --select=F841 Archivist/ Paleographer/ Voyageur/`

**Step 2: Prefix unused parameters and add `@staticmethod` decorators**

- For methods that do not read or write `self`, add `@staticmethod` decorator and remove `self` if appropriate, or keep `self` and add decorator if part of class API contract.
- For required interface parameters that are unused in specific implementations (e.g. general profile methods), prefix parameter names with an underscore `_rec`, `_identity`, `_role`.

**Step 3: Run full module test suites**

Run: `python -m pytest Archivist/tests Paleographer/tests Voyageur/tests -v`
Expected output: PASS.

**Step 4: Commit**

```bash
git add Archivist/ Paleographer/ Voyageur/
git commit -m "refactor(clean): add @staticmethod and prefix unused interface parameters with underscore"
```

---

### Task 5: Resolve Unresolved References, None-Safety, String Conversions, Variable Shadowing, and Protected Member Access

**Files:**
- Modify: `Archivist/General.py` (Fix None-checks before string `.strip()`, string conversions, shadowing names)
- Modify: `Archivist/Census.py` (Fix `HouseholdUnit | None` dict index checks and `None.__setitem__` warnings)
- Modify: `Archivist/HBCA.py` (Fix `None.get()` protection checks and protected member `_build_generic_primary_event_lines` access)
- Modify: `Archivist/Scrip.py` (Fix protected member `_build_generic_primary_event_lines` access)
- Modify: `Antiquarian.py` (Fix protected member `_canvas` access and deprecation warnings)
- Modify: `Paleographer/engine.py` & `Paleographer/Extract.py` (Fix unresolved reference warnings and broad try-except handling)
- Modify: `Voyageur/LAC.py` & `Voyageur/FS.py` (Fix None checks and exception handling)
- Modify: `tests/` (Fix `_default_root`, `_switch_tab`, and `_load_tool_schema` protected member accesses in unit tests by introducing public test helper accessors or explicit `# noqa` where testing private methods)

**Step 1: Run pytest to ensure initial suite is passing**

Run: `python -m pytest`
Expected output: PASS.

**Step 2: Refactor reference resolutions and None protections**

- In `Archivist/General.py`, `Census.py`, `HBCA.py`, `Scrip.py`, add explicit `if item is not None:` guards before calling `.strip()`, `.get()`, or bracket indexing.
- Replace bare `except:` with explicit `except Exception:` in `Paleographer/engine.py`, `Voyageur/LAC.py`, and `Voyageur/FS.py`.
- Resolve shadowing variable names in inner loops and nested helper functions.
- Update helper methods to avoid private member warnings across modules.

**Step 3: Execute full project test suite**

Run: `python -m pytest`
Expected output: PASS with 0 failures.

**Step 4: Commit**

```bash
git add Archivist/ Paleographer/ Voyageur/ Antiquarian.py tests/
git commit -m "fix(quality): add None guards, resolve references, and clean up scope shadowing"
```

---

### Task 6: Update Automated Lint Suite (`tests/test_code_quality.py`) to Match PyCharm Inspection Suite

**Files:**
- Create/Modify: `tests/test_code_quality.py`
- Modify: `AGENTS.md` (Update lint command documentation if needed)

**Step 1: Create `tests/test_code_quality.py` enforcing PyCharm-equivalent static analysis checks**

Write a pytest test file `tests/test_code_quality.py` that runs `flake8` / `pyflakes` / `pycodestyle` programmatically over all project Python modules (`Archivist/`, `Commissioner/`, `Paleographer/`, `Voyageur/`, `PDFix/`, `Registrar/`, `Gazetteer/`, `AntiquarianMCP/`, `Antiquarian.py`).

```python
import subprocess
import sys
import pytest

def test_code_quality_flake8():
    """Verify that flake8 (pycodestyle + pyflakes) reports 0 errors across the codebase."""
    cmd = [
        sys.executable, "-m", "flake8",
        "--max-line-length=120",
        "--exclude=.venv,venv,.git,__pycache__,.pytest_cache,.opencode,build,dist",
        "Archivist", "Commissioner", "Paleographer", "Voyageur",
        "PDFix", "Registrar", "Gazetteer", "AntiquarianMCP", "Antiquarian.py", "tests"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, f"Lint violations found:\n{result.stdout}\n{result.stderr}"
```

**Step 2: Run pytest to execute the new code quality test**

Run: `python -m pytest tests/test_code_quality.py -v`
Expected output: `PASSED` (0 lint violations across the codebase).

**Step 3: Run full repository test suite**

Run: `python -m pytest`
Expected output: All unit tests and the code quality lint test PASS.

**Step 4: Commit**

```bash
git add tests/test_code_quality.py
git commit -m "test(lint): add automated flake8 code quality test matching PyCharm inspection checks"
```

---
