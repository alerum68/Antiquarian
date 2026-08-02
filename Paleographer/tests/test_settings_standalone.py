"""
Confirms Paleographer.py resolves its own runtime settings (SOURCE_DIR, MASTER_DB) from
only its own record type's PREFIXED settings-tab keys (e.g. CHURCH_IMAGE_DIR,
CHURCH_MASTER_DB_NAME) via field_remap - with the generic names (IMAGE_DIR,
MASTER_DB_NAME) never set at all. This is the actual standalone-execution scenario: no
Scriptorium.py subprocess-env injection bridging prefixed names to generic ones.
"""
import importlib
import sys

import pytest


@pytest.fixture
def minimal_paleographer_env(monkeypatch, tmp_path):
    program_dir = tmp_path / "program"
    (program_dir / "Parish").mkdir(parents=True)
    (program_dir / "JSON").mkdir(parents=True)

    env = {
        "PROGRAM_DIR": str(program_dir),
        "JSON_DIR": "JSON",
        "PALEOGRAPHER_RECORD_TYPE": "Parish",
        "MODEL_NAME": "gemini-test-model",
        "GEMINI_API_KEY": "fake-key-not-used",
        "API_BUDGET": "5.00",
        "COST_PER_1M_INPUT": "0.075",
        "COST_PER_1M_OUTPUT": "0.30",
        "CACHE_DISCOUNT_MULTIPLIER": "0.10",
        "VOLUME_TITLE": "Test Volume",
        "VOLUME_NUM": "1",
        # This fixture mocks google.genai.Client (below) to test the api engine's
        # settings resolution - EXTRACTION_ENGINE's own default is now "agy", so pin
        # it explicitly even though none of this file's tests call main() (the only
        # place that would actually trigger a real agy call).
        "EXTRACTION_ENGINE": "api",
        # Only the record type's own PREFIXED keys - no IMAGE_DIR/MASTER_DB_NAME at all,
        # matching how these are actually saved to Paleographer/.env by the settings
        # shell (see Parish.pmt's field_remap front matter).
        "CHURCH_IMAGE_DIR": "Parish",
        "CHURCH_MASTER_DB_NAME": "parish_register.json",
    }
    for key in ("IMAGE_DIR", "MASTER_DB_NAME"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(sys, "argv", ["Paleographer.py"])
    monkeypatch.setattr("google.genai.Client", lambda *a, **k: object())

    sys.modules.pop("Paleographer", None)
    return importlib.import_module("Paleographer")


def test_source_dir_resolves_from_prefixed_key_alone(minimal_paleographer_env):
    module = minimal_paleographer_env
    assert module.SOURCE_DIR.replace("\\", "/").endswith("/Parish")


def test_master_db_resolves_from_prefixed_key_alone(minimal_paleographer_env):
    module = minimal_paleographer_env
    assert module.MASTER_DB.replace("\\", "/").endswith("/JSON/parish_register.json")


def test_load_master_db_writes_record_type_name(minimal_paleographer_env):
    module = minimal_paleographer_env
    data = module.load_master_db()
    assert data["record_type_name"] == "Parish"
