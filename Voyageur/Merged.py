"""
Voyageur (Merged) - Ancestry + FamilySearch dual gather.

Paste both a CENSUS_URL (Ancestry) and an FS_URL (FamilySearch) for the same physical
census page into the Voyageur settings, then run this instead of the two per-source
gathers separately: it runs Ancestry's gather, then FamilySearch's, then merges the two
results (see MergedCensus.py) into one JSON ready for Archivist - one citation, both
source IDs, both web links, NARA as the cited repository.

Reuses A.py's and FS.py's own main() functions directly (each already handles its own
browser automation and download watching) rather than re-implementing that logic here.
"""
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv, set_key

import A
import FS
import MergedCensus


def main() -> None:
    print("========================================")
    print(" Voyageur (Merged) - Ancestry + FamilySearch Gather Automation")
    print("========================================")

    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
    load_dotenv(Path(__file__).resolve().parent / ".env", override=False)

    program_dir = os.getenv("PROGRAM_DIR", "")
    census_url = os.getenv("CENSUS_URL", "").strip()
    fs_url = os.getenv("FS_URL", "").strip()
    json_dir = os.getenv("JSON_DIR", "Scriptorium/Working/Project/JSON")

    if not census_url or not fs_url:
        print("[ERROR] A merged gather needs both an Ancestry URL and a FamilySearch URL in "
              "the Toolbox settings, pointing at the same physical census page.")
        sys.exit(1)

    print("\n[System] Step 1 of 3: Gathering from Ancestry...\n")
    try:
        ancestry_json = A.main()
    except Exception as e:
        print(f"\n[ERROR] Ancestry gather raised {type(e).__name__}: {e}\n"
              "Stopping before FamilySearch - see the traceback above for exactly where it failed.")
        raise
    if not ancestry_json:
        print("\n[ERROR] Ancestry gather did not produce a JSON file; stopping before FamilySearch.")
        sys.exit(1)

    print("\n[System] Step 2 of 3: Gathering from FamilySearch...\n")
    try:
        fs_json = FS.main()
    except Exception as e:
        print(f"\n[ERROR] FamilySearch gather raised {type(e).__name__}: {e}\n"
              f"Ancestry's own JSON was already saved to {ancestry_json} - rerun once this is fixed "
              "rather than repeating the Ancestry step.")
        raise
    if not fs_json:
        print("\n[ERROR] FamilySearch gather did not produce a JSON file.")
        sys.exit(1)

    print("\n[System] Step 3 of 3: Merging the two sources...\n")
    ancestry_data = json.loads(Path(ancestry_json).read_text(encoding="utf-8"))
    fs_data = json.loads(Path(fs_json).read_text(encoding="utf-8"))
    merged = MergedCensus.merge_census(ancestry_data, fs_data)

    json_target_dir = Path(program_dir) / json_dir if program_dir else Path(json_dir)
    json_target_dir.mkdir(parents=True, exist_ok=True)
    # Strip the Ancestry file's own "- ANC" suffix first, so this doesn't read
    # "... - ANC - Merged.json" - "- Merged" already says both sources went into it.
    base_stem = re.sub(r" - ANC$", "", Path(ancestry_json).stem)
    merged_json = json_target_dir / f"{base_stem} - Merged.json"
    merged_json.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")

    # Point "Generate GEDCOM"'s default JSON_FILE at the merged result, superseding
    # whichever per-source file A.main()/FS.main() each just set it to individually.
    set_key(str(Path(__file__).resolve().parent / ".env"), "JSON_FILE", merged_json.name)

    total_participants = sum(len(r.get('participants', [])) for s in merged.get('sheets', [])
                             for r in s.get('records', []))
    print(f"[System] Merge complete: {len(merged.get('sheets', []))} sheet(s), {total_participants} "
          f"participant(s) -> {merged_json.name}")
    print(f"[System] Gather complete. Run Archivist's \"Generate GEDCOM\" when you're ready to "
          f"build the GEDCOM ({merged_json.name}).")


if __name__ == "__main__":
    main()
