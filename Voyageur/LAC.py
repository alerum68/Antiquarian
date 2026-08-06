import argparse
import json
import os
import re
import sys
import time
import multiprocessing as mp
import queue
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv

# Global settings come from the project root's .env; this tool's own settings come from
# its own subfolder's .env, so Voyageur stays runnable standalone.
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
load_dotenv(Path(__file__).resolve().parent / ".env", override=False)

try:
    from . import lac_client
except (ImportError, ValueError):
    import lac_client


# ==========================================
# PATH & CONFIG SETUP
# ==========================================
def _safe_path(base: str, *parts: str) -> str:
    non_blank = [p for p in parts if p]
    if not non_blank:
        return ""
    res = base
    for p in non_blank:
        res = p if os.path.isabs(p) else os.path.join(res, p)
    return res


PROGRAM_DIR = os.environ.get("PROGRAM_DIR", "").strip()
MEDIA_DIR = _safe_path(PROGRAM_DIR, os.environ.get("MEDIA_DIR", "Media").strip())
CHECKPOINT_DIR = _safe_path(PROGRAM_DIR, os.environ.get("LAC_CHECKPOINT_DIR", "Working/LAC"))
COOKIE_FILE = _safe_path(PROGRAM_DIR, os.environ.get("LAC_COOKIE_FILE", "Working/LAC/lac_cookies.txt"))
DEFAULT_ARCHIVAL_NUMBER = os.environ.get("LAC_ARCHIVAL_NUMBER", "RG15")
CDP_PORT = int(os.environ.get("LAC_CDP_PORT", str(lac_client.DEFAULT_CDP_PORT)))

_PID_FROM_FILENAME_RE = re.compile(r"_(\d+)\.pdf$", re.IGNORECASE)


def resolve_pid_from_filename(file_name: str) -> Optional[str]:
    """Returns the PID embedded in a locally-chosen filename (e.g. BAC-LAC_fonandcol_1502188.pdf),
    or None if the filename doesn't follow that convention."""
    if not file_name:
        return None
    match = _PID_FROM_FILENAME_RE.search(file_name)
    return match.group(1) if match else None


def load_cookies(cookie_file: str = COOKIE_FILE, cdp_port: int = CDP_PORT) -> Dict[str, str]:
    """Loads search cookies from a debuggable browser or a cookie file."""
    try:
        return lac_client.load_cookies_from_cdp(port=cdp_port)
    except lac_client.LacCallError:
        pass

    path = Path(cookie_file)
    if not path.is_file():
        raise FileNotFoundError(f"No cookie file at {path}.")
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        raise ValueError(f"Cookie file {path} is empty.")
    return lac_client.parse_cookie_header(raw)


# ==========================================
# CANADIANA IIIF MANIFEST & DOWNLOAD
# ==========================================
def get_env_paths() -> Tuple[str, str, str]:
    """Reads the necessary foundational directories mapped by the Toolbox."""
    program_dir = os.environ.get("PROGRAM_DIR", "").strip()
    media_dir = os.environ.get("MEDIA_DIR", "Media").strip()
    raw_url = os.environ.get("LAC_URL", "").strip()
    return program_dir, media_dir, raw_url


def parse_url(raw_url: str) -> Tuple[str, str]:
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
    manifest_url = f"https://heritage.canadiana.ca/iiif/{base_id}/manifest"
    return roll_num, manifest_url


def setup_directories(program_dir: str, media_dir: str, roll_num: str) -> str:
    """Constructs the final output path relative to the user's media directory."""
    if os.path.isabs(media_dir):
        base_media = media_dir
    else:
        base_media = os.path.join(program_dir, media_dir)
    out_dir = os.path.join(base_media, "LAC", roll_num).replace("\\", "/")
    os.makedirs(out_dir, exist_ok=True)
    return out_dir


def download_manifest(manifest_url: str) -> Dict[str, Any]:
    """Fetches the IIIF structural blueprint for the film roll."""
    print("[Info] Downloading manifest file...")
    try:
        response = requests.get(manifest_url, timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"[Error] Failed to fetch or parse manifest: {e}")
        sys.exit(1)


def download_images(manifest_data: Dict[str, Any], out_dir: str, roll_num: str) -> None:
    """Loops through the manifest canvases and downloads max-resolution files."""
    if "sequences" in manifest_data and manifest_data["sequences"]:
        canvases = manifest_data["sequences"][0].get("canvases", [])
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
# VOLUME HARVEST & PID BUNDLE DOWNLOADS
# ==========================================
def _document_type_for_asset(asset: "lac_client.DigitalObject") -> str:
    return asset.label or "LAC Digital Object"


