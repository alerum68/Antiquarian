"""
Paleographer: General-Purpose Historical Document Extraction Script.

Uses the Gemini API to transcribe historical document images or PDFs of any
record type and extract structured records into a JSON master database,
following one universal schema. Which record type is active, and every
piece of type-specific vocabulary (event types, roles, defaults, schema
extensions), comes entirely from a single .pmt file in prompts/; this
script and engine.py never change when a new record type is added.
"""

import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from dotenv import load_dotenv
from google import genai

import agy_engine
import engine
import postprocess
from ScriptoriumMCP import agy_client

# The Toolbox's own subprocess launcher sets PYTHONIOENCODING=utf-8, but this script also
# supports being run directly from the command line (its debug mode), where stdout would
# otherwise fall back to the system's default codepage and crash on emoji/checkmarks.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Global settings come from the project root's .env; this tool's own settings come from
# its own subfolder's .env, so Paleographer stays runnable standalone.
ROOT_ENV = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ROOT_ENV, override=True)
load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

# EXTRACTION_ENGINE picks which backend actually performs the AI extraction: "agy" (the
# default) shells out to the Antigravity CLI, subscription-covered rather than metered
# per-token; "api" uses the direct google-genai SDK against GEMINI_API_KEY. Read early
# since it decides whether a genai client is even constructed below.
EXTRACTION_ENGINE: str = (os.getenv("EXTRACTION_ENGINE", "agy") or "agy").strip().lower()
if EXTRACTION_ENGINE not in ("api", "agy"):
    raise RuntimeError(f"Unknown EXTRACTION_ENGINE '{EXTRACTION_ENGINE}' - expected 'api' or 'agy'.")

# Only constructed for the api engine - the agy engine never calls engine.
# build_content_part_for_file at all (rasterization replaces it for both images and
# PDFs), so client is never touched/dereferenced on that path regardless of file type.
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY")) if EXTRACTION_ENGINE == "api" else None

# ==========================================
# CONFIGURATION
# ==========================================
RECORD_TYPE_NAME = os.getenv("PALEOGRAPHER_RECORD_TYPE", "")
COLLECTION_TITLE = os.getenv("VOLUME_TITLE")
VOLUME_NUM = os.getenv("VOLUME_NUM", "")

TYPE_CFG = engine.parse_type_config(engine.resolve_prompt_path(RECORD_TYPE_NAME))


def resolve_setting(generic_key: str, default: str = "") -> str:
    """Resolves a generic runtime setting (IMAGE_DIR, MASTER_DB_NAME, ...) via the active
    record type's own field_remap table (see Parish.pmt/Scrip.pmt's front matter): finds
    whichever of this record type's own prefixed .env keys maps to generic_key, and reads
    that. Falls back to reading generic_key directly so a record type with no field_remap
    entry for it (or no field_remap at all) still works. This is what lets Paleographer.py
    resolve its own settings from its own .env with no dependency on Scriptorium.py's GUI
    layer bridging prefixed settings-tab names to the generic names this script reads."""
    for prefixed_key, target in TYPE_CFG.field_remap.items():
        if target == generic_key:
            val = os.getenv(prefixed_key, "")
            if val:
                return val
    return os.getenv(generic_key, default)


API_BUDGET: float = float(os.getenv("API_BUDGET", "5.00"))
COST_CFG = engine.CostConfig(
    cost_per_1m_in=float(os.getenv("COST_PER_1M_INPUT", "0.075")),
    cost_per_1m_out=float(os.getenv("COST_PER_1M_OUTPUT", "0.30")),
    cache_discount_multiplier=float(os.getenv("CACHE_DISCOUNT_MULTIPLIER", "0.10")),
)

PROGRAM_DIR: Path = Path(os.getenv("PROGRAM_DIR", ""))
_MASTER_DB_NAME = resolve_setting("MASTER_DB_NAME")
if not _MASTER_DB_NAME:
    raise RuntimeError(
        "MASTER_DB_NAME resolved to an empty value (check the active record type's own "
        "MASTER_DB_NAME setting, e.g. CHURCH_MASTER_DB_NAME for Parish.pmt) - without it "
        "MASTER_DB would just be the JSON folder itself, not a file inside it.")
