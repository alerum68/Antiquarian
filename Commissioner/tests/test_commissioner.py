"""
Tests for Commissioner.py's orchestration - lac_client is mocked throughout (no live
network), matching the fake-response pattern used in test_lac_client.py.
"""

import json

import pytest

import Commissioner as commissioner
import lac_client


class FakeAsset:
    def __init__(self, asset_id, label, op):
        self.asset_id = asset_id
        self.label = label
        self.op = op


class FakeMetadata:
    def __init__(self, pid, title, reel_numbers=None, series_code=None):
        self.pid = pid
        self.title = title
        self.reel_numbers = reel_numbers or []
        self.series_code = series_code


# ==========================================
# resolve_pid_from_filename
# ==========================================
def test_resolve_pid_from_filename_matches_pid_convention():
    assert commissioner.resolve_pid_from_filename("BAC-LAC_fonandcol_1502188.pdf") == "1502188"


def test_resolve_pid_from_filename_returns_none_for_e_number_convention():
    assert commissioner.resolve_pid_from_filename("e011349655.pdf") is None


def test_resolve_pid_from_filename_returns_none_for_empty():
    assert commissioner.resolve_pid_from_filename("") is None
    assert commissioner.resolve_pid_from_filename(None) is None


# ==========================================
# build_claim_search_query
# ==========================================
def test_build_claim_search_query_prefers_claim_and_scrip():
    record = {"claim_number": "3126", "affidavit_number": "5473", "scrip_number": "12751"}
    assert commissioner.build_claim_search_query(record) == "claim: 3126 Scrip: 12751"


def test_build_claim_search_query_falls_back_to_affidavit_number():
    record = {"affidavit_number": "5473", "scrip_number": "12751"}
    assert commissioner.build_claim_search_query(record) == "claim: 5473 Scrip: 12751"


def test_build_claim_search_query_claim_only():
    record = {"claim_number": "3126"}
    assert commissioner.build_claim_search_query(record) == "claim: 3126"


def test_build_claim_search_query_scrip_only():
    record = {"scrip_number": "12751"}
    assert commissioner.build_claim_search_query(record) == "Scrip: 12751"


def test_build_claim_search_query_falls_back_to_e_number_in_filename():
    record = {"document_metadata": {"file_name": "e011349655.pdf"}}
    assert commissioner.build_claim_search_query(record) == "e011349655"


def test_build_claim_search_query_returns_none_when_nothing_available():
    record = {"document_metadata": {"file_name": "some_scan.pdf"}}
    assert commissioner.build_claim_search_query(record) is None


# ==========================================
# expand_scrip_number_range / build_claim_search_queries
# ==========================================
def test_expand_scrip_number_range_expands_a_real_range():
    assert commissioner.expand_scrip_number_range("2234 to 2241") == \
        ["2234", "2235", "2236", "2237", "2238", "2239", "2240", "2241"]


def test_expand_scrip_number_range_handles_dash_and_en_dash():
    assert commissioner.expand_scrip_number_range("100-103") == ["100", "101", "102", "103"]
    assert commissioner.expand_scrip_number_range("100–103") == ["100", "101", "102", "103"]


def test_expand_scrip_number_range_passes_through_a_single_number():
    assert commissioner.expand_scrip_number_range("12751") == ["12751"]


def test_expand_scrip_number_range_leaves_implausible_spans_unexpanded():
    """An inverted or wildly large "range" is more likely a misread than a genuine
    multi-certificate award - don't generate hundreds of speculative searches."""
    assert commissioner.expand_scrip_number_range("9999 to 100") == ["9999 to 100"]
    assert commissioner.expand_scrip_number_range("100 to 99999") == ["100 to 99999"]


def test_expand_scrip_number_range_empty_input():
    assert commissioner.expand_scrip_number_range(None) == []
    assert commissioner.expand_scrip_number_range("") == []


def test_build_claim_search_queries_one_query_per_number_in_range():
    record = {"claim_number": "297", "scrip_number": "2234 to 2236"}
    queries = commissioner.build_claim_search_queries(record)
    assert queries == ["claim: 297 Scrip: 2234", "claim: 297 Scrip: 2235", "claim: 297 Scrip: 2236"]


