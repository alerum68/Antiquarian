# Settings Consolidation & Paleographer API Removal — Design

## Problem

Following the completed per-tool YAML schema migration (see
`2026-08-07-scriptorium-settings-redesign-design.md`), a second, independent
round of settings issues remains:

- `CENSUS_IMAGE_DIR` still lives in `GLOBAL_VARS` even though it's
  Archivist-specific — a debtage leftover from before the per-tool schema
  split existed.
- Several fields (parish identity, volume identity) are declared in more
  than one tool's `settings_schema.yaml` with divergent defaults, because
  each tool grew its own copy independently. Nothing enforces a single
  source of truth.
- Several genuinely-live hardcoded constants (review thresholds, fuzzy-match
  thresholds, retry tuning) are buried in `.py` files with no UI exposure,
  forcing a code edit for values a user might reasonably want to tune.
- Paleographer maintains two parallel extraction engines — the subscription
  `agy` CLI path and a metered direct Gemini API path (`EXTRACTION_ENGINE`
  env switch) — doubling the maintenance surface for a path that's no
  longer used.

This spec resolves all four, plus a fifth item raised after the audit: the
`agy` path currently gets no benefit from prompt caching at all.

## Design

### 1. `CENSUS_IMAGE_DIR` relocation

Move `CENSUS_IMAGE_DIR` out of `Scriptorium.py`'s `GLOBAL_VARS` ("Global
Directories" section) into `Archivist/settings_schema.yaml`. No loader
changes needed — Archivist already has its own schema file and its own
subfolder `.env` via `ENV_TARGETS`. After this change `CENSUS_IMAGE_DIR`
persists to `Archivist/.env` instead of the project-root `.env`.

One-time migration note: this tool doesn't auto-migrate existing `.env`
values. Whoever runs this change should copy `CENSUS_IMAGE_DIR`'s current
value from the project-root `.env` into `Archivist/.env` (or just re-enter
it once in the Archivist tab after the change) — noted here so it isn't
lost as a surprise on first run.

### 2. Shared-field consolidation (single canonical owner)

Resolution strategy (approved): each duplicated field gets exactly one
canonical owner tool. It's removed from every other tool's
`settings_schema.yaml`. Since `execute_script` already dumps every
`self.string_vars` entry into every subprocess's environment regardless of
which tab owns it, **this is a UI-ownership change only — no runtime
behavior changes.** A value set once, on its canonical tab, remains
available to every tool's subprocess exactly as before.

| Field(s) | Canonical owner | Removed from |
|---|---|---|
| `PARISH_NAME`, `PARISH_CITY`, `PARISH_STATE`, `DEFAULT_EVENT_LOCATION` | Paleographer | Archivist |
| `PARISH_NAME_SHORT`, `PARISH_FILE_NAME`, `REGISTER_NAME`, `REGISTER_SOURCE_ID` | Archivist | Paleographer |
| `VOLUME_TITLE`, `VOLUME_NUM` | Paleographer | Archivist, Voyageur (LAC section) |

**Explicitly out of scope** (do not touch):
- `CALL_NUMBER` / `COLLECTION_URL` / `COLLECTION_NAME` / `REPOSITORY` /
  `REPOSITORY_LOC` vs. their `CHURCH_*` / `SCRIP_*` counterparts — these
  are not duplicates, they're the deliberate `field_remap:` override
  mechanism in `.pmt` front-matter (`Parish.pmt`, `Scrip.pmt`) and must
  keep both the base and prefixed forms.
- `MASTER_DB_NAME` / `OUTPUT_DIR` pairs — same reason.

**Optional, not a firm recommendation:** `LAC_VOLUME` (Voyageur) is the
weaker of two LAC volume fields — it's only read by `LAC.py`'s own
`argparse` default and is never reached through the GUI, since
`execute_script` always passes `--volume` explicitly from
`LAC_HARVEST_VOLUME` when that field is set. It's a candidate to drop
entirely (one fewer LAC field) if desired, but isn't required for this
consolidation to be complete. Leaving it out of the implementation plan
unless explicitly requested.

### 3. New settings to add

