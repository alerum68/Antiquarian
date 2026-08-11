import importlib.util
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

_hbca_path = Path(__file__).resolve().parents[1] / "HBCA.py"
_spec = importlib.util.spec_from_file_location("voyageur_hbca", _hbca_path)
_hbca_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_hbca_mod)

build_keystone_search_url = _hbca_mod.build_keystone_search_url
extract_hbca_location_codes = _hbca_mod.extract_hbca_location_codes
parse_keystone_search_response = _hbca_mod.parse_keystone_search_response


SAMPLE_BIO_TEXT = """
NAME: ADAMS, George
ENTERED SERVICE: 1821
DATES: b. ca. 1796, d. 1864

Appointments & Service:
Outfit Year*     Position        Post             District       HBCA Reference
1821-1825        Laborer         York Factory     York           B.239/g/1-4
1825-1830        Steersman       Moose Factory    Moose          B.135/g/1-5; A.32/21
1830-1835        Retired         Red River                       E.4/1a fo. 45

Search File: 'ADAMS, GEORGE'
"""

SAMPLE_KEYSTONE_HTML = """
<!DOCTYPE html>
<html>
<body>
  <div class="record">
    <h3>Post Journal B.239/a/1</h3>
    <a class="finding-aid" href="/scripts/mwimain.dll/144/PAM_LISTINGS/1234?RECORD">View Record 1234</a>
    <a class="media-link" href="https://pam.minisisinc.com/assets/media/B_239_a_1.pdf">Digitized Microfilm Copy (PDF)</a>  # noqa: E501
    <img src="https://pam.minisisinc.com/assets/images/thumbs/B_239_a_1_001.jpg" />
  </div>
</body>
</html>
"""


def test_extract_hbca_location_codes():
    codes = extract_hbca_location_codes(SAMPLE_BIO_TEXT)
    assert "B.239/g/1-4" in codes or "B.239/g/1" in codes
    assert "A.32/21" in codes
    assert "E.4/1a" in codes or "E.4/1a fo. 45" in codes


def test_build_keystone_search_url():
    # A plain GET URL can't actually run a MINISIS search (it needs a live,
    # session-scoped POST), so this writes a local HTML page that auto-submits
    # the real POST on load and returns that page's file:// URI - a fallback
    # link a human can still click when the automated lookup finds nothing.
    url = build_keystone_search_url("B.239/g/1")
    assert url.startswith("file://")
    assert url.endswith(".html")

    local_path = Path(url2pathname(urlparse(url).path))
    contents = local_path.read_text(encoding="utf-8")
    assert "pam.minisisinc.com" in contents
    assert "B.239/g/1" in contents


def test_parse_keystone_search_response():
    results = parse_keystone_search_response(
        SAMPLE_KEYSTONE_HTML,
        base_url="https://pam.minisisinc.com/scripts/mwimain.dll",
    )
    assert len(results["record_urls"]) >= 1
    assert len(results["media_urls"]) >= 1
    assert any("B_239_a_1.pdf" in u for u in results["media_urls"])
    assert any("1234?RECORD" in u for u in results["record_urls"])


query_keystone_for_code = getattr(_hbca_mod, "query_keystone_for_code", None)
download_and_merge_keystone_media = getattr(_hbca_mod, "download_and_merge_keystone_media", None)

LANDING_PAGE_HTML = """
<html><body>
<form name="frmSearchListings" method="post" action="/scripts/mwimain.dll/521745500/1/0?SEARCH">
  <input type="text" name="LOCATION_CODE">
</form>
</body></html>
"""

RECORD_PAGE_HTML = """
<html><body>
<h1>Northern Department minutes of council</h1>
<div>Item Description</div><div>Northern Department minutes of council</div>
<div>Date</div><div>1851-1870</div>
<div>Fonds/Series Title</div><div>Northern Department minutes of council</div>
<div>Notes</div><div>The microfilm of this record has been digitized.</div>
<div>Location Code</div><div>H2-24-1 ( B.239/k/3 )</div>
<div>Microfilm No.</div><div>1M814</div>
<textarea id="share_link_url">
https://pam.minisisinc.com/scripts/mwimain.dll/144/LISTINGS_IMAGES/LISTINGS_DET_IMAGES/SISN%205154?sessionsearch
</textarea>
<a href="https://PAM.MINISISINC.COM/DIGITALOBJECTS/Access/HBCA%20Microfilm/1M814/B239-K-3-Reel1.pdf">
Click here for PDF File</a>
<a href="https://PAM.MINISISINC.COM/DIGITALOBJECTS/Access/HBCA%20Microfilm/1M814/B239-K-3-Reel2.pdf">
Click here for PDF File</a>
</body></html>
"""


def test_query_keystone_for_code_extracts_metadata_permalink_and_all_reel_pdfs(requests_mock):
    if not query_keystone_for_code:
        import pytest
        pytest.fail("query_keystone_for_code missing")
    requests_mock.get(
        "https://pam.minisisinc.com/scripts/mwimain.dll/144/PAM_LISTINGS?DIRECTSEARCH",
        text=LANDING_PAGE_HTML,
    )
    requests_mock.post(
        "https://pam.minisisinc.com/scripts/mwimain.dll/521745500/1/0",
        text=RECORD_PAGE_HTML,
    )
    result = query_keystone_for_code("B.239/k/3")
    assert len(result["media_urls"]) == 2
    assert "SISN%205154" in result["record_urls"][0]
    assert result["metadata"]["item_description"] == "Northern Department minutes of council"
    assert result["metadata"]["microfilm_no"] == "1M814"


def test_download_and_merge_keystone_media_combines_reels(tmp_path, requests_mock):
    if not download_and_merge_keystone_media:
        import pytest
        pytest.fail("download_and_merge_keystone_media not implemented")
    minimal_pdf = (
        b"%PDF-1.4\n1 0 obj\n<</Type/Catalog/Pages 2 0 R>>\nendobj\n2 0 obj\n"
        b"<</Type/Pages/Count 0/Kids[]>>\nendobj\nxref\n0 3\n"
        b"0000000000 65535 f \n0000000009 00000 n \n0000000052 00000 n \n"
        b"trailer\n<</Size 3/Root 1 0 R>>\nstartxref\n95\n%%EOF\n"
    )
    requests_mock.get("https://example.com/reel1.pdf", content=minimal_pdf)
    requests_mock.get("https://example.com/reel2.pdf", content=minimal_pdf)
    merged_path = download_and_merge_keystone_media(
        ["https://example.com/reel1.pdf", "https://example.com/reel2.pdf"],
        target_dir=tmp_path,
        output_name="B239-K-3.pdf",
    )
    assert merged_path.exists()


def test_keystone_query_is_cached(tmp_path, requests_mock):
    if not query_keystone_for_code:
        import pytest
        pytest.fail("query_keystone_for_code missing")
    cache_file = tmp_path / "keystone_cache.json"
    requests_mock.get(
        "https://pam.minisisinc.com/scripts/mwimain.dll/144/PAM_LISTINGS?DIRECTSEARCH",
        text=LANDING_PAGE_HTML,
    )
    requests_mock.post(
        "https://pam.minisisinc.com/scripts/mwimain.dll/521745500/1/0",
        text=RECORD_PAGE_HTML,
    )
    res1 = query_keystone_for_code("B.239/k/3", cache_file=str(cache_file))
    res2 = query_keystone_for_code("B.239/k/3", cache_file=str(cache_file))
    assert requests_mock.call_count == 2  # one GET + one POST, only on the first call
    assert res1 == res2
