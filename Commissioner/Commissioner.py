"""
Commissioner: LAC-linked cross-referencing sitting between Paleographer and Archivist.
Pipeline: Voyageur -> Paleographer -> Commissioner -> Archivist.

Generic HTTP mechanics live in lac_client.py; this module is the genealogy/pipeline-
aware layer on top of it - resolving which LAC records matter for a given Scrip record
(or a whole volume) and writing results into the same JSON shape Archivist already
reads. No Archivist/GEDCOM concerns here - Commissioner only cross-references the
master DB JSON in place.

Two entry points, both built on the three-pass split locked in this session
(specifically to avoid ever needing to race a cf_clearance cookie's ~30-60 minute
lifetime):

- cross_check_claim_record: single-claim cross-check. Given one Paleographer-extracted
  Scrip record (with its own claim/affidavit/scrip numbers), search once for its related
  certificate/land-grant, download every digital object found, and append entries to
  record["source_documents"].

- retrieve_volume: Pass 1+2 for a whole volume. Pass 1 spends ONE search_volume() call
  to retrieve every PID in the volume. Pass 2 downloads record metadata + every digital
  object for each PID - no cookie needed for any of it, and progress is checkpointed to
  disk so a run spanning multiple cookie refreshes is safely resumable. Pass 3 (running
  the downloaded files through Paleographer/Agy) is a separate, later step - this module
  only gets the files onto disk.
"""

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import lac_client

# ==========================================
# CONFIGURATION
# ==========================================
PROGRAM_DIR = os.getenv("PROGRAM_DIR", "")


def _safe_path(base: str, *parts: str) -> str:
    """Joins paths, letting an absolute part override the base - same convention as
    Archivist.py's own safe_path (not imported directly, to keep this module's only
    dependency ScriptoriumMCP-style generic mechanics, not another pipeline stage)."""
    non_blank = [p for p in parts if p]
    if not non_blank:
        return ""
    res = base
    for p in non_blank:
        res = p if os.path.isabs(p) else os.path.join(res, p)
    return res


JSON_DIR = _safe_path(PROGRAM_DIR, os.getenv("JSON_DIR", ""))
JSON_FILE = os.getenv("COMMISSIONER_JSON_FILE", "") or os.getenv("JSON_FILE", "")
MEDIA_DIR = _safe_path(PROGRAM_DIR, os.getenv("COMMISSIONER_MEDIA_DIR", "Media/Commissioner"))
CHECKPOINT_DIR = _safe_path(PROGRAM_DIR, os.getenv("COMMISSIONER_CHECKPOINT_DIR", "Working/Commissioner"))
COOKIE_FILE = _safe_path(PROGRAM_DIR, os.getenv("COMMISSIONER_COOKIE_FILE", "Working/Commissioner/lac_cookies.txt"))
DEFAULT_ARCHIVAL_NUMBER = os.getenv("COMMISSIONER_ARCHIVAL_NUMBER", "RG15")
CDP_PORT = int(os.getenv("COMMISSIONER_CDP_PORT", str(lac_client.DEFAULT_CDP_PORT)))


# Confirmed live: original affidavit PDFs the user already has follow a
# "..._{PID}.pdf" naming convention (e.g. BAC-LAC_fonandcol_1502188.pdf) - this is the
# cheap, no-network way to resolve a record's own PID before ever touching LAC. Files
# named by their e-number instead (e.g. e011349655.pdf) won't match; those fall back to
# search() by e-number (see build_claim_search_query).
_PID_FROM_FILENAME_RE = re.compile(r"_(\d+)\.pdf$", re.IGNORECASE)


def resolve_pid_from_filename(file_name: str) -> Optional[str]:
    """Returns the PID embedded in a locally-chosen filename, or None if the filename
    doesn't follow that convention (e.g. an e-number-named file, or anything not
    downloaded through this pipeline)."""
    if not file_name:
        return None
    match = _PID_FROM_FILENAME_RE.search(file_name)
    return match.group(1) if match else None


_SCRIP_RANGE_RE = re.compile(r"^\s*(\d+)\s*(?:to|-|–)\s*(\d+)\s*$", re.IGNORECASE)


def expand_scrip_number_range(scrip_number: Optional[str]) -> List[str]:
    """Expands a range like "2234 to 2241" into every individual number in it. A scrip
    claim awarded a range represents MULTIPLE separate certificates, not one (confirmed
    live: Margaret Sabiston's real claim showed exactly this) - searching only the
    range's own literal text as a single query would miss every certificate but whichever
    one happens to match that exact string. Returns [scrip_number] unchanged when it's
    already a single number or doesn't parse as a range - never invents numbers beyond
    what's actually stated, and a wildly large or inverted span (more likely a misread
    than a real award) is left unexpanded too, rather than generating hundreds of
    speculative searches."""
    if not scrip_number:
        return []
    match = _SCRIP_RANGE_RE.match(scrip_number.strip())
    if not match:
        return [scrip_number]
    low, high = int(match.group(1)), int(match.group(2))
    if high < low or high - low > 200:
        return [scrip_number]
    return [str(n) for n in range(low, high + 1)]


