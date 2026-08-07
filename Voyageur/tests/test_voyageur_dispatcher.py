import sys
import types

import pytest

import Voyageur


@pytest.mark.parametrize("source, module_name", [("A", "A"), ("FS", "FS"), ("LAC", "LAC")])
def test_main_dispatches_to_correct_provider_and_strips_mode_token(source, module_name, monkeypatch):
    calls = []
    fake_module = types.ModuleType(module_name)
    fake_module.main = lambda: calls.append(sys.argv[:])
    monkeypatch.setitem(sys.modules, module_name, fake_module)
    monkeypatch.setattr(sys, "argv", ["Voyageur.py", source, "--extra", "value"])

    Voyageur.main()

    assert calls == [["Voyageur.py", "--extra", "value"]]


def test_main_rejects_invalid_source(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["Voyageur.py", "BOGUS"])

    with pytest.raises(SystemExit) as exc_info:
        Voyageur.main()

    assert exc_info.value.code == 1
    assert "[ERROR] Usage: python Voyageur.py <source>" in capsys.readouterr().out


def test_main_rejects_missing_source(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["Voyageur.py"])

    with pytest.raises(SystemExit) as exc_info:
        Voyageur.main()

    assert exc_info.value.code == 1
