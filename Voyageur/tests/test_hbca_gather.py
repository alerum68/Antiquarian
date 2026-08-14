import importlib.util
import threading as _threading
import time as _time
from pathlib import Path

_hbca_path = Path(__file__).resolve().parents[1] / "HBCA.py"
_spec = importlib.util.spec_from_file_location("voyageur_hbca", _hbca_path)
_hbca_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_hbca_mod)


BioSheetEntry = _hbca_mod.BioSheetEntry
build_hbca_scaffold_sheet = _hbca_mod.build_hbca_scaffold_sheet
filter_entries_by_letter = _hbca_mod.filter_entries_by_letter
load_checkpoint = _hbca_mod.load_checkpoint
parse_biographical_index_html = _hbca_mod.parse_biographical_index_html
save_checkpoint = _hbca_mod.save_checkpoint
download_keystone_media = _hbca_mod.download_keystone_media
gather_hbca_sheets = _hbca_mod.gather_hbca_sheets


SAMPLE_INDEX_HTML = """
<!DOCTYPE html>
<html>
<body>
  <div class="content">
    <ul>
      <li><a href="../../_assets/docs/hbca/biographical/a/adams_george.pdf">Adams, George (b. ca. 1796-d. 1864) (fl. 1821-1854)</a></li>  # noqa: E501
      <li><a href="../../_assets/docs/hbca/biographical/a/adams_joseph.pdf">Adams, Joseph (fl. 1730-1737)</a></li>
      <li><a href="../../_assets/docs/hbca/biographical/b/ballenden_john.pdf">Ballenden, John (1810-1856) (fl. 1829-1856)</a></li>  # noqa: E501
      <li><a href="../../_assets/docs/hbca/biographical/c/connolly_william.pdf">Connolly, William (1786-1849) (fl. 1801-1831)</a></li>  # noqa: E501
    </ul>
  </div>
</body>
</html>
"""


def test_parse_biographical_index_html():
    entries = parse_biographical_index_html(
        SAMPLE_INDEX_HTML,
        base_url="https://www.gov.mb.ca/chc/archives/hbca/biographical/index.html",
    )
    assert len(entries) == 4

    first = entries[0]
    assert first.employee_name == "Adams, George (b. ca. 1796-d. 1864) (fl. 1821-1854)"
    assert first.file_name == "adams_george.pdf"
    assert first.letter == "a"
    assert (
        first.pdf_url
        == "https://www.gov.mb.ca/chc/archives/_assets/docs/hbca/biographical/a/adams_george.pdf"
    )

    ballenden = entries[2]
    assert ballenden.file_name == "ballenden_john.pdf"
    assert ballenden.letter == "b"


def test_filter_entries_by_letter():
    entries = parse_biographical_index_html(
        SAMPLE_INDEX_HTML,
        base_url="https://www.gov.mb.ca/chc/archives/hbca/biographical/index.html",
    )

    filtered_a = filter_entries_by_letter(entries, letters=["A"])
    assert len(filtered_a) == 2
    assert all(e.letter == "a" for e in filtered_a)

    filtered_ab = filter_entries_by_letter(entries, letters=["A", "B"])
    assert len(filtered_ab) == 3

    filtered_z = filter_entries_by_letter(entries, letters=["Z"])
    assert len(filtered_z) == 0