def build_claim_search_queries(record: Dict[str, Any]) -> List[str]:
    """Builds the free-text quer(ies) search() needs to find a claim's related documents.
    Confirmed live: "claim: {n} Scrip: {n}" together reliably surfaces both the
    affidavit and the award certificate - scrip numbers alone are reused across claims
    and not unique enough to search on solo (per the user). Falls back to affidavit
    number if claim_number is missing, and to the record's own e-number (parsed from
    document_metadata.file_name) if nothing else is available.

    Returns one query PER individual scrip number when scrip_number is a range (see
    expand_scrip_number_range) - so every certificate in the range actually gets searched
    for. Returns [] when there's genuinely not enough to search on - callers should flag
    the record for review rather than skip it silently."""
    claim_number = record.get("claim_number")
    affidavit_number = record.get("affidavit_number")
    scrip_numbers = expand_scrip_number_range(record.get("scrip_number"))

    primary = claim_number or affidavit_number
    if primary and scrip_numbers:
        return [f"claim: {primary} Scrip: {n}" for n in scrip_numbers]
    if primary:
        return [f"claim: {primary}"]
    if scrip_numbers:
        return [f"Scrip: {n}" for n in scrip_numbers]

    file_name = (record.get("document_metadata") or {}).get("file_name", "")
    e_number_match = re.search(r"(e\d{6,})", file_name, re.IGNORECASE)
    if e_number_match:
        return [e_number_match.group(1)]

    return []


def build_claim_search_query(record: Dict[str, Any]) -> Optional[str]:
    """Backward-compatible single-query form - the first of build_claim_search_queries(),
    or None if there's nothing to search on. Prefer build_claim_search_queries directly
    for anything that should actually search every number in a scrip_number range."""
    queries = build_claim_search_queries(record)
    return queries[0] if queries else None


def _document_type_for_asset(asset: "lac_client.DigitalObject") -> str:
    """A downloaded LAC asset's label often isn't genealogically meaningful on its own
    (e.g. "Page 1") - this exists so callers can override with something more useful
    once they know WHY this PID was fetched (e.g. "Scrip Certificate" for a related-item
    download); on its own it just falls back to whatever label LAC's manifest gave."""
    return asset.label or "LAC Digital Object"


def download_pid_bundle(pid: str, media_dir: str,
                        document_type_override: Optional[str] = None) -> Dict[str, Any]:
    """Pass 2, per-PID: fetches record metadata + manifest, downloads every digital
    object to media_dir/{pid}/{asset_id}.{ext}, and returns a small bundle describing
    what was saved - one entry per asset, shaped to append directly into a record's
    source_documents list (media_path instead of transcription text, per the plan).
    No cookie needed for any of this - record/manifest/asset endpoints are unguarded."""
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


