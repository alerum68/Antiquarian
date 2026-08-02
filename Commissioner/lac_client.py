"""
Generic HTTP client for Library and Archives Canada's Collection Search
(recherche-collection-search.bac-lac.gc.ca) - no genealogy domain knowledge, just the
four LAC endpoints Commissioner.py needs, each confirmed live against the real site:

- get_record_metadata: the catalog record page for a known Item ID (PID).
- get_manifest: the IIIF Presentation API v3 manifest listing an item's digital objects.
- download_asset: the actual file bytes for one digital object (image or PDF).
- search: find item(s) by claim/scrip number when the PID isn't already known.

The site is Cloudflare-protected. record/manifest/download all pass through cleanly with
a plain `cloudscraper` session (confirmed live - no special cookies needed). `search`
specifically sits behind a *second*, stronger layer requiring a real `cf_clearance`
cookie that only a real browser solving an interactive challenge can produce - confirmed
live that cloudscraper's challenge solvers (both its default and Node.js interpreters)
cannot get past it on their own, but replaying a real browser's full cookie jar +
matching headers does work. There is no way around this: `search` always needs a
cookie jar sourced from an actual browser session (see parse_cookie_header), refreshed
periodically by the user, not something this module can obtain on its own.
"""

import json
import re
from dataclasses import dataclass
from typing import Dict, List, Optional
from urllib.parse import quote

import cloudscraper
import requests
import webbrowser
from bs4 import BeautifulSoup

RECORD_HOST = "https://recherche-collection-search.bac-lac.gc.ca"
MANIFEST_HOST = "https://digitalmanifest.bac-lac.gc.ca"
ASSET_HOST = "https://central.bac-lac.gc.ca"

# Heritage Canadiana (heritage.canadiana.ca) independently mirrors LAC's microfilm reels
# via a CRKN digitization partnership. Confirmed live: the reel view page and its IIIF
# Image API v2 backend carry NO Cloudflare challenge at all (plain requests, no
# cloudscraper needed) - a genuine second bulk-retrieval path that never touches LAC's
# protected search endpoint. There is no JSON presentation manifest (confirmed live: the
# obvious /manifest and /presentation/.../manifest URL shapes both 404/fail) - a reel's
# full ordered page list has to be scraped from the view page's embedded IIIF image
# references instead (confirmed live: a single GET of the view page returns all 720 of a
# real reel's page images inline, no pagination needed).
CANADIANA_VIEW_HOST = "https://heritage.canadiana.ca"
CANADIANA_IMAGE_HOST = "https://image-uab.canadiana.ca"

DEFAULT_TIMEOUT_SECONDS = 30
# Confirmed live: manifest URLs are shaped {MANIFEST_HOST}/DigitalManifest/{source_code}/{PID}.
# source_code=1 is the "fonandcol" reference system - confirmed live against a real item.
# Not yet confirmed whether other reference systems (if LAC ever exposes them) use a
# different source_code; fonandcol is the only one Commissioner needs so far.
FONANDCOL_SOURCE_CODE = 1

# Between-request pacing - this is a government site, not a target to hammer. Applied by
# callers (Commissioner.py) between records, not enforced inside this module itself,
# since a single lookup here is already just one or two requests.
POLITE_DELAY_SECONDS = 1.0


class LacCallError(Exception):
    """Base error for any failed LAC call - a non-2xx response, a malformed body, or a
    network failure. Commissioner.py's retry logic catches this specifically."""


class LacSearchAuthError(LacCallError):
    """The search endpoint rejected the request because the supplied cookie jar is
    missing, invalid, or expired (confirmed live: an expired/missing cf_clearance
    returns a page titled "Forbidden: Request denied" or a Cloudflare "Just a moment..."
    challenge, not a clean error status). Distinct from LacCallError so callers can
    surface a specific "refresh your cookies" message instead of a generic failure."""


@dataclass
class RecordMetadata:
    pid: str
    title: str
    digital_object_count: Optional[int]
    reel_numbers: List[str]  # e.g. ["C-14932"] - LAC's own microfilm reel identifier(s),
    # directly usable with Heritage Canadiana's lac_reel_c{number} convention. A register/
    # index item can span many reels (confirmed live); an individual claim record has
    # exactly one, repeated per physical copy - deduped here either way.
    series_code: Optional[str]  # e.g. "RG15-D-II-8-a" - the exact RG sub-series, identifying
    # which of the several historical scrip commissions this record belongs to. A complex
    # item can carry more than one code concatenated with no separator (confirmed live,
    # e.g. "RG15-D-II-8-a-iRG15-D-II-8-a-ii") - stored as the raw text; callers needing the
    # individual codes split out should regex on their own known-code prefixes.


