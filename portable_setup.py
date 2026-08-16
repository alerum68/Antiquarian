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


def fetch_shapefiles(target_dir: Path) -> None:
    gazetteer_dir = target_dir / "Gazetteer"
    gazetteer_dir.mkdir(parents=True, exist_ok=True)
    zip_path = target_dir / "US_AtlasHCB_Counties.zip"

    print(f"Downloading US Newberry Atlas historical county boundaries to {gazetteer_dir}...")
    print("This is a large file (roughly 500 MB) - please be patient.")
    try:
        urllib.request.urlretrieve(NEWBERRY_SHAPEFILE_URL, zip_path)
    except Exception as e:
        print(f"[ERROR] Could not download shapefiles: {e}")
        return

    print("Extracting...")
    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(gazetteer_dir)
    except Exception as e:
        print(f"[ERROR] Could not extract shapefiles: {e}")
        return
    finally:
        zip_path.unlink(missing_ok=True)

    print("Shapefiles installed.")


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
