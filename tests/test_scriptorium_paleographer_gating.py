import pytest

from Scriptorium import Scriptorium as ScriptoriumApp


@pytest.fixture(scope="module")
def app():
    import tkinter
    if getattr(tkinter, "_default_root", None) is not None and isinstance(tkinter._default_root, ScriptoriumApp):
        root = tkinter._default_root
    else:
        root = ScriptoriumApp()
    root._switch_tab("Paleographer")
    yield root
    root.withdraw()


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