def test_build_claim_search_queries_single_query_for_a_plain_number():
    record = {"claim_number": "297", "scrip_number": "12751"}
    assert commissioner.build_claim_search_queries(record) == ["claim: 297 Scrip: 12751"]


def test_build_claim_search_query_returns_first_of_multiple_queries():
    """The backward-compatible singular form still returns just one query - the first."""
    record = {"claim_number": "297", "scrip_number": "2234 to 2236"}
    assert commissioner.build_claim_search_query(record) == "claim: 297 Scrip: 2234"


# ==========================================
# download_pid_bundle
# ==========================================
def test_download_pid_bundle_downloads_each_asset(tmp_path, monkeypatch):
    monkeypatch.setattr(lac_client, "get_record_metadata",
                        lambda pid: FakeMetadata(pid, "Scrip affidavit for Letendre, Roger"))
    monkeypatch.setattr(lac_client, "get_manifest",
                        lambda pid: [FakeAsset("e011355547", "Page 1", "img"),
                                     FakeAsset("e011355548", "Combined PDF", "pdf")])
    written = {}

    def fake_download_asset(asset_id, op):
        written[asset_id] = op
        return b"fake bytes for " + asset_id.encode()
    monkeypatch.setattr(lac_client, "download_asset", fake_download_asset)

    bundle = commissioner.download_pid_bundle("1502188", str(tmp_path))

    assert bundle["pid"] == "1502188"
    assert bundle["lac_catalog_title"] == "Scrip affidavit for Letendre, Roger"
    assert len(bundle["source_documents"]) == 2
    assert bundle["source_documents"][0]["document_type"] == "Page 1"
    assert bundle["source_documents"][0]["lac_asset_id"] == "e011355547"
    assert bundle["source_documents"][0]["source"] == "LAC"

    img_path = tmp_path / "1502188" / "e011355547.jpg"
    pdf_path = tmp_path / "1502188" / "e011355548.pdf"
    assert img_path.read_bytes() == b"fake bytes for e011355547"
    assert pdf_path.read_bytes() == b"fake bytes for e011355548"


def test_download_pid_bundle_skips_already_downloaded_files(tmp_path, monkeypatch):
    monkeypatch.setattr(lac_client, "get_record_metadata", lambda pid: FakeMetadata(pid, "title"))
    monkeypatch.setattr(lac_client, "get_manifest", lambda pid: [FakeAsset("e011355547", "Page 1", "img")])

    calls = []
    monkeypatch.setattr(lac_client, "download_asset", lambda asset_id, op: calls.append(asset_id) or b"data")

    pid_dir = tmp_path / "1502188"
    pid_dir.mkdir()
    (pid_dir / "e011355547.jpg").write_bytes(b"already here")

    commissioner.download_pid_bundle("1502188", str(tmp_path))
    assert calls == []  # never re-downloaded


def test_download_pid_bundle_applies_document_type_override(tmp_path, monkeypatch):
    monkeypatch.setattr(lac_client, "get_record_metadata", lambda pid: FakeMetadata(pid, "title"))
    monkeypatch.setattr(lac_client, "get_manifest", lambda pid: [FakeAsset("e011355547", "Page 1", "img")])
    monkeypatch.setattr(lac_client, "download_asset", lambda asset_id, op: b"data")

    bundle = commissioner.download_pid_bundle("1502188", str(tmp_path), document_type_override="Scrip Certificate")
    assert bundle["source_documents"][0]["document_type"] == "Scrip Certificate"


# ==========================================
# cross_check_claim_record
# ==========================================
def test_cross_check_claim_record_happy_path(tmp_path, monkeypatch):
    record = {
        "document_metadata": {"file_name": "BAC-LAC_fonandcol_1502188.pdf"},
        "claim_number": "3126", "scrip_number": "12751",
        "document_type": "Claimant's Own Affidavit",
    }

    monkeypatch.setattr(lac_client, "get_record_metadata",
                        lambda pid: FakeMetadata(pid, f"title for {pid}"))
    monkeypatch.setattr(lac_client, "get_manifest",
                        lambda pid: [FakeAsset(f"e0{pid}", "Certificate Page", "pdf")])
    monkeypatch.setattr(lac_client, "download_asset", lambda asset_id, op: b"data")
    monkeypatch.setattr(lac_client, "search", lambda query, cookies: ["1502188", "1502999"])

    result = commissioner.cross_check_claim_record(record, cookies={"cf_clearance": "abc"}, media_dir=str(tmp_path))

    assert result["lac_pid"] == "1502188"
    assert result["lac_catalog_title"] == "title for 1502188"
    # own PID excluded from related docs, only the genuinely related one attached
    assert len(result["source_documents"]) == 1
    assert result["source_documents"][0]["lac_pid"] == "1502999"
    assert "review_reason" not in result