def test_build_hbca_scaffold_sheet():
    entry = BioSheetEntry(
        employee_name="Adams, George",
        file_name="adams_george.pdf",
        letter="a",
        pdf_url="https://www.gov.mb.ca/chc/archives/_assets/docs/hbca/biographical/a/adams_george.pdf",
    )
    raw_text = "NAME: ADAMS, George\nDATES: b. ca. 1796 d. 1864\nAppointments & Service: 1821-1854"
    sheet = build_hbca_scaffold_sheet(entry, raw_text=raw_text)

    assert sheet["page_id"] == "adams_george.pdf"
    assert sheet["document_metadata"]["file_name"] == "adams_george.pdf"
    assert sheet["document_metadata"]["file_type"] == "pdf"
    assert (
        sheet["document_metadata"]["source_name"]
        == "Hudson's Bay Company Archives: Biographical Sheets"
    )
    assert (
        sheet["document_metadata"]["source_location"]
        == "Archives of Manitoba, Winnipeg, Manitoba, Canada"
    )
    # document_metadata is Commissioner-shaped (build_empty_sheet's real fields only) -
    # no document_type, no raw_text (write-only, nothing downstream ever reads it back -
    # it's recomputed transiently from the PDF each run), no pdf_url (redundant, already
    # in records[0].citation_text), no employee_name (moved to type_specific_fields).
    assert "document_type" not in sheet["document_metadata"]
    assert "raw_text" not in sheet["document_metadata"]
    assert "pdf_url" not in sheet["document_metadata"]
    assert "employee_name" not in sheet["document_metadata"]

    record = sheet["records"][0]
    assert record["citation_text"] == entry.pdf_url
    assert record["type_specific_fields"]["employee_name"] == "Adams, George"
    assert len(sheet["records"]) == 1
    assert sheet["records"][0]["participants"] == []


def test_build_hbca_scaffold_sheet_does_not_duplicate_keystone_urls():
    entry = BioSheetEntry(
        employee_name="Adams, George",
        file_name="adams_george.pdf",
        letter="a",
        pdf_url="https://example.com/adams_george.pdf",
    )
    sheet = build_hbca_scaffold_sheet(entry, keystone_urls=["https://keystone.example/rec1"])

    assert "keystone_urls" not in sheet["document_metadata"]
    assert sheet["records"][0]["type_specific_fields"]["keystone_urls"] == ["https://keystone.example/rec1"]


