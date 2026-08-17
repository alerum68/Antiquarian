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


def test_visible_sections_for_lac_includes_the_collision_setting():
    """LAC.py now honours GATHER_ON_COLLISION too (default 'skip'), so it belongs in
    LAC's section like every other source's - see the always-shown Gather Settings
    docstring on _voyageur_visible_sections."""
    result = Antiquarian.Antiquarian._voyageur_visible_sections("LAC")

    assert set(result.keys()) == {"Gather Settings"}
    assert "GATHER_ON_COLLISION" in result["Gather Settings"]


def test_visible_sections_for_keystone_shows_hbca_settings_and_the_collision_setting():
    """HBCA.py now honours GATHER_ON_COLLISION too (default 'skip')."""
    result = Antiquarian.Antiquarian._voyageur_visible_sections("Keystone Archives")

    assert set(result.keys()) == {"Gather Settings", "HBCA Settings"}
    assert "GATHER_ON_COLLISION" in result["Gather Settings"]
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


def test_lac_source_shows_the_collision_setting(app):
    """LAC.py now honours GATHER_ON_COLLISION (default 'skip'), so it must show up here
    like it does for every other source."""
    app.string_vars["VOYAGEUR_SOURCE"].set("LAC")
    app._on_voyageur_source_change()

    texts = _all_widget_texts(app.voyageur_form_container)
    assert any("On Existing File" in t for t in texts)


def test_keystone_source_shows_hbca_settings_and_the_collision_setting(app):
    """HBCA.py now honours GATHER_ON_COLLISION (default 'skip')."""
    app.string_vars["VOYAGEUR_SOURCE"].set("Keystone Archives")
    app._on_voyageur_source_change()

    texts = _all_widget_texts(app.voyageur_form_container)
    assert "HBCA Settings" in texts
    assert any("On Existing File" in t for t in texts)