@dataclass
class DigitalObject:
    asset_id: str
    label: str
    media_format: str  # e.g. "image/jpeg", "application/pdf"

    @property
    def op(self) -> str:
        """The `op` query value download_asset needs - "pdf" for a PDF asset, "img" for
        anything else (confirmed live: image assets use op=img, the combined-PDF asset
        uses op=pdf)."""
        return "pdf" if "pdf" in self.media_format.lower() else "img"


def _get_scraper() -> "cloudscraper.CloudScraper":
    """A fresh cloudscraper session per call is deliberate, not an oversight - these are
    infrequent, one-off lookups (not a tight loop needing connection reuse), and a fresh
    session avoids any risk of stale challenge-solve state leaking between unrelated
    calls. `search` is the one function that takes an explicit, separately-sourced
    cookie jar instead, since cloudscraper's own challenge-solving can't reach that
    endpoint at all (see module docstring)."""
    return cloudscraper.create_scraper()


# ==========================================
# RECORD METADATA
# ==========================================
def get_record_metadata(pid: str, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
                        ) -> RecordMetadata:
    """Fetches the catalog record page for a known PID (Item ID) and pulls its title -
    confirmed live to carry a rich descriptive summary (names, birth year, parents,
    claim #, scrip #, date of issue, amount, digital-object count) that can be more
    accurate than an AI-OCR'd reading of the source document itself (confirmed live:
    LAC's own catalog had the correct birth year and scrip number where extraction from
    the scanned document had misread both). Callers should treat this as a cross-check
    source, not blindly overwrite extracted data with it.

    Raises LacCallError on a non-200 response or if no <title> is found."""
    url = f"{RECORD_HOST}/eng/Home/Record?app=fonandcol&IdNumber={pid}"
    scraper = _get_scraper()
    try:
        resp = scraper.get(url, timeout=timeout_seconds)
    except Exception as e:
        raise LacCallError(f"Failed to fetch record metadata for PID {pid}: {e}") from e

    if resp.status_code != 200:
        raise LacCallError(f"Record page for PID {pid} returned status {resp.status_code}")

    soup = BeautifulSoup(resp.content, "lxml")
    title_tag = soup.title
    if not title_tag or not title_tag.get_text(strip=True):
        raise LacCallError(f"Record page for PID {pid} had no <title> - unexpected response shape")
    title = title_tag.get_text(strip=True)

    count_match = re.search(r"\((\d+)\s+digital object", title, re.IGNORECASE)
    digital_object_count = int(count_match.group(1)) if count_match else None

    # Confirmed live: these two fields' element IDs embed the PID itself
    # (...containernotefonandcol{pid}, ...recordcontrolnumbercode{N}textfonandcol{pid}),
    # and the control-number field's numeric code segment (151 in one real example) isn't
    # fixed either - matched by prefix/regex, never a hardcoded full ID string.
    container_el = soup.find(id=re.compile(r"^jq-container-body-recordmediaphysicalmanifestationcontainernote"))
    reel_numbers = sorted(set(re.findall(r"[A-Z]-\d+", container_el.get_text()))) if container_el else []

    control_el = soup.find(id=re.compile(r"^jq-container-body-recordcontrolnumbercode\d+text"))
    series_code = control_el.get_text(strip=True) if control_el else None

    return RecordMetadata(pid=pid, title=title, digital_object_count=digital_object_count,
                          reel_numbers=reel_numbers, series_code=series_code)


