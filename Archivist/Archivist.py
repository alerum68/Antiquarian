"""
Archivist - the toolbox's Create step, thin dispatcher.

Reads a single JSON file produced by Voyageur (Gather) and/or Paleographer (Analysis)
and routes to Census.py (flat per-page census rows, needs household grouping) or
General.py (explicit per-participant roles, church-register/Scrip-shaped) based on the
document's own record_type_name. General.py's behavior for a given record type is
selected via a Profile instance looked up in PROFILE_REGISTRY - GeneralProfile for
every record type except Scrip, which gets Scrip.ScripProfile.
"""
import json
import os
from pathlib import Path
from typing import Callable, Dict

import Census
import General
import Scrip
import Utils

JSON_DIR = os.getenv("JSON_DIR", str(Path(__file__).resolve().parent))
JSON_FILE = os.getenv("JSON_FILE", "")

PROFILE_REGISTRY: Dict[str, Callable[[], "General.Profile"]] = {
    "Scrip": Scrip.ScripProfile,
}


def resolve_profile(record_type_name: str) -> "General.Profile":
    profile_cls = PROFILE_REGISTRY.get(record_type_name, General.GeneralProfile)
    return profile_cls()


def resolve_json_input(json_file: str, json_dir: str) -> Path:
    """Resolves the JSON file to convert. An explicit JSON_FILE setting must exist (a typo
    there is a real error, not a reason to guess). Left blank, falls back to whichever
    *.json file in JSON_DIR was created most recently, so tools like Archivist's
    "Generate GEDCOM" button work as a plain fallback without needing a filename typed in
    every time."""
    if json_file:
        candidate = Path(json_file) if os.path.isabs(json_file) else Path(str(json_dir)) / json_file
        if candidate.is_file():
            return candidate
        raise FileNotFoundError(f"JSON file not found: {candidate}")

    search_dir = Path(str(json_dir))
    candidates = sorted(search_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError(
            f"No JSON_FILE was set, and no *.json files were found in {search_dir} to fall back to.")
    return candidates[0]


if __name__ == "__main__":
    input_path = resolve_json_input(JSON_FILE, JSON_DIR)
    print(f"[System] Using JSON file: {input_path}" + ("" if JSON_FILE else " (auto-selected, most recent)"))

    with open(input_path, "r", encoding="utf-8") as json_fh:
        loaded_data = json.load(json_fh)

    is_census = loaded_data.get("record_type_name", "").startswith("Census_") or "pages" in loaded_data
    if is_census:
        if not os.getenv("GEDCOM_OUTPUT_NAME", "").strip():
            Utils.GEDCOM_OUTPUT_NAME = input_path.stem + ".ged"
        Census.run_census_flavor(loaded_data)
    elif "sheets" in loaded_data:
        General.run_general_flavor(loaded_data, resolve_profile(loaded_data.get("record_type_name", "")))
    else:
        raise ValueError(
            f"Could not determine JSON flavor for {input_path}: expected a top-level "
            f"'sheets' key with a record_type_name, or a legacy 'pages' key (census)."
        )
