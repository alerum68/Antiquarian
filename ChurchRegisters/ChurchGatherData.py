"""
Historical Register Data Extraction Script.

Uses the Gemini API to read images of historical church register pages,
translate them, and write the extracted records into a JSON database.
"""

import json
import math
import os
import re
import sys
import time
from pathlib import Path
from textwrap import dedent
from typing import Dict, List, Union

from PIL import Image
from dotenv import load_dotenv
from google import genai

# Global settings come from the project root's .env; this tool's own settings come from
# its own subfolder's .env, so ChurchRegisters stays runnable standalone.
ROOT_ENV = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ROOT_ENV, override=True)
load_dotenv(Path(__file__).resolve().parent / ".env", override=True)
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# ==========================================
# CONFIGURATION
# ==========================================
# Kept as separate typed globals rather than one mixed-type dict.
PARISH_NAME: Union[str, None] = os.getenv("PARISH_NAME")
PARISH_CITY: str = os.getenv("PARISH_CITY", "")
PARISH_STATE: str = os.getenv("PARISH_STATE", "")
PARISH_LOCATION: str = f"{PARISH_CITY}, {PARISH_STATE}".strip(", ")

VOLUME_TITLE: Union[str, None] = os.getenv("VOLUME_TITLE")
VOLUME_NUM: str = os.getenv("VOLUME_NUM", "")

API_BUDGET: float = float(os.getenv("API_BUDGET", "5.00"))
COST_PER_1M_IN: float = float(os.getenv("COST_PER_1M_INPUT", "0.075"))
COST_PER_1M_OUT: float = float(os.getenv("COST_PER_1M_OUTPUT", "0.30"))
CACHE_DISCOUNT_MULTIPLIER: float = float(os.getenv("CACHE_DISCOUNT_MULTIPLIER", "0.10"))

PROGRAM_DIR: Path = Path(os.getenv("PROGRAM_DIR", ""))
MASTER_DB: str = str(PROGRAM_DIR / os.getenv("JSON_DIR", "") / os.getenv("MASTER_DB_NAME", ""))
IMAGE_DIR: str = str(PROGRAM_DIR / os.getenv("IMAGE_DIR", ""))

MODEL_ID: Union[str, None] = os.getenv("MODEL_NAME")
DEBUG_FILE: Union[str, None] = sys.argv[1] if len(sys.argv) > 1 else None

PROMPTS_DIR: Path = Path(__file__).resolve().parent / "prompts"
DEFAULT_PROMPT_FILE = "Parish.pmt"

JSONType = Union[str, int, float, bool, None, list, dict]

# The schema the LLM's output must conform to.
with open("register_schema.json", "r", encoding="utf-8") as schema_file:
    SCHEMA: Dict[str, JSONType] = json.load(schema_file)


# ==========================================
# PROMPT BUILDING
# ==========================================
def optimize_image(image_path: str, max_dimension: int = 2048) -> Image.Image:
    """
    Downscale an image before sending it to the API, to cut token costs.

    2048px keeps 19th-century cursive legible while limiting tile costs.
    """
    img = Image.open(image_path)
    img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
    return img


def resolve_prompt_path() -> Path:
    """
    Finds the .pmt prompt template requested via CHURCH_PROMPT_FILE (case-insensitive,
    extension optional), falling back to DEFAULT_PROMPT_FILE if not found.
    """
    requested = os.getenv("CHURCH_PROMPT_FILE", "").strip() or DEFAULT_PROMPT_FILE
    if not requested.lower().endswith(".pmt"):
        requested += ".pmt"

    available = {p.name.lower(): p for p in PROMPTS_DIR.glob("*.pmt")} if PROMPTS_DIR.is_dir() else {}

    match = available.get(requested.lower())
    if match:
        return match

    fallback = available.get(DEFAULT_PROMPT_FILE.lower())
    if fallback:
        return fallback

    raise FileNotFoundError(
        f"Could not find prompt template '{requested}' or fallback '{DEFAULT_PROMPT_FILE}' in {PROMPTS_DIR}"
    )


def get_cached_system_instruction() -> str:
    """The static system-instruction ruleset, stored in the Context Cache."""
    return resolve_prompt_path().read_text(encoding="utf-8")