Each of these is a real, currently-hardcoded constant with no UI exposure.
Adding them follows the existing per-tool schema pattern (default, tooltip,
placed alongside its natural sibling section).

| Field | File | Current default | Placement rationale |
|---|---|---|---|
| `REVIEW_THRESHOLD` | `Archivist/Census.py:66` | `0.6` | Pairs with existing `REVIEW_COLOR` |
| `NEXT_AUTO_SOURCE_ID` | `Archivist/Utils.py:86` | `1030` | Pairs with `ROOT_SOURCE_ID` / `REGISTER_SOURCE_ID` |
| `NAME_MATCH_THRESHOLD` | `Voyageur/FS.py:132` | `85` | Parallel to Registrar's exposed fuzzy-match sliders |
| `PARENT_MATCH_THRESHOLD` | `Voyageur/FS.py:133` | `80` | Same as above |
| `DEFAULT_MAX_RETRIES` | `Paleographer/agy_engine.py:38` | `5` | Sibling to exposed `AGY_TIMEOUT_SECONDS` |
| `DEFAULT_BACKOFF_SECONDS` | `Paleographer/agy_engine.py:39` | `5.0` | Same as above |

### 4. Dead-settings removal

**None found.** A complete-corpus audit (all 128 distinct setting keys
across `GLOBAL_VARS` + all six `settings_schema.yaml` files, searched
against every `.py` file and every `.pmt` file in the repo — the `.pmt`
files were essential, since several `CHURCH_*`/`SCRIP_*` fields are only
referenced inside `field_remap:` front-matter or `${VAR}` template
placeholders, invisible to a `.py`-only search) found zero keys with no
reference anywhere. No removal task beyond the ownership relocations in
Section 2.

### 5. Remove Paleographer's Gemini direct-API extraction engine

Approved: eliminate the `EXTRACTION_ENGINE == "api"` path entirely, leaving
`agy` as the sole extraction backend. `HBCRecords.py` is explicitly out of
scope — confirmed twice by the user — it's a standalone script outside the
six-tool GUI ecosystem and keeps its own direct Gemini API usage untouched.

**`Paleographer/Extract.py`:**
- Delete the `EXTRACTION_ENGINE` env read and its validation branch.
- Delete `genai.Client` construction (gated today on `EXTRACTION_ENGINE ==
  "api"`).
- Delete `run_batch_mode`, `is_batch_eligible`, `BATCH_PAGE_THRESHOLD` —
  confirmed dead-on-removal: `agy`'s `main()` path already returns
  immediately after `run_synchronous_batch` and never reaches this code
  today, so nothing currently reachable through `agy` depends on it.
- `run_synchronous_batch`, `process_one_file_sync`, `main()` are **shared**
  — keep them, just delete their `"api"`-branch halves (context-cache
  creation in `run_synchronous_batch`; the `engine.build_content_part_for_file`
  branch in `process_one_file_sync`; the dispatch-to-`run_batch_mode` branch
  in `main()`).

**`Paleographer/engine.py`** (shared helper module — split, not deleted):
- Remove: `run_with_retries`, `build_content_part_for_file`,
  `create_context_cache`, `delete_context_cache`, cost-computation
  machinery (`compute_call_cost`/`CostConfig` reading
  `COST_PER_1M_INPUT`/`COST_PER_1M_OUTPUT`/`CACHE_DISCOUNT_MULTIPLIER`),
  `DailyQuotaExhausted`.
- Keep: `get_dynamic_prompt`, `optimize_image`, `get_pdf_page_count`,
  `get_cached_system_instruction`, `parse_type_config`, `resolve_prompt_path`,
  `build_debug_generation_config`, `build_continuation_context`, `CallCost`
  — all used by the `agy` path today via `agy_engine.py`.

**Delete entirely:** `Paleographer/CacheCleanup.py` (pure Gemini-context-cache
cleanup utility, no `agy` equivalent needed).

**Settings removed** (Paleographer-owned only):
`EXTRACTION_ENGINE`, `COST_PER_1M_INPUT`, `COST_PER_1M_OUTPUT`,
`CACHE_DISCOUNT_MULTIPLIER`, `API_BUDGET`.

