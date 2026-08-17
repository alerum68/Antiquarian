from pathlib import Path

import pytest

import Antiquarian
from Antiquarian import Antiquarian as AntiquarianApp


@pytest.fixture(scope="module")
def app():
    import tkinter
    default_root = getattr(tkinter, "_default_root", None)
    if default_root is not None and isinstance(default_root, AntiquarianApp):
        root = default_root
    else:
        root = AntiquarianApp()
    yield root
    root.withdraw()


def test_prompts_dir_is_a_real_global_setting_with_a_default():
    fields = Antiquarian.GLOBAL_VARS["Global Directories"]
    assert fields["PROMPTS_DIR"] == "Prompts"


def test_prompt_search_dirs_honours_genealogy_dir_and_prompts_dir_override(app, tmp_path):
    app.string_vars["GENEALOGY_DIR"].set(str(tmp_path))
    app.string_vars["PROMPTS_DIR"].set("MyPrompts")

    dirs = app._prompt_search_dirs()

    assert dirs[0] == tmp_path / "MyPrompts"


def test_prompt_search_dirs_bundled_tier_uses_app_dir_not_a_string_var(app):
    """Regression: this tier used to read self.string_vars.get("PROGRAM_DIR"), which is
    never a real GUI field (see _run_subprocess), so it was always empty and this whole
    tier silently never appeared - exactly the tier a portable install's bundled Prompts
    folder depends on."""
    app.string_vars["GENEALOGY_DIR"].set("")

    dirs = app._prompt_search_dirs()

    assert Antiquarian.APP_DIR / "Prompts" in dirs


def test_prompt_search_dirs_still_falls_back_to_the_dev_checkout_prompts_folder(app):
    app.string_vars["GENEALOGY_DIR"].set("")

    dirs = app._prompt_search_dirs()

    assert dirs[-1] == Path(Antiquarian.__file__).resolve().parent / "Paleographer" / "prompts"
