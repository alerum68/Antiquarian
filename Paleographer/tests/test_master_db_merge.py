"""
Confirms get_processed_files/merge_sheets correctly treat Voyageur-written scaffold sheets
(document_metadata present, every record's participants empty) as unprocessed, and that
merge_sheets replaces a placeholder sheet with Paleographer's own real AI-filled sheet for
the same file_name in place, instead of appending a duplicate - see the
Voyageur-Parish-Scrip-scaffold design spec's Architecture section (Fix 1a/1b).
"""
import importlib
import os
import sys

import pytest


# noinspection DuplicatedCode
@pytest.fixture
def minimal_paleographer_env(monkeypatch, tmp_path):
    program_dir = tmp_path / "program"
    (program_dir / "Parish").mkdir(parents=True)
    (program_dir / "JSON").mkdir(parents=True)

    env = {
        "PROGRAM_DIR": str(program_dir),
        "JSON_DIR": "JSON",
        "PALEOGRAPHER_RECORD_TYPE": "Parish",
        "MODEL_NAME": "AI Assistant-test-model",
        "AI_API_KEY": "fake-key-not-used",
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

    sys.modules.pop("Extract", None)
    return importlib.import_module("Extract")


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


def test_merge_sheets_preserves_voyageur_fields_on_placeholder_replacement(minimal_paleographer_env):
    module = minimal_paleographer_env
    placeholder = {
        "page_id": "adams_charles.pdf",
        "document_metadata": {"file_name": "adams_charles.pdf"},
        "records": [{
            "event_type": "Employment",
            "participants": [],
            "type_specific_fields": {
                "parish_of_origin": "",
                "service_history": [{"outfit_years": "1866-1868", "hbca_ref": "B.239/k/3"}],
                "hbca_references": ["B.239/k/3"],
                "keystone_urls": ["https://pam.minisisinc.com/scripts/mwimain.dll/144/x?sessionsearch"],
                "keystone_records": {"B.239/k/3": {"metadata": {"microfilm_no": "1M814"}}},
            },
        }],
    }
    real_sheet = {
        "page_id": "adams_charles.pdf",
        "document_metadata": {"file_name": "adams_charles.pdf"},
        "records": [{
            "event_type": "Employment",
            "participants": [{"role_name": "Employee", "std_given": "Charles", "std_surname": "Adams"}],
            "type_specific_fields": {},
        }],
    }
    master_data = {"sheets": [placeholder]}
    module.merge_sheets(master_data, [real_sheet])

    merged = master_data["sheets"][0]["records"][0]
    assert merged["participants"][0]["std_given"] == "Charles"
    tsf = merged["type_specific_fields"]
    assert tsf["service_history"][0]["hbca_ref"] == "B.239/k/3"
    assert tsf["hbca_references"] == ["B.239/k/3"]
    assert tsf["keystone_urls"] == placeholder["records"][0]["type_specific_fields"]["keystone_urls"]
    assert tsf["keystone_records"]["B.239/k/3"]["metadata"]["microfilm_no"] == "1M814"


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


def _valid_parish_master_db():
    return {
        "collection_title": "Test Volume",
        "record_type_name": "Parish",
        "sheets": [
            {
                "page_id": "abc123.jpg",
                "document_metadata": {"file_name": "abc123.jpg", "file_type": "jpg"},
                "records": [
                    {
                        "event_type": "Baptism",
                        "participants": [
                            {
                                "role_name": "Primary",
                                "std_given": "Jean",
                                "std_surname": "Gagnon",
                                "sex": "M",
                                "is_priest": False,
                            }
                        ],
                    }
                ],
            }
        ],
    }


def test_save_master_db_valid_shape_writes_file_and_prints_no_warning(minimal_paleographer_env, capsys):
    module = minimal_paleographer_env
    master_data = _valid_parish_master_db()

    module.save_master_db(master_data)

    captured = capsys.readouterr()
    assert "[WARN]" not in captured.out
    assert os.path.exists(module.MASTER_DB)


def test_save_master_db_bad_shape_still_writes_file_and_logs_warning(minimal_paleographer_env, capsys):
    module = minimal_paleographer_env
    master_data = {
        "collection_title": "Bad",
        "record_type_name": "Parish",
        "sheets": [{"records": "not-a-list"}],
    }

    module.save_master_db(master_data)

    captured = capsys.readouterr()
    # The warning label is save_master_db's own COLLECTION_TITLE global (derived from the
    # VOLUME_TITLE env var the minimal_paleographer_env fixture sets to "Test Volume"), not
    # master_data's own "collection_title" key - the two are independent.
    assert "[WARN] Commissioner validation failed for 'Test Volume'" in captured.out
    assert os.path.exists(module.MASTER_DB)


def test_save_master_db_injects_collection_metadata_from_citation_overrides(
        minimal_paleographer_env, monkeypatch, tmp_path):
    monkeypatch.setenv("CITATION_TEXT", "Override Citation Text")
    monkeypatch.setenv("CALL_NUMBER", "12345")
    monkeypatch.delenv("REGISTER_SOURCE_ID", raising=False)

    module = minimal_paleographer_env
    db_path = tmp_path / "test_master_db.json"
    module.MASTER_DB = str(db_path)

    test_data = {"collection_title": "Test Title", "sheets": []}
    module.save_master_db(test_data)

    import json
    with open(db_path, "r", encoding="utf-8") as f:
        saved = json.load(f)

    assert "collection_metadata" in saved
    assert saved["collection_metadata"]["CITATION_TEXT"] == "Override Citation Text"
    assert saved["collection_metadata"]["CALL_NUMBER"] == "12345"
    assert "REGISTER_SOURCE_ID" not in saved["collection_metadata"]