# ==========================================
# MANIFEST (digital object list)
# ==========================================
def get_manifest(pid: str, source_code: int = FONANDCOL_SOURCE_CODE,
                 timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> List[DigitalObject]:
    """Fetches the IIIF Presentation API v3 manifest for a known PID and returns its
    digital objects - confirmed live against a real 2-document item: one entry per page
    image plus one for the combined PDF, each with its own `e0XXXXXXX` asset ID
    (confirmed distinct from the PID - one item can have several assets)."""
    url = f"{MANIFEST_HOST}/DigitalManifest/{source_code}/{pid}"
    scraper = _get_scraper()
    try:
        resp = scraper.get(url, timeout=timeout_seconds)
    except Exception as e:
        raise LacCallError(f"Failed to fetch manifest for PID {pid}: {e}") from e

    if resp.status_code != 200:
        raise LacCallError(f"Manifest for PID {pid} returned status {resp.status_code}")

    try:
        data = resp.json()
    except ValueError as e:
        raise LacCallError(f"Manifest for PID {pid} was not valid JSON: {e}") from e

    objects: List[DigitalObject] = []
    for canvas in data.get("items", []):
        label_parts = (canvas.get("label") or {}).get("en") or []
        label = label_parts[0] if label_parts else ""
        for annotation_page in canvas.get("items", []):
            for annotation in annotation_page.get("items", []):
                body = annotation.get("body") or {}
                asset_url = body.get("id") or ""
                media_format = body.get("format") or ""
                asset_match = re.search(r"[?&]id=(e\d+)", asset_url)
                if asset_match:
                    objects.append(DigitalObject(asset_id=asset_match.group(1), label=label,
                                                 media_format=media_format))
    return objects


# ==========================================
# ASSET DOWNLOAD
# ==========================================
def download_asset(asset_id: str, op: str, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> bytes:
    """Downloads one digital object's actual file bytes. `op` is "pdf" or "img" - see
    DigitalObject.op for how to derive it from a manifest entry's media_format."""
    url = f"{ASSET_HOST}/.item/?id={asset_id}&app=fonandcol&op={op}"
    scraper = _get_scraper()
    try:
        resp = scraper.get(url, timeout=timeout_seconds)
    except Exception as e:
        raise LacCallError(f"Failed to download asset {asset_id}: {e}") from e

    if resp.status_code != 200:
        raise LacCallError(f"Asset {asset_id} download returned status {resp.status_code}")
    if not resp.content:
        raise LacCallError(f"Asset {asset_id} download returned an empty body")

    return resp.content


# ==========================================
# HERITAGE CANADIANA (reel mirror, no Cloudflare gate)
# ==========================================
_CANADIANA_IMAGE_REF_RE = re.compile(r"iiif/2/([^/\"]+)/info\.json")


def get_canadiana_reel_pages(reel_id: str, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
                             ) -> List[str]:
    """Fetches a Canadiana reel's view page (reel_id like "lac_reel_c14950" - drop the
    "oocihm." prefix, added here) and returns the ordered list of IIIF image identifiers
    for every page on that reel. Each returned identifier is already the exact
    percent-encoded path segment Canadiana's own HTML uses (e.g.
    "69429%2Fc00000039385") - pass it straight through to download_canadiana_page,
    don't re-encode or decode it."""
    url = f"{CANADIANA_VIEW_HOST}/view/oocihm.{reel_id}"
    try:
        resp = requests.get(url, timeout=timeout_seconds)
    except Exception as e:
        raise LacCallError(f"Failed to fetch Canadiana reel {reel_id}: {e}") from e

    if resp.status_code != 200:
        raise LacCallError(f"Canadiana reel {reel_id} returned status {resp.status_code}")

    image_ids = _CANADIANA_IMAGE_REF_RE.findall(resp.text)
    if not image_ids:
        raise LacCallError(f"Canadiana reel {reel_id} page had no recognizable image references")

    # dict.fromkeys dedupes while preserving first-seen (document) order - each page's
    # info.json ref appears once per size variant on the page in practice, but this is
    # defensive rather than assumed.
    return list(dict.fromkeys(image_ids))


def download_canadiana_page(image_id: str, size: str = "full",
                            timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> bytes:
    """Downloads one page's full-resolution image bytes via Canadiana's IIIF Image API
    v2 backend. `image_id` is one entry from get_canadiana_reel_pages. `size` follows
    IIIF's size-parameter syntax ("full" for maximum resolution, confirmed live: a real
    page downloaded this way was a genuine ~4MB, 6192x5664 JPEG)."""
    url = f"{CANADIANA_IMAGE_HOST}/iiif/2/{image_id}/{size}/full/0/default.jpg"
    try:
        resp = requests.get(url, timeout=timeout_seconds)
    except Exception as e:
        raise LacCallError(f"Failed to download Canadiana page {image_id}: {e}") from e

    if resp.status_code != 200:
        raise LacCallError(f"Canadiana page {image_id} download returned status {resp.status_code}")
    if not resp.content:
        raise LacCallError(f"Canadiana page {image_id} download returned an empty body")

    return resp.content


# ==========================================
# SEARCH (requires a real browser's cookie jar)
# ==========================================
def parse_cookie_header(raw_cookie_header: str) -> Dict[str, str]:
    """Parses a raw `Cookie:` header string (exactly what a browser's DevTools "Copy as
    cURL" gives you after the `-b` flag) into a plain dict `search()` can use. Splits on
    `; ` - cookie values themselves may contain `=` (confirmed live, e.g. the
    `cf_clearance` cookie does), so this only splits on the FIRST `=` per cookie."""
    cookies: Dict[str, str] = {}
    for part in raw_cookie_header.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, value = part.split("=", 1)
        cookies[name.strip()] = value.strip()
    return cookies


_SEARCH_HEADERS = {
    "user-agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"),
    "accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
              "image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"),
    "accept-language": "en-US,en;q=0.9",
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "same-origin",
    "upgrade-insecure-requests": "1",
}


def _do_search_request(url: str, cookies: Dict[str, str], timeout_seconds: int,
                       description: str) -> List[str]:
    """Shared plumbing for search() and search_volume(): fire the request, detect an
    expired/missing cookie jar, and pull PIDs out of the result HTML. `description` is
    just the human-readable label used in the LacSearchAuthError message."""
    try:
        resp = requests.get(url, headers=_SEARCH_HEADERS, cookies=cookies, timeout=timeout_seconds)
    except Exception as e:
        raise LacCallError(f"Search request failed for {description}: {e}") from e

    soup = BeautifulSoup(resp.content, "lxml")
    title = soup.title.get_text(strip=True) if soup.title else ""

    if resp.status_code != 200 or "forbidden" in title.lower() or "just a moment" in title.lower():
        raise LacSearchAuthError(
            f"Search for {description} was rejected (status {resp.status_code}, title "
            f"{title!r}) - the supplied cookie jar is likely missing or expired. Get a "
            f"fresh one: search manually in a real browser, DevTools > Network > copy "
            f"the successful request as cURL, and extract its cookies."
        )

    return sorted(set(re.findall(r"IdNumber=(\d+)", resp.text)))


def search(query: str, cookies: Dict[str, str],
           timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> List[str]:
    """Searches by free-text query (confirmed live query shape: `"claim: {n} Scrip: {n}"`
    reliably surfaces both the affidavit AND the award certificate as separate results -
    per the user, scrip numbers alone are reused/not unique enough to search on solo).

    `cookies` MUST be a real browser's cookie jar (see parse_cookie_header) - there is no
    way to obtain a valid one programmatically (see module docstring). Raises
    LacSearchAuthError specifically when the response indicates the cookie jar is
    missing/expired (a "Forbidden: Request denied" or Cloudflare challenge page, rather
    than real search-results HTML), so callers can surface a clear "go get a fresh
    cookie jar" message instead of a generic failure.

    Returns a list of Item ID (PID) strings found - confirmed live: searching "claim:
    3126 Scrip: 12751" returned two distinct PIDs, one for the affidavit and one for the
    certificate."""
    url = f"{RECORD_HOST}/eng/Home/Result?ST=STAD&q_type_1=q&q_1={quote(query)}&"
    return _do_search_request(url, cookies, timeout_seconds, description=repr(query))


DEFAULT_CDP_PORT = 9222


def load_cookies_from_cdp(port: int = DEFAULT_CDP_PORT, domain_url: str = f"{RECORD_HOST}/",
                          timeout_seconds: int = 10) -> Dict[str, str]:
    """Reads live session cookies straight out of a Chrome/Edge instance the user
    launched with --remote-debugging-port={port} (a separate, dedicated browser window -
    see Commissioner's "Launch Debug Browser" button) after they solved the LAC search
    challenge normally in it - via the Chrome DevTools Protocol's Network.getCookies,
    reading the browser's live in-memory cookie jar directly rather than its on-disk
    store. This exists specifically because Chrome/Edge 127+'s "App-Bound Encryption"
    makes the on-disk cookie store undecryptable by any third-party tool, admin
    privileges included (confirmed via research this session) - CDP sidesteps that
    entirely since it's reading the running browser's own memory, not its disk file.

    Raises LacCallError if no debuggable browser is found on `port` (i.e. it wasn't
    launched with --remote-debugging-port), LacSearchAuthError if a browser IS found but
    has no cookies for the LAC domain yet (the user hasn't searched there yet, or the
    session already expired)."""
    try:
        import websocket  # websocket-client - only needed for this one function
    except ImportError as e:
        raise LacCallError(
            "The websocket-client package is required for CDP cookie reading "
            "(pip install websocket-client)."
        ) from e

    try:
        targets = requests.get(f"http://localhost:{port}/json", timeout=timeout_seconds).json()
    except Exception as e:
        raise LacCallError(
            f"Could not reach a debuggable browser on port {port}: {e}. Launch Chrome or "
            f"Edge with --remote-debugging-port={port} first, then search LAC in that window."
        ) from e

    target = next((t for t in targets if t.get("type") == "page"), None)
    if not target or not target.get("webSocketDebuggerUrl"):
        raise LacCallError(f"No open browser tab found on debug port {port}.")

    ws = websocket.create_connection(target["webSocketDebuggerUrl"], timeout=timeout_seconds)
    try:
        ws.send(json.dumps({"id": 1, "method": "Network.getCookies", "params": {"urls": [domain_url]}}))
        response = json.loads(ws.recv())
    finally:
        ws.close()

    cookies = {c["name"]: c["value"] for c in response.get("result", {}).get("cookies", [])}
    if not cookies:
        raise LacSearchAuthError(
            f"No cookies found for {domain_url} on debug port {port} - search LAC in that "
            f"browser window first (or the session there has already expired)."
        )
    return cookies


def open_search_browser_for_refresh(query: str = "") -> None:
    """Opens the LAC search page in the user's real default browser so they can run one
    search manually and pass the challenge themselves - the only legitimate way to
    refresh a search cookie (see module docstring; deliberately not something this
    module tries to automate). Callers (Commissioner.py) call this when search()/
    search_volume() raises LacSearchAuthError, alongside a printed message telling the
    user to copy the resulting request as cURL and feed its cookies back in."""
    url = f"{RECORD_HOST}/eng/Home/SearchAdvanced"
    if query:
        url = f"{RECORD_HOST}/eng/Home/Result?ST=STAD&q_type_1=q&q_1={quote(query)}&"
    webbrowser.open(url)


def search_volume(vol: str, cookies: Dict[str, str], archival_number: str = "RG15",
                  timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> List[str]:
    """Harvests every PID filed under one volume/box number - the "Pass 1" whole-volume
    harvest call: one search covers an entire volume rather than one claim at a time, so
    a volume's worth of downstream (unguarded) record/manifest/asset calls never need
    the cookie again. `vol` spans 1319-1372 for the RG15-D-II-8 scrip series per the
    user (Finding Aid 15-19 covers 1319-1324; 15-20 through 15-23 cover the rest -
    finding aid 15-18 appears to have been superseded by 15-19, never separately found).

    Query shape is translated from baclac.py's original multi-field advanced search
    (ArchivalNumber=RG15-D-II-8 AND VolumeBoxNumber={vol}, paginated via start/num=100 -
    see DEV/Vols 1319-1324/Vols 1319-1324/baclac.py:260) onto the current site's
    `/eng/Home/Result` route, using the exact field names the user supplied from their
    own testing. NOT YET LIVE-VERIFIED end-to-end by this module (the old site's
    ASP.NET WebForms param names carrying over to the new MVC backend is plausible but
    unconfirmed) - treat the first real call as the test. Also NOT yet confirmed whether
    the new site paginates the same start/num=100 way; this only fetches page one
    (start=0) - a result count worth checking on that first real call before assuming a
    volume with >100 items would be fully captured."""
    query_string = (
        f"ST=STAD&DataSource=Archives|FonAndCol"
        f"&SearchIn_1=ArchivalNumber&SearchInText_1={quote(archival_number)}&Operator_1=AND"
        f"&SearchIn_2=VolumeBoxNumber&SearchInText_2={quote(str(vol))}&Operator_2=AND"
        f"&DataSourceSel=Archives&start=0&num=100&"
    )
    url = f"{RECORD_HOST}/eng/Home/Result?{query_string}"
    return _do_search_request(url, cookies, timeout_seconds, description=f"volume {vol}")