**Settings kept** (in `GLOBAL_VARS`, unaffected):
`GEMINI_API_KEY`, `MODEL_NAME` — these are global, not Paleographer-owned,
and `HBCRecords.py` reads both directly (`os.getenv("GEMINI_API_KEY")`,
`os.getenv("MODEL_NAME")`). Since `HBCRecords.py` is out of scope, removing
either would silently break it.

**Tests to update:** `Paleographer/test_crosscheck.py`,
`Paleographer/test_master_db_merge.py`,
`Paleographer/test_paleographer_pipeline.py`,
`Paleographer/test_settings_standalone.py`,
`ScriptoriumMCP/test_agy_connection.py`.

### 6. `agy` prompt caching

Raised mid-review: ensure the large, repeated system-instruction/main-prompt
content sent on every `agy` call within a run benefits from caching, and
that no cache/session state leaks into a later run.

**Current state:** every `agy` call (`agy_client.call_agy_structured`) is a
fully independent, stateless subprocess invocation — no call anywhere
passes `--continue`/`-c` or `--conversation <id>`. `AgyUsage.cache_read_tokens`
is already parsed from `agy`'s own usage JSON but is never deliberately
produced, since nothing establishes a session for a prefix to be cached
against.

**Constraint discovered:** `agy --help` exposes no `caches`
create/delete subcommand and no `--cache`/prefix-only-cache flag — only
`--continue` (resume most recent conversation) and `--conversation <id>`
(resume a specific one). This is a materially different mechanism from the
old direct-API path's `create_context_cache`/`delete_context_cache`, which
cached only a static system-instruction *prefix* with no memory of prior
calls. `--continue` resumes **full turn history** — every prior prompt and
response in that conversation. Chaining every file in a whole batch run
through one continued conversation risks the model blending or referencing
an earlier, unrelated file's extracted data into a later file's output —
a correctness risk, not just a cost one.

**Four cost-saving ideas were raised and evaluated; one is adopted, three
are declined — including the project-rules idea, which looked most
promising on paper but was falsified by a live test:**

**Investigated and declined — project-level rules as a static prefix.**
`agy`'s own first-party, locally-installed docs
(`~/.gemini/antigravity-cli/builtin/skills/agy-customizations/docs/rules.md`)
confirm a real "Rules" mechanism exists: `GEMINI.md`/`AGENTS.md` files,
discovered by walking from the current working directory up to the
repository root (the folder containing `.git`), injected as always-on
instructions. This is a genuinely different, real mechanism — not the
`.antigravity.md`/`~/.gemini/GEMINI.md` paths from the pasted answer that
prompted this investigation, which don't match anything in the CLI's own
shipped documentation and are likely unreliable.

However, a live test disproved it works for how Paleographer actually
calls `agy`. Test: created a repo-local `GEMINI.md` containing a distinct
literal token, ran `agy --add-dir . --output-format json -p "..."` with
`cwd` set inside the repo (so the `.git` walk-up succeeds) three times: (1)
a trivial arithmetic prompt, (2) a second independent trivial prompt, (3) a
prompt explicitly asking the agent to read `GEMINI.md`. Results:
- The literal token never appeared in any response — the rule was not
  auto-injected into the model's instructions in headless/print mode.
- Calls 1 and 2 (independent, non-continued, nearly identical ~19.4k-token
  input) both showed `cache_read_tokens: 0` — **no implicit cross-call
  caching happens at all by default**, rules or no rules.