def test_hbca_image_dir_reads_from_env(monkeypatch):
    """HBCA_IMAGE_DIR was a hardcoded literal, never actually read from the environment,
    despite being exposed as a configurable setting in settings_schema.yaml - the GUI
    control had no effect. Reloading the module fresh with the env var set is required
    since HBCA_IMAGE_DIR is resolved once at import time, same as the file's other
    module-level settings constants."""
    monkeypatch.setenv("HBCA_IMAGE_DIR", "CustomHBCAFolder")
    spec = importlib.util.spec_from_file_location("voyageur_hbca_reload", _hbca_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.HBCA_IMAGE_DIR == "CustomHBCAFolder"


def test_checkpoint_roundtrip(tmp_path):
    cp_file = tmp_path / "hbca_checkpoint.json"
    downloaded = {"adams_george.pdf", "ballenden_john.pdf"}

    save_checkpoint(cp_file, downloaded_files=downloaded)
    assert cp_file.exists()

    loaded = load_checkpoint(cp_file)
    assert loaded == downloaded


class _FakeKeystoneResponse:
    def __init__(self, status_code, content=b""):
        self.status_code = status_code
        self.content = content


class _FakeKeystoneSession:
    def __init__(self, responses):
        self._responses = responses

    def get(self, url, headers=None, timeout=None):
        _ = (headers, timeout)
        return self._responses[url]


def test_download_keystone_media_reports_non_200_response(tmp_path, capsys):
    session = _FakeKeystoneSession({"https://example.com/missing.jpg": _FakeKeystoneResponse(404)})

    result = download_keystone_media(["https://example.com/missing.jpg"], tmp_path, session=session)

    assert result == []
    assert not (tmp_path / "missing.jpg").exists()
    out = capsys.readouterr().out
    assert "WARN" in out
    assert "404" in out


def test_download_keystone_media_downloads_successful_url(tmp_path):
    session = _FakeKeystoneSession({"https://example.com/page.jpg": _FakeKeystoneResponse(200, b"image-bytes")})

    result = download_keystone_media(["https://example.com/page.jpg"], tmp_path, session=session)

    assert result == [str(tmp_path / "page.jpg")]
    assert (tmp_path / "page.jpg").read_bytes() == b"image-bytes"


def test_download_keystone_media_leaves_no_truncated_file_on_write_failure(tmp_path, monkeypatch):
    session = _FakeKeystoneSession({"https://example.com/page.jpg": _FakeKeystoneResponse(200, b"image-bytes")})

    def fail_replace(_self, _target):
        raise OSError("disk full")

    monkeypatch.setattr(_hbca_mod.Path, "replace", fail_replace)

    result = download_keystone_media(["https://example.com/page.jpg"], tmp_path, session=session)

    assert result == []
    assert not (tmp_path / "page.jpg").exists()


def test_gather_hbca_sheets_one_entry_failure_does_not_crash_the_batch(tmp_path, monkeypatch):
    """Regression test: process_entry ran inside a ThreadPoolExecutor with no try/except
    around its own download call, so one entry's network exception used to propagate out
    of future.result() and crash the entire multi-threaded gather."""
    index_html = (
        '<html><body>'
        '<a href="a/good.pdf">Good, Person</a>'
        '<a href="a/bad.pdf">Bad, Person</a>'
        '</body></html>'
    )

    class FakeIndexResponse:
        text = index_html
        status_code = 200

        def raise_for_status(self):
            pass

    def fake_get(url, headers=None, timeout=None):
        _ = (url, headers, timeout)
        return FakeIndexResponse()

    monkeypatch.setattr(_hbca_mod.requests, "get", fake_get)

    class FakeEntrySession:
        def get(self, url, headers=None, timeout=None):
            _ = (headers, timeout)
            if "bad" in url:
                raise ConnectionError("network down")
            return _FakeKeystoneResponse(200, b"pdf-bytes")

    monkeypatch.setattr(_hbca_mod.requests, "Session", lambda: FakeEntrySession())
    monkeypatch.setattr(_hbca_mod, "extract_text_from_pdf", lambda path: "")

    new_downloads = gather_hbca_sheets(
        index_url="https://fake.url/",
        image_dir=tmp_path / "images",
        master_db_path=tmp_path / "MasterDB_HBCA.json",
        checkpoint_dir=tmp_path / "checkpoint",
        media_dir=tmp_path / "media",
        resolve_keystone=False,
        download_keystone=False,
        max_workers=1,
    )

    assert new_downloads == 1
    assert (tmp_path / "images" / "Bios" / "a" / "good.pdf").exists()
    assert not (tmp_path / "images" / "Bios" / "a" / "bad.pdf").exists()


def test_gather_hbca_sheets_serializes_keystone_media_downloads_across_threads(tmp_path, monkeypatch):
    """Two entries whose Keystone resolution names an overlapping media_url must not race
    on the same destination file - download_keystone_media's existence-check-then-write
    was not synchronized, unlike the correctly-locked MASTER_DB/checkpoint path. Proven via
    a concurrency counter around the real download_keystone_media call: with two threads
    both wanting to download the same media_url, the max-concurrent count must stay at 1 -
    a real race (unsynchronized) would let both threads observe "not yet downloaded"
    simultaneously and let the counter hit 2, since each call sleeps briefly to force
    overlap if nothing is serializing them."""
    index_html = (
        '<html><body>'
        '<a href="a/one.pdf">One, Person</a>'
        '<a href="a/two.pdf">Two, Person</a>'
        '</body></html>'
    )

    class FakeIndexResponse:
        text = index_html
        status_code = 200

        def raise_for_status(self):
            pass

    monkeypatch.setattr(_hbca_mod.requests, "get", lambda *args, **kwargs: FakeIndexResponse())

    class FakeEntrySession:
        def get(self, url, headers=None, timeout=None):
            _ = (url, headers, timeout)
            return _FakeKeystoneResponse(200, b"pdf-bytes")

    monkeypatch.setattr(_hbca_mod.requests, "Session", lambda: FakeEntrySession())
    monkeypatch.setattr(_hbca_mod, "extract_text_from_pdf", lambda path: "location code text")
    monkeypatch.setattr(_hbca_mod, "extract_hbca_location_codes", lambda text: ["CODE1"])

    def fake_query_keystone_for_code(_code, session=None):
        _ = session
        return {"record_urls": [], "media_urls": ["https://keystone.example/shared.jpg"]}

    monkeypatch.setattr(_hbca_mod, "query_keystone_for_code", fake_query_keystone_for_code)

    concurrent = {"active": 0, "max_seen": 0}
    counter_lock = _threading.Lock()
    real_download_keystone_media = _hbca_mod.download_keystone_media

    def tracking_download_keystone_media(media_urls, target_dir, session=None):
        with counter_lock:
            concurrent["active"] += 1
            concurrent["max_seen"] = max(concurrent["max_seen"], concurrent["active"])
        try:
            _time.sleep(0.05)  # widen the window a real race would need to manifest in
            return real_download_keystone_media(media_urls, target_dir, session=session)
        finally:
            with counter_lock:
                concurrent["active"] -= 1

    monkeypatch.setattr(_hbca_mod, "download_keystone_media", tracking_download_keystone_media)

    gather_hbca_sheets(
        index_url="https://fake.url/",
        image_dir=tmp_path / "images",
        master_db_path=tmp_path / "MasterDB_HBCA.json",
        checkpoint_dir=tmp_path / "checkpoint",
        media_dir=tmp_path / "media",
        resolve_keystone=True,
        download_keystone=True,
        max_workers=2,
    )

    assert concurrent["max_seen"] == 1


def test_gather_hbca_sheets_one_entry_write_failure_does_not_crash_the_batch(tmp_path, monkeypatch):
    """Regression test: the first fix round only wrapped the network GET in try/except,
    leaving the atomic_write_bytes() call right below it unguarded - a write-side failure
    (e.g. disk full) still propagated through future.result() and crashed the whole batch,
    exactly the failure mode the GET-side fix claimed to have eliminated. Caught by
    /code-review before this landed."""
    index_html = (
        '<html><body>'
        '<a href="a/good.pdf">Good, Person</a>'
        '<a href="a/bad.pdf">Bad, Person</a>'
        '</body></html>'
    )

    class FakeIndexResponse:
        text = index_html
        status_code = 200

        def raise_for_status(self):
            pass

    def fake_get(url, headers=None, timeout=None):
        _ = (url, headers, timeout)
        return FakeIndexResponse()

    monkeypatch.setattr(_hbca_mod.requests, "get", fake_get)

    class FakeEntrySession:
        def get(self, url, headers=None, timeout=None):
            _ = (url, headers, timeout)
            return _FakeKeystoneResponse(200, b"pdf-bytes")

    monkeypatch.setattr(_hbca_mod.requests, "Session", lambda: FakeEntrySession())
    monkeypatch.setattr(_hbca_mod, "extract_text_from_pdf", lambda path: "")

    real_replace = _hbca_mod.Path.replace

    def fail_replace_for_bad(self, target):
        if "bad" in self.name:
            raise OSError("disk full")
        return real_replace(self, target)

    monkeypatch.setattr(_hbca_mod.Path, "replace", fail_replace_for_bad)

    new_downloads = gather_hbca_sheets(
        index_url="https://fake.url/",
        image_dir=tmp_path / "images",
        master_db_path=tmp_path / "MasterDB_HBCA.json",
        checkpoint_dir=tmp_path / "checkpoint",
        media_dir=tmp_path / "media",
        resolve_keystone=False,
        download_keystone=False,
        max_workers=1,
    )

    assert new_downloads == 1
    assert (tmp_path / "images" / "Bios" / "a" / "good.pdf").exists()
    assert not (tmp_path / "images" / "Bios" / "a" / "bad.pdf").exists()


def test_parse_biographical_index_html_extracts_letter():
    mock_html = '<html><body><a href="a/zebra.pdf">Zebra</a><a href="b/x-weird_name.pdf">X-Weird</a></body></html>'
    entries = parse_biographical_index_html(mock_html, base_url="https://fake.url/")

    assert len(entries) == 2
    assert entries[0].letter == "a"
    assert entries[1].letter == "b"