# ==========================================
# SINGLE-CLAIM CROSS-CHECK
# ==========================================
def cross_check_claim_record(record: Dict[str, Any], cookies: Dict[str, str], media_dir: str
                             ) -> Dict[str, Any]:
    """Single-claim cross-check: resolves this Scrip record's own PID (cross-checking
    metadata against LAC's catalog), searches once for any related documents tied to the
    same claim (certificate/land-grant), and downloads everything found - appending to
    record["source_documents"] rather than overwriting anything already there from
    Paleographer's own extraction. Mutates and returns `record`.

    Cross-checking is deliberately conservative: LAC's catalog title is stored verbatim
    (record["lac_catalog_title"]) rather than auto-parsed and diffed field-by-field
    against the extraction - the one confirmed-live mismatch this session (a birth year
    misread) was caught by a human reading both side by side, not by a regex diff, and a
    brittle automatic parser risks manufacturing false "mismatch" flags. Downstream
    review (human or Archivist) reads both fields side by side instead."""
    file_name = (record.get("document_metadata") or {}).get("file_name", "")
    own_pid = resolve_pid_from_filename(file_name)

    if own_pid:
        record["lac_pid"] = own_pid  # Archivist.generate_uid prefers this over record_id
        try:
            own_bundle = download_pid_bundle(own_pid, media_dir,
                                             document_type_override=record.get("document_type"))
            record["lac_catalog_title"] = own_bundle["lac_catalog_title"]
            # reel_numbers/series_code are LAC catalog metadata, not something printed on
            # the page itself - Paleographer never extracts them, only Commissioner can.
            # Archivist reads these for a citation's Microfilm field and (series_code)
            # as a more authoritative signal than commission_reference free text for
            # picking which of the 5 real Scrip source templates a claim belongs to.
            type_fields = record.setdefault("type_specific_fields", {})
            if own_bundle.get("reel_numbers"):
                type_fields["reel_numbers"] = ", ".join(own_bundle["reel_numbers"])
            if own_bundle.get("series_code"):
                type_fields["rg_series_code"] = own_bundle["series_code"]
        except lac_client.LacCallError as e:
            record.setdefault("review_reason", []).append(f"Commissioner: failed to fetch own PID {own_pid}: {e}")

    queries = build_claim_search_queries(record)
    if not queries:
        record.setdefault("review_reason", []).append(
            "Commissioner: no claim_number/affidavit_number/scrip_number/e-number available to search LAC with")
        return record

    # Usually one query; more than one only when scrip_number was a range (see
    # build_claim_search_queries) - every number in the range gets its own search, since
    # each represents a separate certificate. An expired cookie fails every remaining
    # query identically, so stop entirely on the first LacSearchAuthError rather than
    # retrying it N more times; a plain LacCallError is treated as a one-off blip on that
    # specific query and doesn't abort the rest.
    all_found_pids = set()
    for query in queries:
        try:
            all_found_pids.update(lac_client.search(query, cookies))
        except lac_client.LacSearchAuthError as e:
            record.setdefault("review_reason", []).append(f"Commissioner: search cookie expired/invalid: {e}")
            break
        except lac_client.LacCallError as e:
            record.setdefault("review_reason", []).append(f"Commissioner: search failed for {query!r}: {e}")

    related_pids = sorted(p for p in all_found_pids if p != own_pid)
    source_documents = record.setdefault("source_documents", [])
    for related_pid in related_pids:
        try:
            bundle = download_pid_bundle(related_pid, media_dir)
            source_documents.extend(bundle["source_documents"])
        except lac_client.LacCallError as e:
            record.setdefault("review_reason", []).append(
                f"Commissioner: failed to fetch related PID {related_pid}: {e}")

    return record


# ==========================================
# VOLUME RETRIEVAL (checkpointed, resumable)
# ==========================================
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
    """Pass 1: the one cookie-gated call per volume. Idempotent/resumable - if the
    checkpoint already has PIDs for this volume (from an earlier partial run), skips the
    search entirely rather than spending cookie budget again."""
    checkpoint = load_checkpoint(checkpoint_path)
    if checkpoint.get("pids"):
        return checkpoint["pids"]

    pids = lac_client.search_volume(vol, cookies, archival_number=archival_number)
    checkpoint["pids"] = pids
    checkpoint["volume"] = vol
    save_checkpoint(checkpoint_path, checkpoint)
    return pids


def download_volume_assets(pids: List[str], media_dir: str, checkpoint_path: str) -> Dict[str, Any]:
    """Pass 2: bulk, unattended download for a whole volume's worth of PIDs - no cookie
    needed for any of it. Checkpoints after every PID (not just at the end) so a crash
    or interruption partway through a large volume doesn't lose completed work, and a
    re-run picks up exactly where it left off. One PID's failure doesn't abort the rest
    of the volume - it's recorded in failed_pids and the loop continues."""
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


def retrieve_volume(vol: str, cookies: Dict[str, str], media_dir: str, checkpoint_path: str,
                    archival_number: str = "RG15") -> Dict[str, Any]:
    """Pass 1 + Pass 2 for one volume: retrieve every PID (one cookie-gated call, skipped
    if already checkpointed), then bulk-download everything found (no cookie needed).
    Pass 3 - running the downloaded files through Paleographer/Agy - is intentionally
    not part of this function; it's a separate, later, fully-decoupled step."""
    pids = retrieve_volume_pids(vol, cookies, checkpoint_path, archival_number=archival_number)
    return download_volume_assets(pids, media_dir, checkpoint_path)


