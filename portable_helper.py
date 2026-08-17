"""
Antiquarian Portable Setup

Standalone first-run provisioning tool for the raw Antiquarian_Portable_*.zip
distribution only. installer.iss's own wizard already does this at install time for
both Standard and installer-driven Portable installs (downloading the Newberry
shapefiles, installing AGY CLI) - this replicates the same two steps for someone who
just unzipped the portable build instead, since that path runs no installer at all.

Deliberately kept out of Antiquarian.py itself: the main app never auto-triggers
downloads or elevation prompts on its own. This is a separate, explicit tool a
portable user runs once (or re-runs to refresh the shapefiles/AGY) after extracting.

Stdlib-only by design - this gets its own small, dependency-free PyInstaller --onefile
build (see build.py), so it stays a quick, single-exe download rather than pulling in
the main app's full dependency set.
"""

import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

NEWBERRY_SHAPEFILE_URL = "https://publications.newberry.org/ahcb/downloads/gis/US_AtlasHCB_Counties.zip"
# The original Borealis Dataverse source has no single-zip download (8 separate per-year
# DOIs) - this is a pre-zipped mirror hosted as a GitHub Release asset in this same repo.
CA_SHAPEFILE_URL = (
    "https://github.com/alerum68/Antiquarian/releases/download/gazetteer-ca-data-v1/CA_UNICEN_Counties.zip")
AGY_INSTALL_COMMAND = [
    "powershell.exe", "-NoProfile", "-Command",
    "irm https://antigravity.google/cli/install.ps1 | iex",
]


def own_dir() -> Path:
    """Wherever this exe (or script, for local testing) actually lives - the portable
    install's own folder, matching APP_DIR's reasoning in Antiquarian.py."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _download_and_extract(url: str, zip_path: Path, extract_dir: Path, label: str) -> None:
    extract_dir.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {label} to {extract_dir}...")
    try:
        urllib.request.urlretrieve(url, zip_path)
    except Exception as e:
        print(f"[ERROR] Could not download {label}: {e}")
        return

    print("Extracting...")
    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract_dir)
    except Exception as e:
        print(f"[ERROR] Could not extract {label}: {e}")
        return
    finally:
        zip_path.unlink(missing_ok=True)

    print(f"{label} installed.")


def fetch_shapefiles(target_dir: Path) -> None:
    gazetteer_dir = target_dir / "Gazetteer"

    print("This includes a large file (roughly 500 MB) - please be patient.")
    _download_and_extract(
        NEWBERRY_SHAPEFILE_URL, target_dir / "US_AtlasHCB_Counties.zip",
        gazetteer_dir, "US Newberry Atlas historical county boundaries")

    # Extracts into its own CA_UNICEN_Counties subfolder, matching Gazetteer.py's
    # CA_SHAPEFILE_DIR expectation (the zip is flat, not nested).
    _download_and_extract(
        CA_SHAPEFILE_URL, target_dir / "CA_UNICEN_Counties.zip",
        gazetteer_dir / "CA_UNICEN_Counties", "Canadian UNI-CEN Census Division boundaries")


def ensure_agy_installed() -> None:
    print("Checking for Antigravity CLI (agy)...")
    agy_path = shutil.which("agy")
    if agy_path:
        result = subprocess.run([agy_path, "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"agy is already installed: {result.stdout.strip()}")
            return

    print("agy not found - running the official installer...")
    try:
        subprocess.run(AGY_INSTALL_COMMAND, check=True)
        print("agy installed. You may need to open a new terminal window before it's on PATH.")
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] agy installation failed: {e}")


def main() -> None:
    target_dir = own_dir()
    print(f"Antiquarian Portable Setup - provisioning {target_dir}\n")
    fetch_shapefiles(target_dir)
    print()
    ensure_agy_installed()
    print("\nSetup complete. You can close this window.")
    input("Press Enter to exit...")


if __name__ == "__main__":
    main()
