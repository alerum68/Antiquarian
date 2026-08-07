import sys
import types

import pytest

import Paleographer


@pytest.mark.parametrize("mode", ["enrich", "crosscheck", "partition", "resolve-names"])
def test_main_dispatches_enrichment_modes_to_scriptools(mode, monkeypatch):
    calls = []
    fake_module = types.ModuleType("ScripTools")
    fake_module.main = lambda: calls.append(sys.argv[:])
    monkeypatch.setitem(sys.modules, "ScripTools", fake_module)
    monkeypatch.setattr(sys, "argv", ["Paleographer.py", mode, "--extra", "value"])

    Paleographer.main()

    assert calls == [["Paleographer.py", mode, "--extra", "value"]]


def test_main_dispatches_no_args_to_extract(monkeypatch):
    calls = []
    fake_module = types.ModuleType("Extract")
    fake_module.main = lambda: calls.append(sys.argv[:])
    monkeypatch.setitem(sys.modules, "Extract", fake_module)
    monkeypatch.setattr(sys, "argv", ["Paleographer.py"])

    Paleographer.main()

    assert calls == [["Paleographer.py"]]


def test_main_dispatches_debug_filename_to_extract(monkeypatch):
    calls = []
    fake_module = types.ModuleType("Extract")
    fake_module.main = lambda: calls.append(sys.argv[:])
    monkeypatch.setitem(sys.modules, "Extract", fake_module)
    monkeypatch.setattr(sys, "argv", ["Paleographer.py", "some_file.pdf"])

    Paleographer.main()

    assert calls == [["Paleographer.py", "some_file.pdf"]]
