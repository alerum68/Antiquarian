import importlib.util
from pathlib import Path

_hbca_path = Path(__file__).resolve().parents[1] / "HBCA.py"
_spec = importlib.util.spec_from_file_location("voyageur_hbca", _hbca_path)
_hbca_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_hbca_mod)

parse_bio_sheet_text = _hbca_mod.parse_bio_sheet_text


def test_parse_bio_sheet_populated_table():
    sample_text = """
    NAME: ADAMS, Charles PARISH: ENTERED SERVICE: DATES:
    Appointments & Service
    Outfit Year* Position Post District HBCA Reference
    1866-1868 Postmaster The Pas Cumberland B.239/k/3, p. 334, 356
    1868-1871 Clerk in charge Rapid River English River B.239/k/3, p. 377, 407, 433
    1874-1875 Clerk in charge Lake St. Anns Upper Saskatchewan B.239/k/4, fo. 2d
    Filename: Adams, Charles (fl. 1866-1882). JHB/ek May/85
    """
    data = parse_bio_sheet_text(sample_text)

    assert data["parish_of_origin"] == ""
    assert len(data["service_history"]) == 3
    assert data["service_history"][0]["hbca_ref"] == "B.239/k/3"
    assert data["service_history"][0]["post"] == "The Pas"
    assert data["service_history"][2]["hbca_ref"] == "B.239/k/4"
    assert data["needs_llm_structured_review"] is False
    # No structured DATES field, so the Filename footer's floruit range is the fallback
    assert "1866-1882" in data["service_years_range"] or "1866-1882" in (data.get("vital_dates_summary") or "")


def test_parse_bio_sheet_blank_header_and_empty_table_flags_for_llm_review():
    sample_text = """
    NAME: ADAMS, George PARISH: ENTERED SERVICE: DATES:
    Appointments & Service
    Outfit Year* Position Ship District HBCA Reference
    George Adams is listed as one of seven passengers boarding the chartered vessel Hadlow...
    In summer 1816 Adams apparently joined the employ of the Hudson's Bay Company...3
    Filename: Adams, George (fl. 1815-1823) JHB October 1998
    """
    data = parse_bio_sheet_text(sample_text)

    assert data["parish_of_origin"] == ""
    assert data["service_history"] == []
    assert data["needs_llm_structured_review"] is True
