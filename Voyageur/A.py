import json
import os
import re
import shutil
import sys
import time
import urllib.parse
import webbrowser
from pathlib import Path

from dotenv import load_dotenv, set_key

import census_schema


def _move_with_retry(src: Path, dst: Path, attempts: int = 5, delay: float = 0.5) -> None:
    """Chrome (or antivirus scanning it) can still hold a freshly-downloaded file open for
    a brief moment after it appears in the folder listing, so an immediate shutil.move can
    lose to a transient PermissionError/WinError 32 on Windows. Retries ride out that
    window instead of letting the whole gather crash with the file left stranded."""
    for attempt in range(1, attempts + 1):
        try:
            shutil.move(str(src), str(dst))
            return
        except OSError as e:
            if attempt == attempts:
                print(f"[ERROR] Could not move {src.name} to {dst} after {attempts} attempts: {e}")
                raise
            time.sleep(delay)


def _cleanup_checkpoint_files(downloads_dir: Path, prefix: str, start_time: float) -> None:
    """Deletes this run's own leftover periodic checkpoint downloads (see
    downloadCheckpointJson in Voyageur.js) now that the final combined JSON has already
    been moved out - they're superseded and, unlike the final JSON, nothing else ever
    cleans them up, so a long gather would otherwise leave several of them sitting in the
    Downloads folder permanently. Best-effort: a checkpoint that can't be deleted (still
    briefly locked, already gone) is left in place rather than raising."""
    for p in downloads_dir.iterdir():
        if (p.is_file() and p.suffix.lower() == '.json' and p.name.startswith(prefix)
                and '[checkpoint' in p.name and p.stat().st_mtime >= start_time):
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass


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

    program_dir = os.getenv("PROGRAM_DIR", "")
    url = os.getenv("CENSUS_URL", "").strip()
    json_dir = os.getenv("JSON_DIR", "Scriptorium/Working/Project/JSON")
    # Matches Scriptorium.py's own CENSUS_IMAGE_DIR default ("Census", resolved against
    # MEDIA_DIR by the GUI before this ever runs) - only used at all when running this
    # script standalone with no .env value set.
    base_img_setting = os.getenv("CENSUS_IMAGE_DIR", "Census")

    if not url:
        print("[ERROR] Please enter an Ancestry URL in the Toolbox settings first.")
        sys.exit(1)

    dbid, start_id = parse_ancestry_url(url)
    if not dbid or not start_id:
        print("[ERROR] Could not parse database ID (dbid) or record ID (h) from the URL.")
        sys.exit(1)

    print(f"[System] Extracted -> DBID: {dbid} | Start ID: {start_id}")

    start_time = time.time()
    auto_url = url + ("&mgs_auto=1" if "?" in url else "?mgs_auto=1")
    print("[System] Launching browser...")
    webbrowser.open(auto_url)

    print("\n[System] Waiting for Tampermonkey downloads (Auto-Batch will start automatically)...")

    # Voyageur.js downloads via plain <a download> rather than GM_download (see CHANGELOG -
    # GM_download's permission grant proved unreliable). Chrome replaces "/" in a download
    # attribute with "_" instead of creating subfolders, so these land flat in the Downloads
    # root with a "TMP_A_"/"TMP_A_Images_" filename prefix instead of a real subfolder -
    # that prefix is also what lets this scan pick its own files out from whatever else
    # happens to be in the Downloads root.
    downloads_dir = Path.home() / "Downloads"
    json_prefix = "TMP_A_"
    image_prefix = "TMP_A_Images_"
    json_file = None

    try:
        while True:
            # noinspection broad-exception
            try:
                # image_prefix files are always .jpg (never .json), so the suffix check
                # above already excludes them - no separate "not an image" check needed.
                candidates = [
                    p for p in downloads_dir.iterdir()
                    if p.is_file() and p.suffix.lower() == '.json'
                    and p.name.startswith(json_prefix)
                    and p.stat().st_mtime >= start_time
                    and '[checkpoint' not in p.name
                ]
                if candidates:
                    json_file = max(candidates, key=lambda p: p.stat().st_mtime)
                    print(f"[System] Detected Final JSON: {json_file.name}")
            except Exception:
                pass

            if json_file:
                break
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[System] Operation cancelled by user.")
        sys.exit(0)

    print("\n[System] Processing extracted files...")

    json_target_dir = Path(program_dir) / json_dir if program_dir else Path(json_dir)
    json_target_dir.mkdir(parents=True, exist_ok=True)

    final_json = json_target_dir / json_file.name[len(json_prefix):]
    _move_with_retry(json_file, final_json)
    _cleanup_checkpoint_files(downloads_dir, json_prefix, start_time)

    # Normalize at gather time: translate Ancestry's own raw column header text into the
    # shared record schema's field names via the declarative field map, so Archivist never
    # has to guess among several possible header spellings downstream. Overwrites the same
    # file in place - Archivist still just reads whatever JSON_FILE points to.
    with open(final_json, "r", encoding="utf-8") as f:
        raw_gather = json.load(f)
    census_year_raw = raw_gather.get("census_year", "")
    collection_title = f"{census_year_raw} US Federal Census - {raw_gather.get('location', '')}".strip(" -")
    normalized = census_schema.normalize_census_pages(
        raw_gather, "ancestry_census", collection_title, f"Census_{census_year_raw}")
    census_schema.validate_against_commissioner(normalized, collection_title)
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
    set_key(str(Path(__file__).resolve().parent.parent / "Archivist" / ".env"), "JSON_FILE", final_json.name)

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
    if os.path.isabs(base_img_setting):
        base_img_dir = Path(base_img_setting)
    else:
        media_setting = os.getenv("MEDIA_DIR", "Media")
        base_media_dir = Path(media_setting) if os.path.isabs(media_setting) else (
            Path(program_dir) / media_setting if program_dir else Path(media_setting))
        base_img_dir = base_media_dir / base_img_setting
    img_target_dir = base_img_dir / census_folder / location_folder
    img_target_dir.mkdir(parents=True, exist_ok=True)

    img_count = 0
    image_candidates = [
        p for p in downloads_dir.iterdir()
        if p.is_file() and p.suffix.lower() == '.jpg'
        and p.name.startswith(image_prefix) and p.stat().st_mtime >= start_time
    ]
    for file_path in image_candidates:
        # noinspection broad-exception
        try:
            final_img = img_target_dir / file_path.name[len(image_prefix):]
            _move_with_retry(file_path, final_img)
            img_count += 1
        except Exception:
            pass

    print(f"[System] Moved JSON and {img_count} images to Project folders.")
    print(f"[System] Gather complete. Run Archivist's \"Generate GEDCOM\" when you're ready to "
          f"build the GEDCOM ({final_json.name}).")

    # Gather's job stops here - it stages the JSON (already normalized into the shared
    # sheets[].records[].participants[] schema above) and images and hands off, rather
    # than launching GEDCOM generation itself.
    #
    # NOTE: as of the field-map normalization work, this JSON's shape is the unified
    # schema, not the old {census_year, location, pages: [...]} shape. Archivist's own
    # census-ingestion path has not been updated to read this shape yet (tracked
    # separately) - until that lands, this normalized output is not yet consumable by
    # Archivist. This is expected, sequenced work, not a bug.
    #
    # Archivist's build_gedcom_from_census/APID_DB/CENSUS_YEAR fallbacks already derive
    # everything they need from the JSON's own
    # 'census_year'/'location' fields and each page's own scraped columns, so nothing here
    # needs to be persisted for Archivist to find later - see run_census_flavor's
    # get_json_fallback calls and its own image-folder reconstruction from census_year/location.

    return final_json


if __name__ == "__main__":
    main()
