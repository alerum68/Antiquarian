"""Tests for A.py's census-gather normalization call site (Issue #3 test-coverage gap)."""
import json
import A
from A import parse_ancestry_url


def test_parse_ancestry_url_view_style():
    url = "https://search.ancestry.com/cgi-bin/sse.dll?db=somedb&indiv=try&view/1234:567"
    assert parse_ancestry_url(url) == ("567", "1234")


def test_parse_ancestry_url_collections_with_pid():
    url = ("https://www.ancestry.com/imageviewer/collections/7667/images/4211353_00001"
           "?queryId=527a29b7&usePUB=true&pId=17613762")
    assert parse_ancestry_url(url) == ("7667", "17613762")


def test_parse_ancestry_url_dbid_and_h_query_params():
    url = "https://www.ancestry.com/some/path?dbid=60525&h=123456"
    assert parse_ancestry_url(url) == ("60525", "123456")


def test_parse_ancestry_url_collections_without_pid_uses_image_number():
    """Regression: newer Ancestry imageviewer URLs drop &pId= and put the image number
    straight in the path instead (.../images/<num>-<slug>), which the older patterns
    couldn't match - produced "Could not parse database ID (dbid) or record ID (h)
    from the URL" on an otherwise-valid gather URL."""
    url = ("https://www.ancestry.com/imageviewer/collections/62308/images/"
           "43290879-North_Dakota-051775-0001?usePUB=true&_phsrc=MpD179")
    assert parse_ancestry_url(url) == ("62308", "43290879")


def test_parse_ancestry_url_unparseable_returns_none_none():
    assert parse_ancestry_url("https://www.ancestry.com/search/") == (None, None)


def test_normalize_ancestry_census_gather_derives_title_and_record_type():
    raw_gather = {
        "census_year": "1880", "location": "Kent County, Michigan",
        "pages": [{
            "page_number": 12, "state": "Michigan", "county": "Kent", "city": "",
            "country": "USA", "roll_number": "T9_1", "repository": "Ancestry.com",
            "people": [
                {"columns": {"Given Name": "Jean", "Surname": "Gagnon", "Gender": "M",
                             "Age": "40", "Relationship to Head": "Head", "Family Number": "5"},
                 "pid": "p1"},
            ],
        }],
    }

    normalized = A.normalize_ancestry_census_gather(raw_gather)

    assert normalized["record_type_name"] == "Census_1880"
    assert normalized["collection_title"] == "1880 USA Census - Kent County, Michigan"
    assert len(normalized["sheets"]) == 1


def test_normalize_ancestry_census_gather_derives_canadian_title_from_page_country():
    """Regression: confirmed live (2026-08-15, dbId 1578, Ontario) that collection_title
    hardcoded "US Federal Census" regardless of the gather's own country - the title must
    instead reflect whatever Voyageur.js's own ancestryCountryFromState() recorded on the
    raw page."""
    raw_gather = {
        "census_year": "1871", "location": "Ontario",
        "pages": [{
            "page_number": 1, "state": "Ontario", "county": "Frontenac", "city": "",
            "country": "Canada", "repository": "Ancestry.com",
            "people": [
                {"columns": {"Given Name": "Charles", "Surname": "Bernard", "Gender": "M",
                             "Age": "40", "Family Number": "1"}, "pid": "p1"},
            ],
        }],
    }

    normalized = A.normalize_ancestry_census_gather(raw_gather)

    assert normalized["collection_title"] == "1871 Canada Census - Ontario"


MINIMAL_NORMALIZED = {
    "citation": {"collection_name": "United States Federal Census, 1860"},
    "sheets": [{
        "records": [{
            "year": "1860",
            "type_specific_fields": {
                "country": "USA",
                "state": "Minnesota",
                "county": "Ramsey",
                "city": "St Paul",
                "enumeration_district": "",
            }
        }]
    }]
}


def test_a_main_image_routing_uses_live_data_not_filename():
    """A.py image routing reads census_year/location from data, not the filename stem."""
    from _gather_helpers import extract_census_image_routing_fields
    year, country, loc_folder, coll_name = extract_census_image_routing_fields(MINIMAL_NORMALIZED)
    assert year == "1860"
    assert country == "USA"
    assert loc_folder == "Minnesota - Ramsey - St Paul"
    assert coll_name == "United States Federal Census, 1860"


def test_a_normalize_then_extract_routing_fields_round_trips():
    """Integration regression: extract_census_image_routing_fields() must read whatever
    shape normalize_ancestry_census_gather() actually produces, not a hand-built fixture -
    census_year previously lived only in test fixtures' type_specific_fields, a shape the
    real normalizer never produces (it stores year as the record's own top-level "year" key,
    a sibling of type_specific_fields - see census_schema.py), which let census_year come
    back "" for every real gather while the hand-built-fixture tests kept passing."""
    from _gather_helpers import extract_census_image_routing_fields
    raw_gather = {
        "census_year": "1900", "location": "Minnesota",
        "pages": [{
            "page_number": 1, "state": "Minnesota", "county": "Ramsey", "city": "St Paul",
            "country": "USA", "repository": "Ancestry.com",
            "people": [
                {"columns": {"Given Name": "Jean", "Surname": "Gagnon", "Gender": "M",
                             "Age": "40", "Family Number": "1"}, "pid": "p1"},
            ],
        }],
    }
    normalized = A.normalize_ancestry_census_gather(raw_gather)
    year, country, loc_folder, _ = extract_census_image_routing_fields(normalized)
    assert year == "1900"
    assert country == "USA"
    assert loc_folder == "Minnesota - Ramsey - St Paul"


def test_recover_orphaned_runs_survives_malformed_recovered_json(tmp_path, monkeypatch):
    """Regression: extract_census_image_routing_fields() must not crash
    _recover_orphaned_runs() when a recovered file parses as valid JSON but has an
    unexpected shape (e.g. a non-dict record) - recovery is explicitly best-effort for
    files this run didn't produce itself (see the function's own docstring: 'never guess,
    fall back'), so a malformed shape must fall back to empty routing fields, never
    propagate an unhandled exception and crash main() before the gather even starts."""
    # HBCA.py/LAC.py call load_dotenv() at import time, which - if either was imported
    # earlier in the same pytest session - can leave a real, machine-specific absolute
    # MEDIA_DIR in os.environ; resolve_census_image_dir() then ignores genealogy_dir
    # entirely and tries to mkdir that real path. Force it back to the relative default
    # so this test's image routing stays confined to tmp_path regardless of test order.
    monkeypatch.setenv("MEDIA_DIR", "Media")

    downloads_dir = tmp_path / "downloads"
    downloads_dir.mkdir()
    json_target_dir = tmp_path / "json_target"
    json_target_dir.mkdir()
    genealogy_dir = str(tmp_path / "genealogy")

    # Valid JSON, but 'records' holds a non-dict entry - extract_census_image_routing_fields
    # previously raised AttributeError on records[0].get(...) for a shape like this.
    (downloads_dir / "TMP_A_stale1_Bad.json").write_text(
        json.dumps({"sheets": [{"records": ["not-a-dict"]}]}))

    A._recover_orphaned_runs(downloads_dir, "current", json_target_dir, genealogy_dir)

    assert (json_target_dir / "Bad.json").exists()
