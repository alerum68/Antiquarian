import json
from pathlib import Path

from Commissioner.fact_registry import export_fact_types_json, is_family_fact

FACT_TYPES_JSON_PATH = Path(__file__).resolve().parent.parent / "FactTypes.json"


def test_is_family_fact_distinguishes_scope():
    assert is_family_fact("Marriage") is True
    assert is_family_fact("Birth") is False


def test_export_fact_types_json_matches_real_file_on_disk():
    """Guardrail: Archivist.py, Paleographer.py, engine.py, Voyageur.py, and FS.py
    all still read the real FactTypes.json directly. If Commissioner.models'
    FACT_DEFINITIONS ever drifts from that file, this must fail immediately."""
    with open(FACT_TYPES_JSON_PATH, "r", encoding="utf-8") as f:
        real = json.load(f)
    assert export_fact_types_json() == real
