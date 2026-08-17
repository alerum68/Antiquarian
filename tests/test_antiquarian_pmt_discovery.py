"""Tests that Antiquarian.py's .pmt discovery matches engine.py's tier order."""
from pathlib import Path


def test_list_record_types_finds_pmt_from_genealogy_dir(tmp_path, monkeypatch):
    """_list_record_types() must discover a .pmt placed in GENEALOGY_DIR/Prompts."""
    prompts_dir = tmp_path / "Prompts"
    prompts_dir.mkdir()
    (prompts_dir / "Custom.pmt").write_text("---\ndocument_type: Custom\n---\n", encoding="utf-8")

    monkeypatch.setenv("GENEALOGY_DIR", str(tmp_path))
    monkeypatch.setenv("PROGRAM_DIR", "")

    # Import the module without instantiating the GUI
    import importlib
    import sys
    import unittest.mock as mock

    class DummyCTk:
        pass

    mock_ctk = mock.MagicMock()
    mock_ctk.CTk = DummyCTk
    sys.modules.setdefault("customtkinter", mock_ctk)

    mock_tk = mock.MagicMock()
    sys.modules.setdefault("tkinter", mock_tk)
    sys.modules.setdefault("tkinter.messagebox", mock.MagicMock())
    sys.modules.setdefault("tkinter.filedialog", mock.MagicMock())
    spec = importlib.util.spec_from_file_location(
        "antiquarian_gui", Path(__file__).resolve().parents[1] / "Antiquarian.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # Instantiate a dummy app to avoid UI logic
    class DummyApp:
        def __init__(self):
            self.string_vars = {
                "GENEALOGY_DIR": mock.MagicMock(),
                "PROGRAM_DIR": mock.MagicMock()
            }
            self.string_vars["GENEALOGY_DIR"].get.return_value = str(tmp_path)
            self.string_vars["PROGRAM_DIR"].get.return_value = ""

    app = DummyApp()
    app._prompt_search_dirs = mod.Antiquarian._prompt_search_dirs.__get__(app)

    # We can bind the unbound method to our dummy app instance
    types = mod.Antiquarian._list_record_types(app)
    assert "Custom.pmt" in types, f"Expected Custom.pmt in {types}"
