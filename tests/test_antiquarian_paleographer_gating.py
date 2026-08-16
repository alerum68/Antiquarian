import pytest

from Antiquarian import Antiquarian as AntiquarianApp


@pytest.fixture(scope="module")
def app():
    import tkinter
    default_root = getattr(tkinter, "_default_root", None)
    if default_root is not None and isinstance(default_root, AntiquarianApp):
        root = default_root
    else:
        root = AntiquarianApp()
    root.switch_tab("Paleographer")
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
