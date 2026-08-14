# Task Tracking

| # | Status | Notes |
|---|--------|-------|
| 1 | ⏭️ | Skip (no new folders/files) |
| 2 | ✅ | Auto image dirs, hardcoded IMAGE_EXTENSION, removed env lookups |
| 3 | ✅ | Removed CENSUS_IMAGE_DIR/IMAGE_EXTENSION from globals, separated Parish/Scrip settings |
| 4 | ✅ | py_compile pass, YAML validation pass, A.py docstring fix applied |
| 5 | ✅ | Fixed escaped triple-quote docstring in Voyageur/A.py |
| 6 | ✅ | CHANGELOG.md updated with Added/Removed/Fixed entries |
| 7 | ✅ | Debt plan written + fully executed: `docs/superpowers/plans/2026-08-11-resolve-reviewer-debt.md` (D1–D5 committed; D6/D7 ruled no-op) |
| 8 | 🔄 | PyCharm Inspection Fixes plan in progress (`docs/plans/2026-08-13-pycharm-inspection-fixes.md`); Task 1 complete |

## Reviewer-Debt Resolution (2026-08-11) — D1–D5 closed, all verified
* ✅ **D1 (HBCA_MAX_WORKERS)** — `Voyageur/HBCA.py:87` → `int(os.getenv("HBCA_MAX_WORKERS", "8"))`; schema default `"10"`→`"8"` (`7856b39`). Task-reviewer REQUIRED-ALL-MET/PASS.
* ✅ **D2 (dead LAC_MAX_WORKERS)** — schema key + migration-test shape removed; repo grep zero refs outside docs (`7856b39`).
* ✅ **D3 (MASTER_DB tooltip)** — reworded to real fallback (`1a62204`); fix round made blank GUI honor `master_database.json` (`f3ac2e5`, re-reviewer ADDRESSED/CLEAR).
* ✅ **D4 (dead IMAGE_DIR conftest)** — `os.environ.setdefault("IMAGE_DIR", "images")` deleted; `MASTER_DB_NAME`/`MODEL_NAME` kept (`1a62204`).
* ✅ **D5 (golden hermeticity)** — `Archivist/tests/conftest.py` pins 6 env keys (ORG_NAME, RESEARCHER, SUBM_ADDRESS, MGS_GROUP_URL, ANCESTRY_GROUP_URL, ROOT_SOURCE_ID) before `Utils` import; proven byte-identical with env cleared (`6271f36`). Task-reviewer REQUIRED-ALL-MET/PASS.
* ✅ **Docs checkboxes** — 453 `-x[ ]` → `- [ ]` + SUPERSEDED banners in 13 historical plan docs (`d99370b`); 6 inline-code refs in active plan intentionally left (describing the finding itself).
* ⏭️ **D6 (whitespace hunks HBCA.py)** — no-op (harmless committed content). **D7 (untracked opencode.json)** — no-op (gitignored per local-only policy).
* ✅ Gates: full suite **406 passed**, pycodestyle exit 0, py_compile exit 0, code-reviewer verdict below.

## Infra: Remote phone access (open-code serve + Tailscale)
* ✅ `scripts/opencode-serve.ps1` — hidden launcher, reads creds from `.agent/.env`, self-healing restart loop.
* ✅ `OPENCODE_SERVER_PASSWORD`/`USERNAME` appended to `.agent/.env` (gitignored).
* ✅ Windows Firewall: allow TCP 4096, remote scope `100.64.0.0/10` (Tailscale only).
* ✅ Scheduled task `OpenCode Serve` at logon (hidden, restart-on-failure 3x/1min).
* ✅ Tailscale installed (v1.102.2), PC `100.101.188.72` + phone `100.110.192.18` on tailnet.
* ✅ Verified: `/global/health`, `/project`, `/project/current`, `/session` (200, auth required).
* 📱 Phone client: OpenCode Mobile (Play Store) → `http://100.101.188.72:4096`, user `opencode`, pw in `.agent/.env`. If "no projects", refresh/reopen app.