# ==========================================
# MAIN EXECUTION
# ==========================================
def resolve_json_input(json_file: str, json_dir: str) -> Path:
    """Same convention as Archivist.resolve_json_input: an explicit path wins; blank
    falls back to whichever *.json in json_dir was modified most recently, so Commissioner
    runs against whatever Paleographer/Archivist are already pointed at without a
    filename typed in separately."""
    if json_file:
        candidate = Path(json_file) if os.path.isabs(json_file) else Path(str(json_dir)) / json_file
        if candidate.is_file():
            return candidate
        raise FileNotFoundError(f"JSON file not found: {candidate}")

    search_dir = Path(str(json_dir))
    candidates = sorted(search_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError(f"No JSON file was set, and no *.json files were found in {search_dir}.")
    return candidates[0]


def load_cookies(cookie_file: str, cdp_port: int = CDP_PORT) -> Dict[str, str]:
    """Cookies for the search endpoint - tries reading them live from a debuggable
    Chrome/Edge instance first (see lac_client.load_cookies_from_cdp; the user launches
    one with --remote-debugging-port, solves the LAC search there, no DevTools copy-paste
    needed), falling back to the manually-maintained cookie file (COMMISSIONER_COOKIE_FILE)
    if no debuggable browser is reachable on that port. Either path ultimately needs the
    user to have solved a real search recently (~30-60 min) - neither obtains a cookie on
    its own."""
    try:
        return lac_client.load_cookies_from_cdp(port=cdp_port)
    except lac_client.LacCallError:
        pass  # no debuggable browser on that port - fall through to the file

    path = Path(cookie_file)
    if not path.is_file():
        raise FileNotFoundError(f"No cookie file at {path}.")
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        raise ValueError(f"Cookie file {path} is empty.")
    return lac_client.parse_cookie_header(raw)


def main() -> None:
    parser = argparse.ArgumentParser(description="Commissioner: LAC-linked cross-referencing for Scrip records")
    parser.add_argument("mode", choices=["crosscheck", "retrieve"], nargs="?", default="crosscheck",
                        help="'crosscheck' cross-checks every Scrip record in the active JSON against "
                             "LAC and downloads related documents; 'retrieve' bulk-downloads one whole "
                             "volume's worth of PIDs, no AI/JSON involved.")
    parser.add_argument("--volume", default=os.getenv("COMMISSIONER_VOLUME", ""),
                        help="Volume/box number to retrieve (retrieve mode only).")
    args = parser.parse_args()

    os.makedirs(MEDIA_DIR, exist_ok=True)
    os.makedirs(CHECKPOINT_DIR, exist_ok=True)

    if args.mode == "retrieve":
        if not args.volume:
            print("[FATAL ERROR] --volume is required for retrieve mode (or set COMMISSIONER_VOLUME).")
            return

        print("Loading search cookies...")
        try:
            cookies = load_cookies(COOKIE_FILE)
        except (FileNotFoundError, ValueError) as e:
            print(f"[FATAL ERROR] {e} Search LAC once in a real browser, then paste its Cookie header "
                  f"into that file. Opening the search page now.")
            lac_client.open_search_browser_for_refresh()
            return

        checkpoint_path = str(Path(CHECKPOINT_DIR) / f"volume_{args.volume}.json")
        print(f"Retrieving volume {args.volume} (archival number {DEFAULT_ARCHIVAL_NUMBER})...")
        try:
            result = retrieve_volume(args.volume, cookies, MEDIA_DIR, checkpoint_path,
                                     archival_number=DEFAULT_ARCHIVAL_NUMBER)
        except lac_client.LacSearchAuthError as e:
            print(f"[FATAL ERROR] {e} Opening the search page now.")
            lac_client.open_search_browser_for_refresh()
            return

        print(f"Found {len(result.get('pids', []))} PID(s); downloaded "
              f"{len(result.get('downloaded_pids', []))}, {len(result.get('failed_pids', {}))} failed. "
              f"Re-run to resume/retry failures - already-downloaded PIDs are skipped.")
        return

    # crosscheck mode
    input_path = resolve_json_input(JSON_FILE, JSON_DIR)
    print(f"[System] Using JSON file: {input_path}" + ("" if JSON_FILE else " (auto-selected, most recent)"))
    with open(input_path, "r", encoding="utf-8") as f:
        master_data = json.load(f)

    record_type_name = master_data.get("record_type_name", "")
    if record_type_name != "Scrip":
        print(f"[System] record_type_name is '{record_type_name}', not 'Scrip' - Commissioner only "
              f"cross-checks Scrip records today. Nothing to do.")
        return

    print("Loading search cookies...")
    try:
        cookies = load_cookies(COOKIE_FILE)
    except (FileNotFoundError, ValueError) as e:
        print(f"[Warning] {e} Proceeding without search cookies - only own-PID lookups (from the "
              f"source filename) will resolve; related-document discovery will be flagged for "
              f"review on every record instead.")
        cookies = {}

    processed_count = 0
    for sheet in master_data.get("sheets", []):
        for record in sheet.get("records", []):
            cross_check_claim_record(record, cookies, MEDIA_DIR)
            processed_count += 1

    with open(input_path, "w", encoding="utf-8") as f:
        json.dump(master_data, f, indent=2, ensure_ascii=False)
    print(f"Cross-checked {processed_count} record(s). Saved to {input_path}")


if __name__ == "__main__":
    main()
