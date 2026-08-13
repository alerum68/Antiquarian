# Resolve Reviewer Debt Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close out every parked item from the SDD ledger and the code-reviewer's minor findings from the 2026-08-11 test-fix run, leaving the repo debt-free: functional `HBCA_MAX_WORKERS`, no dead `LAC_MAX_WORKERS` schema key, an accurate `MASTER_DB` tooltip, no dead `IMAGE_DIR` env fallback, machine-independent Archivist golden tests, and GSD-standard checkboxes in historical plan docs. Items D6 (benign whitespace hunks in `HBCA.py`) and D7 (untracked `opencode.json`) are **no-ops** — D6 is harmless committed content and D7 is deliberately gitignored at `.gitignore:21` per AGENTS.md's local-only policy, so committing it would violate convention.

**Architecture:** Four independent, file-disjoint tasks (all wave 1, no shared files):

- **Task 1 (Voyageur):** Replace the hardcoded `HBCA_MAX_WORKERS = 8` module constant with an env read (`os.getenv("HBCA_MAX_WORKERS", "8")`) so the launcher setting actually takes effect, preserving today's runtime behavior (default 8); align the schema default `"10"` → `"8"` and the migration-test expected shape. Remove the dead `LAC_MAX_WORKERS` schema key (LAC.py has no concurrency to wire it into) and drop it from the migration-test expected shape.
- **Task 2 (Paleographer):** Reword the `MASTER_DB` tooltip to state the real fallback (`ScripTools.py:639` uses `"master_database.json"`, not `MASTER_DB_NAME`); delete the dead `os.environ.setdefault("IMAGE_DIR", "images")` from `tests/conftest.py` (no Paleographer code reads `IMAGE_DIR` anymore — the completeness suite proves it).
- **Task 3 (Archivist):** Make the golden-file tests hermetic by pinning the exact env constants the goldens encode (`ORG_NAME`, `RESEARCHER`, `SUBM_ADDRESS`, plus any other `Utils.py` GLOBAL_VARS constants appearing in the SUBM/header/SOUR blocks) in `Archivist/tests/conftest.py` *before* test modules import `Utils` — the goldens were captured with this machine's values, so forcing the same values is behavior-preserving and removes the machine-`.env` dependence.
- **Task 4 (Docs):** Normalize the 453 non-standard `-x[ ]` markers across 13 historical plan docs to GSD-standard `- [ ]` (unchecked = not executed) and add a `> **SUPERSEDED:**` banner to each affected file so the historical meaning is preserved and documented (per GSD: checklists use only `- [ ]`/`- [x]`; the tracker records cancelled status separately).

**Tech Stack:** Python 3.12, pytest, pycodestyle, YAML, PowerShell (mechanical doc normalization).

## Global Constraints

- Golden-file discipline: NEVER re-run `capture_golden_gedcom.py` to make a test pass; Task 3 must make tests hermetic without touching golden files.
- Completeness test contract: every tool-specific `os.getenv`/`os.environ.get` key must remain present in its tool's `settings_schema.yaml` (GLOBAL_VARS keys and `PROGRAM_DIR` exempt). After Task 1, `HBCA_MAX_WORKERS` becomes an env read — it must stay in `Voyageur/settings_schema.yaml`.
- Behavior-preserving debt cleanup: default `HBCA_MAX_WORKERS` stays `8` (current runtime behavior); only the schema default text changes `"10"` → `"8"`.
- Test gates: `python -m pytest` full suite stays green (406 expected — migration-test expected shapes update in Task 1), `python -m pycodestyle --max-line-length=120` exit 0, `python -m py_compile` on every touched `.py`.
- No new files unless required; one commit per task; update `docs/plans/task.md` (table-only live tracker) after each task.
- All work on branch `Unify`.

### Task 1 — Voyageur settings debt (D1: wire `HBCA_MAX_WORKERS`; D2: remove dead `LAC_MAX_WORKERS`)

- [x] **1a. Wire `HBCA_MAX_WORKERS` in `Voyageur/HBCA.py`:**
  - Replace line 87's module constant `HBCA_MAX_WORKERS = 8` with `HBCA_MAX_WORKERS = int(os.getenv("HBCA_MAX_WORKERS", "8"))`. Verify `os` is imported in the file (grep first; it reads env elsewhere, so it should already be). Keep the constant name unchanged — line 731 uses it as a default parameter value (`max_workers: int = HBCA_MAX_WORKERS`), which keeps working unchanged.
  - AVOID changing the default to `"10"` — that would silently raise concurrency 8→10 for everyone not setting the env var.
