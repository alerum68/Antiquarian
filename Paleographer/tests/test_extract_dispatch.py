# noinspection PyUnresolvedReferences
import Extract


def test_extract_module_has_main():
    assert callable(Extract.main)