MASTER_DB: str = str(PROGRAM_DIR / os.getenv("JSON_DIR", "") / _MASTER_DB_NAME)
SOURCE_DIR: str = str(PROGRAM_DIR / resolve_setting("IMAGE_DIR"))

MODEL_ID: str = os.getenv("MODEL_NAME") or ""
if not MODEL_ID:
    raise RuntimeError("MODEL_NAME is not set. Check your .env configuration.")
DEBUG_FILE: Union[str, None] = sys.argv[1] if len(sys.argv) > 1 else None

# agy-engine-only settings. AGY_MODEL_ID is always passed explicitly to every agy call,
# never left to agy's own default - confirmed live that agy's own default (when
# --model is omitted) is a flash-tier model with materially worse OCR quality, and
# that shorthand values like "pro"/"flash" are not valid --model values at all.
AGY_MODEL_ID: str = os.getenv("AGY_MODEL_NAME") or agy_engine.DEFAULT_MODEL
AGY_CLI_BIN: str = os.getenv("AGY_CLI_BIN") or agy_client.DEFAULT_CLI_BIN
AGY_TIMEOUT_SECONDS: int = int(os.getenv("AGY_TIMEOUT_SECONDS", str(agy_client.DEFAULT_TIMEOUT_SECONDS)))

SOURCE_SUFFIXES = engine.IMAGE_SUFFIXES + (".pdf",)

with open(Path(__file__).resolve().parent / "schema.json", "r", encoding="utf-8") as _schema_file:
    CORE_SCHEMA: Dict[str, Any] = json.load(_schema_file)

SCHEMA: Dict[str, Any] = engine.build_merged_schema(CORE_SCHEMA, TYPE_CFG.extra_fields)