def download_pid_bundle(pid: str, media_dir: str,
                        document_type_override: Optional[str] = None) -> Dict[str, Any]:
    """Fetches record metadata + manifest for a PID, downloads every digital object to
    media_dir/{pid}/{asset_id}.{ext}, and returns bundle dict."""
    metadata = lac_client.get_record_metadata(pid)
    assets = lac_client.get_manifest(pid)

    pid_dir = Path(media_dir) / pid
    pid_dir.mkdir(parents=True, exist_ok=True)

    entries: List[Dict[str, Any]] = []
    for asset in assets:
        ext = "pdf" if asset.op == "pdf" else "jpg"
        file_path = pid_dir / f"{asset.asset_id}.{ext}"
        if not file_path.exists():
            data = lac_client.download_asset(asset.asset_id, asset.op)
            file_path.write_bytes(data)

        entries.append({
            "document_type": document_type_override or _document_type_for_asset(asset),
            "media_path": str(file_path),
            "lac_pid": pid,
            "lac_asset_id": asset.asset_id,
            "source": "LAC",
        })

    return {
        "pid": pid,
        "lac_catalog_title": metadata.title,
        "reel_numbers": metadata.reel_numbers,
        "series_code": metadata.series_code,
        "source_documents": entries,
    }


def load_checkpoint(checkpoint_path: str) -> Dict[str, Any]:
    if os.path.exists(checkpoint_path):
        with open(checkpoint_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"pids": [], "downloaded_pids": [], "failed_pids": {}}


