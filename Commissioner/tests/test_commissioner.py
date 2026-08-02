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


# ==========================================
# extract_citation_fields
# ==========================================
def test_extract_citation_fields_parses_all_scrip_fields():
    citation = "Scrip affidavit for Letendre, Roger; claim no. 5473; scrip no. 12751; allotment no. 142; date of issue: 5 May 1886; amount: 240 dollars"
    parsed = commissioner.extract_citation_fields(citation)
    assert parsed["claim_number"] == "5473"
    assert parsed["scrip_number"] == "12751"
    assert parsed["allotment_number"] == "142"
    assert parsed["issue_date"] == "5 May 1886"
    assert parsed["scrip_issue_date"] == "5 May 1886"
    assert parsed["scrip_amount"] == "240 dollars"


def test_extract_citation_fields_handles_empty():
    assert commissioner.extract_citation_fields("") == {}
    assert commissioner.extract_citation_fields(None) == {}


# ==========================================
# collection classification & partitioning
# ==========================================
def test_collection_for_series_code():
    res = commissioner.collection_for_series_code("RG15-D-II-8-a-i")
    assert res is not None
    assert res[0] == "RG15-D-II-8-a"
    assert res[1] == "Affidavits, 1870-1885"
    assert res[2] == "Finding Aid 15-19"
    assert res[3] == "confirmed"

    assert commissioner.collection_for_series_code("UNKNOWN-CODE") is None
    assert commissioner.collection_for_series_code(None) is None


def test_collection_for_volume():
    res_b = commissioner.collection_for_volume("1326", None)
    assert res_b[0] == "RG15-D-II-8-b"
    assert res_b[3] == "inferred"

    res_c = commissioner.collection_for_volume(None, "1331-1340")
    assert res_c[0] == "RG15-D-II-8-c"
    assert res_c[3] == "inferred"

    # Straddling range should return None
    assert commissioner.collection_for_volume(None, "1324-1335") is None


def test_classify_sheet_collection_prefers_series_code():
    sheet = {
        "records": [{"type_specific_fields": {"rg_series_code": "RG15-D-II-8-a"}}],
        "document_metadata": {"volume": "1335"},  # in series c volume range
    }
    code, title, fa, status = commissioner.classify_sheet_collection(sheet)
    assert code == "RG15-D-II-8-a"
    assert status == "confirmed"


def test_partition_json_by_collection(tmp_path):
    data = {
        "record_type_name": "Scrip",
        "sheets": [
            {
                "page_id": "p1",
                "records": [{"type_specific_fields": {"rg_series_code": "RG15-D-II-8-a"}}],
            },
            {
                "page_id": "p2",
                "document_metadata": {"volume": "1328"},
                "records": [{}],
            },
            {
                "page_id": "p3",
                "records": [{}],
            },
        ],
    }
    out_dir = tmp_path / "by_collection"
    partitions = commissioner.partition_json_by_collection(data, out_dir)

    assert "RG15-D-II-8-a" in partitions
    assert "RG15-D-II-8-b" in partitions
    assert "unclassified" in partitions

    with open(partitions["RG15-D-II-8-a"], encoding="utf-8") as f:
        p_a = json.load(f)
        assert p_a["collection_title"] == "Affidavits, 1870-1885"
        assert len(p_a["sheets"]) == 1

    with open(partitions["RG15-D-II-8-b"], encoding="utf-8") as f:
        p_b = json.load(f)
        assert p_b["collection_title"] == "Applications, 1885"
        assert len(p_b["sheets"]) == 1

    with open(partitions["unclassified"], encoding="utf-8") as f:
        p_u = json.load(f)
        assert len(p_u["sheets"]) == 1


# ==========================================
# Metadata Enrichment
# ==========================================
def test_enrich_record_from_lac_metadata():
    sheet = {"document_metadata": {}}
    record = {"type_specific_fields": {}}
    meta = FakeMetadata(
        "1502188",
        "Scrip affidavit for Letendre, Roger; claim no. 5473; date of issue: 5 May 1886",
        reel_numbers=["C-14929"],
        series_code="RG15-D-II-8-a",
    )

    commissioner.enrich_record_from_lac_metadata(sheet, record, meta)

    assert record["lac_catalog_title_live"] == meta.title
    assert sheet["document_metadata"]["reel_numbers"] == ["C-14929"]
    assert record["type_specific_fields"]["rg_series_code"] == "RG15-D-II-8-a"
    assert record["type_specific_fields"]["reel_numbers"] == "C-14929"
    assert record["type_specific_fields"]["claim_number"] == "5473"
    assert record["type_specific_fields"]["issue_date"] == "5 May 1886"


def test_enrich_json_data_with_checkpoint(tmp_path, monkeypatch):
    monkeypatch.setattr(lac_client, "get_record_metadata",
                        lambda pid: FakeMetadata(pid, f"Scrip affidavit; claim no. {pid}", reel_numbers=["C-1234"]))

    checkpoint_path = str(tmp_path / "enrich_checkpoint.json")
    data = {
        "record_type_name": "Scrip",
        "sheets": [
            {"document_metadata": {"pid": "101"}, "records": [{}]},
            {"document_metadata": {"pid": "102"}, "records": [{}]},
        ],
    }

    result = commissioner.enrich_json_data(data, checkpoint_path=checkpoint_path, delay_seconds=0.0)
    assert result["sheets"][0]["records"][0]["type_specific_fields"]["claim_number"] == "101"
    assert result["sheets"][1]["records"][0]["type_specific_fields"]["claim_number"] == "102"

    checkpoint = commissioner.load_checkpoint(checkpoint_path)
    assert checkpoint["done_pids"] == ["101", "102"]


