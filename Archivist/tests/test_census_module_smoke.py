# noinspection PyUnresolvedReferences
import Census
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_census_module_imports_and_exposes_run_census_flavor():
    assert callable(Census.run_census_flavor)
