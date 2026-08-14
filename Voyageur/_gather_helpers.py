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
import threading
import time
import webbrowser
from pathlib import Path

from dotenv import set_key
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Writes data to path via a temp file + atomic rename, so a crash/interruption
    mid-write never leaves a truncated file sitting at the final path - a caller that
    skips re-downloading an already-existing file would otherwise treat that truncated
    file as complete forever. On any failure the temp file is removed and the original
    exception re-raised; the final path is never touched unless the write fully
    succeeded."""
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        with open(tmp_path, "wb") as f:
            f.write(data)
        tmp_path.replace(path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def move_with_retry(src: Path, dst: Path, attempts: int = 5, delay: float = 0.5,
                    on_collision: str = "overwrite") -> str:
    """Moves src to dst, retrying on transient Windows file-lock errors. Returns "moved" or
    "skipped" (when on_collision="skip" and dst already exists - src is discarded either way,
    since a skipped download is never needed again)."""
    if on_collision == "skip" and dst.exists():
        src.unlink(missing_ok=True)
        return "skipped"
    for attempt in range(1, attempts + 1):
        try:
            shutil.move(str(src), str(dst))
            return "moved"
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


def find_orphaned_gather_runs(downloads_dir: Path, source_prefix: str,
                              current_run_id: str) -> dict:
    """Returns the leftover TMP_<source>_<runId>_* files in downloads_dir grouped by
    their embedded run ID, excluding the run that is still in progress. Each run's
    entry is {'final': Path | None, 'checkpoints': [Path, ...], 'images': [Path, ...]}:
    a run_id with 'final' set is a complete, recoverable gather; one with only
    checkpoints/images never produced its final JSON and is reported as-is - no final
    is ever guessed or synthesized. Only regular files are considered, and only those
    whose name starts with source_prefix (the source's own fixed prefix, e.g.
    'TMP_A_' or 'TMP_FS_'); the run ID is the text between source_prefix and the next
    '_' (run IDs are plain hex so they never contain one themselves). A .jpg belongs in
    'images'; a .json matching TMP_<source>_<runId>_final.json belongs in 'final' (at
    most one per run); a .json whose remainder contains the literal 'checkpoint'
    substring (e.g. ..._checkpoint_<N>.json) belongs in 'checkpoints'."""
    runs: dict = {}
    for p in downloads_dir.iterdir():
        if not p.is_file() or not p.name.startswith(source_prefix):
            continue
        rest = p.name[len(source_prefix):]
        if '_' not in rest:
            continue
        run_id, remainder = rest.split('_', 1)
        if run_id == current_run_id:
            continue
        entry = runs.setdefault(run_id, {'final': None, 'checkpoints': [], 'images': []})
        if p.suffix.lower() == '.jpg':
            entry['images'].append(p)
        elif p.suffix.lower() == '.json':
            if remainder == 'final.json':
                entry['final'] = p
            elif 'checkpoint' in remainder:
                entry['checkpoints'].append(p)
    return runs


def build_gather_launch_url(url: str, run_id: str) -> str:
    """Appends the auto-start flag and this run's own unique ID to the gather URL so
    Voyageur.js can read both from window.location.href: mgs_auto=1 starts the batch
    automatically, mgs_run=<id> is embedded into every filename this run downloads so two
    runs (even of the identical record) never produce colliding Downloads filenames - see
    the Voyageur Downloads Handling Redesign spec."""
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}mgs_auto=1&mgs_run={run_id}"


def launch_gather_browser(url: str, run_id: str) -> float:
    start_time = time.time()
    auto_url = build_gather_launch_url(url, run_id)
    print("[System] Launching browser...")
    webbrowser.open(auto_url)
    print("\n[System] Waiting for Tampermonkey downloads (Auto-Batch will start automatically)...")
    return start_time


def _block_until_ready(ready: threading.Event) -> None:
    ready.wait()


def wait_for_final_json_event(downloads_dir: Path, json_prefix: str, label: str) -> Path:
    """State-based replacement for the old time.sleep(1) polling loop: blocks on a real
    filesystem "file created" event for this run's own final JSON instead of waking up
    once a second to re-scan the directory. No timeout, matching the polling loop's own
    previous behavior (it never gave up on its own either) - just event-driven instead of
    poll-driven, per project direction (prefer state-based waiting over timers wherever a
    real event exists)."""
    ready = threading.Event()
    found: dict = {}

    def matches(p: Path) -> bool:
        return (p.suffix.lower() == '.json' and p.name.startswith(json_prefix)
                and '[checkpoint' not in p.name)

    class _FinalJsonHandler(FileSystemEventHandler):
        def _set_found_if_match(self, path: str) -> None:
            p = Path(path)
            if matches(p):
                found['path'] = p
                ready.set()

        def on_created(self, event):
            if event.is_directory:
                return
            self._set_found_if_match(event.src_path)

        def on_moved(self, event):
            if event.is_directory:
                return
            # Chrome stages downloads to a .crdownload file (which only fires on_created
            # for the staging name, never the final name) and then renames it to the
            # final filename via a filesystem move - so the final file's arrival is only
            # ever observed here, against dest_path (the new location), not src_path.
            self._set_found_if_match(event.dest_path)

    observer = Observer()
    observer.schedule(_FinalJsonHandler(), str(downloads_dir), recursive=False)
    observer.start()
    try:
        # A file matching this run's own final-JSON pattern may already exist by the time
        # the observer is attached (e.g. a very fast gather) - its on_created event would
        # never fire since it already happened, so check directly before waiting.
        existing = [p for p in downloads_dir.iterdir() if p.is_file() and matches(p)]
        if existing:
            found['path'] = max(existing, key=lambda p: p.stat().st_mtime)
            ready.set()

        _block_until_ready(ready)
    except KeyboardInterrupt:
        print("\n[System] Operation cancelled by user.")
        sys.exit(0)
    finally:
        observer.stop()
        observer.join()

    print(f"[System] Detected {label}: {found['path'].name}")
    return found['path']


def move_downloaded_images(downloads_dir: Path, image_prefix: str, start_time: float,
                           img_target_dir: Path, on_collision: str = "overwrite") -> tuple:
    """Moves every downloaded image to img_target_dir. A move that fails (e.g. a transient
    Windows file lock outlasting move_with_retry's own retries) is not fatal - it's retried
    once more, in a second pass over just the failures, after the rest of the batch has had
    a chance to finish and any lock has had a moment longer to clear. Returns
    (moved_count, skipped_names, failed_names)."""
    image_candidates = [
        p for p in downloads_dir.iterdir()
        if p.is_file() and p.suffix.lower() == '.jpg'
        and p.name.startswith(image_prefix) and p.stat().st_mtime >= start_time
    ]

    moved = []
    skipped = []
    failed = {}  # prefixed source name -> (file_path, final name) for files still pending

    def attempt(candidate_path: Path) -> None:
        final_name = candidate_path.name[len(image_prefix):]
        final_img = img_target_dir / final_name
        status = move_with_retry(candidate_path, final_img, on_collision=on_collision)
        (moved if status == "moved" else skipped).append(final_name)

    for file_path in image_candidates:
        # noinspection broad-exception
        try:
            attempt(file_path)
        except Exception as e:
            print(f"[ERROR] Could not move image {file_path.name}: {e}")
            failed[file_path.name] = file_path

    if failed:
        print(f"[System] Retrying {len(failed)} failed image move(s) once...")
        time.sleep(1.0)
        for name, file_path in list(failed.items()):
            if not file_path.exists():
                continue
            # noinspection broad-exception
            try:
                attempt(file_path)
                del failed[name]
            except Exception as e:
                print(f"[ERROR] Retry failed for {name}: {e}")

    final_failed_names = [name[len(image_prefix):] for name in failed]
    if final_failed_names:
        print(f"[WARN] {len(final_failed_names)} image(s) could not be moved after retry: "
              f"{', '.join(final_failed_names)}")

    return len(moved), skipped, final_failed_names


def resolve_census_image_dir(base_img_setting: str, genealogy_dir: str, census_folder: str,
                             location_folder: str) -> Path:
    if os.path.isabs(base_img_setting):
        base_img_dir = Path(base_img_setting)
    else:
        media_setting = os.getenv("MEDIA_DIR", "Media")
        base_media_dir = Path(media_setting) if os.path.isabs(media_setting) else (
            Path(genealogy_dir) / media_setting if genealogy_dir else Path(media_setting))
        base_img_dir = base_media_dir / base_img_setting
    img_target_dir = base_img_dir / census_folder / location_folder
    img_target_dir.mkdir(parents=True, exist_ok=True)
    return img_target_dir


def write_archivist_json_file(final_json_name: str) -> None:
    set_key(str(Path(__file__).resolve().parent.parent / "Archivist" / ".env"), "JSON_FILE", final_json_name)
