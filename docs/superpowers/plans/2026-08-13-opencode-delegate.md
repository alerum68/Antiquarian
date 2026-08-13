# OpenCode Delegation Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Claude Code a second, free, key-less delegation target — OpenCode CLI (already authenticated, no separate login) — by adding a `.claude/agents/opencode-delegate.md` subagent that shells out to `opencode run --agent implementer` (DeepSeek, write mode) or `opencode run --agent code-reviewer` (enforced read-only, second opinion), mirroring the existing `antigravity-delegate` subagent's shape.

**Architecture:** Four sequential tasks, each gitignored-local except the final tracker update: (1) fix a real invocation bug found during investigation — `implementer`/`code-reviewer` are `mode: subagent` and OpenCode's CLI silently refuses to run subagents directly, so both must become `mode: all`; (2) write the new Claude-side subagent definition, whose invocation contract depends on (1) being correct; (3) document the new delegation target in `.claude/CLAUDE.md`; (4) prove the whole bridge works end-to-end with two throwaway smoke tests run directly via Bash (not through the new subagent), exactly as the design spec required, before anyone trusts the subagent definition in a real session.

**Tech Stack:** OpenCode CLI v1.18.16 (already installed, already authenticated via `~/.local/share/opencode/auth.json`), Claude Code subagent frontmatter (YAML), Markdown, PowerShell/Bash.

**Spec:** User-provided design brief, given in-session on 2026-08-13 ("Add OpenCode as a Free, Key-less Delegation Target"). No separate spec file — this plan's Goal/Architecture and the Global Constraints below are the spec's operative content, corrected against two empirical findings the spec's author did not have when writing it (see Global Constraints, items 4 and 5).

## Global Constraints

