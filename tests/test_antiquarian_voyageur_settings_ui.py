import pytest

import Antiquarian
from Antiquarian import Antiquarian as AntiquarianApp


def test_visible_sections_includes_universal_gather_settings_and_collision_setting():
    result = Antiquarian.Antiquarian._voyageur_visible_sections("Ancestry")

    assert set(result.keys()) == {"Gather Settings"}
    assert "GATHER_URL" in result["Gather Settings"]
    assert "GATHER_ON_COLLISION" in result["Gather Settings"]


def test_visible_sections_for_familysearch_shows_only_gather_settings():
    result = Antiquarian.Antiquarian._voyageur_visible_sections("FamilySearch")

    assert "HBCA Settings" not in result
    assert set(result.keys()) == {"Gather Settings"}
    assert "GATHER_ON_COLLISION" in result["Gather Settings"]


def test_visible_sections_for_lac_does_not_include_ancestry_only_settings():
    """GATHER_ON_COLLISION only means anything to A.py/FS.py - LAC.py never reads it, so
    it must not leak into LAC's section just because Gather Settings is always included."""
    result = Antiquarian.Antiquarian._voyageur_visible_sections("LAC")

    assert set(result.keys()) == {"Gather Settings"}
    assert "GATHER_ON_COLLISION" not in result["Gather Settings"]


def test_visible_sections_for_keystone_shows_hbca_settings_and_no_collision_setting():
    result = Antiquarian.Antiquarian._voyageur_visible_sections("Keystone Archives")

    assert set(result.keys()) == {"Gather Settings", "HBCA Settings"}
    assert "GATHER_ON_COLLISION" not in result["Gather Settings"]
    assert "HBCA_LETTER_FILTER" in result["HBCA Settings"]


@pytest.fixture(scope="module")
def app():
    import tkinter
    default_root = getattr(tkinter, "_default_root", None)
    if default_root is not None and isinstance(default_root, AntiquarianApp):
        root = default_root
    else:
        root = AntiquarianApp()
    root.switch_tab("Voyageur")
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


def test_ancestry_source_shows_the_collision_setting(app):
    app.string_vars["VOYAGEUR_SOURCE"].set("Ancestry")
    app._on_voyageur_source_change()

    texts = _all_widget_texts(app.voyageur_form_container)
    assert any("On Existing File" in t for t in texts)
    assert "HBCA Settings" not in texts


def test_lac_source_does_not_show_the_ancestry_only_collision_setting(app):
    """Regression test for the exact bug a review caught: an earlier version of this
    feature put GATHER_ON_COLLISION in the always-shown Gather Settings section, which
    made it appear for LAC even though LAC.py never reads that env var."""
    app.string_vars["VOYAGEUR_SOURCE"].set("LAC")
    app._on_voyageur_source_change()

    texts = _all_widget_texts(app.voyageur_form_container)
    assert not any("On Existing File" in t for t in texts)


def test_keystone_source_shows_hbca_settings_and_not_the_collision_setting(app):
    app.string_vars["VOYAGEUR_SOURCE"].set("Keystone Archives")
    app._on_voyageur_source_change()

    texts = _all_widget_texts(app.voyageur_form_container)
    assert "HBCA Settings" in texts
    assert not any("On Existing File" in t for t in texts)
