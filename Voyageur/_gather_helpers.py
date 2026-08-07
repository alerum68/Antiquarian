"""
Shared gather helpers for Voyageur's provider scripts (A.py, FS.py). Chrome (or antivirus
scanning it) can still hold a freshly-downloaded file open for a brief moment after it
appears in the folder listing, so an immediate shutil.move/unlink can lose to a transient
PermissionError/WinError 32 on Windows - these retry helpers ride out that window instead
of letting a gather crash with the file left stranded. The remaining functions here are the
Tampermonkey-download-wait/image-move/image-dir-resolution/Archivist-write-back logic that
used to be duplicated between A.py and FS.py's own main().
"""

import os
import shutil
import sys
import time
import webbrowser
from pathlib import Path

from dotenv import set_key


def move_with_retry(src: Path, dst: Path, attempts: int = 5, delay: float = 0.5) -> None:
    for attempt in range(1, attempts + 1):
        try:
            shutil.move(str(src), str(dst))
            return
        except OSError as e:
            if attempt == attempts:
                print(f"[ERROR] Could not move {src.name} to {dst} after {attempts} attempts: {e}")
                raise
            time.sleep(delay)


def cleanup_checkpoint_files(downloads_dir: Path, prefix: str, start_time: float) -> None:
    """Deletes this run's own leftover periodic checkpoint downloads (see
    downloadCheckpointJson in Voyageur.js) now that the final combined JSON has already
    been moved/written out - they're superseded and, unlike the final JSON, nothing else
    ever cleans them up, so a long gather would otherwise leave several of them sitting in
    the Downloads folder permanently. Best-effort: a checkpoint that can't be deleted (still
    briefly locked, already gone) is left in place rather than raising."""
    for p in downloads_dir.iterdir():
        if (p.is_file() and p.suffix.lower() == '.json' and p.name.startswith(prefix)
                and '[checkpoint' in p.name and p.stat().st_mtime >= start_time):
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass


def launch_gather_browser(url: str) -> float:
    start_time = time.time()
    auto_url = url + ("&mgs_auto=1" if "?" in url else "?mgs_auto=1")
    print("[System] Launching browser...")
    webbrowser.open(auto_url)
    print("\n[System] Waiting for Tampermonkey downloads (Auto-Batch will start automatically)...")
    return start_time


def wait_for_downloaded_json(downloads_dir: Path, prefix: str, start_time: float, label: str) -> Path:
    json_file = None
    try:
        while True:
            # noinspection broad-exception
            try:
                candidates = [
                    p for p in downloads_dir.iterdir()
                    if p.is_file() and p.suffix.lower() == '.json'
                    and p.name.startswith(prefix)
                    and p.stat().st_mtime >= start_time
                    and '[checkpoint' not in p.name
                ]
                if candidates:
                    json_file = max(candidates, key=lambda p: p.stat().st_mtime)
                    print(f"[System] Detected {label}: {json_file.name}")
            except OSError:
                pass

            if json_file:
                break
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[System] Operation cancelled by user.")
        sys.exit(0)
    return json_file


def move_downloaded_images(downloads_dir: Path, image_prefix: str, start_time: float,
                            img_target_dir: Path) -> int:
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
            move_with_retry(file_path, final_img)
            img_count += 1
        except Exception as e:
            print(f"[ERROR] Could not move image {file_path.name}: {e}")
    return img_count


def resolve_census_image_dir(base_img_setting: str, program_dir: str, census_folder: str,
                              location_folder: str) -> Path:
    if os.path.isabs(base_img_setting):
        base_img_dir = Path(base_img_setting)
    else:
        media_setting = os.getenv("MEDIA_DIR", "Media")
        base_media_dir = Path(media_setting) if os.path.isabs(media_setting) else (
            Path(program_dir) / media_setting if program_dir else Path(media_setting))
        base_img_dir = base_media_dir / base_img_setting
    img_target_dir = base_img_dir / census_folder / location_folder
    img_target_dir.mkdir(parents=True, exist_ok=True)
    return img_target_dir


def write_archivist_json_file(final_json_name: str) -> None:
    set_key(str(Path(__file__).resolve().parent.parent / "Archivist" / ".env"), "JSON_FILE", final_json_name)
