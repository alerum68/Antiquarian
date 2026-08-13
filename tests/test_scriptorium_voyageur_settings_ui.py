import pytest

import Scriptorium
from Scriptorium import Scriptorium as ScriptoriumApp


def test_visible_sections_includes_matching_provider_and_universal_gather_settings():
    result = Scriptorium.Scriptorium._voyageur_visible_sections("Ancestry")

    assert set(result.keys()) == {"Ancestry", "Gather Settings"}
    assert "A_URL" in result["Ancestry"]
    assert "GATHER_ON_COLLISION" in result["Ancestry"]
    assert "VOYAGEUR_SOURCE" in result["Gather Settings"]


def test_visible_sections_excludes_other_providers():
    result = Scriptorium.Scriptorium._voyageur_visible_sections("FamilySearch")

    assert "Ancestry" not in result
    assert "LAC" not in result
    assert "HBCA / Manitoba Archives" not in result
    assert set(result.keys()) == {"FamilySearch", "Gather Settings"}


def test_visible_sections_for_lac_does_not_include_ancestry_only_settings():
    """GATHER_ON_COLLISION only means anything to A.py/FS.py - LAC.py never reads it, so
    it must not leak into LAC's section just because Gather Settings is always included."""
    result = Scriptorium.Scriptorium._voyageur_visible_sections("LAC")

    assert set(result.keys()) == {"LAC", "Gather Settings"}
    assert "GATHER_ON_COLLISION" not in result["LAC"]
    assert "GATHER_ON_COLLISION" not in result["Gather Settings"]


@pytest.fixture(scope="module")
def app():
    import tkinter
    if getattr(tkinter, "_default_root", None) is not None and isinstance(tkinter._default_root, ScriptoriumApp):
        root = tkinter._default_root
    else:
        root = ScriptoriumApp()
    root._switch_tab("Voyageur")
    yield root
    root.withdraw()


def _all_widget_texts(container) -> list:
    """Collects every widget's .cget("text") found anywhere under the scrollable form
    container - both section headers and field labels are plain CTkLabels, no dedicated
    widget type to distinguish them, so this walks the whole tree and returns everything."""
    texts = []
    for child in container.winfo_children():
        text = None
        try:
            text = child.cget("text")
        except Exception:
            pass
        if text:
            texts.append(text)
        texts.extend(_all_widget_texts(child))
    return texts


def test_ancestry_source_shows_its_own_section_and_collision_setting(app):
    app.string_vars["VOYAGEUR_SOURCE"].set("Ancestry")
    app._on_voyageur_source_change()

    texts = _all_widget_texts(app.voyageur_form_container)
    assert "Ancestry" in texts
    assert any("On Existing File" in t for t in texts)
    assert "FamilySearch" not in texts


def test_lac_source_does_not_show_the_ancestry_only_collision_setting(app):
    """Regression test for the exact bug a review caught: an earlier version of this
    feature put GATHER_ON_COLLISION in the always-shown Gather Settings section, which
    made it appear for LAC even though LAC.py never reads that env var."""
    app.string_vars["VOYAGEUR_SOURCE"].set("LAC")
    app._on_voyageur_source_change()

    texts = _all_widget_texts(app.voyageur_form_container)
    assert "LAC" in texts
    assert not any("On Existing File" in t for t in texts)
