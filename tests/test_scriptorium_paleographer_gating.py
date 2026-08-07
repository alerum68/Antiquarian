import pytest

from Scriptorium import Scriptorium as ScriptoriumApp


@pytest.fixture(scope="module")
def app():
    # Module-scoped: constructing a second Tk/CTk root after destroying the first
    # in the same process is flaky on Windows (intermittent "Can't find a usable
    # tk.tcl" from the second interpreter). One instance is reused across both
    # tests below; each test fully overwrites the record-type var and re-runs
    # _on_record_type_change() before asserting, so there's no state leakage.
    root = ScriptoriumApp()
    root._switch_tab("Paleographer")
    yield root
    root.destroy()


def test_scrip_record_type_enables_enrichment_buttons(app):
    app.string_vars["PALEOGRAPHER_RECORD_TYPE"].set("Scrip.pmt")
    app._on_record_type_change()
    assert app.paleographer_enrich_btn.cget("state") == "normal"
    assert app.paleographer_partition_btn.cget("state") == "normal"
    assert app.paleographer_resolve_names_btn.cget("state") == "normal"


def test_non_scrip_record_type_disables_enrichment_buttons(app):
    app.string_vars["PALEOGRAPHER_RECORD_TYPE"].set("Parish.pmt")
    app._on_record_type_change()
    assert app.paleographer_enrich_btn.cget("state") == "disabled"
    assert app.paleographer_partition_btn.cget("state") == "disabled"
    assert app.paleographer_resolve_names_btn.cget("state") == "disabled"