- [x] **1b. Align schema default in `Voyageur/settings_schema.yaml`:** change `HBCA_MAX_WORKERS` default `"10"` → `"8"` (line 70) so the launcher shows what the code actually uses.
- [x] **1c. Remove dead `LAC_MAX_WORKERS` from `Voyageur/settings_schema.yaml`:** delete the key block (lines 39-41). Grep the whole repo first (`rg "LAC_MAX_WORKERS"` ) to confirm no code or test reads it (LAC.py has no ThreadPool/executor/concurrency at all). AVOID wiring it into LAC.py — there is no worker pool to drive, so the key is dead weight (YAGNI).
- [x] **1d. Update `tests/test_scriptorium_settings_migration.py`:** in `test_voyageur_schema_matches_expected_shape`, remove `"LAC_MAX_WORKERS": "1",` from the `"LAC"` section and change `"HBCA_MAX_WORKERS": "10"` → `"8"` in the `"HBCA / Manitoba Archives"` section. These are intentional, schema-aligned changes (not "make the test pass" hacks).
- [x] **1e. Verify:** `python -m py_compile Voyageur/HBCA.py`; `python -m pytest tests/test_scriptorium_settings_migration.py tests/test_settings_schema_completeness.py tests/test_load_tool_schema.py -v`; `python -m pytest Voyageur/tests -v`; `python -m pycodestyle --max-line-length=120 Voyageur/HBCA.py`.
- [x] **1f. Commit:** one commit, message like `fix(Voyageur): wire HBCA_MAX_WORKERS, remove dead LAC_MAX_WORKERS` — only the three touched files.

### Task 2 — Paleographer tooltip + dead conftest env (D3, D4)

- [x] **2a. Reword `MASTER_DB` tooltip in `Paleographer/settings_schema.yaml` (line 19).** Current text claims "Leave blank to use the active record type's own MASTER_DB_NAME setting" — false for the Scrip enrichment/partitioning tools: `ScripTools.py:639/659/671/684` fall back to the literal `"master_database.json"`. New wording must state the real fallback, e.g.: `"Path to the JSON master database used by the Scrip enrichment/partitioning tools. Leave blank to use the default 'master_database.json'."` (verify the exact resolve behavior in `ScripTools.py` before finalizing wording).
- [x] **2b. Delete dead line in `Paleographer/tests/conftest.py`:** remove `os.environ.setdefault("IMAGE_DIR", "images")` (line 15). Keep the `MASTER_DB_NAME` and `MODEL_NAME` setdefaults (lines 13-14) — those are still read. Confirm nothing in `Paleographer/` reads `IMAGE_DIR` via env (grep; the schema-completeness suite already proves no `os.getenv("IMAGE_DIR")` remains).
- [x] **2c. Verify:** `python -m pytest tests/test_settings_schema_completeness.py tests/test_load_tool_schema.py -v`; `python -m pytest Paleographer/tests -v`; `python -m py_compile Paleographer/tests/conftest.py`; `python -m pycodestyle --max-line-length=120 Paleographer/tests/conftest.py`.
- [x] **2d. Commit:** one commit, e.g. `docs(Paleographer): fix MASTER_DB tooltip; drop dead IMAGE_DIR test fallback`.

### Task 3 — Archivist golden hermeticity (D5)

