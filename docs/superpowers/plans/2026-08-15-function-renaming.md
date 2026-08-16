# Function Renaming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename 8 cryptic/inconsistent function names across Commissioner, Archivist, and Voyageur to clear, verb-led, PEP8-compliant names, with every caller verified against real grep output rather than assumed.

**Architecture:** Each function is renamed with PyCharm's semantic `rename_refactoring` tool, which resolves the symbol (not text) and updates every real reference project-wide in one operation. Every caller list below was independently verified via repo-wide grep before writing this plan, and is re-checked by grep after each rename as a sanity pass — not the primary safety mechanism, since the tool itself is symbol-aware.

**Tech Stack:** Python, pytest, pycodestyle.

**Supersedes:** `docs/plans/2026-08-15-function-renaming-design.md` and `docs/plans/2026-08-15-commissioner-refactoring.md` (both untracked drafts started by Gemini/Antigravity). Those drafts correctly identified the same 3 Commissioner targets (`cap_case`, `parse_to_iso`, `validate_soft`) but their own caller-list examples were wrong when checked against real grep output (e.g. claimed `cap_case` was called from `Paleographer/Extract.py` alone; it's actually called from 8 files across 3 different `cap_case` implementations — see Corrections below). This plan replaces them; the two draft files should be deleted once this plan is approved, not kept alongside it.

## Corrections to the original design

Three findings from auditing Commissioner (all 25 functions), Voyageur, Archivist, and Paleographer (all files, excluding tests) before writing this plan:

1. **`cap_case` is three independent functions, not one.** `Commissioner/normalization.py:30`, `Archivist/Utils.py:166`, and `Voyageur/census_schema.py:56` are three separate implementations with the same name and near-identical bodies. A blind repo-wide find-and-replace of the string `cap_case` (implied by the original draft's "grep_search and replace" method) would rename all three at once, including two that were never scoped by the original Commissioner-only plan. Tasks 1, 4, and 5 below rename each independently, with explicit caller lists per implementation so no task's replacement touches another's callers.
2. **Only 8 functions total warrant renaming** across the four modules audited. Everything else — 22 of Commissioner's 25 functions, and effectively all of Paleographer, Archivist, and Voyageur beyond the 6 flagged below — is already clear, verb-led, PEP8 snake_case. This is not a codebase-wide rewrite; it's 8 precise renames.
3. **Consolidating the three `cap_case` implementations into one shared function is a separate, larger refactor** (behavior de-duplication, not renaming) and is explicitly out of scope here. Flagging it for a future decision, not building it now.

## Global Constraints

- Comments: terse, single-line, WHY-only. No AI attribution anywhere.
- Every rename task's caller list below was produced by a real grep run this session, not estimated — do not add or skip a caller without re-running the grep yourself if the file has changed since.
- **Execution mechanism:** each rename is performed with the `mcp__pycharm__rename_refactoring` tool (`pathInProject`, `symbolName`, `newName`, `projectPath`), not text-based find/replace and not AI delegation — it resolves the symbol semantically (imports, scope), so it cannot cross-contaminate a same-named-but-different function living in another file, and it does not touch comments/strings that merely mention the name. `projectPath` is `C:/Users/Jason Cole/Documents/Genealogy/Scriptorium` on every call. Treat a "success" response as provisional, not proof — always follow with the task's own test run and a repo-wide grep for the old name before committing.
- Run Python tests with: `pytest <scoped path> -q` (path given per task); full suite with `pytest . -q` in the final task.
- Lint with: `python -m pycodestyle --max-line-length=120 <touched files>`.

---

### Task 1: Rename Commissioner's `cap_case` → `capitalize_text_string`

**Files:**
- Modify: `Commissioner/normalization.py:30`
- Modify: `Paleographer/Extract.py:56,114`
- Modify: `Voyageur/FS.py:191,260,274`
- Modify: `Commissioner/tests/test_normalization.py:42`

**Interfaces:**
- Produces: `capitalize_text_string(text: str) -> str` in `Commissioner/normalization.py`, same signature and body as today's `cap_case`.
- Consumes: nothing new — pure rename, no behavior change.

**Do NOT touch:** `Archivist/Utils.py::cap_case` or `Voyageur/census_schema.py::cap_case` — separate functions, separate tasks (4 and 5).

- [ ] **Step 1: Confirm baseline passes**

Run: `pytest Commissioner/tests/test_normalization.py Paleographer/tests/ Voyageur/tests/test_fs.py -q`
Expected: PASS (baseline, before any change)

- [ ] **Step 2: Confirm current caller set is unchanged**

Run: `grep -rn "cap_case" --include="*.py" . | grep -v "Utils.cap_case\|Archivist/Utils.py\|census_schema"`
Expected: exactly the 5 lines listed in Files above, plus the definition itself (`Commissioner/normalization.py:30`) — if anything else appears, stop and re-scope before delegating.

- [ ] **Step 3: Rename via PyCharm**

Call `mcp__pycharm__rename_refactoring`:
- `pathInProject`: `Commissioner/normalization.py`
- `symbolName`: `cap_case`
- `newName`: `capitalize_text_string`
- `projectPath`: `C:/Users/Jason Cole/Documents/Genealogy/Scriptorium`

Expected: success, with all 5 real call sites (`Paleographer/Extract.py:56,114`, `Voyageur/FS.py:191,260,274`) and the test call (`Commissioner/tests/test_normalization.py:42`) updated automatically. `Archivist/Utils.py` and `Voyageur/census_schema.py` are untouched — different symbols, resolved separately.

- [ ] **Step 4: Verify — run tests**

Run: `pytest Commissioner/tests/test_normalization.py Paleographer/tests/ Voyageur/tests/test_fs.py -q`
Expected: PASS

- [ ] **Step 5: Verify — confirm zero stale references and zero cross-contamination**

Run: `grep -rn "cap_case" --include="*.py" .`
Expected: only 2 matches remain — `Archivist/Utils.py:166` and `Voyageur/census_schema.py:56` (both untouched, out of scope for this task).

- [ ] **Step 6: Lint and commit**

Run: `python -m pycodestyle --max-line-length=120 Commissioner/normalization.py Paleographer/Extract.py Voyageur/FS.py Commissioner/tests/test_normalization.py`
Expected: exit 0

```bash
git add Commissioner/normalization.py Paleographer/Extract.py Voyageur/FS.py Commissioner/tests/test_normalization.py
git commit -m "refactor(commissioner): rename cap_case to capitalize_text_string"
```

---

### Task 2: Rename Commissioner's `parse_to_iso` → `parse_date_to_iso_format`

**Files:**
- Modify: `Commissioner/normalization.py:57`
- Modify: `Voyageur/FS.py:252,254,272,273`
- Modify: `Paleographer/Extract.py:280,286,288`
- Modify: `Commissioner/tests/test_normalization.py:46`

**Interfaces:**
- Produces: `parse_date_to_iso_format(reading: Optional[str]) -> Optional[str]`, same body as today's `parse_to_iso`. This is the only function of this name in the repo — no cross-contamination risk like Task 1.

- [ ] **Step 1: Confirm baseline passes**

Run: `pytest Commissioner/tests/test_normalization.py Voyageur/tests/test_fs.py Paleographer/tests/ -q`
Expected: PASS

- [ ] **Step 2: Rename via PyCharm**

Call `mcp__pycharm__rename_refactoring`:
- `pathInProject`: `Commissioner/normalization.py`
- `symbolName`: `parse_to_iso`
- `newName`: `parse_date_to_iso_format`
- `projectPath`: `C:/Users/Jason Cole/Documents/Genealogy/Scriptorium`

Expected: success, with all 7 call sites (`Voyageur/FS.py:252,254,272,273`, `Paleographer/Extract.py:280,286,288`) and the test (`Commissioner/tests/test_normalization.py:46`) updated automatically.

- [ ] **Step 3: Verify — tests and stale-reference check**

Run: `pytest Commissioner/tests/test_normalization.py Voyageur/tests/test_fs.py Paleographer/tests/ -q`
Expected: PASS

Run: `grep -rn "parse_to_iso" --include="*.py" .`
Expected: no matches.

- [ ] **Step 4: Lint and commit**

Run: `python -m pycodestyle --max-line-length=120 Commissioner/normalization.py Voyageur/FS.py Paleographer/Extract.py Commissioner/tests/test_normalization.py`
Expected: exit 0

```bash
git add Commissioner/normalization.py Voyageur/FS.py Paleographer/Extract.py Commissioner/tests/test_normalization.py
git commit -m "refactor(commissioner): rename parse_to_iso to parse_date_to_iso_format"
```

---

### Task 3: Rename Commissioner's `validate_soft` → `validate_collection_softly`

**Files:**
- Modify: `Commissioner/record_registry.py:164`
- Modify: `Voyageur/LAC.py:142`, `Voyageur/HBCA.py:708`, `Voyageur/FS.py:459`, `Voyageur/census_schema.py:328`
- Modify: `Paleographer/Extract.py:327`
- Modify: `Commissioner/tests/test_record_registry.py:322,331,338`

**Interfaces:**
- Produces: `validate_collection_softly(data: dict, document_type: str, label: str) -> None`, same body. Only definition of this name in the repo.

- [ ] **Step 1: Confirm baseline passes**

Run: `pytest Commissioner/tests/test_record_registry.py Voyageur/tests/ Paleographer/tests/ -q`
Expected: PASS

- [ ] **Step 2: Rename via PyCharm**

Call `mcp__pycharm__rename_refactoring`:
- `pathInProject`: `Commissioner/record_registry.py`
- `symbolName`: `validate_soft`
- `newName`: `validate_collection_softly`
- `projectPath`: `C:/Users/Jason Cole/Documents/Genealogy/Scriptorium`

Expected: success, with the definition, every import statement, and all 9 call sites (`Voyageur/LAC.py:142`, `Voyageur/HBCA.py:708`, `Voyageur/FS.py:459`, `Voyageur/census_schema.py:328`, `Paleographer/Extract.py:327`, `Commissioner/tests/test_record_registry.py:322,331,338`) updated automatically.

- [ ] **Step 3: Verify — tests and stale-reference check**

Run: `pytest Commissioner/tests/test_record_registry.py Voyageur/tests/ Paleographer/tests/ -q`
Expected: PASS

Run: `grep -rn "validate_soft" --include="*.py" .`
Expected: no matches.

- [ ] **Step 4: Lint and commit**

Run: `python -m pycodestyle --max-line-length=120 Commissioner/record_registry.py Voyageur/LAC.py Voyageur/HBCA.py Voyageur/FS.py Voyageur/census_schema.py Paleographer/Extract.py Commissioner/tests/test_record_registry.py`
Expected: exit 0

```bash
git add Commissioner/record_registry.py Voyageur/LAC.py Voyageur/HBCA.py Voyageur/FS.py Voyageur/census_schema.py Paleographer/Extract.py Commissioner/tests/test_record_registry.py
git commit -m "refactor(commissioner): rename validate_soft to validate_collection_softly"
```

---

### Task 4: Rename Archivist's `cap_case` → `capitalize_text_string`

**Files:**
- Modify: `Archivist/Utils.py:166` (definition), `Archivist/Utils.py:179` (internal self-call inside `clean_place()`)
- Modify: `Archivist/Census.py:947,949,951,953,955,956,1391`
- Modify: `Archivist/General.py:87,131,342,733,734,735,1137`
- Modify: `Archivist/HBCA.py:54`

**Interfaces:**
- Produces: `capitalize_text_string(text: CellValue) -> str` in `Archivist/Utils.py`, same body, same docstring content. A DIFFERENT function from Task 1's — both end up named `capitalize_text_string` but live in different modules (`Utils.capitalize_text_string` vs `normalization.capitalize_text_string`), which is the intended, consistent outcome, not a collision.

**Do NOT touch:** `Commissioner/normalization.py::capitalize_text_string` (Task 1's, already renamed by the time this task runs) or `Voyageur/census_schema.py::cap_case` (Task 5).

- [ ] **Step 1: Confirm baseline passes**

Run: `pytest Archivist/tests/ -q`
Expected: PASS

- [ ] **Step 2: Rename via PyCharm**

Call `mcp__pycharm__rename_refactoring`:
- `pathInProject`: `Archivist/Utils.py`
- `symbolName`: `cap_case`
- `newName`: `capitalize_text_string`
- `projectPath`: `C:/Users/Jason Cole/Documents/Genealogy/Scriptorium`

Expected: success, with the internal caller (`clean_place()` at `Utils.py:179`) and every external call site (`Archivist/Census.py:947,949,951,953,955,956,1391`, `Archivist/General.py:87,131,342,733,734,735,1137`, `Archivist/HBCA.py:54`) updated automatically. `Commissioner/normalization.py` and `Voyageur/census_schema.py` are untouched — different symbols.

- [ ] **Step 3: Verify — tests and stale-reference check**

Run: `pytest Archivist/tests/ -q`
Expected: PASS

Run: `grep -rn "Utils\.cap_case\|Archivist/Utils.py.*def cap_case" .`
Expected: no matches.

Run: `grep -rn "cap_case" --include="*.py" .`
Expected: only `Voyageur/census_schema.py:56` remains (Task 5, not yet run).

- [ ] **Step 4: Lint and commit**

Run: `python -m pycodestyle --max-line-length=120 Archivist/Utils.py Archivist/Census.py Archivist/General.py Archivist/HBCA.py`
Expected: exit 0

```bash
git add Archivist/Utils.py Archivist/Census.py Archivist/General.py Archivist/HBCA.py
git commit -m "refactor(archivist): rename cap_case to capitalize_text_string"
```

---

### Task 5: Rename Voyageur's `census_schema.cap_case` → `capitalize_text_string`

**Files:**
- Modify: `Voyageur/census_schema.py:56` (definition), `:182,193` (internal callers, only callers that exist)

**Interfaces:**
- Produces: `capitalize_text_string(text: str) -> str` in `Voyageur/census_schema.py`, internal-only (no external callers found in this session's audit or the earlier repo-wide `cap_case` grep).

- [ ] **Step 1: Confirm baseline passes**

Run: `pytest Voyageur/tests/test_census_schema.py -q`
Expected: PASS (adjust path if the actual test file differs — confirm with `ls Voyageur/tests/ | grep -i census_schema` first if this fails)

- [ ] **Step 2: Rename via PyCharm**

Call `mcp__pycharm__rename_refactoring`:
- `pathInProject`: `Voyageur/census_schema.py`
- `symbolName`: `cap_case`
- `newName`: `capitalize_text_string`
- `projectPath`: `C:/Users/Jason Cole/Documents/Genealogy/Scriptorium`

Expected: success, with the two internal callers (lines 182, 193) updated. No external callers exist — confirmed via repo-wide grep this session — so no other file changes.

- [ ] **Step 3: Verify — tests and stale-reference check**

Run: `pytest Voyageur/tests/test_census_schema.py -q`
Expected: PASS

Run: `grep -rn "cap_case" --include="*.py" .`
Expected: no matches anywhere in the repo (Tasks 1, 4, 5 all complete by this point).

- [ ] **Step 4: Lint and commit**

Run: `python -m pycodestyle --max-line-length=120 Voyageur/census_schema.py`
Expected: exit 0

```bash
git add Voyageur/census_schema.py
git commit -m "refactor(voyageur): rename census_schema's cap_case to capitalize_text_string"
```

---

### Task 6: Rename Archivist's `spouse_evaluation` → `evaluate_spouse_match`

**Files:**
- Modify: `Archivist/Census.py:246` (definition), `:353,377` (internal callers)

**Interfaces:**
- Produces: `evaluate_spouse_match(a: pd.Series, b: pd.Series) -> Tuple[bool, float, str]`, same body. Internal-only, no external callers.

- [ ] **Step 1: Confirm baseline passes**

Run: `pytest Archivist/tests/test_census.py -q`
Expected: PASS

- [ ] **Step 2: Rename via PyCharm**

Call `mcp__pycharm__rename_refactoring`:
- `pathInProject`: `Archivist/Census.py`
- `symbolName`: `spouse_evaluation`
- `newName`: `evaluate_spouse_match`
- `projectPath`: `C:/Users/Jason Cole/Documents/Genealogy/Scriptorium`

Expected: success, with both callers (lines 353, 377) updated. No other file references this function.

- [ ] **Step 3: Verify — tests and stale-reference check**

Run: `pytest Archivist/tests/test_census.py -q`
Expected: PASS

Run: `grep -rn "spouse_evaluation" --include="*.py" .`
Expected: no matches.

- [ ] **Step 4: Lint and commit**

Run: `python -m pycodestyle --max-line-length=120 Archivist/Census.py`
Expected: exit 0

```bash
git add Archivist/Census.py
git commit -m "refactor(archivist): rename spouse_evaluation to evaluate_spouse_match"
```

---

### Task 7: Rename Archivist's `child_evaluation` → `evaluate_child_match`

**Files:**
- Modify: `Archivist/Census.py:265` (definition), `:310` (internal caller)

**Interfaces:**
- Produces: `evaluate_child_match(unit: HouseholdUnit, member: pd.Series) -> Tuple[bool, float, str]`, same body. Internal-only.

- [ ] **Step 1: Confirm baseline passes**

Run: `pytest Archivist/tests/test_census.py -q`
Expected: PASS

- [ ] **Step 2: Rename via PyCharm**

Call `mcp__pycharm__rename_refactoring`:
- `pathInProject`: `Archivist/Census.py`
- `symbolName`: `child_evaluation`
- `newName`: `evaluate_child_match`
- `projectPath`: `C:/Users/Jason Cole/Documents/Genealogy/Scriptorium`

Expected: success, with the one caller (line 310) updated. No other file references this function.

- [ ] **Step 3: Verify — tests and stale-reference check**

Run: `pytest Archivist/tests/test_census.py -q`
Expected: PASS

Run: `grep -rn "child_evaluation" --include="*.py" .`
Expected: no matches.

- [ ] **Step 4: Lint and commit**

Run: `python -m pycodestyle --max-line-length=120 Archivist/Census.py`
Expected: exit 0

```bash
git add Archivist/Census.py
git commit -m "refactor(archivist): rename child_evaluation to evaluate_child_match"
```

---

### Task 8: Rename Voyageur's `sex_code` → `normalize_sex_code`

**Files:**
- Modify: `Voyageur/FS.py:169` (definition), `:241` (internal caller)

**Interfaces:**
- Produces: `normalize_sex_code(raw: str) -> str`, same body. Internal-only — the name `sex_code` reads as a noun/label, not a verb that normalizes raw text into `"M"`/`"F"`/`""`.

- [ ] **Step 1: Confirm baseline passes**

Run: `pytest Voyageur/tests/test_fs.py -q`
Expected: PASS

- [ ] **Step 2: Rename via PyCharm**

Call `mcp__pycharm__rename_refactoring`:
- `pathInProject`: `Voyageur/FS.py`
- `symbolName`: `sex_code`
- `newName`: `normalize_sex_code`
- `projectPath`: `C:/Users/Jason Cole/Documents/Genealogy/Scriptorium`

Expected: success, with the one caller (line 241) updated. No other file references this function.

- [ ] **Step 3: Verify — tests and stale-reference check**

Run: `pytest Voyageur/tests/test_fs.py -q`
Expected: PASS

Run: `grep -rn "sex_code" --include="*.py" . | grep -v "SEX_COLUMN_MAP\|sex_code_map"`
Expected: no matches (excludes any unrelated constant names that happen to contain the substring — confirm none exist before treating this as clean).

- [ ] **Step 4: Lint and commit**

Run: `python -m pycodestyle --max-line-length=120 Voyageur/FS.py`
Expected: exit 0

```bash
git add Voyageur/FS.py
git commit -m "refactor(voyageur): rename sex_code to normalize_sex_code"
```

---

### Task 9: Full-suite verification and cleanup of the superseded drafts

**Files:**
- Delete: `docs/plans/2026-08-15-function-renaming-design.md`, `docs/plans/2026-08-15-commissioner-refactoring.md` (both untracked, superseded by this plan)

- [ ] **Step 1: Run the full test suite**

Run: `pytest . -q`
Expected: PASS, same total count as pre-refactor baseline (no tests silently dropped or newly failing).

- [ ] **Step 2: Full repo-wide check for any of the 8 old names**

Run: `grep -rn "\bcap_case\b\|\bparse_to_iso\b\|\bvalidate_soft\b\|\bspouse_evaluation\b\|\bchild_evaluation\b\|\bsex_code\b" --include="*.py" .`
Expected: no matches anywhere — including docstrings, comments, and non-test files this plan's per-task greps might not have covered.

- [ ] **Step 3: Full pycodestyle pass**

Run: `python -m pycodestyle --max-line-length=120 Commissioner/ Archivist/ Voyageur/ Paleographer/`
Expected: exit 0

- [ ] **Step 4: Remove the superseded draft files**

```bash
rm docs/plans/2026-08-15-function-renaming-design.md docs/plans/2026-08-15-commissioner-refactoring.md
```

(No `git rm` needed — both are untracked.)

- [ ] **Step 5: Update task tracking**

Add a row to `docs/plans/task.md` recording this plan's completion, per this project's task-tracking convention.

---

## Self-Review

**Spec coverage:** all 8 confirmed candidates from the Commissioner/Voyageur/Archivist/Paleographer audit have a task. Paleographer had zero candidates, so no Paleographer rename task exists — correctly reflects the audit, not an omission.

**Placeholder scan:** no TBD/TODO. Task 5's baseline-test path has a fallback instruction (`ls` to find the real file) rather than a guessed path, since the audit didn't confirm the exact census_schema test filename — this is a concrete instruction to resolve a real unknown, not a vague placeholder.

**Type consistency:** every task's proposed new name matches across its own Interfaces block, delegate instructions, and verification greps. The two `capitalize_text_string` outcomes (Tasks 1 and 4) are explicitly called out as separate functions in separate modules, not a naming collision, in both tasks' Interfaces blocks.

**Cross-task ordering:** Tasks 1, 4, and 5 (the three `cap_case` variants) are independent and can run in any order relative to each other, but each task's "confirm remaining cap_case count" step assumes the stated prior tasks are already done — if executed out of order, adjust the expected leftover count accordingly (called out inline in Tasks 4 and 5).

---

Plan complete and saved to `docs/superpowers/plans/2026-08-15-function-renaming.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
