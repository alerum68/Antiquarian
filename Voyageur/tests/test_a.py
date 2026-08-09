"""Tests for A.py's census-gather normalization call site (Issue #3 test-coverage gap)."""
import A


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
    assert normalized["collection_title"] == "1880 US Federal Census - Kent County, Michigan"
    assert len(normalized["sheets"]) == 1