## Infra: SSH to Alienware (2026-08-11) - WORKING
* ✅ OpenSSH server upgraded 9.5.5.1 → 10.0.0.0p2 (`C:\WINDOWS\System32\OpenSSH`, backup `OpenSSH.bak-9.5`); service `sshd` LocalSystem/Automatic, port 22; firewall `OpenSSH-Server-In-TCP`.
* ✅ Local admin `remote` created (SSH-only) — key auth verified on localhost + Tailnet IP `100.89.32.37` (`Accepted publickey` in event log).
* ✅ Root cause of "Unknown error [preauth]" after `Postponed publickey`: private key `id_ed25519_scriptorium` was **passphrase-encrypted**; BatchMode clients can't sign → client RST (10054) → server logs the crash. Server + S4U were healthy all along (proven via `-ddd` harness + 4624 audits).
* ✅ Fix: new no-passphrase key `id_ed25519_remote` at `administrators_authorized_keys:2`; old key still works in interactive clients.
* ✅ RDP dropped (Win11 Home can't host); SSH is the remote path; notes in `Working/remote-ssh.md` (gitignored).
* ✅ JetBrains Gateway fixed (2026-08-11 eve): (1) `HKLM:\SOFTWARE\OpenSSH\DefaultShell` `cmd.exe`→`C:\Program Files\PowerShell\7\pwsh.exe` + sshd restart (Gateway needs PowerShell); (2) `remote` had no real profile (`USERPROFILE` fell back to `C:\WINDOWS`) — SSH session created `C:\Users\remote` hive files, manually added missing ProfileList entry (`...ProfileList\S-1-5-21-2115311038-1782867078-1966355712-1006`, Flags/State=0) + icacls grant. Verified: `USERPROFILE=C:\Users\remote`, HKCU loads, profile writable.

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

## OpenCode Delegation Bridge (2026-08-13)
* ✅ Task 1 fix: `.opencode/agents/implementer.md` and `.opencode/agents/code-reviewer.md` changed `mode: subagent` → `mode: all`. Root cause: OpenCode's CLI cannot invoke a `mode: subagent` agent directly via `opencode run --agent <name>` — it prints `agent "<name>" is a subagent, not a primary agent. Falling back to default agent` **and exits 0**, silently substituting the full-permission `build` agent instead. `mode: all` makes both agents directly runnable while still usable inside `build`'s internal SDD dispatch.
* ✅ Task 2: new `.claude/agents/opencode-delegate.md` — Claude-side subagent wrapping `opencode run --agent implementer` (write mode, DeepSeek) and `opencode run --agent code-reviewer` (enforced read-only second opinion), mirroring `antigravity-delegate`'s shape. `tools: Bash, Read, Glob` only (no `Write`/`Edit` — all file changes happen through the delegated CLI).
* ✅ Task 3: `.claude/CLAUDE.md` updated with the new three-way delegation section (Claude / Antigravity-Gemini / OpenCode-DeepSeek), replacing the old two-way section.
* ✅ Task 4 smoke tests, run directly via Bash (not through the new subagent, per design — validates the raw CLI path first):
  * Write-mode (`opencode run --agent implementer --auto`): created `DEV/tests/test_opencode_smoke.py` (gitignored, throwaway); independently verified via `python -m pytest` → **1 passed**; `grep -c "Falling back to default agent"` on the JSON transcript → **0**; last JSON event confirmed `step_finish`/`reason:"stop"`. File deleted after verification (`rm`, no git involved — `/DEV/` is gitignored).
  * Read-only (`opencode run --agent code-reviewer`): asked it to review the latest commit via its own `git log -1 --stat`/`git show` Bash calls; independently verified `grep -c "Falling back to default agent"` → **0**; `git status --short` showed only a pre-existing untracked plan file (`docs/superpowers/plans/2026-08-13-opencode-delegate.md`, mtime predates this dispatch) — confirmed via the JSON transcript that `code-reviewer` issued only `git log`/`git show` reads, no write-tool calls, so the working tree was genuinely unchanged by the dispatch.
  * Both smoke tests: **PASS**. Neither triggered the silent-fallback warning.