# ==========================================
# Mojibake & Maiden Name Resolution
# ==========================================
def test_fix_mojibake():
    assert commissioner.fix_mojibake("Geneviã¨ve") == "Geneviève"
    assert commissioner.fix_mojibake("mÃ©tis") == "métis"
    assert commissioner.fix_mojibake("St. FranÃ§ois Xavier") == "St. François Xavier"
    assert commissioner.fix_mojibake("Normal Name") == "Normal Name"


def test_build_composite_record_number():
    tf = {"claim_number": "297", "allotment_number": "", "scrip_number": "2234 to 2241"}
    assert commissioner.build_composite_record_number(tf) == "297-0-2234 to 2241"

    tf2 = {"claim_number": "100", "allotment_number": "50", "scrip_number": "200"}
    assert commissioner.build_composite_record_number(tf2) == "100-50-200"

    assert commissioner.build_composite_record_number({}) == "0-0-0"


def test_resolve_maiden_name_for_record():
    record = {
        "lac_catalog_title": "scrip affidavit for sabiston, margaret; born: january 21, 1851; husband: john sabiston; father: john falster",
        "participants": [
            {
                "role_number": "1", "role_name": "Claimant", "role_semantic": "primary",
                "std_given": "Margaret", "std_surname": "Sabiston", "sex": "F",
            },
            {
                "role_number": "6", "role_name": "Father", "role_semantic": "father",
                "std_given": "John", "std_surname": "Falster", "sex": "M",
            },
            {
                "role_number": "2", "role_name": "Spouse", "role_semantic": "spouse",
                "std_given": "John", "std_surname": "Sabiston", "sex": "M",
            },
        ],
    }

    modified = commissioner.resolve_maiden_name_for_record(record)
    assert modified is True
    primary = record["participants"][0]
    assert primary["std_surname"] == "Falster"
    assert primary["alternate_names"] == [{"value": "Margaret Sabiston"}]


def test_resolve_maiden_name_via_enrichment():
    sheet = {"document_metadata": {}}
    record = {
        "type_specific_fields": {},
        "participants": [
            {
                "role_number": "1", "role_name": "Claimant", "role_semantic": "primary",
                "std_given": "Marie", "std_surname": "Grant", "sex": "F",
            },
            {
                "role_number": "6", "role_name": "Father", "role_semantic": "father",
                "std_given": "Pierre", "std_surname": "Bastien", "sex": "M",
            },
        ],
    }
    meta = FakeMetadata(
        "1500000",
        "Scrip affidavit for Grant, Marie; father: Pierre Bastien; claim no. 123",
    )

    commissioner.enrich_record_from_lac_metadata(sheet, record, meta)
    primary = record["participants"][0]
    assert primary["std_surname"] == "Bastien"
    assert primary["alternate_names"] == [{"value": "Marie Grant"}]
    assert record["record_number"] == "123-0-0"


def test_parse_single_name_compound():
    # Compound prefixes: St., De La, Le, Des
    g, s, d = commissioner.parse_single_name("Bonaventure St. Arnaud")
    assert g == "Bonaventure"
    assert s == "St. Arnaud"
    assert d == ""

    g, s, d = commissioner.parse_single_name("Pierre De La Ronde")
    assert g == "Pierre"
    assert s == "De La Ronde"
    assert d == ""

    g, s, d = commissioner.parse_single_name("Joseph Le Blanc")
    assert g == "Joseph"
    assert s == "Le Blanc"
    assert d == ""

    g, s, d = commissioner.parse_single_name("Marie Des Ruisseaux")
    assert g == "Marie"
    assert s == "Des Ruisseaux"
    assert d == ""

    # Dit name parsing
    g, s, d = commissioner.parse_single_name("Jean Baptiste Bruneau dit Charron")
    assert g == "Jean Baptiste"
    assert s == "Bruneau dit Charron"
    assert d == "Charron"


def test_fix_all_participant_names():
    record = {
        "participants": [
            {
                "role_number": "1", "role_name": "Claimant", "role_semantic": "primary",
                "std_given": "Jean Baptiste", "std_surname": "St. Arnaud", "sex": "",
            },
            {
                "role_number": "6", "role_name": "Father", "role_semantic": "father",
                "std_given": "Bonaventure St.", "std_surname": "Arnaud", "sex": "M",
            },
            {
                "role_number": "7", "role_name": "Mother", "role_semantic": "mother",
                "std_given": "Marie De La", "std_surname": "Ronde", "sex": "F",
            },
        ],
    }

    modified = commissioner.fix_all_participant_names_in_record(record)
    assert modified is True

    p_claimant = record["participants"][0]
    p_father = record["participants"][1]
    p_mother = record["participants"][2]

    assert p_claimant["std_given"] == "Jean Baptiste"
    assert p_claimant["std_surname"] == "St. Arnaud"

    assert p_father["std_given"] == "Bonaventure"
    assert p_father["std_surname"] == "St. Arnaud"

    assert p_mother["std_given"] == "Marie"
    assert p_mother["std_surname"] == "De La Ronde"



