# Task Tracking

| # | Status | Notes |
|---|--------|-------|
| 1 | ⏭️ | Skip (no new folders/files) |
| 2 | ✅ | Auto image dirs, hardcoded IMAGE_EXTENSION, removed env lookups |
| 3 | ✅ | Removed CENSUS_IMAGE_DIR/IMAGE_EXTENSION from globals, separated Parish/Scrip settings |
| 4 | ✅ | py_compile pass, YAML validation pass, A.py docstring fix applied |
| 5 | ✅ | Fixed escaped triple-quote docstring in Voyageur/A.py |
| 6 | ✅ | CHANGELOG.md updated with Added/Removed/Fixed entries |

## Infra: Remote phone access (open-code serve + Tailscale)
* ✅ `scripts/opencode-serve.ps1` — hidden launcher, reads creds from `.agent/.env`, self-healing restart loop.
* ✅ `OPENCODE_SERVER_PASSWORD`/`USERNAME` appended to `.agent/.env` (gitignored).
* ✅ Windows Firewall: allow TCP 4096, remote scope `100.64.0.0/10` (Tailscale only).
* ✅ Scheduled task `OpenCode Serve` at logon (hidden, restart-on-failure 3x/1min).
* ✅ Tailscale installed (v1.102.2), PC `100.101.188.72` + phone `100.110.192.18` on tailnet.
* ✅ Verified: `/global/health`, `/project`, `/project/current`, `/session` (200, auth required).
* 📱 Phone client: OpenCode Mobile (Play Store) → `http://100.101.188.72:4096`, user `opencode`, pw in `.agent/.env`. If "no projects", refresh/reopen app.

## Current Task: UI Cleanup - Auto Image Dirs & Tab Separation
* ✅ Removed `CENSUS_IMAGE_DIR` and `IMAGE_EXTENSION` from Global Settings (`Scriptorium.py`).
* ✅ Removed `*_IMAGE_DIR` (e.g. `CHURCH_IMAGE_DIR`, `SCRIP_IMAGE_DIR`) from `Paleographer/settings_schema.yaml` and `.pmt` field_remaps.
* ✅ Automated Image Dir resolution: `Media/<Prompt_Name>` via `TYPE_CFG.name` in `Extract.py`.
* ✅ Separated Paleographer settings: Scrip now has its own `SCRIP_GEDCOM_NAME`; Parish keeps `CHURCH_GEDCOM_NAME`/`CHURCH_MASTER_DB_NAME`.

## Test Fix Run (2026-08-11) — full suite 406 passed / 0 failed
* ✅ Fixed all 37 test failures across 5 clusters: `GENERAL_CONFIG` NameError in `Scrip.py`/`HBCA.py` (×19); stale `*_IMAGE_DIR` field_remap tests (×3); settings schema completeness (×6); migration shape tests (×3); Paleographer pipeline + census fixtures (×6).
* ✅ Completed UI-overhaul hardcoding of GEDCOM attribution values (`COPYRIGHT_START=2018`, `GEDCOM_NOTE`/`GEDCOM_CONC`) using the canonical golden values; golden fixtures byte-identical to HEAD.
* ✅ Re-added cross-cutting API/processing env keys to `GLOBAL_VARS` ("API & Processing"); exempted `PROGRAM_DIR` from the completeness test (internal); removed dead `CENSUS_IMAGE_DIR` read.
* ✅ Gates: `pycodestyle --max-line-length=120` exit 0, `py_compile` OK, code-reviewer APPROVE (minors parked in SDD ledger).
* ⏭ Parked (deferred, non-blocking): inert `HBCA_MAX_WORKERS`/`LAC_MAX_WORKERS` schema keys, `MASTER_DB` tooltip wording, dead `conftest.py` `IMAGE_DIR` setdefault, goldens' machine-`.env` `ORG_NAME` dependence.

## SDD Subagent Pipeline Smoke Test (2026-08-10)
* ✅ Ran synthetic scratch task through full SDD loop (implementer → task-reviewer → code-reviewer → fix → re-reviewer): 12/12 tests passed, review PASS/PASS, all findings addressed.
* ✅ Provider fix: `nemotron-3-ultra-free` (task-reviewer) and `north-mini-code-free` (re-reviewer) broken upstream on OpenCode Zen ("Upstream request failed"/"Unexpected server error"); replaced with verified-working `deepseek-v4-flash-free` and `mimo-v2.5-free` in `.opencode/agents/`.
* ✅ `opencode.json` `small_model` moved off dead `north-mini-code-free` → `opencode/mimo-v2.5-free`.
* ✅ `build.md` cost-routing text + DONE_WITH_CONCERNS brief-correction convention updated.
* ⏭ Open: `opencode.json` is untracked — consider committing so model routing is version-controlled (code-reviewer recommendation).

## Local-Only Paths (2026-08-10)
* ✅ `.gitignore` covers `/.opencode/`, `/Working/`, `/AGENTS.md` (consolidated duplicate `/.opencode/` entries; kept `/scripts/opencode-serve.*` ignores).
* ✅ Untracked from index: `.opencode/agents/*`, `Working/HBCA/*` (SearchLinks + checkpoint), `AGENTS.md` via `git rm -r --cached` — files remain on disk.
* ✅ Committed as `725adb5` "chore: untrack local-only paths (.opencode/agents, Working, AGENTS.md)" — 58 files, +9/−1058.

## /superpowers Slash Command (2026-08-11)
* ✅ Created `.opencode/command/superpowers.md` — `/superpowers <goal>` routes to the `superpowers` primary agent via `agent: superpowers`; template passes the goal as `$ARGUMENTS` and requires plan-then-build.
* ✅ Fixed `.opencode/agents/superpowers.md` stale skill refs: `.agent/skills/` (singular) + nonexistent `brainstorming`/`writing-plans`/`executing-plans`/`verification-before-completion` → real registered skills (planner, plan-checker, executor, verifier, empirical-validation, etc.) loaded via the skill tool; plan location corrected to `docs/superpowers/plans/`.
* ✅ Full SDD loop passed: implementer DONE_WITH_CONCERNS (description frontmatter named stale skills as prose) → controller spec fix → fix round → task-reviewer REQUIRED-ALL-MET/PASS → code-reviewer CLEAR TO COMPLETE.
* ✅ `.opencode/` remains local-only (untracked); restart opencode for the new command to load.

## AGENTS.md Refresh (2026-08-11, /init)
* ✅ Regenerated `AGENTS.md` (was 22-line stub): full architecture (Commissioner root + 3 pipeline stages + leaf utilities), verified commands (pytest/pycodestyle/py_compile/YAML-validation), data contracts (.pmt, settings_schema.yaml, Media convention, golden-file discipline), SDD working conventions, planning layout, environment + local-only paths.
* ✅ Fact-check pass (task-reviewer): 4 Minor findings (conftest sys.path, `.agent/skills` ≠ copies, "everything else committed" overbroad, schema-completeness exemption) — all fixed directly; no Critical/Important.
* ✅ `AGENTS.md` is local-only (gitignored); new sessions load the refreshed manual automatically.