def get_dynamic_prompt(file_name: str, volume: str, pages_str: str) -> str:
    """Per-image metadata block appended to the cached prompt."""
    return dedent(f"""
        Metadata Context:
        File: {file_name},
        Volume: {volume},
        Pages: {pages_str},
        Church: {PARISH_NAME},
        Location: {PARISH_LOCATION}
    """)


# ==========================================
# MAIN EXECUTION
# ==========================================
# noinspection GrazieInspection
def run_batch_process() -> None:
    """
    Process every image in the source directory through the Gemini API,
    tracking spend and appending results to the JSON database.
    """
    master_data: Dict[str, Union[str, float, int, List[Dict[str, JSONType]], None]]

    if os.path.exists(MASTER_DB):
        with open(MASTER_DB, 'r', encoding='utf-8') as f:
            master_data = json.load(f)
            total_spent = float(master_data.get("total_spent", 0.0))
            total_pages_processed = int(master_data.get("total_pages_processed", 0))
    else:
        master_data = {"register_title": VOLUME_TITLE,
                       "sheets": [],
                       "total_spent": 0.0,
                       "total_pages_processed": 0
                       }
        total_spent = 0.0
        total_pages_processed = 0

    processed_files = set()
    existing_sheets = master_data.get('sheets', [])
    if isinstance(existing_sheets, list):
        for s in existing_sheets:
            if isinstance(s, dict):
                metadata = s.get('document_metadata', {})
                if isinstance(metadata, dict) and 'file_name' in metadata:
                    processed_files.add(metadata['file_name'])

    all_images = [f for f in os.listdir(IMAGE_DIR)
                  if f.lower().endswith(('.jpg', '.jpeg', '.png', '.tiff', '.tif'))
                  ]

    # Handle Debug Mode override
    if DEBUG_FILE:
        if DEBUG_FILE not in all_images:
            print(f"[DEBUG MODE] '{DEBUG_FILE}' not found in {IMAGE_DIR}. Aborting.")
            return
        print(
            f"[DEBUG MODE] Processing ONLY '{DEBUG_FILE}' with thinking enabled. "
            f"Nothing will be saved to {MASTER_DB}.\n"
        )
        all_images = [DEBUG_FILE]

    total_files = len(all_images)

    active_cache_name = None
    if not DEBUG_FILE:
        print(f"Found {total_files} images in the source directory.")
        print("Creating Context Cache for System Instructions to reduce costs...")
        try:
            cache = client.caches.create(
                model=MODEL_ID,
                config=genai.types.CreateCachedContentConfig(
                    system_instruction=get_cached_system_instruction(),
                    ttl="86400s",  # 24 hours
                )
            )
            active_cache_name = cache.name
            print(f"Cache created successfully: {active_cache_name}\n")
        except Exception as e:
            print(f"Warning: Failed to create cache. Proceeding without it. Error: {e}\n")

    try:
        for index, filename in enumerate(all_images, start=1):
            if not DEBUG_FILE and filename in processed_files:
                print(f"[{index}/{total_files}] Skipping {filename} (already processed).")
                continue

            file_base = os.path.splitext(filename)[0]
            file_ext = os.path.splitext(filename)[1].upper().replace(".", "")
            if file_ext == "JPG":
                file_ext = "JPEG"

            print(f"[{index}/{total_files}] Processing {filename} with {MODEL_ID}...",
                  end="", flush=True)

            pages_str = file_base.split('_')[-1]

            try:
                img = optimize_image(os.path.join(IMAGE_DIR, filename))
                prompt = get_dynamic_prompt(file_base, VOLUME_NUM, pages_str)

                if DEBUG_FILE:
                    # Cache cannot be used with thinking mode enabled in current API
                    prompt = get_cached_system_instruction() + "\n\n" + prompt
                    gen_config_kwargs = dict(thinking_config=genai.types.ThinkingConfig(include_thoughts=True),
                                             )
                    prompt += (
                        "\n\nOUTPUT FORMAT: Respond with ONLY raw JSON matching this "
                        "schema, no markdown code fences, no commentary before or "
                        f"after:\n{json.dumps(SCHEMA)}"
                    )
                else:
                    gen_config_kwargs = dict(
                        response_mime_type="application/json",
                        response_schema=SCHEMA,
                    )
                    if active_cache_name:
                        gen_config_kwargs["cached_content"] = active_cache_name

                max_retries = 10
                max_json_retries = 3
                attempts = 0
                json_attempts = 0
                success = False
                gave_up_early = None

                while attempts < max_retries and not success:
                    try:
                        response = client.models.generate_content(
                            model=MODEL_ID,
                            contents=[prompt, img], config=genai.types.GenerateContentConfig(**gen_config_kwargs)
                        )

                        # Extract model's internal reasoning if in debug mode
                        if DEBUG_FILE:
                            thought_parts = [
                                p.text for p in response.candidates[0].content.parts
                                if getattr(p, "thought", False)
                            ]
                            if thought_parts:
                                print("\n\n--- MODEL THINKING ---")
                                print("\n".join(thought_parts))
                                print("--- END THINKING ---\n")

                        # Clean output and parse JSON
                        raw_text = response.text.strip()
                        backticks = "`" * 3
                        if raw_text.startswith(backticks):
                            # Remove markdown code fences if model stubbornly includes them
                            regex_pattern = r"^" + backticks + r"(?:json)?\s*|\s*" + backticks + r"$"
                            raw_text = re.sub(regex_pattern, "", raw_text.strip())

                        page_data: Dict[str, JSONType] = json.loads(raw_text)
                        usage = response.usage_metadata

                        in_tokens = out_tokens = cached_tokens = thoughts_tokens = 0
                        call_cost = remaining_budget = 0.0
                        estimated_pages_left = 0

                        if usage:
                            in_tokens = getattr(usage, 'prompt_token_count', 0)
                            out_tokens = getattr(usage, 'candidates_token_count', 0)
                            cached_tokens = getattr(usage, 'cached_content_token_count', 0)
                            thoughts_tokens = getattr(usage, 'thoughts_token_count', 0)

                            cache_rate = COST_PER_1M_IN * CACHE_DISCOUNT_MULTIPLIER
                            cost_cached = (cached_tokens / 1_000_000) * cache_rate
                            cost_in = (in_tokens / 1_000_000) * COST_PER_1M_IN
                            cost_out = ((out_tokens + thoughts_tokens) / 1_000_000) * COST_PER_1M_OUT

                            call_cost = cost_cached + cost_in + cost_out
                            total_spent += call_cost
                            total_pages_processed += 1

                            # Determine run-rate and remaining budget
                            avg_cost_per_page = (total_spent / total_pages_processed
                                                 if total_pages_processed > 0 else 0
                                                 )
                            load_dotenv(ROOT_ENV, override=True)
                            live_budget = float(os.getenv("API_BUDGET", str(API_BUDGET)))
                            remaining_budget = max(0.0, live_budget - total_spent)
                            estimated_pages_left = (math.floor(remaining_budget / avg_cost_per_page)
                                                    if avg_cost_per_page > 0 else 0
                                                    )

                        # Inject document metadata back into each parsed sheet
                        extracted_sheets = page_data.get("sheets", [])
                        if isinstance(extracted_sheets, list):
                            for sheet in extracted_sheets:
                                if isinstance(sheet, dict):
                                    if "document_metadata" not in sheet:
                                        sheet["document_metadata"] = {}
                                    metadata = sheet["document_metadata"]
                                    if isinstance(metadata, dict):
                                        metadata["file_name"] = filename
                                        metadata["file_type"] = file_ext
                                        metadata["volume"] = VOLUME_NUM

                        if DEBUG_FILE:
                            print("--- EXTRACTED JSON (not saved to master DB) ---")
                            print(json.dumps(page_data, indent=2, ensure_ascii=False))
                            if usage:
                                total_tokens = (getattr(usage, 'total_token_count', None)
                                                or (cached_tokens + in_tokens + out_tokens + thoughts_tokens)
                                                )
                                print(
                                    f" DONE! ✓ (debug) | Call Cost: ${call_cost:.4f} | "
                                    f"Total Spent: ${total_spent:.4f} | Remaining: ${remaining_budget:.2f}"
                                )
                                print(
                                    f"      Tokens -> Cached: {cached_tokens} | "
                                    f"Input: {in_tokens} | Output: {out_tokens} | "
                                    f"Thinking: {thoughts_tokens} = Total: {total_tokens}"
                                )
                            else:
                                print(" DONE! ✓ (debug run)")
                        else:
                            # Append to master dataset
                            master_sheets = master_data.get("sheets")
                            if isinstance(master_sheets, list) and isinstance(extracted_sheets, list):
                                master_sheets.extend(extracted_sheets)
                            else:
                                master_data["sheets"] = extracted_sheets

                            master_data["total_spent"] = total_spent
                            master_data["total_pages_processed"] = total_pages_processed

                            # Ensure the parent directory exists before saving
                            os.makedirs(os.path.dirname(MASTER_DB), exist_ok=True)

                            with open(MASTER_DB, 'w', encoding='utf-8') as f:
                                json.dump(master_data, f, indent=2, ensure_ascii=False)

                            if usage:
                                total_tokens = (getattr(usage, 'total_token_count', None)
                                                or (cached_tokens + in_tokens + out_tokens + thoughts_tokens)
                                                )
                                print(f" DONE! ✓ | Cost: ${call_cost:.4f}")
                                print(
                                    f"      Tokens -> Cached: {cached_tokens} | "
                                    f"Input: {in_tokens} | Output: {out_tokens} | "
                                    f"Thinking: {thoughts_tokens} = Total: {total_tokens}"
                                )
                                print(
                                    f"      Budget -> Total Spent: ${total_spent:.4f} | "
                                    f"Est Pages Left: ~{estimated_pages_left}"
                                )
                            else:
                                print(" DONE! ✓")

                        success = True

                    except json.JSONDecodeError as e:
                        json_attempts += 1
                        print(f"\n   [!] Malformed JSON generated. Retrying... ({e})",
                              end="", flush=True)
                        if json_attempts >= max_json_retries:
                            gave_up_early = (
                                f"malformed JSON {max_json_retries}x in a row "
                                "(likely a systemic issue, not transient)"
                            )
                            break
                        time.sleep(2)
                        attempts += 1

                    except genai.errors.ClientError as api_error:
                        error_msg = str(api_error)

                        if "PerDay" in error_msg:
                            print("\n\n[FATAL ERROR] Daily Quota Exhausted.")
                            print("Progress saved. Exiting script to prevent infinite crashing.")
                            return

                        if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                            match = re.search(r"retry in (\d+\.?\d*)s", error_msg)
                            if match:
                                wait_time = float(match.group(1)) + 1.5
                            else:
                                # Exponential backoff: 35s, 70s, 140s...
                                wait_time = 35.0 * (2 ** attempts)

                            print(f"\n   [!] Rate limit hit. Sleeping {wait_time:.2f}s "
                                  f"(Attempt {attempts + 1})...", end="", flush=True)
                            time.sleep(wait_time)
                            attempts += 1

                        elif "500" in error_msg or "503" in error_msg or "504" in error_msg:
                            print(f"\n   [!] Google Server Error ({error_msg[:30]}). "
                                  "Sleeping 5s...", end="", flush=True)
                            time.sleep(5)
                            attempts += 1

                        else:
                            print(f" API ERROR! ✗\nDetails: {error_msg}")
                            break

                if not success:
                    if gave_up_early:
                        print(f"\n[{index}/{total_files}] SKIPPED: {filename}: {gave_up_early}.")
                    elif attempts >= max_retries:
                        print(f"\n[{index}/{total_files}] FAILED: {filename} exhausted all {max_retries} retries.")

            except Exception as e:
                # Catch broad local exceptions (e.g., Pillow image read errors)
                print(f" LOCAL ERROR! ✗\nDetails: {e}")

    finally:
        if active_cache_name:
            try:
                client.caches.delete(active_cache_name)
                print(f"\nDeleted context cache: {active_cache_name}")
            except Exception as e:
                print(f"\nWarning: Failed to delete cache {active_cache_name} "
                      f"(it will expire on its own via TTL). Error: {e}")


if __name__ == "__main__":
    run_batch_process()