- Call 3's attempt to read the file via a tool was auto-denied by headless
  mode's permission model (the same known limitation already documented in
  `agy_engine.py`'s PDF-rasterization rationale — an internal tool call
  silently blocked with no terminal to approve it). Working around that
  would require `--dangerously-skip-permissions`, which this codebase
  deliberately never uses (see `agy_client.py`'s own safety rationale) —
  not worth relaxing an existing, deliberate safety boundary to chase a
  cost optimization.

Conclusion: whatever surface *does* auto-load `GEMINI.md`/`AGENTS.md` (the
interactive TUI or IDE, most likely), Paleographer's headless/`-p` calls
don't hit it. Not pursuing this further.

**Adopted — `--continue` scoped to one file's own chunked-extraction
sequence** (`call_agy_extract_chunked`'s per-chunk calls
plus its final consolidation pass) — the case that already wants
continuity today (`build_continuation_context` already threads
page-continuity markers between chunks manually). The first chunk call of a
file omits `--continue`/starts fresh; every subsequent chunk call and the
consolidation call for that same file pass `-c`. Never chain across
separate, independent files — each file's first call always starts a new
conversation.
- **Sharpened verification step:** because `--continue` resumes full turn
  history, chunk N's call under `--continue` carries forward every prior
  chunk's images too, not just a cached text prefix — chunk 4 of a 4-chunk
  file would carry chunks 1-3's images (30 pages) plus its own 10, not a
  cheap cached prefix. So checking `cache_read_tokens` > 0 alone is not
  enough to prove this is a net win. Before shipping: run a real
  multi-chunk document and compare **total tokens actually billed/reported
  across the whole file** (sum of every chunk's `total_tokens`, chained vs.
  un-chained) — only keep chaining if that sum is actually lower, not just
  nonzero-cache-adjacent. Also confirm no cross-chunk contamination (the
  model referencing an earlier chunk's specific record data
  inappropriately in a later one). If either check fails, fall back to no
  chaining at all — the current, already-shipped behavior — rather than
  accept a correctness or cost regression for a theoretical optimization.

**Declined — blank image inputs.** Submitting images with no accompanying
instructional text doesn't fit this pipeline: the model needs the schema
and extraction instructions alongside the images on every call, or it has
no task to perform. The valid idea underneath this suggestion — keep
static/shared content as an unbroken prefix, with variable per-call content
appended after — is already how `call_agy_extract` builds `full_prompt`
(`prompt_text` first, `file_instruction` last). No change needed.

**Declined — flatten instructions into a rendered PNG.** A real Gemini
pricing quirk (images price at a flat per-tile rate regardless of embedded
text density) but it optimizes for *per-token metered billing* — the exact
cost model this task is deliberately moving Paleographer away from by
standardizing on `agy`'s flat subscription. It also risks the model
misreading rendered instruction text, which is a correctness cost this
schema-driven extraction pipeline shouldn't take on for a billing model
it no longer uses.

**"Cleared at end of run, or if aborted":** `agy` does persist each
conversation as a local SQLite file under
`~/.gemini/antigravity-cli/conversations/*.db` — discovered during the
live test above, this contradicts an earlier draft of this section that
assumed there was nothing to clean up. In practice this doesn't require
explicit deletion for correctness: the adopted `--continue` scoping never
reuses a conversation id across files or runs (each file's first chunk
starts a fresh, unnamed conversation; nothing stores or looks up a prior
run's id), so an aborted or completed run simply stops referencing its
`.db` file rather than leaking state into the next one. The files
themselves are inert leftovers, not live session state — cleaning them up
is a disk-hygiene nice-to-have, not a correctness requirement. Out of
scope for this design; if it becomes worth doing, a periodic sweep of
that directory (e.g., delete conversations older than N days) is a
separate, small, standalone task.

## Testing

- Sections 1–4: no new automated test needed. The base settings-redesign
  spec's schema-completeness regression test (every `os.getenv`/`os.environ`
  read has a matching schema key) already catches drift here; re-run it
  after the relocations to confirm both the newly-added and newly-removed
  fields are consistent with actual code reads.
- Section 5: existing Paleographer test suite must be updated per the file
  list above and pass with `EXTRACTION_ENGINE`/the `"api"` path gone.
- Section 6: not unit-testable (depends on live `agy` subprocess behavior
  and real token-usage reporting) — the live verification step described
  above is the actual test.

## Out of scope

- `HBCRecords.py` — confirmed out of scope by the user.
- `CALL_NUMBER`/`COLLECTION_*`/`REPOSITORY*` vs. `CHURCH_*`/`SCRIP_*`
  `field_remap:` pairs, and `MASTER_DB_NAME`/`OUTPUT_DIR` pairs.
- Any change to the already-completed per-tool YAML schema migration
  itself (see `2026-08-07-scriptorium-settings-redesign-design.md`).
- Dropping `LAC_VOLUME` — noted as optional in Section 2, not included as
  a task.
