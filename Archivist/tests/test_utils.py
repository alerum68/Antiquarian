import Utils
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_clean_val_strips_and_stringifies():
    assert Utils.clean_val("  Jean  ") == "Jean"
    assert Utils.clean_val(None) == ""


def test_get_event_gedcom_tag_person_and_family_buckets():
    assert Utils.get_event_gedcom_tag("Baptism") == "BAPM"
    assert Utils.get_event_gedcom_tag("Marriage") == "MARR"
    assert Utils.get_event_gedcom_tag("Some Future Fact Type") == "EVEN"


def test_split_full_name_splits_on_last_space():
    assert Utils.split_full_name("Jean Baptiste Gagnon") == ("Jean Baptiste", "Gagnon")


def test_resolve_source_id_returns_precoded_value_for_known_census_year():
    assert Utils.resolve_source_id("Census_1880") == Utils.PRECODED_SOURCE_IDS["Census_1880"]