- Never pass `-m`/`--model` to `opencode run` — always let `--agent <name>`'s own frontmatter `model:` win (`implementer` → `opencode/deepseek-v4-flash-free`, `code-reviewer` → `opencode/big-pickle`).
- Always pass `--dir "C:/Users/Jason Cole/Documents/Genealogy/Scriptorium"` (forward slashes — matches the existing `.claude/agents/general-purpose.md` convention) and `--format json`.
- `opencode-delegate` gets `tools: Bash, Read, Glob` — no `Write`/`Edit`. All file changes happen through the delegated CLI, never reconstructed by the subagent itself.
- No `PreToolUse` hook / gate on `opencode-delegate`'s Bash tool (unlike `antigravity-delegate`'s `hooks.PreToolUse`) — this integration is project-scoped and gitignored, wrapping a CLI the user already runs directly and trusts; that threat model does not require gating.
- **Finding (this plan, Task 1):** `implementer` and `code-reviewer` are `mode: subagent` in `.opencode/agents/*.md`. OpenCode's CLI cannot run a subagent directly — `opencode run --agent code-reviewer` prints `agent "code-reviewer" is a subagent, not a primary agent. Falling back to default agent` **and exits 0**, silently substituting the full-permission `build` agent instead. Confirmed empirically. This must be fixed (`mode: subagent` → `mode: all`, OpenCode's third mode: "available in all contexts" — both directly runnable and still usable inside `build`'s own internal SDD dispatch) before any dispatch contract that names `implementer`/`code-reviewer` explicitly is trustworthy.
- **Finding (this plan, Task 1):** Because the fallback above is silent and exits 0, `opencode-delegate` must treat the literal stderr substring `Falling back to default agent` as a hard failure regardless of exit code or JSON stream content — a typo'd `--agent` name would otherwise silently run `build` (blanket write permission) with no error signal.
- **Finding (this plan, Task 1):** `build` and `implementer` both carry `"permission": "*", "action": "allow", "pattern": "*"` in their effective permission (confirmed empirically: `implementer` wrote a file via direct CLI invocation with no `--auto` flag and no prompt). `--auto` is therefore a no-op for write-mode calls in this repo's current config — it is kept in the documented invocation anyway as a portability safety net (a different/future permission default could make it load-bearing), but the **real** safety mechanism for write-mode is branch/worktree isolation before invoking, and diff review after. `code-reviewer` alone carries a real `permission: edit: deny` override (confirmed empirically: it refused a direct write-tool probe, stating "Write tool: not available in my toolset") — it is the only genuinely enforced read-only target, and only after the `mode: all` fix makes it directly invocable.
- All files this plan touches are gitignored except `docs/plans/task.md`: `.claude/` (`.gitignore:12` `/.claude/`) and `.opencode/` (`.gitignore`'s "Local-only" block). No git commit applies to any task in this plan. Per top-level Claude Code instructions, do not commit even the `docs/plans/task.md` update without explicit user request.
- No change to `opencode.json`'s top-level `model` (stays `opencode/big-pickle`) — every invocation in this plan passes `--agent` explicitly, so the top-level default is never exercised by this integration.
- No change to `AGENTS.md` — it documents OpenCode's own independent `/superpowers` workflow; this bridge is Claude-Code-specific and belongs only in `.claude/CLAUDE.md`.

---

### Task 1: Enable direct CLI invocation of `implementer` and `code-reviewer`

**Files:**
- Modify: `.opencode/agents/implementer.md:3`
- Modify: `.opencode/agents/code-reviewer.md:3`

**Interfaces:**
- Produces: a verified fact that `opencode run --dir "C:/Users/Jason Cole/Documents/Genealogy/Scriptorium" --agent implementer|code-reviewer --format json "<prompt>"` runs the named agent directly (no silent fallback), which Task 2's subagent definition depends on.

- [ ] **1a. Edit `.opencode/agents/implementer.md`:** change line 3 from `mode: subagent` to `mode: all`. No other change.

- [ ] **1b. Edit `.opencode/agents/code-reviewer.md`:** change line 3 from `mode: subagent` to `mode: all`. No other change.

- [ ] **1c. Verify no silent fallback on `implementer`:**

Run:
```bash
cd "C:\Users\Jason Cole\Documents\Genealogy\Scriptorium"
opencode run --dir "C:/Users/Jason Cole/Documents/Genealogy/Scriptorium" --agent implementer --format json "There is no separate brief file for this probe — this prompt is the full brief. Do not implement anything. Just reply with the single word: READY." 2>&1 | head -c 600
```
Expected: no `Falling back to default agent` line in the output; the JSON stream contains a `"type":"text"` part with `"text":"READY"`.

- [ ] **1d. Verify no silent fallback on `code-reviewer`, and confirm it still cannot write:**

Run:
```bash
cd "C:\Users\Jason Cole\Documents\Genealogy\Scriptorium"
opencode run --dir "C:/Users/Jason Cole/Documents/Genealogy/Scriptorium" --agent code-reviewer --format json "This is a permission probe, not a real review. Attempt to write a file at DEV/tests/_opencode_permission_probe.tmp containing the word probe, then report whether the write tool succeeded or was denied. Do not do a real code review." 2>&1
ls DEV/tests/_opencode_permission_probe.tmp 2>&1
```
Expected: no `Falling back to default agent` line; the reply states it has no write tool / declines to write; `ls` reports "No such file or directory" (nothing was written). If the file exists, `rm` it and treat this step as failed — do not proceed to Task 2.

No commit — both files are gitignored (`.opencode/` is untracked per `.gitignore`).

---

### Task 2: Create `.claude/agents/opencode-delegate.md`

**Files:**
- Create: `.claude/agents/opencode-delegate.md`

**Interfaces:**
- Consumes: Task 1's verified fact that `implementer`/`code-reviewer` accept direct `--agent` invocation.
- Produces: the subagent Claude Code will select when a task's description matches "free, key-less delegation via OpenCode/DeepSeek."

- [ ] **2a. Write the file exactly as follows:**

```markdown
---
name: opencode-delegate
description: |
  Use this subagent for bulk/mechanical work when the user wants a free,
  key-less alternative to Antigravity — OpenCode CLI is already installed
  and authenticated on this machine (~/.local/share/opencode/auth.json),
  no API key or separate login needed. Routes write-mode work to this
  repo's own `.opencode/agents/implementer` (DeepSeek, opencode/deepseek-v4-flash-free)
  and read-only second-opinion review to `.opencode/agents/code-reviewer`
  (opencode/big-pickle, permission.edit:deny enforced by OpenCode itself).
  It shells out to `opencode run` and returns OpenCode's own status
  contract verbatim — it does not itself ship or claim success.

  Do NOT use it for small, self-contained, or judgement-heavy tasks:
  delegating a tiny task is a measured net loss (round-trip cost exceeds
  the savings) — the caller should just do those directly.

  <example>
  Context: A mechanical multi-file change the user wants done without
  spending Gemini/Antigravity quota or managing a second credential.
  user: "Rename every FooBar reference to BazQux across the repo — use the free option, no API key."
  assistant: "I'll use opencode-delegate to run the implementer agent
  (DeepSeek, free, already authenticated) on a dedicated branch, then
  review the diff myself before merging."
  </example>

  <example>
  Context: Claude wants a second opinion on a diff before merging, at zero
  API cost.
  user: "Get a free second opinion on this diff before we merge."
  assistant: "I'll use opencode-delegate to run the code-reviewer agent —
  it's read-only by OpenCode's own permission enforcement, so no branch
  isolation is needed for this one."
  </example>

  <example>
  Context: A tiny one-off edit.
  user: "Fix this one typo in the README."
  assistant: "That's below the break-even — I'll just do it directly, not via opencode-delegate."
  </example>
tools: Bash, Read, Glob
model: inherit
---

You are the OpenCode delegation executor for this repo. Your job is to
route one well-scoped unit of work to OpenCode's own `implementer` or
`code-reviewer` agent and return its report verbatim. OpenCode/DeepSeek
does the heavy lifting; you only orchestrate and relay. **You do not
verify and you do not claim success** — verification is the caller's
(Claude's) job.

## Core rule — everything goes through `opencode run`

You have **no `Write` and no `Edit`**. All file creation/editing happens
inside the delegated `opencode run` process, never in your own reply.
Never reconstruct file contents in your reply — if the caller needs to
see what changed, tell them to `Read` the file or `git diff` it
themselves.

Never pass `-m`/`--model` — each `--agent`'s own frontmatter model wins
(`implementer` = DeepSeek, `code-reviewer` = the most capable free model).
Reusing OpenCode's existing per-agent routing is the point; do not
re-decide models here.

## Standard invocations

**(a) Bulk/mechanical code generation — write mode:**

```bash
opencode run --dir "C:/Users/Jason Cole/Documents/Genealogy/Scriptorium" --agent implementer --auto --format json "<full brief prompt>"
```

`--auto` is currently a no-op in this repo (the agent's default permission
already allows all in-project writes) but keep it — it is the correct flag
for headless write-mode and is a safety net if the permission default ever
tightens. The real safety mechanism is: **the caller must `git checkout -b`
a dedicated branch (or use a worktree) before invoking this**, and must
review the diff before merging — `implementer` will commit directly to
whatever branch is checked out when you invoke it.

**(b) Second-opinion review — read-only by construction:**

```bash
opencode run --dir "C:/Users/Jason Cole/Documents/Genealogy/Scriptorium" --agent code-reviewer --format json "<full brief prompt>"
```

Never pass `--auto` here — it is unnecessary (OpenCode's own
`permission.edit: deny` on `code-reviewer` blocks writes) and would
contradict the read-only intent. Give `code-reviewer` either a small diff
pasted inline, or a `git diff <base>...<branch>` command it can run itself
with its own Bash access (it has no write tool, but retains read/bash) —
do not assume a controller has pre-generated a diff file for you.

## Input-contract override (read this before every dispatch)

`implementer.md` and `code-reviewer.md` describe their inputs (brief path,
report path, plan path, ledger path) as things an OpenCode-side *build*
controller provides when dispatching them internally. That controller is
not in play when you invoke them directly from the CLI. Your dispatch
prompt must say, explicitly, near the top:

> "There is no separate brief/plan/ledger file for this invocation — this
> prompt is the complete input. There is no separate report file — write
> your full report/findings directly in your reply text, then end with the
> short status contract on its own line."

This overrides their internal controller-dispatch assumption; without it
they may stall waiting for a file path that does not exist.

## Cost/break-even discipline

1. Check the break-even first — small, self-contained, or judgement-heavy
   tasks are a net loss to delegate; do those yourself.
2. Do not invent a new digest format. Lean on each agent's own report
   contract:
   - `implementer` → `DONE` / `DONE_WITH_CONCERNS` / `NEEDS_CONTEXT` /
     `BLOCKED`, plus commits and a one-line test summary.
   - `code-reviewer` → `Verdict: Approved` / `Findings` (labeled
     Critical/Important/Minor, each citing `file:line`), plus `Strengths`.
     Skip the "Ledger triage" part of its output format — there is no
     ledger in ad hoc invocation; tell it so via the override above.
3. Batch — one fully-specified dispatch beats several round-trips.

## What to return to the caller

1. The agent's status contract **verbatim** (see above) — do not
   summarize or reword it away.
2. A short **"VERIFY THIS"** line naming the exact command the caller must
   run themselves (e.g. `python -m pytest <path> -q`, `git diff <branch>`,
   `git status --short`). Never assert the work is correct or done —
   OpenCode's self-report is a claim, not evidence.
3. Whether this was write-mode (`implementer`) or read-only
   (`code-reviewer`), so the caller knows what branch/diff state to expect.

## Failure handling

- **Silent-fallback check (do this first, every time):** if stderr
  contains the literal substring `Falling back to default agent`, treat
  this as a hard failure and stop — do not trust anything in the JSON
  stream that follows. This happens on both an unrecognized `--agent` name
  and (before Task 1's fix) any subagent-mode agent; exit code is `0` in
  both cases, so exit code alone cannot detect it. Report the exact
  warning line and which `--agent` value you passed.
- If `opencode run` exits non-zero, or the JSON stream ends without a
  `step_finish` event whose `reason` is `"stop"`, report the raw stderr
  tail (or the last few JSON lines) and stop — no silent retry.
- If OpenCode reports a provider/auth/quota error, tell the caller to run
  `opencode auth login` (or check `~/.local/share/opencode/auth.json`)
  interactively rather than retrying headless.
```

- [ ] **2b. Verify the frontmatter is well-formed YAML with the required keys:**

Run:
```bash
cd "C:\Users\Jason Cole\Documents\Genealogy\Scriptorium"
python -c "
import re, yaml
text = open('.claude/agents/opencode-delegate.md', encoding='utf-8').read()
m = re.match(r'^---\n(.*?)\n---\n', text, re.S)
fm = yaml.safe_load(m.group(1))
assert fm['name'] == 'opencode-delegate'
assert fm['tools'] == 'Bash, Read, Glob'
assert 'Write' not in fm['tools'] and 'Edit' not in fm['tools']
assert fm['model'] == 'inherit'
assert 'hooks' not in fm
print('OK', fm['name'], fm['tools'], fm['model'])
"
```
Expected: `OK opencode-delegate Bash, Read, Glob inherit` with no traceback.

No commit — `.claude/` is gitignored (`.gitignore:12`).

---

### Task 3: Document the new delegation target in `.claude/CLAUDE.md`

**Files:**
- Modify: `.claude/CLAUDE.md`

- [ ] **3a. Replace the existing section:**

Old text (verbatim, to locate and replace):
```markdown
# Agent Delegation (Claude vs. Gemini)
* **Claude (You):** Act as the senior architect. Handle complex logic, final code reviews, and high-level architectural decisions. 
* **Gemini (Antigravity):** Act as the junior developer. Use the `antigravity-for-claude-code` tool to delegate bulk file writing, low-level reasoning tasks, unit test generation, and large schema digests.
* **Protocol:** Inform the user when deploying Gemini. After Gemini completes, summarize its results briefly, then implement.
```

New text:
```markdown
# Agent Delegation (Claude vs. Gemini vs. OpenCode)
* **Claude (You):** Act as the senior architect. Handle complex logic, final code reviews, and high-level architectural decisions.
* **Gemini (Antigravity):** Act as the junior developer. Use the `antigravity-for-claude-code` tool (`antigravity-delegate` subagent) to delegate bulk file writing, low-level reasoning tasks, unit test generation, and large schema digests. Requires the user's Antigravity/Gemini credentials.
* **OpenCode (DeepSeek, free/key-less):** A second junior-developer option with no API key or separate login — already authenticated on this machine. Use the `opencode-delegate` subagent for the same class of bulk/mechanical write-mode work (routes to `.opencode/agents/implementer`, DeepSeek) when avoiding Gemini quota/credentials matters, or for a free second-opinion review (routes to `.opencode/agents/code-reviewer`, enforced read-only).
* **Protocol:** Inform the user when deploying Gemini or OpenCode. After the delegate completes, verify its work (run tests, review the diff) before treating it as done — a delegate's self-report is a claim, not evidence — then summarize briefly and implement/finalize.
```

- [ ] **3b. Verify the edit landed:**

Run:
```bash
cd "C:\Users\Jason Cole\Documents\Genealogy\Scriptorium"
grep -n "OpenCode" .claude/CLAUDE.md
```
Expected: at least 3 matching lines (the section header and the two bullets mentioning OpenCode).

No commit — `.claude/` is gitignored.

---

### Task 4: End-to-end smoke tests, run directly via Bash (not through the subagent)

**Files:**
- Create then delete (throwaway, gitignored — `/DEV/` per `.gitignore`): `DEV/tests/test_opencode_smoke.py`

**Interfaces:**
- Consumes: Task 1's fixed invocation contract, Task 2's documented command syntax.
- Produces: empirical proof the bridge works, before `opencode-delegate` is trusted in a real session.

- [ ] **4a. Write-mode smoke test — dispatch:**

Run:
```bash
cd "C:\Users\Jason Cole\Documents\Genealogy\Scriptorium"
opencode run --dir "C:/Users/Jason Cole/Documents/Genealogy/Scriptorium" --agent implementer --auto --format json "There is no separate brief file for this smoke test — this prompt is the full brief. Create a file at DEV/tests/test_opencode_smoke.py containing exactly one trivial pytest test function that asserts 1 + 1 == 2. Do not run any git commands (this directory is gitignored, there is nothing to commit). Then reply with the DONE status contract." > "$TEMP/opencode_smoke_write.json" 2>&1
cat "$TEMP/opencode_smoke_write.json" | tail -c 2000
```

- [ ] **4b. Independently verify — do not trust the reply:**

Run:
```bash
cd "C:\Users\Jason Cole\Documents\Genealogy\Scriptorium"
grep -c "Falling back to default agent" "$TEMP/opencode_smoke_write.json"
python -m pytest DEV/tests/test_opencode_smoke.py -q
```
Expected: the `grep -c` prints `0` (no silent fallback); `pytest` shows `1 passed`. Also open the JSON file and confirm the last event is a `step_finish` with `"reason":"stop"` (a parseable final event, not a truncated/errored stream).

- [ ] **4c. Delete the throwaway file:**

Run:
```bash
rm "C:/Users/Jason Cole/Documents/Genealogy/Scriptorium/DEV/tests/test_opencode_smoke.py"
```
No git revert needed — `/DEV/` is gitignored, so the file was never tracked.

- [ ] **4d. Read-only smoke test — dispatch:**

Run:
```bash
cd "C:\Users\Jason Cole\Documents\Genealogy\Scriptorium"
opencode run --dir "C:/Users/Jason Cole/Documents/Genealogy/Scriptorium" --agent code-reviewer --format json "There is no separate plan/diff/ledger file for this smoke test — this prompt is the complete input. Run 'git log -1 --stat' yourself via your Bash tool to see the most recent commit, and give a one-paragraph opinion on whether its commit message matches its diff. This is a smoke test of your read-only invocation, not a real review — do not attempt to write or edit anything. End with your normal Verdict/Findings/Strengths contract." > "$TEMP/opencode_smoke_review.json" 2>&1
cat "$TEMP/opencode_smoke_review.json" | tail -c 2000
```

- [ ] **4e. Independently verify:**

Run:
```bash
cd "C:\Users\Jason Cole\Documents\Genealogy\Scriptorium"
grep -c "Falling back to default agent" "$TEMP/opencode_smoke_review.json"
git status --short
```
Expected: `grep -c` prints `0`; `git status --short` prints nothing (working tree unchanged — `code-reviewer` made no writes).

- [ ] **4f. Update `docs/plans/task.md`:** add a dated entry under a new `## OpenCode Delegation Bridge (2026-08-13)` heading summarizing: the `mode: all` fix and why it was necessary (subagents can't be invoked directly, silent 0-exit fallback), the new `.claude/agents/opencode-delegate.md`, the `.claude/CLAUDE.md` update, and both smoke tests' pass/fail result. Do not commit — the user has not asked for a commit on this work.

---

## Verification

- [ ] Task 1: both `.opencode/agents/*.md` files show `mode: all`; direct invocation of both produces no `Falling back to default agent` line; `code-reviewer` still refuses to write.
- [ ] Task 2: `.claude/agents/opencode-delegate.md` exists, frontmatter parses with `python -c "...yaml.safe_load..."` above, `tools` excludes `Write`/`Edit`, no `hooks` key.
- [ ] Task 3: `.claude/CLAUDE.md` contains the new three-way delegation section; old two-way section is gone.
- [ ] Task 4: write-mode smoke test produced a real, passing pytest file (verified independently, not from the reply), then was deleted; read-only smoke test left `git status --short` empty; neither smoke test triggered the silent-fallback warning.
- [ ] `docs/plans/task.md` updated.

## Success Criteria

- [ ] Claude Code can delegate bulk/mechanical write-mode work to OpenCode/DeepSeek with no API key and no additional login, on a dedicated branch, with the diff reviewable before merge.
- [ ] Claude Code can get a free, OpenCode-enforced read-only second opinion via `code-reviewer` with no risk of accidental writes.
- [ ] Both paths fail loudly (not silently as `build`) on a bad `--agent` name or an un-fixed `mode: subagent` agent.
- [ ] `.claude/CLAUDE.md` documents both delegation targets and when to pick each.