def test_cross_check_claim_record_writes_reel_numbers_and_series_code_into_type_specific_fields(
        tmp_path, monkeypatch):
    """reel_numbers/series_code are LAC catalog metadata (Commissioner fetches them via
    get_record_metadata) that no claimant affidavit ever states on the page itself - only
    Commissioner can attach them. Archivist reads type_specific_fields.reel_numbers for a
    citation's Microfilm field, and rg_series_code as a more authoritative signal than
    free-text commission_reference for picking the right RootsMagic source template."""
    record = {
        "document_metadata": {"file_name": "BAC-LAC_fonandcol_1502188.pdf"},
        "claim_number": "3126", "scrip_number": "12751",
    }
    monkeypatch.setattr(lac_client, "get_record_metadata",
                        lambda pid: FakeMetadata(pid, f"title for {pid}",
                                                 reel_numbers=["C-14929", "C-14930"],
                                                 series_code="RG15-D-II-8-a"))
    monkeypatch.setattr(lac_client, "get_manifest", lambda pid: [])
    monkeypatch.setattr(lac_client, "download_asset", lambda asset_id, op: b"data")
    monkeypatch.setattr(lac_client, "search", lambda query, cookies: [])

    result = commissioner.cross_check_claim_record(record, cookies={}, media_dir=str(tmp_path))

    assert result["type_specific_fields"]["reel_numbers"] == "C-14929, C-14930"
    assert result["type_specific_fields"]["rg_series_code"] == "RG15-D-II-8-a"


def test_cross_check_claim_record_searches_every_number_in_a_scrip_range(tmp_path, monkeypatch):
    """A range like "2234 to 2241" must generate a search per number, and results from
    every one of those searches get merged into a single deduped related-PID set."""
    record = {
        "document_metadata": {"file_name": "BAC-LAC_fonandcol_1502188.pdf"},
        "claim_number": "297", "scrip_number": "2234 to 2236",
    }
    monkeypatch.setattr(lac_client, "get_record_metadata",
                        lambda pid: FakeMetadata(pid, f"title for {pid}"))
    monkeypatch.setattr(lac_client, "get_manifest",
                        lambda pid: [FakeAsset(f"e0{pid}", "Certificate Page", "pdf")])
    monkeypatch.setattr(lac_client, "download_asset", lambda asset_id, op: b"data")

    seen_queries = []

    def fake_search(query, cookies):
        seen_queries.append(query)
        # Different scrip numbers in the range surface different certificate PIDs.
        return {"claim: 297 Scrip: 2234": ["1502188", "1503000"],
               "claim: 297 Scrip: 2235": ["1502188", "1503001"],
               "claim: 297 Scrip: 2236": ["1502188"]}.get(query, [])
    monkeypatch.setattr(lac_client, "search", fake_search)

    result = commissioner.cross_check_claim_record(record, cookies={"cf_clearance": "abc"}, media_dir=str(tmp_path))

    assert seen_queries == ["claim: 297 Scrip: 2234", "claim: 297 Scrip: 2235", "claim: 297 Scrip: 2236"]
    related_pids = sorted(d["lac_pid"] for d in result["source_documents"])
    assert related_pids == ["1503000", "1503001"]  # own PID (1502188) excluded, deduped across queries


