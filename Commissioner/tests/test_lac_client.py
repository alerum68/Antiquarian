"""
Tests for lac_client.py against fake HTTP responses - no live network access. Mirrors
ScriptoriumMCP/tests/test_agy_client.py's fake-response pattern: monkeypatch the
underlying HTTP call (cloudscraper.create_scraper / requests.get) to return a canned
FakeResponse instead of hitting the real site.
"""

import json
import sys
import types

import pytest

import lac_client


class FakeResponse:
    def __init__(self, status_code=200, text="", json_data=None, content=None):
        self.status_code = status_code
        self.text = text
        self.content = content if content is not None else text.encode("utf-8")
        self._json_data = json_data
        self.url = "https://example.invalid/fake"

    def json(self):
        if self._json_data is None:
            raise ValueError("no JSON body configured on this FakeResponse")
        return self._json_data


class FakeScraper:
    """Stand-in for cloudscraper.CloudScraper - just needs a .get()."""

    def __init__(self, response=None, exc=None):
        self._response = response
        self._exc = exc
        self.calls = []

    def get(self, url, timeout=None):
        self.calls.append(url)
        if self._exc:
            raise self._exc
        return self._response


RECORD_TITLE = ("Scrip affidavit for Letendre, Roger; born: ABT 1849 "
                "(2 digital objects)")

MANIFEST_JSON = {
    "items": [
        {
            "label": {"en": ["Page 1"]},
            "items": [{"items": [{"body": {
                "id": "https://central.bac-lac.gc.ca/.item/?id=e011355547&app=fonandcol&op=img",
                "format": "image/jpeg",
            }}]}],
        },
        {
            "label": {"en": ["Combined PDF"]},
            "items": [{"items": [{"body": {
                "id": "https://central.bac-lac.gc.ca/.item/?id=e011355548&app=fonandcol&op=pdf",
                "format": "application/pdf",
            }}]}],
        },
    ]
}


# ==========================================
# RECORD METADATA
# ==========================================
def test_get_record_metadata_happy_path(monkeypatch):
    scraper = FakeScraper(response=FakeResponse(status_code=200,
                                                 text=f"<html><head><title>{RECORD_TITLE}</title></head></html>"))
    monkeypatch.setattr(lac_client, "_get_scraper", lambda: scraper)

    result = lac_client.get_record_metadata("1502188")
    assert result.pid == "1502188"
    assert "Letendre, Roger" in result.title
    assert result.digital_object_count == 2
    assert result.reel_numbers == []
    assert result.series_code is None
    assert scraper.calls == ["https://recherche-collection-search.bac-lac.gc.ca/eng/Home/Record?app=fonandcol&IdNumber=1502188"]


def test_get_record_metadata_extracts_reel_numbers_and_series_code(monkeypatch):
    html = f"""
    <html><head><title>{RECORD_TITLE}</title></head><body>
      <div id="jq-container-body-recordmediaphysicalmanifestationcontainernotefonandcol1503710">
        C-14932 : Copy No. 1C-14932 : Copy No. 2C-14932 : Copy No. 3C-14932 : Copy No. 4
      </div>
      <div id="jq-container-body-recordcontrolnumbercode151textfonandcol1503710">
        RG15-D-II-8-a
      </div>
    </body></html>
    """
    scraper = FakeScraper(response=FakeResponse(status_code=200, text=html))
    monkeypatch.setattr(lac_client, "_get_scraper", lambda: scraper)

    result = lac_client.get_record_metadata("1503710")
    assert result.reel_numbers == ["C-14932"]  # deduped from the 4 "Copy No." repeats
    assert result.series_code == "RG15-D-II-8-a"


def test_get_record_metadata_dedupes_and_sorts_multiple_reel_numbers(monkeypatch):
    """A register/index item can span many reels (confirmed live)."""
    html = """
    <html><head><title>Register title</title></head><body>
      <div id="jq-container-body-recordmediaphysicalmanifestationcontainernotefonandcol164144">
        C-14926 : copies sur microfilm Copy No. 1C-14925 : copies sur microfilm Copy No. 1
        C-14926 : copies sur microfilm Copy No. 2
      </div>
    </body></html>
    """
    scraper = FakeScraper(response=FakeResponse(status_code=200, text=html))
    monkeypatch.setattr(lac_client, "_get_scraper", lambda: scraper)

    result = lac_client.get_record_metadata("164144")
    assert result.reel_numbers == ["C-14925", "C-14926"]


def test_get_record_metadata_raises_on_non_200(monkeypatch):
    scraper = FakeScraper(response=FakeResponse(status_code=404, text="<html></html>"))
    monkeypatch.setattr(lac_client, "_get_scraper", lambda: scraper)

    with pytest.raises(lac_client.LacCallError, match="status 404"):
        lac_client.get_record_metadata("999999")


