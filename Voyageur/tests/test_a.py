"""Tests for A.py's census-gather normalization call site (Issue #3 test-coverage gap)."""
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