def test_cross_check_claim_record_stops_on_auth_error_but_keeps_earlier_results(tmp_path, monkeypatch):
    """If the cookie expires partway through a range of searches, stop immediately
    (every remaining query would fail identically) but keep whatever was already found."""
    record = {"claim_number": "297", "scrip_number": "2234 to 2236"}
    monkeypatch.setattr(lac_client, "get_record_metadata", lambda pid: FakeMetadata(pid, "title"))
    monkeypatch.setattr(lac_client, "get_manifest", lambda pid: [FakeAsset(f"e0{pid}", "Page", "img")])
    monkeypatch.setattr(lac_client, "download_asset", lambda asset_id, op: b"data")

    def fake_search(query, cookies):
        if query.endswith("2234"):
            return ["1503000"]
        raise lac_client.LacSearchAuthError("cookie expired")
    monkeypatch.setattr(lac_client, "search", fake_search)

    result = commissioner.cross_check_claim_record(record, cookies={}, media_dir=str(tmp_path))
    assert any(d["lac_pid"] == "1503000" for d in result["source_documents"])
    assert any("cookie expired" in r for r in result["review_reason"])


def test_cross_check_claim_record_flags_when_no_query_buildable(tmp_path, monkeypatch):
    record = {"document_metadata": {"file_name": "some_scan.pdf"}}
    result = commissioner.cross_check_claim_record(record, cookies={}, media_dir=str(tmp_path))
    assert any("no claim_number" in r for r in result["review_reason"])
    assert "source_documents" not in result


def test_cross_check_claim_record_flags_on_search_auth_error(tmp_path, monkeypatch):
    record = {"claim_number": "3126", "scrip_number": "12751"}

    def raise_auth_error(query, cookies):
        raise lac_client.LacSearchAuthError("cookie expired")
    monkeypatch.setattr(lac_client, "search", raise_auth_error)

    result = commissioner.cross_check_claim_record(record, cookies={}, media_dir=str(tmp_path))
    assert any("cookie expired" in r for r in result["review_reason"])


def test_cross_check_claim_record_continues_past_one_failed_related_pid(tmp_path, monkeypatch):
    record = {"claim_number": "3126", "scrip_number": "12751"}
    monkeypatch.setattr(lac_client, "search", lambda query, cookies: ["1502999", "1503000"])

    def fake_get_record_metadata(pid):
        if pid == "1502999":
            raise lac_client.LacCallError("boom")
        return FakeMetadata(pid, "title")
    monkeypatch.setattr(lac_client, "get_record_metadata", fake_get_record_metadata)
    monkeypatch.setattr(lac_client, "get_manifest", lambda pid: [FakeAsset(f"e0{pid}", "Page", "img")])
    monkeypatch.setattr(lac_client, "download_asset", lambda asset_id, op: b"data")

    result = commissioner.cross_check_claim_record(record, cookies={}, media_dir=str(tmp_path))
    assert len(result["source_documents"]) == 1
    assert result["source_documents"][0]["lac_pid"] == "1503000"
    assert any("1502999" in r for r in result["review_reason"])


# ==========================================
# load_cookies (CDP-first, file fallback)
# ==========================================
def test_load_cookies_prefers_cdp_when_reachable(monkeypatch, tmp_path):
    monkeypatch.setattr(lac_client, "load_cookies_from_cdp",
                        lambda port=9222: {"cf_clearance": "from_cdp"})
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text("cf_clearance=from_file", encoding="utf-8")

    cookies = commissioner.load_cookies(str(cookie_file))
    assert cookies == {"cf_clearance": "from_cdp"}


def test_load_cookies_falls_back_to_file_when_cdp_unreachable(monkeypatch, tmp_path):
    def raise_call_error(port=9222):
        raise lac_client.LacCallError("no debuggable browser")
    monkeypatch.setattr(lac_client, "load_cookies_from_cdp", raise_call_error)

    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text("cf_clearance=from_file", encoding="utf-8")

    cookies = commissioner.load_cookies(str(cookie_file))
    assert cookies == {"cf_clearance": "from_file"}


def test_load_cookies_raises_when_both_cdp_and_file_fail(monkeypatch, tmp_path):
    monkeypatch.setattr(lac_client, "load_cookies_from_cdp",
                        lambda port=9222: (_ for _ in ()).throw(lac_client.LacCallError("no browser")))
    missing_file = tmp_path / "does_not_exist.txt"

    with pytest.raises(FileNotFoundError):
        commissioner.load_cookies(str(missing_file))


