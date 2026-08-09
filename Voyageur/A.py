import json
import os
import re
import sys
import urllib.parse
from pathlib import Path

from dotenv import load_dotenv

import census_schema
from _gather_helpers import (
    cleanup_checkpoint_files,
    launch_gather_browser,
    move_downloaded_images,
    move_with_retry,
    resolve_census_image_dir,
    wait_for_downloaded_json,
    write_archivist_json_file,
)


# ==========================================
# URL PARSING
# ==========================================
def parse_ancestry_url(url: str):
    """Extract APID (dbid) and Start Record ID from Ancestry URLs."""
    view_match = re.search(r'view/(\d+):(\d+)', url)
    if view_match:
        return view_match.group(2), view_match.group(1)

    col_match = re.search(r'collections/(\d+)', url)
    pid_match = re.search(r'[?&]pId=(\d+)', url, re.IGNORECASE)
    if col_match and pid_match:
        return col_match.group(1), pid_match.group(1)

    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query)
    if 'dbid' in qs and 'h' in qs:
        return qs['dbid'][0], qs['h'][0]

    return None, None


def normalize_ancestry_census_gather(raw_gather: dict, dbid: str = "") -> dict:
    """Translates a raw Ancestry census gather into the shared record schema, deriving
    collection_title/record_type_name from the gather's own census_year/location - the
    exact translation main() applies at gather time, pulled out here so it's testable
    without a browser session."""
    census_year_raw = raw_gather.get("census_year", "")
    collection_title = f"{census_year_raw} US Federal Census - {raw_gather.get('location', '')}".strip(" -")
    normalized = census_schema.normalize_and_validate_census(
        raw_gather, "ancestry_census", collection_title, f"Census_{census_year_raw}")
    if dbid:
        for page in normalized.get("pages", []):
            page["apid_db"] = dbid
    return normalized


# ==========================================
# MAIN EXECUTION
# ==========================================
def main() -> Path:
    print("========================================")
    print(" Voyageur (A) - Ancestry Gather Automation")
    print("========================================")

    # Global settings come from the project root's .env; this tool's own settings come
    # from its own subfolder's .env, so this sub-script stays runnable standalone.
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
    load_dotenv(Path(__file__).resolve().parent / ".env", override=False)

    program_dir = os.getenv("PROGRAM_DIR", str(Path(__file__).resolve().parent.parent))
    genealogy_dir = os.getenv("GENEALOGY_DIR", "")
    url = os.getenv("A_URL", "").strip()
    json_dir = os.getenv("JSON_DIR", "Scriptorium/Working/Project/JSON")
    # Matches Scriptorium.py's own default ("Census", resolved against
    # MEDIA_DIR by the GUI before this ever runs).
    base_img_setting = "Census"

    if not url:
        print("[ERROR] Please enter an Ancestry URL in the Toolbox settings first.")
        sys.exit(1)

    dbid, start_id = parse_ancestry_url(url)
    if not dbid or not start_id:
        print("[ERROR] Could not parse database ID (dbid) or record ID (h) from the URL.")
        sys.exit(1)

    print(f"[System] Extracted -> DBID: {dbid} | Start ID: {start_id}")

    start_time = launch_gather_browser(url)

    # Voyageur.js downloads via plain <a download> rather than GM_download (see CHANGELOG -
    # GM_download's permission grant proved unreliable). Chrome replaces "/" in a download
    # attribute with "_" instead of creating subfolders, so these land flat in the Downloads
    # root with a "TMP_A_"/"TMP_A_Images_" filename prefix instead of a real subfolder -
    # that prefix is also what lets this scan pick its own files out from whatever else
    # happens to be in the Downloads root.
    downloads_dir = Path.home() / "Downloads"
    json_prefix = "TMP_A_"
    image_prefix = "TMP_A_Images_"
    json_file = wait_for_downloaded_json(downloads_dir, json_prefix, start_time, "Final JSON")

    print("\n[System] Processing extracted files...")

    json_target_dir = Path(program_dir) / json_dir if program_dir else Path(json_dir)
    json_target_dir.mkdir(parents=True, exist_ok=True)

    final_json = json_target_dir / json_file.name[len(json_prefix):]
    move_with_retry(json_file, final_json)
    cleanup_checkpoint_files(downloads_dir, json_prefix, start_time)

    # Normalize at gather time: translate Ancestry's own raw column header text into the
    # shared record schema's field names via the declarative field map, so Archivist never
    # has to guess among several possible header spellings downstream. Overwrites the same
    # file in place - Archivist still just reads whatever JSON_FILE points to.
    with open(final_json, "r", encoding="utf-8") as f:
        raw_gather = json.load(f)
    normalized = normalize_ancestry_census_gather(raw_gather, dbid)
    with open(final_json, "w", encoding="utf-8") as f:
        json.dump(normalized, f, indent=2, ensure_ascii=False)

    # Persist this as the JSON_FILE setting immediately, before anything below (the image
    # move) can fail - so even if that fails, Archivist's "Generate GEDCOM" (the manual/retry
    # button) still targets the exact file that was just produced, instead of whatever
    # JSON_FILE happened to be set to before this run started. JSON_FILE is read by
    # Archivist (see its own ARCHIVIST_VARS entry in Scriptorium.py), so it's written to
    # Archivist's own .env, not this script's own subfolder one - confirmed live this was
    # the actual bug behind Archivist immediately failing with FileNotFoundError right
    # after a real gather succeeded: this used to write to Voyageur/.env, a file Archivist
    # never reads at all.
    write_archivist_json_file(final_json.name)

    stem_parts = final_json.stem.split(' - ', 1)
    census_year = stem_parts[0].strip() if len(stem_parts) > 0 else "Unknown_Year"
    raw_location = stem_parts[1].strip() if len(stem_parts) > 1 else "Unknown_Location"

    location_folder = re.sub(r'^USA\s*-\s*', '', raw_location)
    census_folder = f"{census_year} US Federal Census"

    # CENSUS_IMAGE_DIR is a subfolder *of the Base Media Directory* (MEDIA_DIR), not of
    # PROGRAM_DIR directly. Resolved here independently (rather than relying on
    # Scriptorium.py's GUI to pre-resolve it into an absolute path before launching this
    # as a subprocess) so this script produces correct output standalone, with nothing
    # else open. An already-absolute CENSUS_IMAGE_DIR (whether GUI-resolved or set
    # directly by the user) is used as-is, never re-nested.
    img_target_dir = resolve_census_image_dir(base_img_setting, genealogy_dir, census_folder, location_folder)

    img_count = move_downloaded_images(downloads_dir, image_prefix, start_time, img_target_dir)
    print(f"[System] Moved JSON and {img_count} images to Project folders.")
    print(f"[System] Gather complete. Run Archivist's \"Generate GEDCOM\" when you're ready to "
          f"build the GEDCOM ({final_json.name}).")

    # Gather's job stops here - it stages the JSON (already normalized into the shared
    # sheets[].records[].participants[] schema above) and images and hands off, rather
    # than launching GEDCOM generation itself.
    return final_json


if __name__ == "__main__":
    main()