- [x] **3a. Audit which env constants the goldens encode:** read `Archivist/Utils.py` around line 53 (`ORG_NAME = os.getenv(...)`) and every other GLOBAL_VARS constant used by `General.py`/`Scrip.py` in the GEDCOM header, SUBM, and Source blocks. The goldens (`scrip_rm.ged`, `scrip_ftm.ged`, `parish_rm.ged`, `parish_ftm.ged`) encode at least `ORG_NAME` ("Michif Genealogical Society"), `RESEARCHER` ("Jason Cole"), and the SUBM address/`_WEBTAG` URLs — identify the exact env keys feeding those values (grep the golden files for the encoded strings, then trace back to their `os.getenv` sources in `Utils.py`).
- [x] **3b. Pin the values in `Archivist/tests/conftest.py`:** at the top of the file, *before* any module import that triggers `Utils` load, set `os.environ` for each identified key to the exact value the goldens encode (plain assignment, e.g. `os.environ["ORG_NAME"] = "Michif Genealogical Society"` — NOT `setdefault`, so a developer's root `.env` can't override and break hermeticity). `conftest.py` runs before test modules under pytest, so this lands before `test_archivist_dispatcher.py`'s `import Utils` at line 10. AVOID `setdefault` (allows machine `.env` to override → still machine-dependent).
- [x] **3c. Confirm `_regenerate` needs no other pinning:** `test_archivist_dispatcher.py` already pins `General.IMAGE_DIR` (line 45) and normalizes DATE/TIME (line 49) — leave those. If `Utils.safe_path` on any remaining env-derived path differs from the golden, pin that env key in conftest too rather than touching the golden.
- [x] **3d. Prove hermeticity empirically:** run the golden tests twice — once normally, once with the env vars forcibly cleared (e.g. `$env:ORG_NAME=''; $env:RESEARCHER=''; $env:SUBM_ADDRESS=''; python -m pytest Archivist/tests/test_archivist_dispatcher.py -v`). Both runs must pass identically. Then `python -m pytest Archivist/tests -v` (includes census ingestion), `python -m py_compile Archivist/tests/conftest.py`.
- [x] **3e. Commit:** one commit, e.g. `test(Archivist): make golden GEDCOM tests hermetic (pin env constants)`.

### Task 4 — Plan-docs checkbox normalization (code-reviewer finding: `-x[ ]` × 453)

- [x] **4a. Normalize the 13 affected plan docs under `docs/superpowers/plans/`:** for each file containing `-x[` (confirmed: `2026-08-06-census-commissioner-wiring.md`, `2026-08-06-paleographer-structural-split.md`, `2026-08-06-paleographer-voyageur-debt-cleanup.md`, `2026-08-06-program-documentation.md`, `2026-08-06-scaffold-contract-extensibility.md`, `2026-08-06-voyageur-dispatcher-consolidation.md`, `2026-08-06-voyageur-parish-scrip-scaffold.md`, `2026-08-07-archivist-structural-split.md`, `2026-08-07-close-out-open-issues.md`, `2026-08-07-scriptorium-settings-redesign.md`, `2026-08-08-archivist-source-id-resolution.md`, `2026-08-08-familysearch-household-view-gather.md`, `2026-08-09-scriptorium-ui-overhaul.md`):
  - Replace every `-x[ ]` with `- [ ]` (GSD-standard unchecked checkbox — these steps were never executed, so unchecked is the honest state). Mechanical replace only; do not touch task text.
  - Add a `> **SUPERSEDED:**` banner near the top of each affected file (after the header blockquote/`Goal:` block) documenting that steps marked `- [ ]` were superseded and not executed, preserving the historical meaning GSD's tracker records as cancelled.
  - PowerShell one-liner for the replace (example): `Get-ChildItem docs/superpowers/plans/*.md | ForEach-Object { (Get-Content $_.FullName -Raw) -replace '-x\[ \]', '- [ ]' | Set-Content $_.FullName -NoNewline }` — then verify with `Select-String -Path "docs\superpowers\plans\*.md" -Pattern "-x\["` → zero matches.
- [x] **4b. Verify:** `(Select-String -Path "docs\superpowers\plans\*.md" -Pattern "-x\[").Count -eq 0`; spot-check 2-3 files render as valid checkbox lists and the SUPERSEDED banner reads correctly. No Python tests affected, but run `python -m pytest tests -q` to be safe.
- [x] **4c. Commit:** one commit, e.g. `docs(plans): normalize -x[ ] markers to GSD-standard checkboxes with SUPERSEDED banners`.

## Verification

- [x] Full suite: `python -m pytest` → 406 passed, 0 failed (migration-shape changes in Task 1 are the only expected test edits).
- [x] `python -m pycodestyle --max-line-length=120` exit 0.
- [x] `python -m py_compile` on all touched `.py` files.
- [x] Schema completeness + load-tool-schema tests green after both schema changes.
- [x] Golden tests pass with env vars cleared (Task 3d empirical proof).
- [x] Zero `-x[` occurrences remain in `docs/superpowers/plans/`.
- [x] `docs/plans/task.md` updated after every task; D6/D7 documented as no-ops.
- [x] All four task commits on branch `Unify`, then final push.

## Success Criteria

- [x] All ledger debt D1–D5 resolved and committed; D6/D7 explicitly ruled no-op in `docs/plans/task.md`.
- [x] All four tasks verified with evidence (test output, grep counts, pycodestyle/py_compile exit 0).
- [x] Full suite green on branch `Unify`; working tree clean.