def test_get_record_metadata_raises_when_no_title(monkeypatch):
    scraper = FakeScraper(response=FakeResponse(status_code=200, text="<html><head></head></html>"))
    monkeypatch.setattr(lac_client, "_get_scraper", lambda: scraper)

    with pytest.raises(lac_client.LacCallError, match="no <title>"):
        lac_client.get_record_metadata("999999")


def test_get_record_metadata_digital_object_count_absent(monkeypatch):
    scraper = FakeScraper(response=FakeResponse(status_code=200,
                                                 text="<html><head><title>Some record, no count in title</title></head></html>"))
    monkeypatch.setattr(lac_client, "_get_scraper", lambda: scraper)

    result = lac_client.get_record_metadata("1502188")
    assert result.digital_object_count is None


# ==========================================
# MANIFEST
# ==========================================
def test_get_manifest_happy_path(monkeypatch):
    scraper = FakeScraper(response=FakeResponse(status_code=200, json_data=MANIFEST_JSON))
    monkeypatch.setattr(lac_client, "_get_scraper", lambda: scraper)

    objects = lac_client.get_manifest("1502188")
    assert len(objects) == 2
    assert objects[0].asset_id == "e011355547"
    assert objects[0].label == "Page 1"
    assert objects[0].op == "img"
    assert objects[1].asset_id == "e011355548"
    assert objects[1].op == "pdf"


def test_get_manifest_raises_on_non_200(monkeypatch):
    scraper = FakeScraper(response=FakeResponse(status_code=500, text=""))
    monkeypatch.setattr(lac_client, "_get_scraper", lambda: scraper)

    with pytest.raises(lac_client.LacCallError, match="status 500"):
        lac_client.get_manifest("1502188")


def test_get_manifest_raises_on_bad_json(monkeypatch):
    bad_response = FakeResponse(status_code=200, text="not json")

    def broken_json():
        raise ValueError("no JSON object could be decoded")
    bad_response.json = broken_json
    scraper = FakeScraper(response=bad_response)
    monkeypatch.setattr(lac_client, "_get_scraper", lambda: scraper)

    with pytest.raises(lac_client.LacCallError, match="not valid JSON"):
        lac_client.get_manifest("1502188")


# ==========================================
# ASSET DOWNLOAD
# ==========================================
def test_download_asset_happy_path(monkeypatch):
    scraper = FakeScraper(response=FakeResponse(status_code=200, content=b"%PDF-1.4 fake bytes"))
    monkeypatch.setattr(lac_client, "_get_scraper", lambda: scraper)

    data = lac_client.download_asset("e011355548", "pdf")
    assert data == b"%PDF-1.4 fake bytes"


def test_download_asset_raises_on_non_200(monkeypatch):
    scraper = FakeScraper(response=FakeResponse(status_code=403, content=b""))
    monkeypatch.setattr(lac_client, "_get_scraper", lambda: scraper)

    with pytest.raises(lac_client.LacCallError, match="status 403"):
        lac_client.download_asset("e011355548", "pdf")


def test_download_asset_raises_on_empty_body(monkeypatch):
    scraper = FakeScraper(response=FakeResponse(status_code=200, content=b""))
    monkeypatch.setattr(lac_client, "_get_scraper", lambda: scraper)

    with pytest.raises(lac_client.LacCallError, match="empty body"):
        lac_client.download_asset("e011355548", "pdf")


# ==========================================
# HERITAGE CANADIANA
# ==========================================
CANADIANA_PAGE_HTML = """
<html><body>
<img src="https://image-uab.canadiana.ca/iiif/2/69429%2Fc00000039385/info.json">
<img src="https://image-uab.canadiana.ca/iiif/2/69429%2Fc0000003939r/info.json">
<img src="https://image-uab.canadiana.ca/iiif/2/69429%2Fc00000039385/info.json">
</body></html>
"""


def test_get_canadiana_reel_pages_happy_path(monkeypatch):
    monkeypatch.setattr(lac_client.requests, "get",
                        lambda url, timeout=None: FakeResponse(status_code=200, text=CANADIANA_PAGE_HTML))

    pages = lac_client.get_canadiana_reel_pages("lac_reel_c14950")
    # deduped, order-preserved
    assert pages == ["69429%2Fc00000039385", "69429%2Fc0000003939r"]


def test_get_canadiana_reel_pages_raises_on_non_200(monkeypatch):
    monkeypatch.setattr(lac_client.requests, "get",
                        lambda url, timeout=None: FakeResponse(status_code=404, text=""))

    with pytest.raises(lac_client.LacCallError, match="status 404"):
        lac_client.get_canadiana_reel_pages("lac_reel_c99999")


