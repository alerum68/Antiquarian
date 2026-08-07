"""
Confirms get_processed_files/merge_sheets correctly treat Voyageur-written scaffold sheets
(document_metadata present, every record's participants empty) as unprocessed, and that
merge_sheets replaces a placeholder sheet with Paleographer's own real AI-filled sheet for
the same file_name in place, instead of appending a duplicate - see the
Voyageur-Parish-Scrip-scaffold design spec's Architecture section (Fix 1a/1b).
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
        "EXTRACTION_ENGINE": "api",
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


def _placeholder_sheet(file_name):
    return {
        "page_id": file_name,
        "document_metadata": {"file_name": file_name, "file_type": "jpg"},
        "records": [{"event_type": None, "participants": []}],
    }


def _real_sheet(file_name):
    return {
        "page_id": file_name,
        "document_metadata": {"file_name": file_name, "file_type": "jpg"},
        "records": [{
            "event_type": "Baptism",
            "participants": [{"role_name": "Child", "full_name": "Jean Gagnon", "sex": "M", "is_priest": False}],
        }],
    }


def test_get_processed_files_excludes_placeholder_scaffold_sheet(minimal_paleographer_env):
    module = minimal_paleographer_env
    master_data = {"sheets": [_placeholder_sheet("abc123.jpg")]}
    assert module.get_processed_files(master_data) == set()


def test_get_processed_files_includes_real_sheet(minimal_paleographer_env):
    module = minimal_paleographer_env
    master_data = {"sheets": [_real_sheet("abc123.jpg")]}
    assert module.get_processed_files(master_data) == {"abc123.jpg"}


def test_get_processed_files_ignores_sheet_with_no_records(minimal_paleographer_env):
    module = minimal_paleographer_env
    sheet = {"page_id": "abc123.jpg", "document_metadata": {"file_name": "abc123.jpg"}, "records": []}
    master_data = {"sheets": [sheet]}
    assert module.get_processed_files(master_data) == set()


def test_merge_sheets_replaces_placeholder_with_real_sheet_same_file_name(minimal_paleographer_env):
    module = minimal_paleographer_env
    master_data = {"sheets": [_placeholder_sheet("abc123.jpg")]}
    real_sheet = _real_sheet("abc123.jpg")

    module.merge_sheets(master_data, [real_sheet])

    assert len(master_data["sheets"]) == 1
    assert master_data["sheets"][0] is real_sheet


def test_merge_sheets_appends_when_no_matching_placeholder(minimal_paleographer_env):
    module = minimal_paleographer_env
    master_data = {"sheets": [_real_sheet("abc123.jpg")]}
    other_sheet = _real_sheet("def456.jpg")

    module.merge_sheets(master_data, [other_sheet])

    assert len(master_data["sheets"]) == 2
    assert master_data["sheets"][1] is other_sheet


def test_merge_sheets_appends_when_master_sheets_missing(minimal_paleographer_env):
    module = minimal_paleographer_env
    master_data = {}
    new_sheet = _real_sheet("abc123.jpg")

    module.merge_sheets(master_data, [new_sheet])

    assert master_data["sheets"] == [new_sheet]
