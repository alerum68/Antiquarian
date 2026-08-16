# Paleographer Structural Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **SUPERSEDED:** This plan is historical. Its checklist steps marked `- [ ]` were superseded and never executed as written; see the live tracker `docs/plans/task.md` for the actual disposition.

**Goal:** Split `Paleographer/Paleographer.py` (2,148 lines) into a thin dispatcher plus two real sibling modules — `Extract.py` (record-type-generic extraction, mirrors `Voyageur.py`'s post-rewrite shape) and `ScripTools.py` (Scrip-only enrichment) — deleting ~756 lines of `engine.py`/`agy_engine.py` content that are folded in and duplicated today. Fix two independent bugs found during design. No other behavior change.

**Architecture:** `Paleographer.py` becomes a ~20-line dispatcher routing on `sys.argv[1]`. `Extract.py` imports `engine`/`agy_engine` as real sibling modules instead of duplicating their content. `ScripTools.py` owns the Scrip-only `enrich`/`crosscheck`/`partition`/`resolve-names` logic. Every `POSTPROCESS` helper function moves to whichever file its actual call sites live in (verified by grep, not guessed).

**Tech Stack:** Python, pytest.

## Global Constraints

- No behavior change to extraction or enrichment logic — every moved function is a verbatim lift; same inputs produce the same outputs. The only intentional behavior changes are the two bug fixes called out in Task 2 and Task 5.
- `engine.py` and `agy_engine.py` themselves are untouched — only how `Extract.py` reaches their functions changes (real import instead of folded-in duplicate).
- Full `pytest` suite stays green after every task.
- `test_engine.py`, `test_agy_engine.py`, `test_schema.py` are untouched — they already import the standalone `engine`/`agy_engine` files directly.
- No AI attribution, "Co-Authored-By", or AI Assistant stamps in commits.
- Spec: `docs/superpowers/specs/2026-08-06-paleographer-structural-split-design.md`.

---

## Function allocation reference (verified by grep against `Paleographer.py` before Task 1 started — do not re-derive)

**To `Extract.py`** (POSTPROCESS section, lines 79–245 of the current `Paleographer.py`): `strip_diacritics` (80), `derive_role_numbers` (89), `derive_role_semantics` (102), `_find_role_number` (111), `derive_suffixes` (118), `_participant_key` (141), `_label_for` (148), `_source_document_entry` (157), `_merge_record_into` (167), `merge_same_claim_records` (205), `apply_defaults` (223).

**To `ScripTools.py`** (POSTPROCESS section, lines 246–530): `fix_mojibake` (246), `clean_dit_name` (283), `parse_single_name` (290), `fix_participant_name` (353), `fix_all_participant_names_in_record` (384), `build_composite_record_number` (407), `resolve_maiden_name_for_record` (415), `resolve_dataset_maiden_names` (475), `extract_citation_fields` (512). **Correction from the design doc:** the design's "best read" placed `fix_mojibake` and `extract_citation_fields` in `Extract.py`; grep of actual call sites (`fix_mojibake` called only at what are today lines 481, 483, 488, 517, 1883, 1930; `extract_citation_fields` called only at 1890, 1942) shows both are reachable only from `ScripTools.py`'s territory. This plan uses the corrected allocation.

**Deleted entirely, not moved** (lines 531–1287, the `ENGINE`/`AGY ENGINE` banners): all of it — `Extract.py` calls the real `engine.py`/`agy_engine.py` instead.

**To `Extract.py`** (lines 1288–1747: `PALEOGRAPHER CONFIGURATION`, `RECORD POST-PROCESSING`, `MASTER DB HELPERS`, `FILE CLASSIFICATION`, `SYNCHRONOUS PROCESSING`, `BATCH PROCESSING`) plus the "Standard extraction mode" body of `main()` (lines 2098–2145).

**To `ScripTools.py`** (lines 1748–2018, `SCRIP ENRICHMENT & PARTITIONING`) plus the enrichment-mode body of `main()` (lines 2022–2096, restructured — see Task 2).

---

### Task 1: Create `Extract.py`

**Files:**
- Create: `Paleographer/Extract.py`
- Test: `Paleographer/tests/test_extract_dispatch.py` (new, minimal)

**Interfaces:**
- Consumes: `engine.py` and `agy_engine.py` as real sibling modules (both already exist, untouched).
- Produces: `Extract.main()` — no arguments, reads `sys.argv[1]` itself for the optional `DEBUG_FILE` positional. Consumed by Task 3's dispatcher and by the four test files repointed in Task 4.

- [ ] **Step 1: Create `Paleographer/Extract.py` with header, imports, and the POSTPROCESS-Extract functions**

Use the Write tool. Start the file with:

```python
"""
Extract: record-type-generic document extraction for Paleographer.

Uses the AI Assistant API (via engine.py) or the AGY CLI (via agy_engine.py) to
transcribe historical document images or PDFs of any record type and extract
structured records into a JSON master database, following one universal schema.
Which record type is active, and every piece of type-specific vocabulary (event
types, roles, defaults, schema extensions), comes entirely from a single .pmt file
in prompts/; this module never changes when a new record type is added.

Antiquarian.py launches Paleographer.py (the dispatcher) as a subprocess with
cwd=Paleographer/, so engine and agy_engine import here as plain sibling modules.
"""

import json
import math
import os
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from dotenv import load_dotenv
from google import genai

# The Toolbox's own subprocess launcher sets PYTHONIOENCODING=utf-8, but this module also
# supports being run directly (its debug mode), where stdout would otherwise fall back to
# the system's default codepage and crash on emoji/checkmarks.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# AntiquarianMCP lives in a sibling tool folder, not an installed package - add the repo
# root to sys.path so it can be imported by absolute path.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from AntiquarianMCP import agy_client  # noqa: E402

from Commissioner import normalization  # noqa: E402

import engine
import agy_engine

# Global settings come from the project root's .env; this tool's own settings come from
# its own subfolder's .env, so Paleographer stays runnable standalone.
ROOT_ENV = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ROOT_ENV, override=True)
load_dotenv(Path(__file__).resolve().parent / ".env", override=True)


# ==============================================================================
# POSTPROCESS
# ==============================================================================
```

Then append the body of the `POSTPROCESS`-to-`Extract.py` functions, copied **verbatim** (unchanged) from the current `Paleographer/Paleographer.py` lines 80–245: `strip_diacritics`, `derive_role_numbers`, `derive_role_semantics`, `_find_role_number`, `derive_suffixes`, `_participant_key`, `_label_for`, `_source_document_entry`, `_merge_record_into`, `merge_same_claim_records`, `apply_defaults` — in that order, exactly as they appear today. Copy the text directly; do not retype it by hand.

- [ ] **Step 2: Append the `PALEOGRAPHER CONFIGURATION` section**

Copy `Paleographer.py` lines 1291–1365 verbatim (everything from the `EXTRACTION_ENGINE` comment through the `SCHEMA` assignment, including the `CONFIGURATION` sub-banner and `resolve_setting`), under a new banner:

```python
# ==============================================================================
# CONFIGURATION
# ==============================================================================
```

Then apply these exact substitutions to the copied text (every other line is unchanged):

| Original line (current `Paleographer.py`) | Replace with |
|---|---|
| `TYPE_CFG = parse_type_config(resolve_prompt_path(RECORD_TYPE_NAME))` | `TYPE_CFG = engine.parse_type_config(engine.resolve_prompt_path(RECORD_TYPE_NAME))` |
| `COST_CFG = CostConfig(` | `COST_CFG = engine.CostConfig(` |
| `AGY_MODEL_ID: str = os.getenv("AGY_MODEL_NAME") or DEFAULT_MODEL` | `AGY_MODEL_ID: str = os.getenv("AGY_MODEL_NAME") or agy_engine.DEFAULT_MODEL` |
| `SOURCE_SUFFIXES = IMAGE_SUFFIXES + (".pdf",)` | `SOURCE_SUFFIXES = engine.IMAGE_SUFFIXES + (".pdf",)` |
| `SCHEMA: Dict[str, Any] = build_merged_schema(CORE_SCHEMA, TYPE_CFG.extra_fields)` | `SCHEMA: Dict[str, Any] = engine.build_merged_schema(CORE_SCHEMA, TYPE_CFG.extra_fields)` |

- [ ] **Step 3: Append `RECORD POST-PROCESSING`, `MASTER DB HELPERS`, `FILE CLASSIFICATION`, `SYNCHRONOUS PROCESSING`, `BATCH PROCESSING`**

Copy `Paleographer.py` lines 1369–1747 verbatim, in order, keeping their existing banner comments (`RECORD POST-PROCESSING`, `MASTER DB HELPERS`, `FILE CLASSIFICATION`, `SYNCHRONOUS PROCESSING`, `BATCH PROCESSING`). Then apply these exact substitutions:

| Original line | Replace with |
|---|---|
| `def record_cost(master_data: Dict[str, Any], usage_metadata: Any) -> CallCost:` | `def record_cost(master_data: Dict[str, Any], usage_metadata: Any) -> engine.CallCost:` |
| `        cost = adapt_agy_usage_to_call_cost(usage_metadata)` | `        cost = agy_engine.adapt_agy_usage_to_call_cost(usage_metadata)` |
| `        cost = compute_call_cost(usage_metadata, COST_CFG)` | `        cost = engine.compute_call_cost(usage_metadata, COST_CFG)` |
| `def print_cost_line(master_data: Dict[str, Any], cost: CallCost) -> None:` | `def print_cost_line(master_data: Dict[str, Any], cost: engine.CallCost) -> None:` |
| `    return get_pdf_page_count(file_path) > TYPE_CFG.batch_page_threshold` | `    return engine.get_pdf_page_count(file_path) > TYPE_CFG.batch_page_threshold` |
| `        return build_debug_generation_config()` | `        return engine.build_debug_generation_config()` |
| `    dynamic_prompt = get_dynamic_prompt(TYPE_CFG, file_metadata)` | `    dynamic_prompt = engine.get_dynamic_prompt(TYPE_CFG, file_metadata)` |
| `    dynamic_prompt += build_continuation_context(pending_continuation)` | `    dynamic_prompt += engine.build_continuation_context(pending_continuation)` |
| `        images = (rasterize_pdf_to_images(file_path) if file_path.suffix.lower() == ".pdf"` | `        images = (agy_engine.rasterize_pdf_to_images(file_path) if file_path.suffix.lower() == ".pdf"` |
| `                  else [optimize_image(str(file_path))])` | `                  else [engine.optimize_image(str(file_path))])` |
| `        full_prompt = get_cached_system_instruction(TYPE_CFG) + "\n\n" + dynamic_prompt` (first occurrence, inside the agy branch) | `        full_prompt = engine.get_cached_system_instruction(TYPE_CFG) + "\n\n" + dynamic_prompt` |
| `            result = call_agy_extract_chunked(images, SCHEMA, full_prompt, model=AGY_MODEL_ID,` | `            result = agy_engine.call_agy_extract_chunked(images, SCHEMA, full_prompt, model=AGY_MODEL_ID,` |
| `            page_data, usage_metadata = run_with_agy_retries(call_fn)` | `            page_data, usage_metadata = agy_engine.run_with_agy_retries(call_fn)` |
| `        _, content_part = build_content_part_for_file(client, file_path)` (both occurrences) | `        _, content_part = engine.build_content_part_for_file(client, file_path)` |
| `            prompt = get_cached_system_instruction(TYPE_CFG) + "\n\n" + dynamic_prompt` (second occurrence, inside the api branch) | `            prompt = engine.get_cached_system_instruction(TYPE_CFG) + "\n\n" + dynamic_prompt` |
| `            prompt += debug_schema_suffix(SCHEMA)` | `            prompt += engine.debug_schema_suffix(SCHEMA)` |
| `            raw_text = strip_markdown_fences((response.text or "").strip())` (both occurrences) | `            raw_text = engine.strip_markdown_fences((response.text or "").strip())` |
| `            page_data, usage_metadata = run_with_retries(call_fn)` | `            page_data, usage_metadata = engine.run_with_retries(call_fn)` |
| `            active_cache_name = create_context_cache(` | `            active_cache_name = engine.create_context_cache(` |
| `                client, MODEL_ID, get_cached_system_instruction(TYPE_CFG))` | `                client, MODEL_ID, engine.get_cached_system_instruction(TYPE_CFG))` |
| `            except DailyQuotaExhausted:` | `            except engine.DailyQuotaExhausted:` |
| `            delete_context_cache(client, active_cache_name)` | `            engine.delete_context_cache(client, active_cache_name)` |
| `        completed, still_pending = check_batch_jobs(client, pending_jobs)` | `        completed, still_pending = engine.check_batch_jobs(client, pending_jobs)` |
| `            for source_file, response in retrieve_batch_results(client, entry["job_name"]):` | `            for source_file, response in engine.retrieve_batch_results(client, entry["job_name"]):` |
| `        system_instruction = get_cached_system_instruction(TYPE_CFG)` | `        system_instruction = engine.get_cached_system_instruction(TYPE_CFG)` |
| `        file_metadata = {"File": file_path.stem, "Pages": str(get_pdf_page_count(file_path))}` | `        file_metadata = {"File": file_path.stem, "Pages": str(engine.get_pdf_page_count(file_path))}` |
| `        prompt = system_instruction + "\n\n" + get_dynamic_prompt(TYPE_CFG, file_metadata)` | `        prompt = system_instruction + "\n\n" + engine.get_dynamic_prompt(TYPE_CFG, file_metadata)` |
| `        requests.append(build_batch_request(MODEL_ID, [prompt, content_part], filename,` | `        requests.append(engine.build_batch_request(MODEL_ID, [prompt, content_part], filename,` |
| `    job_name = submit_batch_job(client, MODEL_ID, requests)` | `    job_name = engine.submit_batch_job(client, MODEL_ID, requests)` |

- [ ] **Step 4: Append `Extract.py`'s own `main()`**

```python
# ==============================================================================
# MAIN EXECUTION
# ==============================================================================
def main() -> None:
    if EXTRACTION_ENGINE == "agy":
        print("Verifying AGY CLI authentication...")
        if not agy_client.check_or_prompt_auth(AGY_MODEL_ID, cli_bin=AGY_CLI_BIN):
            print("[FATAL ERROR] Could not authenticate with agy. Run the 'Test Agy "
                  "Connection' action in Antiquarian's Global Settings, or `agy` "
                  "directly, to sign in, then try again.")
            return
        print("Authenticated.\n")

    master_data = load_master_db()
    all_files = list_source_files()

    if DEBUG_FILE:
        if DEBUG_FILE not in all_files:
            print(f"[DEBUG MODE] '{DEBUG_FILE}' not found in {SOURCE_DIR}. Aborting.")
            return
        print(f"[DEBUG MODE] Processing ONLY '{DEBUG_FILE}' with thinking enabled. "
              f"Nothing will be saved to {MASTER_DB}.\n")
        run_synchronous_batch([DEBUG_FILE], master_data)
        return

    processed_files = get_processed_files(master_data)
    already_in_batch = {fn for entry in master_data.get("pending_batch_jobs", [])
                        for fn in entry.get("file_names", [])}
    pending_files = [f for f in all_files if f not in processed_files and f not in already_in_batch]

    if EXTRACTION_ENGINE == "agy":
        if pending_files:
            run_synchronous_batch(pending_files, master_data)
        else:
            print("No new files to process.")
        return

    sync_files: List[str] = []
    batch_files: List[str] = []
    for filename in pending_files:
        file_path = Path(SOURCE_DIR) / filename
        (batch_files if is_batch_eligible(file_path) else sync_files).append(filename)

    if batch_files or master_data.get("pending_batch_jobs"):
        run_batch_mode(batch_files, master_data)

    if sync_files:
        run_synchronous_batch(sync_files, master_data)
    elif not batch_files and not master_data.get("pending_batch_jobs"):
        print("No new files to process.")


if __name__ == "__main__":
    main()
```

This is a verbatim copy of current `Paleographer.py` lines 2098–2145, wrapped as a standalone function (no substitutions needed — none of the names it calls are `engine`/`agy_engine` names).

- [ ] **Step 5: Fix any missed import or unused import**

Run: `python -c "import ast; ast.parse(open('Paleographer/Extract.py', encoding='utf-8').read())"`
Expected: no output (valid syntax).

Run: `cd Paleographer && python -c "import Extract"`
Expected: no `ImportError`/`NameError`. If one occurs naming a stdlib/typing symbol, add it to the Step 1 import block (the Step 1 list is a best-effort starting set, not guaranteed complete for every corner of the copied code). If it names an `engine.py`/`agy_engine.py` symbol, that call site was missed in Step 2/3's substitution table — find it and prefix it.

- [ ] **Step 6: Write a minimal dispatch-import smoke test**

Create `Paleographer/tests/test_extract_dispatch.py`:

```python
import Extract


def test_extract_module_has_main():
    assert callable(Extract.main)
```

- [ ] **Step 7: Run the new test**

Run: `pytest Paleographer/tests/test_extract_dispatch.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add Paleographer/Extract.py Paleographer/tests/test_extract_dispatch.py
git commit -m "Create Extract.py: record-type-generic extraction split out of Paleographer.py"
```

---

### Task 2: Create `ScripTools.py`, including the `type_specific_fields` bug fix

**Files:**
- Create: `Paleographer/ScripTools.py`
- Test: `Paleographer/tests/test_scriptools_dispatch.py` (new, minimal)

**Interfaces:**
- Consumes: `Voyageur.lac_client`/`Voyageur.LAC` (triple-fallback import, same pattern as today).
- Produces: `ScripTools.main()` — no arguments, parses `sys.argv` itself via `argparse` (the `mode` positional is still present in `sys.argv` when this is called — the dispatcher in Task 3 does not strip it). Consumed by Task 3's dispatcher and by `test_crosscheck.py` in Task 4.

- [ ] **Step 1: Create `Paleographer/ScripTools.py` with header, imports, and the POSTPROCESS-ScripTools functions**

```python
"""
ScripTools: Scrip-specific document enrichment for Paleographer.

Enriches, cross-checks against LAC search, partitions by collection, and resolves
maiden/dit names for Scrip claim records extracted by Extract.py. This module is
intentionally Scrip-only — it is not a generalization target for other record types.

Antiquarian.py launches Paleographer.py (the dispatcher) as a subprocess with
cwd=Paleographer/, so this module imports as a plain sibling.
"""

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from Voyageur import lac_client
    from Voyageur import LAC as voyageur_lac
except (ImportError, ValueError):
    try:
        from . import lac_client
        from . import LAC as voyageur_lac
    except (ImportError, ValueError):
        import lac_client
        import LAC as voyageur_lac

ROOT_ENV = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ROOT_ENV, override=True)
load_dotenv(Path(__file__).resolve().parent / ".env", override=True)


# ==============================================================================
# POSTPROCESS
# ==============================================================================
```

Then append the body of `fix_mojibake`, `clean_dit_name`, `parse_single_name`, `fix_participant_name`, `fix_all_participant_names_in_record`, `build_composite_record_number`, `resolve_maiden_name_for_record`, `resolve_dataset_maiden_names`, `extract_citation_fields`, copied **verbatim** from current `Paleographer.py` lines 246–530, in that order. Copy the text directly; do not retype it by hand.

- [ ] **Step 2: Append `SCRIP ENRICHMENT & PARTITIONING`, with the `type_specific_fields` bug fixed**

Copy `Paleographer.py` lines 1751–2018 verbatim (everything under the `SCRIP ENRICHMENT & PARTITIONING` banner), keeping the banner comment, **except** for `build_claim_search_queries`/`build_claim_search_query` (current lines 1843–1867): every other reader of Scrip's type-specific fields goes through `record["type_specific_fields"]` (per `build_merged_schema` — `.pmt`-declared `extra_fields` nest there), but these two functions currently read `claim_number`/`scrip_number`/`affidavit_number` off the top level of `record`, so they silently return no query for any real extracted record. Write these two functions as:

```python
def expand_scrip_number_range(scrip_number: Optional[str]) -> List[str]:
    if not scrip_number:
        return []
    match = _SCRIP_RANGE_RE.match(scrip_number)
    if not match:
        return [scrip_number.strip()]
    start, end = int(match.group(1)), int(match.group(2))
    if end < start or end - start > 500:
        return [scrip_number.strip()]
    return [str(n) for n in range(start, end + 1)]


def build_claim_search_queries(record: Dict[str, Any]) -> List[str]:
    fields = record.get("type_specific_fields", {})
    claim_number = fields.get("claim_number")
    if claim_number:
        return [claim_number.strip()]
    queries = []
    for num in expand_scrip_number_range(fields.get("scrip_number")):
        queries.append(num)
    affidavit_number = fields.get("affidavit_number")
    if affidavit_number:
        queries.append(affidavit_number.strip())
    return queries


def build_claim_search_query(record: Dict[str, Any]) -> Optional[str]:
    queries = build_claim_search_queries(record)
    return queries[0] if queries else None
```

Read the actual current bodies of `expand_scrip_number_range` (line 1830), `build_claim_search_queries` (1843), and `build_claim_search_query` (1865) in `Paleographer/Paleographer.py` before writing this — the block above is the corrected shape (top-level reads replaced with `record.get("type_specific_fields", {})` reads), but copy `expand_scrip_number_range`'s body and `_SCRIP_RANGE_RE`'s definition (line 1827) verbatim from the source; only `build_claim_search_queries`/`build_claim_search_query` change behavior.

- [ ] **Step 3: Append `ScripTools.py`'s own `main()`**

```python
# ==============================================================================
# MAIN EXECUTION
# ==============================================================================
def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Paleographer: AI-driven extraction & document enrichment.")
    parser.add_argument("mode", choices=["enrich", "crosscheck", "partition", "resolve-names"],
                        help="Operating mode")
    parser.add_argument("--json", dest="json_path", default=None,
                        help="Path to JSON dataset (for enrich, crosscheck, partition, resolve-names)")
    parser.add_argument("--delay", type=float, default=0.4, help="Delay in seconds between requests (for enrich)")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of records to process (for enrich)")
    parser.add_argument("--output-dir", default=None, help="Output directory for partitioned datasets")
    parser.add_argument("--cookie-file", default=voyageur_lac.COOKIE_FILE,
                        help="Path to browser cookies file for LAC search (for crosscheck)")
    args, _ = parser.parse_known_args()

    if args.mode == "crosscheck":
        target = resolve_json_input(args.json_path or os.getenv("MASTER_DB", "master_database.json"),
                                    os.getenv("OUTPUT_DIR", str(Path(__file__).resolve().parent / "output")))
        print(f"Cross-checking claims in dataset: {target}...")
        try:
            cookies = voyageur_lac.load_cookies(args.cookie_file)
        except (FileNotFoundError, ValueError) as e:
            print(f"[FATAL ERROR] {e} Search LAC once in a real browser, then paste its Cookie header "
                  f"into that file.")
            return
        with open(target, "r", encoding="utf-8") as f:
            data = json.load(f)
        for sheet in data.get("sheets", []):
            for record in sheet.get("records", []):
                cross_check_claim_record(record, cookies, voyageur_lac.MEDIA_DIR)
        with open(target, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Cross-check complete: {target}")
        return

    if args.mode == "enrich":
        target = resolve_json_input(args.json_path or os.getenv("MASTER_DB", "master_database.json"),
                                    os.getenv("OUTPUT_DIR", str(Path(__file__).resolve().parent / "output")))
        print(f"Enriching dataset: {target}...")
        with open(target, "r", encoding="utf-8") as f:
            data = json.load(f)
        enrich_json_data(data, delay_seconds=args.delay, limit=args.limit)
        with open(target, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Enrichment complete: {target}")
        return

    if args.mode == "partition":
        target = resolve_json_input(args.json_path or os.getenv("MASTER_DB", "master_database.json"),
                                    os.getenv("OUTPUT_DIR", str(Path(__file__).resolve().parent / "output")))
        out_dir = Path(args.output_dir) if args.output_dir else target.parent / "partitioned"
        print(f"Partitioning dataset {target} into {out_dir}...")
        with open(target, "r", encoding="utf-8") as f:
            data = json.load(f)
        written = partition_json_by_collection(data, out_dir)
        print(f"Partitioned into {len(written)} collections in {out_dir}")
        for k, p in written.items():
            print(f" - {k}: {p.name}")
        return

    if args.mode == "resolve-names":
        target = resolve_json_input(args.json_path or os.getenv("MASTER_DB", "master_database.json"),
                                    os.getenv("OUTPUT_DIR", str(Path(__file__).resolve().parent / "output")))
        print(f"Resolving names in dataset: {target}...")
        with open(target, "r", encoding="utf-8") as f:
            data = json.load(f)
        count = resolve_dataset_maiden_names(data)
        with open(target, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Resolved maiden/dit names for {count} records in {target}")
        return


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Fix any missed import**

Run: `python -c "import ast; ast.parse(open('Paleographer/ScripTools.py', encoding='utf-8').read())"`
Expected: no output.

Run: `cd Paleographer && python -c "import ScripTools"`
Expected: no error. Add any missing import the same way as Task 1 Step 5.

- [ ] **Step 5: Write the `type_specific_fields` regression test and a dispatch smoke test**

Create `Paleographer/tests/test_scriptools_dispatch.py`:

```python
import ScripTools


def test_scriptools_module_has_main():
    assert callable(ScripTools.main)


def test_build_claim_search_query_reads_type_specific_fields():
    record = {"type_specific_fields": {"claim_number": "123"}}
    assert ScripTools.build_claim_search_query(record) == "123"


def test_build_claim_search_query_top_level_fields_are_ignored():
    record = {"claim_number": "123"}
    assert ScripTools.build_claim_search_query(record) is None
```

- [ ] **Step 6: Run the new tests**

Run: `pytest Paleographer/tests/test_scriptools_dispatch.py -v`
Expected: PASS (3 tests). The second test documents the fix — before this task, `build_claim_search_query` read the top level and this same input would have returned a truthy value instead of `None`.

- [ ] **Step 7: Commit**

```bash
git add Paleographer/ScripTools.py Paleographer/tests/test_scriptools_dispatch.py
git commit -m "Create ScripTools.py: Scrip-only enrichment split out of Paleographer.py, fix type_specific_fields read"
```

---

### Task 3: Rewrite `Paleographer.py` as a thin dispatcher

**Files:**
- Modify: `Paleographer/Paleographer.py` (full rewrite — 2,148 lines → ~20 lines)
- Test: `Paleographer/tests/test_paleographer_dispatcher.py` (new)

**Interfaces:**
- Consumes: `Extract.main()`, `ScripTools.main()` (Tasks 1–2) — both take no arguments and read `sys.argv` themselves.
- Produces: nothing consumed by later tasks. `Antiquarian.py` already launches `Paleographer/Paleographer.py` as a subprocess with cwd set to its own directory (`Antiquarian.py:1869`) — that contract is unchanged.

- [ ] **Step 1: Write the failing dispatcher tests**

Create `Paleographer/tests/test_paleographer_dispatcher.py`:

```python
import sys
import types

import pytest

import Paleographer


@pytest.mark.parametrize("mode", ["enrich", "crosscheck", "partition", "resolve-names"])
def test_main_dispatches_enrichment_modes_to_scriptools(mode, monkeypatch):
    calls = []
    fake_module = types.ModuleType("ScripTools")
    fake_module.main = lambda: calls.append(sys.argv[:])
    monkeypatch.setitem(sys.modules, "ScripTools", fake_module)
    monkeypatch.setattr(sys, "argv", ["Paleographer.py", mode, "--extra", "value"])

    Paleographer.main()

    assert calls == [["Paleographer.py", mode, "--extra", "value"]]


def test_main_dispatches_no_args_to_extract(monkeypatch):
    calls = []
    fake_module = types.ModuleType("Extract")
    fake_module.main = lambda: calls.append(sys.argv[:])
    monkeypatch.setitem(sys.modules, "Extract", fake_module)
    monkeypatch.setattr(sys, "argv", ["Paleographer.py"])

    Paleographer.main()

    assert calls == [["Paleographer.py"]]


def test_main_dispatches_debug_filename_to_extract(monkeypatch):
    calls = []
    fake_module = types.ModuleType("Extract")
    fake_module.main = lambda: calls.append(sys.argv[:])
    monkeypatch.setitem(sys.modules, "Extract", fake_module)
    monkeypatch.setattr(sys, "argv", ["Paleographer.py", "some_file.pdf"])

    Paleographer.main()

    assert calls == [["Paleographer.py", "some_file.pdf"]]
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `pytest Paleographer/tests/test_paleographer_dispatcher.py -v`
Expected: FAIL — the current `Paleographer.py` is still the 2,148-line monolith; `Paleographer.main()` does not dispatch to sibling modules at all.

- [ ] **Step 3: Overwrite `Paleographer.py` entirely**

This is a full-file replacement (use the Write tool, not a targeted edit). Replace the entire contents of `Paleographer/Paleographer.py` with:

```python
"""
Paleographer: thin dispatcher for AI-driven document extraction and Scrip-specific
enrichment.

Extraction (record-type-generic, driven entirely by the active .pmt file) lives in
Extract.py. Scrip-only enrichment (enrich, crosscheck, partition, resolve-names)
lives in ScripTools.py. Antiquarian.py launches this as a subprocess with
cwd=Paleographer/, so Extract.py and ScripTools.py import as plain sibling modules.
"""

import sys

ENRICHMENT_MODES = ("enrich", "crosscheck", "partition", "resolve-names")


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] in ENRICHMENT_MODES:
        import ScripTools
        ScripTools.main()
    else:
        import Extract
        Extract.main()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `pytest Paleographer/tests/test_paleographer_dispatcher.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Run the full Paleographer test suite**

Run: `pytest Paleographer/tests/ -v`
Expected: `test_engine.py`, `test_agy_engine.py`, `test_schema.py` still PASS unchanged. `test_master_db_merge.py`, `test_paleographer_pipeline.py`, `test_crosscheck.py`, `test_settings_standalone.py` will FAIL at collection (they still do `importlib.import_module("Paleographer")` and call functions no longer defined there) — this is expected here; Task 4 fixes them. Confirm the failures are exactly these four files and are import/attribute errors, not something new.

- [ ] **Step 6: Commit**

```bash
git add Paleographer/Paleographer.py Paleographer/tests/test_paleographer_dispatcher.py
git commit -m "Rewrite Paleographer.py as a thin dispatcher to Extract.py/ScripTools.py"
```

---

### Task 4: Repoint the four test files still importing `Paleographer`

**Files:**
- Modify: `Paleographer/tests/test_master_db_merge.py`
- Modify: `Paleographer/tests/test_settings_standalone.py`
- Modify: `Paleographer/tests/test_crosscheck.py`
- Modify: `Paleographer/tests/test_paleographer_pipeline.py`

**Interfaces:**
- Consumes: `Extract.py` (Task 1), `ScripTools.py` (Task 2), `engine.py` (untouched, already has its own test coverage in `test_engine.py`).
- Produces: nothing consumed by later tasks.

This task has no new tests of its own — it repoints existing tests to the modules that now define the functions they exercise. Verified function membership (grepped against each file before this task started):

- `test_master_db_merge.py` (`importlib.import_module("Paleographer")` at line 47) calls `module.get_processed_files`, `module.merge_sheets`, `module.save_master_db`, `module.MASTER_DB` — all `Extract.py`.
- `test_settings_standalone.py` (line 53) calls `module.SOURCE_DIR`, `module.MASTER_DB`, `module.load_master_db` — all `Extract.py`.
- `test_crosscheck.py` (line 45) exercises `cross_check_claim_record` and LAC cookie handling — all `ScripTools.py`.
- `test_paleographer_pipeline.py` (two import sites, lines 127 and 574) calls `module.main()`, `module.EXTRACTION_ENGINE`, `module.client` (all `Extract.py`), **and** `module.build_merged_schema`, `module.parse_type_config`, `module.resolve_prompt_path`, `module.build_vocabulary_summary` (lines 350, 370, 373, 393, 396 — these are `engine.py` functions, no longer defined on `Extract` as bare names since `Extract.py` calls them as `engine.build_merged_schema` etc.).

- [ ] **Step 1: Repoint `test_master_db_merge.py`**

```python
old_string: return importlib.import_module("Paleographer")
```

```python
new_string: return importlib.import_module("Extract")
```

- [ ] **Step 2: Repoint `test_settings_standalone.py`**

```python
old_string: return importlib.import_module("Paleographer")
```

```python
new_string: return importlib.import_module("Extract")
```

- [ ] **Step 3: Repoint `test_crosscheck.py`**

```python
old_string: return importlib.import_module("Paleographer")
```

```python
new_string: return importlib.import_module("ScripTools")
```

- [ ] **Step 4: Repoint `test_paleographer_pipeline.py`**

Read the file first to confirm the exact surrounding context at each site (two `importlib.import_module("Paleographer")` calls and the five `module.<engine-function>` call sites), then:

- Replace both occurrences of `importlib.import_module("Paleographer")` with `importlib.import_module("Extract")`.
- Add `import engine` near the top of the file, alongside its other imports.
- Replace `module.build_merged_schema(` with `engine.build_merged_schema(` (line ~350).
- Replace both `module.parse_type_config(module.resolve_prompt_path(` with `engine.parse_type_config(engine.resolve_prompt_path(` (lines ~370, ~393).
- Replace both `module.build_vocabulary_summary(` with `engine.build_vocabulary_summary(` (lines ~373, ~396).

- [ ] **Step 5: Run the full Paleographer test suite**

Run: `pytest Paleographer/tests/ -v`
Expected: all tests PASS, including the four repointed files.

- [ ] **Step 6: Commit**

```bash
git add Paleographer/tests/test_master_db_merge.py Paleographer/tests/test_settings_standalone.py Paleographer/tests/test_crosscheck.py Paleographer/tests/test_paleographer_pipeline.py
git commit -m "Repoint Paleographer test suite from the monolith to Extract.py/ScripTools.py"
```

---

### Task 5: UI-gate the Scrip-only buttons in Antiquarian.py

**Files:**
- Modify: `Antiquarian.py:1523-1536` (`_on_record_type_change`)
- Modify: `Antiquarian.py:1566-1578` (button creation)
- Test: `tests/test_antiquarian_paleographer_gating.py` (new — check the existing `tests/` directory structure first; if Antiquarian has no existing GUI-logic test file, create this one at the repo root `tests/` directory alongside any existing Antiquarian tests, or inside `Antiquarian/tests/` if that's the established location. If `Antiquarian.py` has no test directory at all, place it at `tests/test_antiquarian_paleographer_gating.py`.)

**Interfaces:**
- Consumes: `self.string_vars["PALEOGRAPHER_RECORD_TYPE"]` (existing), `self._on_record_type_change` (existing method, being modified).
- Produces: nothing consumed by later tasks.

A Parish or Census user can click "Enrich Metadata" today and get a silent no-op — `classify_sheet_collection` falls to `UNKNOWN_COLLECTION_LABEL` for any sheet without Scrip-shaped fields. Disable (not hide, to keep layout stable) the Enrich Metadata / Partition Collections / Resolve Names / Crosscheck-adjacent buttons unless the selected Record Type is `Scrip`.

- [ ] **Step 1: Store button references and gate them in `_on_record_type_change`**

```python
old_string:
        ctk.CTkButton(btn_box, text="Enrich Metadata", fg_color="#2b7a4b", hover_color="#1e5935",
                      text_color=C_TEXT,
                      command=lambda: self.execute_script("ANALYSIS_SCRIPT", "enrich")).pack(side="left", padx=5)
        ctk.CTkButton(btn_box, text="Partition Collections", fg_color="#7A5B2B", hover_color="#5B431E",
                      text_color=C_TEXT,
                      command=lambda: self.execute_script("ANALYSIS_SCRIPT", "partition")).pack(side="left", padx=5)
        ctk.CTkButton(btn_box, text="Resolve Names", fg_color="#4A5568", hover_color="#2D3748",
                      text_color=C_TEXT,
                      command=lambda: self.execute_script("ANALYSIS_SCRIPT", "resolve-names")).pack(side="left", padx=5)
```

```python
new_string:
        self.paleographer_enrich_btn = ctk.CTkButton(
            btn_box, text="Enrich Metadata", fg_color="#2b7a4b", hover_color="#1e5935",
            text_color=C_TEXT, command=lambda: self.execute_script("ANALYSIS_SCRIPT", "enrich"))
        self.paleographer_enrich_btn.pack(side="left", padx=5)
        self.paleographer_partition_btn = ctk.CTkButton(
            btn_box, text="Partition Collections", fg_color="#7A5B2B", hover_color="#5B431E",
            text_color=C_TEXT, command=lambda: self.execute_script("ANALYSIS_SCRIPT", "partition"))
        self.paleographer_partition_btn.pack(side="left", padx=5)
        self.paleographer_resolve_names_btn = ctk.CTkButton(
            btn_box, text="Resolve Names", fg_color="#4A5568", hover_color="#2D3748",
            text_color=C_TEXT, command=lambda: self.execute_script("ANALYSIS_SCRIPT", "resolve-names"))
        self.paleographer_resolve_names_btn.pack(side="left", padx=5)
```

- [ ] **Step 2: Gate the buttons inside `_on_record_type_change`**

```python
old_string:
    def _on_record_type_change(self, _value: Optional[str] = None):
        """Rebuilds the settings form to only show the fields the selected .pmt's own
        settings_sections declares as relevant, instead of every Paleographer field for
        every record type."""
        record_type = self.string_vars["PALEOGRAPHER_RECORD_TYPE"].get()

        if hasattr(self, "paleographer_form_container"):
```

```python
new_string:
    def _on_record_type_change(self, _value: Optional[str] = None):
        """Rebuilds the settings form to only show the fields the selected .pmt's own
        settings_sections declares as relevant, instead of every Paleographer field for
        every record type. Also gates the Scrip-only enrichment buttons - Enrich Metadata,
        Partition Collections, and Resolve Names have no meaning for non-Scrip record
        types and silently no-op if clicked (classify_sheet_collection has no Scrip-shaped
        fields to key off of), so disable rather than hide them to keep the button row's
        layout stable across Record Type switches."""
        record_type = self.string_vars["PALEOGRAPHER_RECORD_TYPE"].get()

        if hasattr(self, "paleographer_enrich_btn"):
            scrip_state = "normal" if record_type == "Scrip" else "disabled"
            self.paleographer_enrich_btn.configure(state=scrip_state)
            self.paleographer_partition_btn.configure(state=scrip_state)
            self.paleographer_resolve_names_btn.configure(state=scrip_state)

        if hasattr(self, "paleographer_form_container"):
```

- [ ] **Step 3: Determine the record-type values `_list_record_types()` actually produces**

Read `Antiquarian.py`'s `_list_record_types` method (referenced at line 1548) to confirm it returns `.pmt` file stems (e.g. `"Scrip"`, `"Parish"`, `"Census"`) and not full filenames like `"Scrip.pmt"` — the gating check in Step 2 compares `record_type == "Scrip"`. If `_list_record_types()` returns filenames with the `.pmt` suffix instead, change the comparison to `record_type == "Scrip.pmt"` and note this in the commit message.

- [ ] **Step 4: Write the gating test**

Create `tests/test_antiquarian_paleographer_gating.py` (adjust the import path in the first line if `Antiquarian.py`'s test suite imports it differently elsewhere — check an existing Antiquarian test file for the established import pattern first):

```python
import customtkinter as ctk
import pytest

from Antiquarian import AntiquarianApp


@pytest.fixture
def app():
    root = AntiquarianApp()
    yield root
    root.destroy()


def test_scrip_record_type_enables_enrichment_buttons(app):
    app.string_vars["PALEOGRAPHER_RECORD_TYPE"].set("Scrip")
    app._on_record_type_change()
    assert app.paleographer_enrich_btn.cget("state") == "normal"
    assert app.paleographer_partition_btn.cget("state") == "normal"
    assert app.paleographer_resolve_names_btn.cget("state") == "normal"


def test_non_scrip_record_type_disables_enrichment_buttons(app):
    app.string_vars["PALEOGRAPHER_RECORD_TYPE"].set("Parish")
    app._on_record_type_change()
    assert app.paleographer_enrich_btn.cget("state") == "disabled"
    assert app.paleographer_partition_btn.cget("state") == "disabled"
    assert app.paleographer_resolve_names_btn.cget("state") == "disabled"
```

If `AntiquarianApp()` cannot be constructed headlessly in this environment (CustomTkinter needs a display), report `DONE_WITH_CONCERNS` rather than forcing it — note in the report which import/construction failed, keep Steps 1-3's gating code as-is (it is correct regardless), and skip Steps 4-5 for an automated test; manual verification substitutes (toggle Record Type in the running GUI, confirm the three buttons enable/disable).

- [ ] **Step 5: Run the test**

Run: `pytest tests/test_antiquarian_paleographer_gating.py -v` (or skip per the fallback above)
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add Antiquarian.py tests/test_antiquarian_paleographer_gating.py
git commit -m "Gate Enrich/Partition/Resolve-Names buttons to Scrip record type"
```

---

### Task 6: Verify scaffold-placeholder round-trip coverage

**Files:**
- Modify (maybe): `Paleographer/tests/test_master_db_merge.py`

**Interfaces:**
- Consumes: `Extract.get_processed_files`, `Extract.merge_sheets`, `Extract._sheet_is_placeholder` (Task 1, repointed in Task 4).
- Produces: nothing consumed by later tasks.

This verifies the "consume the Sub-project 3 scaffold as pure analysis" half of the original Sub-project 6 scope. Investigation during brainstorming found the mechanism already implemented by Sub-projects 3/4 — this task is verification, adding coverage only if a real gap exists.

- [ ] **Step 1: Read the current test coverage**

Read `Paleographer/tests/test_master_db_merge.py` in full (it is short — under 180 lines per the grep in Task 4). Check whether an existing test already covers this exact scenario: a `master_data` dict seeded with a `build_empty_sheet`-shaped placeholder sheet for a given `file_name` (i.e. a sheet whose `records` are absent/empty and that `Extract._sheet_is_placeholder` would return `True` for), then `merge_sheets` called with a real (non-placeholder) sheet for that same `file_name`, asserting the placeholder is replaced in place (one sheet in the result, not two).

- [ ] **Step 2: If covered, stop here**

If an existing test (e.g. one of the ones referencing `other_sheet`/`new_sheet` around lines 93-115 per Task 4's grep) already exercises exactly that placeholder-replacement path, no new test is needed. Report which test covers it and move to Step 5 (commit is a no-op in this case — skip it).

- [ ] **Step 3: If not covered, add the test**

Read `Commissioner/record_registry.py`'s `build_empty_sheet()` (referenced at `Commissioner/record_registry.py:178-211`) first to construct a realistic placeholder shape. Add to `Paleographer/tests/test_master_db_merge.py`:

```python
def test_merge_sheets_replaces_placeholder_scaffold_in_place(build_master_data):
    # Shape matches Commissioner.record_registry.build_empty_sheet(): a scaffold sheet
    # Voyageur writes before Paleographer ever runs, carrying no extracted records yet.
    placeholder_sheet = {
        "file_name": "abc123.jpg",
        "records": [],
    }
    master_data = build_master_data([placeholder_sheet])

    real_sheet = {
        "file_name": "abc123.jpg",
        "records": [{"participants": [{"first_name": "Jean", "surname": "Tremblay"}]}],
    }

    module.merge_sheets(master_data, [real_sheet])

    matching = [s for s in master_data["sheets"] if s["file_name"] == "abc123.jpg"]
    assert len(matching) == 1
    assert matching[0]["records"] == real_sheet["records"]
```

Adapt this to whatever fixture/helper pattern (`build_master_data` or equivalent) the existing tests in this file already use — read the file's existing fixtures first rather than inventing a new one; use `module.merge_sheets` (the file's existing alias for the `Extract` import from Task 4) consistently with the rest of the file.

- [ ] **Step 4: Run the test**

Run: `pytest Paleographer/tests/test_master_db_merge.py -v`
Expected: PASS.

- [ ] **Step 5: Commit (only if Step 3 added a test)**

```bash
git add Paleographer/tests/test_master_db_merge.py
git commit -m "Add scaffold-placeholder round-trip regression test for merge_sheets"
```

---

### Task 7: Rename `CENSUS_URL` to `A_URL`

**Files:**
- Modify: `Voyageur/A.py:58`
- Modify: `Antiquarian.py:106,235,331`
- Modify: `Voyageur/.env:4`
- Modify: `Archivist/.env:1`

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing consumed by later tasks. Purely mechanical rename — matches the `FS_URL`/`LAC_URL` convention the other two Voyageur sources already follow.

- [ ] **Step 1: Rename in `Voyageur/A.py`**

```python
old_string:
    url = os.getenv("CENSUS_URL", "").strip()
```

```python
new_string:
    url = os.getenv("A_URL", "").strip()
```

- [ ] **Step 2: Rename in `Antiquarian.py`**

```python
old_string:
                 "Ancestry": {"CENSUS_URL": ""},
```

```python
new_string:
                 "Ancestry": {"A_URL": ""},
```

```python
old_string:
    "CENSUS_URL": "The web address (URL) of the specific Ancestry.com census page you want to gather.",
```

```python
new_string:
    "A_URL": "The web address (URL) of the specific Ancestry.com census page you want to gather.",
```

```python
old_string:
    "CENSUS_URL": "Ancestry Census URL",
```

```python
new_string:
    "A_URL": "Ancestry Census URL",
```

- [ ] **Step 3: Rename the env var key in `Voyageur/.env`**

Change line 4 from `CENSUS_URL='https://www.ancestry.com/imageviewer/collections/7667/images/4211353_00001?queryId=527a29b7-f294-4e6a-814a-76b2b4e11e0b&usePUB=true&_phsrc=uYF181&_phstart=successSource&usePUBJs=true&pId=17613762'` to `A_URL='https://www.ancestry.com/imageviewer/collections/7667/images/4211353_00001?queryId=527a29b7-f294-4e6a-814a-76b2b4e11e0b&usePUB=true&_phsrc=uYF181&_phstart=successSource&usePUBJs=true&pId=17613762'` — only the key name changes, the URL value is untouched. `.env` files are typically gitignored; confirm with `git check-ignore Voyageur/.env` before attempting to `git add` it in Step 6 — if ignored, this edit still matters locally but is not part of the commit.

- [ ] **Step 4: Rename the env var key in `Archivist/.env`**

Change line 1 from `CENSUS_URL='https://www.ancestry.com/imageviewer/collections/2442/images/M-T0627-03009-00399?usePUB=true&_phsrc=MpD112&pId=105307051'` to `A_URL='https://www.ancestry.com/imageviewer/collections/2442/images/M-T0627-03009-00399?usePUB=true&_phsrc=MpD112&pId=105307051'` — same rule, key only.

- [ ] **Step 5: Search for any remaining `CENSUS_URL` references and update tests**

Run: `grep -rn "CENSUS_URL" --include=*.py .` (or the project's Grep tool equivalent) and fix any remaining source-code or test reference this plan's Step 1-2 greps didn't already cover (the design doc's own text mentioning `CENSUS_URL` historically, in `docs/superpowers/specs/`, is documentation of past work and does not need updating).

- [ ] **Step 6: Run the full test suite**

Run: `pytest -v` (project-wide)
Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add Voyageur/A.py Antiquarian.py
git commit -m "Rename CENSUS_URL to A_URL, matching the FS_URL/LAC_URL convention"
```

(`.env` files stay uncommitted per Step 3's ignore-check, unless that check shows they are actually tracked — if `git check-ignore` finds them tracked, add them to this same commit instead.)

---

## Self-review notes

- **Spec coverage:** Split (Tasks 1-3), Fix/`type_specific_fields` (Task 2), Fix/UI gating (Task 5), Verify/scaffold round-trip (Task 6), Rename (Task 7), test repointing (Task 4) — every Scope item in the design doc maps to a task.
- **Placeholder scan:** the UI-gating task (5) has two conditional fallbacks (test directory location, `_list_record_types()` return shape, headless GUI construction) — these are investigate-then-decide steps with an explicit fallback behavior specified in each case, not open-ended "handle appropriately" placeholders.
- **Type consistency:** `Extract.main()`/`ScripTools.main()` (both no-argument, `sys.argv`-reading) are used identically in Task 3's dispatcher and Task 3's tests. `record["type_specific_fields"]` matches the nesting `build_merged_schema` (in `engine.py`, unchanged) already produces for every other Scrip field reader.
