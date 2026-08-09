import importlib.util
from pathlib import Path

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
    url = build_keystone_search_url("B.239/g/1")
    assert "pam.minisisinc.com" in url
    assert "B.239/g/1" in url or "B_239_g_1" in url or "B.239%2Fg%2F1" in url


def test_parse_keystone_search_response():
    results = parse_keystone_search_response(
        SAMPLE_KEYSTONE_HTML,
        base_url="https://pam.minisisinc.com/scripts/mwimain.dll",
    )
    assert len(results["record_urls"]) >= 1
    assert len(results["media_urls"]) >= 1
    assert any("B_239_a_1.pdf" in u for u in results["media_urls"])
    assert any("1234?RECORD" in u for u in results["record_urls"])