def test_get_canadiana_reel_pages_raises_when_no_images_found(monkeypatch):
    monkeypatch.setattr(lac_client.requests, "get",
                        lambda url, timeout=None: FakeResponse(status_code=200, text="<html></html>"))

    with pytest.raises(lac_client.LacCallError, match="no recognizable image references"):
        lac_client.get_canadiana_reel_pages("lac_reel_c99999")


def test_download_canadiana_page_happy_path(monkeypatch):
    monkeypatch.setattr(lac_client.requests, "get",
                        lambda url, timeout=None: FakeResponse(status_code=200, content=b"fake jpeg bytes"))

    data = lac_client.download_canadiana_page("69429%2Fc00000039385")
    assert data == b"fake jpeg bytes"


def test_download_canadiana_page_raises_on_empty_body(monkeypatch):
    monkeypatch.setattr(lac_client.requests, "get",
                        lambda url, timeout=None: FakeResponse(status_code=200, content=b""))

    with pytest.raises(lac_client.LacCallError, match="empty body"):
        lac_client.download_canadiana_page("69429%2Fc00000039385")


# ==========================================
# COOKIE PARSING
# ==========================================
def test_parse_cookie_header_basic():
    raw = "a=1; b=2; c=3"
    assert lac_client.parse_cookie_header(raw) == {"a": "1", "b": "2", "c": "3"}


def test_parse_cookie_header_value_containing_equals():
    raw = "cf_clearance=abc123==.def456-ghi789; __cf_bm=xyz"
    parsed = lac_client.parse_cookie_header(raw)
    assert parsed["cf_clearance"] == "abc123==.def456-ghi789"
    assert parsed["__cf_bm"] == "xyz"


def test_parse_cookie_header_ignores_malformed_segments():
    raw = "a=1; ;   ; b=2"
    assert lac_client.parse_cookie_header(raw) == {"a": "1", "b": "2"}


# ==========================================
# SEARCH
# ==========================================
SEARCH_RESULTS_HTML = """
<html><head><title>Search Results</title></head><body>
<a href="/eng/Home/Record?app=fonandcol&IdNumber=1502188">result 1</a>
<a href="/eng/Home/Record?app=fonandcol&IdNumber=1502189">result 2</a>
</body></html>
"""


def test_search_happy_path(monkeypatch):
    captured = {}

    def fake_get(url, headers=None, cookies=None, timeout=None):
        captured["url"] = url
        captured["cookies"] = cookies
        return FakeResponse(status_code=200, text=SEARCH_RESULTS_HTML)

    monkeypatch.setattr(lac_client.requests, "get", fake_get)

    pids = lac_client.search("claim: 3126 Scrip: 12751", cookies={"cf_clearance": "abc"})
    assert pids == ["1502188", "1502189"]
    assert captured["cookies"] == {"cf_clearance": "abc"}
    assert "q_1=claim%3A" in captured["url"] or "q_1=claim" in captured["url"]


def test_search_raises_lac_search_auth_error_on_forbidden_title(monkeypatch):
    forbidden_html = "<html><head><title>403 - Interdit: Requ&ecirc;te refus&eacute;e / Forbidden: Request denied</title></head></html>"
    monkeypatch.setattr(lac_client.requests, "get",
                        lambda url, headers=None, cookies=None, timeout=None: FakeResponse(status_code=200, text=forbidden_html))

    with pytest.raises(lac_client.LacSearchAuthError):
        lac_client.search("claim: 3126 Scrip: 12751", cookies={})


def test_search_raises_lac_search_auth_error_on_challenge_title(monkeypatch):
    challenge_html = "<html><head><title>Just a moment...</title></head></html>"
    monkeypatch.setattr(lac_client.requests, "get",
                        lambda url, headers=None, cookies=None, timeout=None: FakeResponse(status_code=200, text=challenge_html))

    with pytest.raises(lac_client.LacSearchAuthError, match="expired"):
        lac_client.search("claim: 3126 Scrip: 12751", cookies={"stale": "cookie"})


def test_search_raises_lac_search_auth_error_on_non_200(monkeypatch):
    monkeypatch.setattr(lac_client.requests, "get",
                        lambda url, headers=None, cookies=None, timeout=None: FakeResponse(status_code=403, text="<html></html>"))

    with pytest.raises(lac_client.LacSearchAuthError):
        lac_client.search("claim: 3126 Scrip: 12751", cookies={})