# ==========================================
# CHECKPOINTING
# ==========================================
def test_load_checkpoint_returns_default_when_missing(tmp_path):
    checkpoint_path = str(tmp_path / "checkpoint.json")
    data = commissioner.load_checkpoint(checkpoint_path)
    assert data == {"pids": [], "downloaded_pids": [], "failed_pids": {}}


def test_save_and_load_checkpoint_roundtrip(tmp_path):
    checkpoint_path = str(tmp_path / "sub" / "checkpoint.json")
    commissioner.save_checkpoint(checkpoint_path, {"pids": ["1", "2"]})
    assert commissioner.load_checkpoint(checkpoint_path) == {"pids": ["1", "2"]}


# ==========================================
# VOLUME RETRIEVAL
# ==========================================
def test_retrieve_volume_pids_calls_search_volume_once(tmp_path, monkeypatch):
    checkpoint_path = str(tmp_path / "checkpoint.json")
    calls = []

    def fake_search_volume(vol, cookies, archival_number="RG15"):
        calls.append(vol)
        return ["1319001", "1319002"]
    monkeypatch.setattr(lac_client, "search_volume", fake_search_volume)

    pids = commissioner.retrieve_volume_pids("1319", cookies={"cf_clearance": "abc"}, checkpoint_path=checkpoint_path)
    assert pids == ["1319001", "1319002"]
    assert calls == ["1319"]

    # second call should be a no-op against lac_client - already checkpointed
    pids_again = commissioner.retrieve_volume_pids("1319", cookies={"cf_clearance": "abc"}, checkpoint_path=checkpoint_path)
    assert pids_again == ["1319001", "1319002"]
    assert calls == ["1319"]  # not called again


def test_download_volume_assets_is_resumable_and_skips_completed(tmp_path, monkeypatch):
    checkpoint_path = str(tmp_path / "checkpoint.json")
    media_dir = str(tmp_path / "media")
    commissioner.save_checkpoint(checkpoint_path, {"pids": ["1", "2"], "downloaded_pids": ["1"], "failed_pids": {}})

    calls = []

    def fake_download_pid_bundle(pid, media_dir_arg, document_type_override=None):
        calls.append(pid)
        return {"pid": pid, "lac_catalog_title": "t", "source_documents": []}
    monkeypatch.setattr(commissioner, "download_pid_bundle", fake_download_pid_bundle)

    result = commissioner.download_volume_assets(["1", "2"], media_dir, checkpoint_path)
    assert calls == ["2"]  # "1" already downloaded, skipped
    assert result["downloaded_pids"] == ["1", "2"]


def test_download_volume_assets_records_failure_and_continues(tmp_path, monkeypatch):
    checkpoint_path = str(tmp_path / "checkpoint.json")
    media_dir = str(tmp_path / "media")

    def fake_download_pid_bundle(pid, media_dir_arg, document_type_override=None):
        if pid == "2":
            raise lac_client.LacCallError("network blip")
        return {"pid": pid, "lac_catalog_title": "t", "source_documents": []}
    monkeypatch.setattr(commissioner, "download_pid_bundle", fake_download_pid_bundle)

    result = commissioner.download_volume_assets(["1", "2", "3"], media_dir, checkpoint_path)
    assert result["downloaded_pids"] == ["1", "3"]
    assert "network blip" in result["failed_pids"]["2"]


def test_retrieve_volume_runs_both_passes(tmp_path, monkeypatch):
    checkpoint_path = str(tmp_path / "checkpoint.json")
    media_dir = str(tmp_path / "media")

    monkeypatch.setattr(lac_client, "search_volume", lambda vol, cookies, archival_number="RG15": ["1", "2"])
    monkeypatch.setattr(commissioner, "download_pid_bundle",
                        lambda pid, media_dir_arg, document_type_override=None: {"pid": pid, "lac_catalog_title": "t", "source_documents": []})

    result = commissioner.retrieve_volume("1319", cookies={"cf_clearance": "abc"}, media_dir=media_dir,
                                          checkpoint_path=checkpoint_path)
    assert result["pids"] == ["1", "2"]
    assert result["downloaded_pids"] == ["1", "2"]