def save_checkpoint(checkpoint_path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(checkpoint_path) or ".", exist_ok=True)
    with open(checkpoint_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def retrieve_volume_pids(vol: str, cookies: Dict[str, str], checkpoint_path: str,
                         archival_number: str = "RG15") -> List[str]:
    """Discovers all PIDs in an archival volume using LAC search endpoint."""
    checkpoint = load_checkpoint(checkpoint_path)
    if checkpoint.get("pids"):
        return checkpoint["pids"]

    pids = lac_client.search_volume(vol, cookies, archival_number=archival_number)
    checkpoint["pids"] = pids
    checkpoint["volume"] = vol
    save_checkpoint(checkpoint_path, checkpoint)
    return pids


def download_volume_assets(pids: List[str], media_dir: str, checkpoint_path: str) -> Dict[str, Any]:
    """Sequential bulk download for a list of PIDs with checkpointing."""
    checkpoint = load_checkpoint(checkpoint_path)
    downloaded = set(checkpoint.get("downloaded_pids", []))
    failed = checkpoint.get("failed_pids", {})

    for pid in pids:
        if pid in downloaded:
            continue
        try:
            download_pid_bundle(pid, media_dir)
            downloaded.add(pid)
            failed.pop(pid, None)
        except lac_client.LacCallError as e:
            failed[pid] = str(e)

        checkpoint["downloaded_pids"] = sorted(downloaded)
        checkpoint["failed_pids"] = failed
        save_checkpoint(checkpoint_path, checkpoint)

    return checkpoint


def _worker_download_loop(worker_id: int, task_queue: mp.Queue, result_queue: mp.Queue,
                          rate_lock: Any, last_req_time: Any, current_delay: Any,
                          media_dir: str) -> None:
    """Worker process for concurrent asset downloads with rate limiting."""
    while True:
        try:
            pid = task_queue.get_nowait()
        except queue.Empty:
            break

        result_queue.put(("START", worker_id, pid, time.time()))
        try:
            with rate_lock:
                now = time.time()
                elapsed = now - last_req_time.value
                delay_val = current_delay.value
                if elapsed < delay_val:
                    time.sleep(delay_val - elapsed)
                last_req_time.value = time.time()

            bundle = download_pid_bundle(pid, media_dir)
            result_queue.put(("SUCCESS", worker_id, pid, bundle))
        except Exception as e:
            err_str = str(e)
            if "403" in err_str:
                result_queue.put(("403_ERROR", worker_id, pid, err_str))
            else:
                result_queue.put(("FAIL", worker_id, pid, err_str))


def download_volume_assets_multiworker(pids: List[str], media_dir: str, checkpoint_path: str,
                                       max_workers: int = 4, base_delay: float = 0.3,
                                       timeout_seconds: int = 45) -> Dict[str, Any]:
    """Concurrent multi-worker PID downloading with watchdog timeout."""
    checkpoint = load_checkpoint(checkpoint_path)
    downloaded = set(checkpoint.get("downloaded_pids", []))
    failed = checkpoint.get("failed_pids", {})

    pids_to_process = [p for p in pids if p not in downloaded]
    if not pids_to_process:
        return checkpoint

    print(f"[LAC Multi-Worker] Processing {len(pids_to_process)} PIDs with {max_workers} workers...")

    manager = mp.Manager()
    rate_lock = manager.Lock()
    last_req_time = manager.Value('d', 0.0)
    current_delay = manager.Value('d', base_delay)

    task_queue = manager.Queue()
    result_queue = manager.Queue()

    for pid in pids_to_process:
        task_queue.put(pid)

    active_workers = {i: {"process": None, "pid": None, "start_time": 0} for i in range(max_workers)}

    def start_worker(wid):
        p = mp.Process(target=_worker_download_loop,
                       args=(wid, task_queue, result_queue, rate_lock, last_req_time, current_delay, media_dir))
        p.start()
        active_workers[wid]["process"] = p
        active_workers[wid]["pid"] = None

    for wid in range(max_workers):
        start_worker(wid)

    processed_count = 0
    total_target = len(pids_to_process)

    while processed_count < total_target:
        now = time.time()
        for wid, worker in active_workers.items():
            if worker["pid"] and (now - worker["start_time"] > timeout_seconds):
                hung_pid = worker["pid"]
                print(f"\n[Watchdog] Worker {wid} hung on PID {hung_pid}. Restarting worker...")
                worker["process"].terminate()
                worker["process"].join()
                task_queue.put(hung_pid)
                start_worker(wid)

        try:
            msg = result_queue.get(timeout=0.2)
        except queue.Empty:
            continue

        msg_type, wid, pid = msg[0], msg[1], msg[2]

        if msg_type == "START":
            active_workers[wid]["pid"] = pid
            active_workers[wid]["start_time"] = msg[3]
        elif msg_type == "SUCCESS":
            active_workers[wid]["pid"] = None
            downloaded.add(pid)
            failed.pop(pid, None)
            processed_count += 1
            checkpoint["downloaded_pids"] = sorted(downloaded)
            checkpoint["failed_pids"] = failed
            save_checkpoint(checkpoint_path, checkpoint)
            print(f"\rDownloaded PID {pid} [{processed_count}/{total_target}]", end="", flush=True)
        elif msg_type == "403_ERROR":
            active_workers[wid]["pid"] = None
            with rate_lock:
                current_delay.value = min(current_delay.value * 2.0, 5.0)
            task_queue.put(pid)
        elif msg_type == "FAIL":
            active_workers[wid]["pid"] = None
            failed[pid] = msg[3]
            processed_count += 1
            checkpoint["failed_pids"] = failed
            save_checkpoint(checkpoint_path, checkpoint)

    print("\n[LAC Multi-Worker] Download run completed.")
    return checkpoint


def retrieve_volume(vol: str, cookies: Dict[str, str], media_dir: str, checkpoint_path: str,
                    archival_number: str = "RG15", max_workers: int = 1) -> Dict[str, Any]:
    """High-level volume retrieval: gathers PIDs and downloads all associated assets."""
    pids = retrieve_volume_pids(vol, cookies, checkpoint_path, archival_number=archival_number)
    if max_workers > 1:
        return download_volume_assets_multiworker(pids, media_dir, checkpoint_path, max_workers=max_workers)
    return download_volume_assets(pids, media_dir, checkpoint_path)


# ==========================================
# MAIN EXECUTION
# ==========================================
def main() -> None:
    parser = argparse.ArgumentParser(description="Voyageur LAC Gatherer: Canadiana IIIF and LAC Volume Harvester")
    parser.add_argument("--url", default=os.environ.get("LAC_URL", ""),
                        help="Canadiana IIIF URL (e.g., https://heritage.canadiana.ca/view/oocihm.lac_reel_c2170).")
    parser.add_argument("--volume", default=os.environ.get("LAC_VOLUME", ""),
                        help="LAC Volume number to harvest (e.g., 1325).")
    parser.add_argument("--archival-number", default=DEFAULT_ARCHIVAL_NUMBER,
                        help="Archival series number (default: RG15).")
    parser.add_argument("--cookie-file", default=COOKIE_FILE,
                        help="Path to browser cookies file for LAC search.")
    parser.add_argument("--media-dir", default=MEDIA_DIR,
                        help="Base output media directory.")
    parser.add_argument("--workers", type=int, default=int(os.environ.get("LAC_MAX_WORKERS", "1")),
                        help="Number of concurrent workers for volume downloading (default 1).")
    args = parser.parse_args()

    # Route 1: Volume harvesting
    if args.volume:
        print(f"[System] Starting LAC Volume retrieval for Volume {args.volume}...")
        try:
            cookies = load_cookies(args.cookie_file)
        except (FileNotFoundError, ValueError) as e:
            print(f"[FATAL ERROR] {e} Search LAC once in a real browser, then paste its Cookie header "
                  f"into that file. Opening search browser...")
            lac_client.open_search_browser_for_refresh()
            return

        checkpoint_path = str(Path(CHECKPOINT_DIR) / f"volume_{args.volume}.json")
        try:
            result = retrieve_volume(args.volume, cookies, args.media_dir, checkpoint_path,
                                     archival_number=args.archival_number, max_workers=args.workers)
        except lac_client.LacSearchAuthError as e:
            print(f"[FATAL ERROR] {e} Opening the search page now.")
            lac_client.open_search_browser_for_refresh()
            return

        print(f"[System] Harvested volume {args.volume}: {len(result.get('pids', []))} PID(s), "
              f"{len(result.get('downloaded_pids', []))} downloaded, "
              f"{len(result.get('failed_pids', {}))} failed.")
        return

    # Route 2: Canadiana IIIF Reel URL
    url = args.url
    if not url:
        print("[Error] Either LAC_URL or LAC_VOLUME must be provided.")
        sys.exit(1)

    program_dir = os.environ.get("PROGRAM_DIR", "").strip()
    roll, manifest = parse_url(url)
    output_directory = setup_directories(program_dir, args.media_dir, roll)
    manifest_json = download_manifest(manifest)
    download_images(manifest_json, output_directory, roll)


if __name__ == "__main__":
    main()