# ==========================================
# SEARCH_VOLUME
# ==========================================
def test_search_volume_happy_path(monkeypatch):
    captured = {}

    def fake_get(url, headers=None, cookies=None, timeout=None):
        captured["url"] = url
        return FakeResponse(status_code=200, text=SEARCH_RESULTS_HTML)

    monkeypatch.setattr(lac_client.requests, "get", fake_get)

    pids = lac_client.search_volume("1319", cookies={"cf_clearance": "abc"})
    assert pids == ["1502188", "1502189"]
    assert "SearchInText_1=RG15" in captured["url"]
    assert "SearchInText_2=1319" in captured["url"]
    assert "VolumeBoxNumber" in captured["url"]


def test_search_volume_raises_lac_search_auth_error_on_expired_cookie(monkeypatch):
    challenge_html = "<html><head><title>Just a moment...</title></head></html>"
    monkeypatch.setattr(lac_client.requests, "get",
                        lambda url, headers=None, cookies=None, timeout=None: FakeResponse(status_code=200, text=challenge_html))

    with pytest.raises(lac_client.LacSearchAuthError):
        lac_client.search_volume("1319", cookies={})


# ==========================================
# CDP COOKIE READER
# ==========================================
class FakeWSConnection:
    def __init__(self, response_payload):
        self.response_payload = response_payload
        self.sent = []
        self.closed = False

    def send(self, data):
        self.sent.append(data)

    def recv(self):
        return json.dumps(self.response_payload)

    def close(self):
        self.closed = True


def _install_fake_websocket_module(monkeypatch, response_payload):
    fake_module = types.SimpleNamespace(
        create_connection=lambda url, timeout=None: FakeWSConnection(response_payload))
    monkeypatch.setitem(sys.modules, "websocket", fake_module)
    return fake_module


def test_load_cookies_from_cdp_happy_path(monkeypatch):
    targets = [{"type": "page", "webSocketDebuggerUrl": "ws://localhost:9222/devtools/page/ABC"}]
    monkeypatch.setattr(lac_client.requests, "get",
                        lambda url, timeout=None: FakeResponse(status_code=200, json_data=targets))
    cdp_response = {"result": {"cookies": [{"name": "cf_clearance", "value": "abc123"},
                                           {"name": "__cf_bm", "value": "xyz789"}]}}
    _install_fake_websocket_module(monkeypatch, cdp_response)

    cookies = lac_client.load_cookies_from_cdp(port=9222)
    assert cookies == {"cf_clearance": "abc123", "__cf_bm": "xyz789"}


def test_load_cookies_from_cdp_raises_when_no_debug_port_reachable(monkeypatch):
    def broken_get(url, timeout=None):
        raise ConnectionError("refused")
    monkeypatch.setattr(lac_client.requests, "get", broken_get)

    with pytest.raises(lac_client.LacCallError, match="Could not reach"):
        lac_client.load_cookies_from_cdp(port=9222)


def test_load_cookies_from_cdp_raises_when_no_page_target(monkeypatch):
    monkeypatch.setattr(lac_client.requests, "get",
                        lambda url, timeout=None: FakeResponse(status_code=200, json_data=[]))

    with pytest.raises(lac_client.LacCallError, match="No open browser tab"):
        lac_client.load_cookies_from_cdp(port=9222)


def test_load_cookies_from_cdp_raises_auth_error_when_no_cookies_yet(monkeypatch):
    targets = [{"type": "page", "webSocketDebuggerUrl": "ws://localhost:9222/devtools/page/ABC"}]
    monkeypatch.setattr(lac_client.requests, "get",
                        lambda url, timeout=None: FakeResponse(status_code=200, json_data=targets))
    _install_fake_websocket_module(monkeypatch, {"result": {"cookies": []}})

    with pytest.raises(lac_client.LacSearchAuthError, match="search LAC"):
        lac_client.load_cookies_from_cdp(port=9222)


# ==========================================
# BROWSER-REFRESH HELPER
# ==========================================
def test_open_search_browser_for_refresh_opens_advanced_search_by_default(monkeypatch):
    captured = {}
    monkeypatch.setattr(lac_client.webbrowser, "open", lambda url: captured.setdefault("url", url))

    lac_client.open_search_browser_for_refresh()
    assert captured["url"] == "https://recherche-collection-search.bac-lac.gc.ca/eng/Home/SearchAdvanced"


def test_open_search_browser_for_refresh_opens_query_when_given(monkeypatch):
    captured = {}
    monkeypatch.setattr(lac_client.webbrowser, "open", lambda url: captured.setdefault("url", url))

    lac_client.open_search_browser_for_refresh("claim: 3126 Scrip: 12751")
    assert "q_1=claim" in captured["url"]
