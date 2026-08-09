import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent / "golden"))

from capture_golden_gedcom import PARISH_FIXTURE, SCRIP_FIXTURE  # noqa: E402
import Utils  # noqa: E402
import General  # noqa: E402

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"


DEFAULT_GENERAL_CONFIG = {
    'volume_num': '',
    'register_source_id': '1',
    'register_name': '',
    'parish_name': '',
    'parish_name_short': '',
    'parish_location': '',
    'volume_title': '',
    'date_range_str': '',
    'diocese': '',
    'collection_url': '',
    'collection_name': '',
    'parish_file_name': '',
    'default_location': '',
    'citation_detail': '',
    'citation_text': '',
    'role_clergy': 'Priest',
    'role_default_witness': 'Witness',
    'clergy_honorific': 'Father',
}


def _regenerate(fixture: dict, target_software: str, profile) -> str:
    General.set_active_profile(profile)
    General.CALL_NUMBER = ""
    General.COLLECTION_URL = ""
    General.COLLECTION_NAME = ""
    General.REPOSITORY = ""
    General.REPOSITORY_LOC = ""
    General.IMAGE_DIR = Utils.safe_path("C:/Users/Jason Cole/Documents/Genealogy", "Census")
    General.GENERAL_CONFIG.clear()
    General.GENERAL_CONFIG.update(DEFAULT_GENERAL_CONFIG)
    raw = General.build_gedcom_from_general(fixture, target_software)
    return re.sub(r"1 DATE .*\r?\n2 TIME .*", "1 DATE 07 AUG 2026\n2 TIME 14:11:32", raw)


def test_scrip_rm_matches_golden():
    import Scrip
    actual = _regenerate(SCRIP_FIXTURE, "RM", Scrip.ScripProfile())
    expected = (GOLDEN_DIR / "scrip_rm.ged").read_text(encoding="utf-8")
    assert actual == expected


def test_scrip_ftm_matches_golden():
    import Scrip
    actual = _regenerate(SCRIP_FIXTURE, "FTM", Scrip.ScripProfile())
    expected = (GOLDEN_DIR / "scrip_ftm.ged").read_text(encoding="utf-8")
    assert actual == expected


def test_parish_rm_matches_golden():
    actual = _regenerate(PARISH_FIXTURE, "RM", General.GeneralProfile())
    expected = (GOLDEN_DIR / "parish_rm.ged").read_text(encoding="utf-8")
    assert actual == expected


def test_parish_ftm_matches_golden():
    actual = _regenerate(PARISH_FIXTURE, "FTM", General.GeneralProfile())
    expected = (GOLDEN_DIR / "parish_ftm.ged").read_text(encoding="utf-8")
    assert actual == expected