# ==========================================
# RECORD POST-PROCESSING
# ==========================================
def finalize_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Applies every generic mechanical post-processing step to one extracted record."""
    postprocess.derive_role_numbers(record, TYPE_CFG.roles)
    postprocess.derive_role_semantics(record, TYPE_CFG.roles)
    postprocess.derive_record_identity(record, TYPE_CFG.event_types)
    postprocess.derive_suffixes(record, TYPE_CFG.roles)
    postprocess.apply_defaults(record, TYPE_CFG.defaults.get("record", {}))

    if record.get("event_date"):
        record["event_date"] = postprocess.parse_to_iso(record["event_date"])

    for participant in record.get("participants", []):
        participant["std_given"] = postprocess.strip_diacritics(participant.get("std_given"))
        participant["std_surname"] = postprocess.strip_diacritics(participant.get("std_surname"))
        if participant.get("birth_date"):
            participant["birth_date"] = postprocess.parse_to_iso(participant["birth_date"])
        if participant.get("death_date"):
            participant["death_date"] = postprocess.parse_to_iso(participant["death_date"])
        postprocess.apply_defaults(participant, TYPE_CFG.defaults.get("participant", {}))

    return record


def finalize_page_data(page_data: Dict[str, Any]) -> Dict[str, Any]:
    for sheet in page_data.get("sheets", []):
        for record in sheet.get("records", []):
            finalize_record(record)
    # After every record has its record_id (event_type + record_number) set, fold
    # together any that share one - e.g. a witness affidavit and the claimant's own
    # affidavit, sworn on different pages but supporting the same claim - into a single
    # record, rather than leaving separate documents for the same claim unmerged.
    postprocess.merge_same_claim_records(page_data.get("sheets", []))
    return page_data


def tag_document_metadata(page_data: Dict[str, Any], file_name: str, file_ext: str) -> None:
    for sheet in page_data.get("sheets", []):
        metadata = sheet.setdefault("document_metadata", {})
        metadata["file_name"] = file_name
        metadata["file_type"] = file_ext
        metadata["volume"] = VOLUME_NUM


# ==========================================
# MASTER DB HELPERS
# ==========================================
def load_master_db() -> Dict[str, Any]:
    if os.path.exists(MASTER_DB):
        with open(MASTER_DB, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("record_type_name", TYPE_CFG.name)
        return data
    return {"collection_title": COLLECTION_TITLE, "record_type_name": TYPE_CFG.name, "sheets": [],
            "total_spent": 0.0, "total_pages_processed": 0, "pending_batch_jobs": []}


def save_master_db(master_data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(MASTER_DB), exist_ok=True)
    with open(MASTER_DB, "w", encoding="utf-8") as f:
        json.dump(master_data, f, indent=2, ensure_ascii=False)


def get_processed_files(master_data: Dict[str, Any]) -> set:
    processed = set()
    for sheet in master_data.get("sheets", []):
        metadata = sheet.get("document_metadata", {})
        if isinstance(metadata, dict) and "file_name" in metadata:
            processed.add(metadata["file_name"])
    return processed


def merge_sheets(master_data: Dict[str, Any], new_sheets: List[Dict[str, Any]]) -> None:
    master_sheets = master_data.get("sheets")
    if isinstance(master_sheets, list):
        master_sheets.extend(new_sheets)
    else:
        master_data["sheets"] = new_sheets


def record_cost(master_data: Dict[str, Any], usage_metadata: Any) -> engine.CallCost:
    if isinstance(usage_metadata, agy_client.AgyUsage):
        cost = agy_engine.adapt_agy_usage_to_call_cost(usage_metadata)
    else:
        cost = engine.compute_call_cost(usage_metadata, COST_CFG)
    master_data["total_spent"] = float(master_data.get("total_spent", 0.0)) + cost.call_cost
    master_data["total_pages_processed"] = int(master_data.get("total_pages_processed", 0)) + 1
    return cost


def print_cost_line(master_data: Dict[str, Any], cost: engine.CallCost) -> None:
    total_tokens = cost.cached_tokens + cost.in_tokens + cost.out_tokens + cost.thoughts_tokens
    print(f" DONE! | Cost: ${cost.call_cost:.4f}")
    print(f"      Tokens -> Cached: {cost.cached_tokens} | Input: {cost.in_tokens} | "
          f"Output: {cost.out_tokens} | Thinking: {cost.thoughts_tokens} = Total: {total_tokens}")

    if EXTRACTION_ENGINE == "agy":
        # Subscription-covered - no per-call dollar cost, so the budget/pages-left
        # arithmetic below (built around metered API pricing) would otherwise just
        # print a meaningless "~0 pages left" forever, since avg_cost stays 0.
        print("      Budget -> N/A (subscription backend, no per-call cost)")
        return

    total_spent = master_data["total_spent"]
    total_pages = master_data["total_pages_processed"]
    avg_cost = total_spent / total_pages if total_pages else 0.0

    load_dotenv(ROOT_ENV, override=True)
    live_budget = float(os.getenv("API_BUDGET", str(API_BUDGET)))
    remaining_budget = max(0.0, live_budget - total_spent)
    estimated_pages_left = math.floor(remaining_budget / avg_cost) if avg_cost > 0 else 0
    print(f"      Budget -> Total Spent: ${total_spent:.4f} | Est Pages Left: ~{estimated_pages_left}")


# ==========================================
# FILE CLASSIFICATION
# ==========================================
def list_source_files() -> List[str]:
    return sorted(f for f in os.listdir(SOURCE_DIR) if f.lower().endswith(SOURCE_SUFFIXES))


def is_batch_eligible(file_path: Path) -> bool:
    """A PDF crosses the batch threshold if it has more pages than the active type's
    (or engine's default) threshold. Images are never batch-eligible."""
    if file_path.suffix.lower() != ".pdf":
        return False
    return engine.get_pdf_page_count(file_path) > TYPE_CFG.batch_page_threshold


# ==========================================
# SYNCHRONOUS PROCESSING
# ==========================================
def build_gen_config_kwargs(active_cache_name: Optional[str]) -> Dict[str, Any]:
    if DEBUG_FILE:
        return engine.build_debug_generation_config()
    kwargs: Dict[str, Any] = dict(response_mime_type="application/json", response_schema=SCHEMA)
    if active_cache_name:
        kwargs["cached_content"] = active_cache_name
    return kwargs


def process_one_file_sync(filename: str, active_cache_name: Optional[str],
                          pending_continuation: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Processes one file synchronously (real-time API call with retries). Returns a
    dict with page_data/usage_metadata on success, or None on failure (already printed).
    Raises engine.DailyQuotaExhausted, which the caller must handle by stopping the run.
    pending_continuation, if given, is the previous image's cut-off last record - see
    engine.build_continuation_context and UNIVERSAL_PROMPT_SUFFIX's PAGE CONTINUITY rule."""
    file_path = Path(SOURCE_DIR) / filename
    file_base = file_path.stem
    file_ext = file_path.suffix.upper().replace(".", "")
    if file_ext == "JPG":
        file_ext = "JPEG"
    pages_str = file_base.split("_")[-1]

    file_metadata = {"File": file_base, "Pages": pages_str}
    dynamic_prompt = engine.get_dynamic_prompt(TYPE_CFG, file_metadata)
    dynamic_prompt += engine.build_continuation_context(pending_continuation)

    if EXTRACTION_ENGINE == "agy":
        # PDFs are rasterized to images locally rather than trusting agy's own native
        # PDF file-reading via --add-dir: confirmed live that native PDF reading works
        # for light queries but is unreliable for a full schema-constrained extraction
        # (agy's own agent can try an internal tool call that headless mode auto-denies,
        # silently returning no structured output at all). Rasterizing reuses the same
        # mechanism already proven reliable for direct image input. agy has no
        # cached_content slot, so the full system instruction goes inline every call
        # (the same concatenation the api engine only does for DEBUG_FILE).
        images = (agy_engine.rasterize_pdf_to_images(file_path) if file_path.suffix.lower() == ".pdf"
                  else [engine.optimize_image(str(file_path))])
        full_prompt = engine.get_cached_system_instruction(TYPE_CFG) + "\n\n" + dynamic_prompt

        def call_fn() -> Any:
            # call_agy_extract_chunked (not call_agy_extract directly): confirmed live
            # that a single call staging many pages at once (a real 38-page case file)
            # fails consistently, not just intermittently - chunking is required for
            # reliability on any large multi-page document, not just an optimization.
            result = agy_engine.call_agy_extract_chunked(images, SCHEMA, full_prompt, model=AGY_MODEL_ID,
                                                          cli_bin=AGY_CLI_BIN, timeout_seconds=AGY_TIMEOUT_SECONDS)
            return result.structured_output, result.usage

        try:
            page_data, usage_metadata = agy_engine.run_with_agy_retries(call_fn)
        except RuntimeError as e:
            print(f"\n[FAILED] {filename}: {e}")
            return None
    else:
        _, content_part = engine.build_content_part_for_file(client, file_path)

        if DEBUG_FILE:
            prompt = engine.get_cached_system_instruction(TYPE_CFG) + "\n\n" + dynamic_prompt
            prompt += engine.debug_schema_suffix(SCHEMA)
        else:
            prompt = dynamic_prompt

        contents = [prompt, content_part]

        def call_fn() -> Any:
            response = client.models.generate_content(
                model=MODEL_ID, contents=contents,
                config=genai.types.GenerateContentConfig(**build_gen_config_kwargs(active_cache_name)),
            )

            if DEBUG_FILE:
                parts = (response.candidates[0].content.parts or []) if response.candidates and \
                    response.candidates[0].content else []
                thought_parts = [p.text for p in parts if getattr(p, "thought", False) and p.text]
                if thought_parts:
                    print("\n\n--- MODEL THINKING ---")
                    print("\n".join(thought_parts))
                    print("--- END THINKING ---\n")

            raw_text = engine.strip_markdown_fences((response.text or "").strip())
            return json.loads(raw_text), response.usage_metadata

        try:
            page_data, usage_metadata = engine.run_with_retries(call_fn)
        except RuntimeError as e:
            print(f"\n[FAILED] {filename}: {e}")
            return None

    page_data = finalize_page_data(page_data)
    tag_document_metadata(page_data, filename, file_ext)

    return {"page_data": page_data, "usage_metadata": usage_metadata}


def pop_trailing_cutoff_record(sheets: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """If the last record of the last sheet is flagged continues_on_next_image, pops it out
    (carrying its origin sheet's page_id/document_metadata along for pending_sheet_info,
    in case nothing continues it and it needs to be saved back on its own) and returns it.
    None if there's nothing pending."""
    if not sheets:
        return None
    last_sheet = sheets[-1]
    records = last_sheet.get("records", [])
    if not records or not records[-1].get("continues_on_next_image"):
        return None
    record = records.pop()
    record["_pending_sheet_info"] = {"page_id": last_sheet.get("page_id"),
                                     "document_metadata": last_sheet.get("document_metadata")}
    return record


def consumed_leading_continuation(sheets: List[Dict[str, Any]]) -> bool:
    """True if the first record of the first sheet says it merged the pending continuation
    context it was given - the pending record should be discarded (it was never saved),
    not reattached."""
    if not sheets:
        return False
    first_records = sheets[0].get("records", [])
    return bool(first_records and first_records[0].get("continues_from_previous_image"))


def reattach_leftover_record(sheets: List[Dict[str, Any]], leftover: Dict[str, Any]) -> None:
    """Nothing on the new image continued the pending record after all - save it back as
    its own one-record sheet, using the sheet info it originally came from, ahead of this
    file's own sheets so reading order is preserved."""
    sheet_info = leftover.pop("_pending_sheet_info", {}) or {}
    sheets.insert(0, {"page_id": sheet_info.get("page_id", ""),
                      "document_metadata": sheet_info.get("document_metadata", {}), "records": [leftover]})


def run_synchronous_batch(files: List[str], master_data: Dict[str, Any]) -> None:
    total_files = len(files)
    active_cache_name = None
    pending_continuation: Optional[Dict[str, Any]] = None

    if not DEBUG_FILE and files:
        print(f"Found {total_files} file(s) to process synchronously.")
        if EXTRACTION_ENGINE == "api":
            # Context caching is genai-only (and requires a working API key) - agy has
            # no cached_content equivalent, see process_one_file_sync's agy branch.
            print("Creating Context Cache for System Instructions to reduce costs...")
            active_cache_name = engine.create_context_cache(
                client, MODEL_ID, engine.get_cached_system_instruction(TYPE_CFG))
            if active_cache_name:
                print(f"Cache created successfully: {active_cache_name}\n")

    try:
        for index, filename in enumerate(files, start=1):
            print(f"[{index}/{total_files}] Processing {filename} with {MODEL_ID}...", end="", flush=True)
            try:
                result = process_one_file_sync(filename, active_cache_name, pending_continuation)
            except engine.DailyQuotaExhausted:
                print("\n\n[FATAL ERROR] Daily Quota Exhausted.")
                print("Progress saved. Exiting script to prevent infinite crashing.")
                if not DEBUG_FILE and pending_continuation is not None:
                    reattach_leftover_record(master_data.setdefault("sheets", []), pending_continuation)
                    save_master_db(master_data)
                return
            except Exception as e:
                print(f" LOCAL ERROR! Details: {e}")
                continue

            if result is None:
                continue

            cost = record_cost(master_data, result["usage_metadata"])
            sheets = result["page_data"].get("sheets", [])

            if DEBUG_FILE:
                print("--- EXTRACTED JSON (not saved to master DB) ---")
                print(json.dumps(result["page_data"], indent=2, ensure_ascii=False))
                print_cost_line(master_data, cost)
            else:
                if pending_continuation is not None and not consumed_leading_continuation(sheets):
                    # Nothing here continued it after all - save it as its own record,
                    # still exactly as flagged/reviewable as before this feature existed.
                    reattach_leftover_record(sheets, pending_continuation)
                pending_continuation = pop_trailing_cutoff_record(sheets)
                merge_sheets(master_data, sheets)
                save_master_db(master_data)
                print_cost_line(master_data, cost)

        if not DEBUG_FILE and pending_continuation is not None:
            # The very last file's last record was cut off with no further image to
            # check against - save it rather than silently drop it.
            reattach_leftover_record(master_data.setdefault("sheets", []), pending_continuation)
            save_master_db(master_data)
    finally:
        if active_cache_name:
            engine.delete_context_cache(client, active_cache_name)
            print(f"\nDeleted context cache: {active_cache_name}")


# ==========================================
# BATCH PROCESSING (large multi-page documents)
# ==========================================
def run_batch_mode(files: List[str], master_data: Dict[str, Any]) -> None:
    """Batch-eligible files (large multipage PDFs) go through Gemini's Batch API
    instead of the synchronous loop. One run both retrieves any previously-submitted
    job that has since completed and submits any newly-pending files as a new job,
    then returns without blocking on Gemini."""
    pending_jobs = master_data.setdefault("pending_batch_jobs", [])

    if pending_jobs:
        completed, still_pending = engine.check_batch_jobs(client, pending_jobs)
        master_data["pending_batch_jobs"] = still_pending

        for entry in completed:
            print(f"Retrieving results for completed batch job {entry['job_name']}...")
            for source_file, response in engine.retrieve_batch_results(client, entry["job_name"]):
                try:
                    raw_text = engine.strip_markdown_fences((response.text or "").strip())
                    page_data = json.loads(raw_text)
                except (json.JSONDecodeError, AttributeError) as e:
                    print(f"   [!] Could not parse batch result for {source_file}: {e}")
                    continue

                page_data = finalize_page_data(page_data)
                file_ext = Path(source_file).suffix.upper().replace(".", "")
                tag_document_metadata(page_data, source_file, file_ext)
                merge_sheets(master_data, page_data.get("sheets", []))
                cost = record_cost(master_data, response.usage_metadata)
                print(f"Merged {source_file}: cost ${cost.call_cost:.4f}")

            save_master_db(master_data)

    if not files:
        if not master_data.get("pending_batch_jobs"):
            print("No new or pending batch files.")
        return

    print(f"Submitting {len(files)} file(s) as a new batch job...")
    system_instruction = engine.get_cached_system_instruction(TYPE_CFG)
    requests = []
    for filename in files:
        file_path = Path(SOURCE_DIR) / filename
        _, content_part = engine.build_content_part_for_file(client, file_path)
        file_metadata = {"File": file_path.stem, "Pages": str(engine.get_pdf_page_count(file_path))}
        prompt = system_instruction + "\n\n" + engine.get_dynamic_prompt(TYPE_CFG, file_metadata)
        gen_config_kwargs: Dict[str, Any] = dict(response_mime_type="application/json", response_schema=SCHEMA)
        requests.append(engine.build_batch_request(MODEL_ID, [prompt, content_part], filename,
                                                   gen_config_kwargs))

    job_name = engine.submit_batch_job(client, MODEL_ID, requests)
    master_data.setdefault("pending_batch_jobs", []).append(
        {"job_name": job_name, "submitted_at": time.strftime("%Y-%m-%d %H:%M:%S"), "file_names": files})
    save_master_db(master_data)
    print(f"Submitted batch job '{job_name}' for {len(files)} file(s). Check back later; "
          "re-run this same step to retrieve results once Gemini finishes.")


# ==========================================
# MAIN EXECUTION
# ==========================================
def main() -> None:
    if EXTRACTION_ENGINE == "agy":
        # Deliberately interactive, separate from the per-file loop below (which stays
        # fully headless) - lets first-time Google sign-in happen once, up front,
        # rather than surprising the user mid-batch.
        print("Verifying Antigravity CLI authentication...")
        if not agy_client.check_or_prompt_auth(AGY_MODEL_ID, cli_bin=AGY_CLI_BIN):
            print("[FATAL ERROR] Could not authenticate with agy. Run the 'Test Agy "
                  "Connection' action in Scriptorium's Global Settings, or `agy` "
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
        # agy has no async Batch API equivalent at all (not a size cutoff like the api
        # engine's page-count threshold - a total absence of an async path), so every
        # file - image or PDF, any page count - goes through the same synchronous loop.
        # PDFs are not skipped or treated as unsupported: process_one_file_sync handles
        # them via rasterization on this path.
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
