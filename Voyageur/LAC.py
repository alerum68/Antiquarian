import os
import re
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

# Global settings come from the project root's .env; this tool's own settings come from
# its own subfolder's .env, so Voyageur stays runnable standalone.
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
load_dotenv(Path(__file__).resolve().parent / ".env", override=False)


# ==========================================
# URL & PATH SETUP
# ==========================================
def get_env_paths():
    """Reads the necessary foundational directories mapped by the Toolbox."""
    program_dir = os.environ.get("PROGRAM_DIR", "").strip()
    media_dir = os.environ.get("MEDIA_DIR", "Media").strip()
    raw_url = os.environ.get("LAC_URL", "").strip()

    if not raw_url:
        print("[Error] No LAC_URL found in environment variables.")
        sys.exit(1)

    return program_dir, media_dir, raw_url


def parse_url(raw_url):
    """Sanitizes the user's pasted URL into a proper IIIF manifest API call."""
    print(f"[Info] Target URL: {raw_url}")

    base_id_match = re.search(r'(oocihm\.lac_reel_[a-zA-Z0-9]+)', raw_url, re.IGNORECASE)
    if not base_id_match:
        print("[Error] Could not find a valid Canadiana identifier (oocihm.lac_reel...) in the URL.")
        sys.exit(1)

    base_id = base_id_match.group(1)

    roll_match = re.search(r'lac_reel_([a-zA-Z0-9]+)', base_id, re.IGNORECASE)
    roll_num = roll_match.group(1) if roll_match else "Unknown_Roll"
    print(f"[Info] Extracted Roll Number: {roll_num}")

    # Force format into IIIF manifest URL, stripping any /view/ or user page numbers
    manifest_url = f"https://heritage.canadiana.ca/iiif/{base_id}/manifest"

    return roll_num, manifest_url


def setup_directories(program_dir, media_dir, roll_num):
    """Constructs the final output path relative to the user's media directory."""
    if os.path.isabs(media_dir):
        base_media = media_dir
    else:
        base_media = os.path.join(program_dir, media_dir)

    # Standardize to [MEDIA]/LAC/[ROLL_NUM]
    out_dir = os.path.join(base_media, "LAC", roll_num).replace("\\", "/")
    os.makedirs(out_dir, exist_ok=True)
    return out_dir


# ==========================================
# MANIFEST & DOWNLOAD
# ==========================================
def download_manifest(manifest_url):
    """Fetches the IIIF structural blueprint for the film roll."""
    print("[Info] Downloading manifest file...")
    try:
        response = requests.get(manifest_url, timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"[Error] Failed to fetch or parse manifest: {e}")
        sys.exit(1)


def download_images(manifest_data, out_dir, roll_num):
    """Loops through the manifest canvases and downloads max-resolution files."""
    # Support IIIF Presentation API v2 (Older standard)
    if "sequences" in manifest_data and manifest_data["sequences"]:
        canvases = manifest_data["sequences"][0].get("canvases", [])
    # Support IIIF Presentation API v3 (Newer standard)
    elif "items" in manifest_data:
        canvases = manifest_data.get("items", [])
    else:
        print("[Error] No valid sequences or items found in the manifest.")
        print(f"[Debug] Manifest Keys returned: {list(manifest_data.keys())}")
        sys.exit(1)

    total = len(canvases)

    if total == 0:
        print("[Error] No images found in the manifest.")
        sys.exit(1)

    print(f"[Info] Found {total} images to download.")

    # Using a session for connection pooling to speed up mass requests
    session = requests.Session()

    for i, canvas in enumerate(canvases, 1):
        try:
            img_id = ""

            if "images" in canvas:
                images = canvas.get("images", [])
                if images:
                    resource = images[0].get("resource", {})
                    img_id = resource.get("@id", "")

            elif "items" in canvas:
                items = canvas.get("items", [])
                if items:
                    annotations = items[0].get("items", [])
                    if annotations:
                        body = annotations[0].get("body", {})
                        if isinstance(body, dict):
                            img_id = body.get("id", "")
                        elif isinstance(body, list) and body:
                            img_id = body[0].get("id", "")

            if not img_id:
                print(f"\n[Warning] Could not extract image URL for canvas {i}")
                continue

            filename = f"{roll_num}_{i:04d}.jpg"
            filepath = os.path.join(out_dir, filename)

            # Skip if file already exists to permit resuming
            if os.path.exists(filepath):
                print(f"\rDownloading [{i}/{total}]...", end="", flush=True)
                continue

            print(f"\rDownloading [{i}/{total}]...", end="", flush=True)

            img_resp = session.get(img_id, timeout=20)
            img_resp.raise_for_status()

            with open(filepath, 'wb') as f:
                f.write(img_resp.content)

        except Exception as e:
            print(f"\n[Warning] Failed to download image {i}: {e}")

    print(f"\n\n[System] LAC Download for {roll_num} completed successfully!")


# ==========================================
# MAIN EXECUTION
# ==========================================
def main() -> None:
    p_dir, m_dir, url = get_env_paths()
    roll, manifest = parse_url(url)
    output_directory = setup_directories(p_dir, m_dir, roll)

    manifest_json = download_manifest(manifest)
    download_images(manifest_json, output_directory, roll)


if __name__ == "__main__":
    main()
