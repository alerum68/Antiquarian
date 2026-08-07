"""Tests for LAC.py's Commissioner-scaffold building blocks: MASTER_DB path resolution
(mirroring Paleographer.py's own resolve_setting), load/save, and scaffold-sheet
deduplicated append. See the Voyageur-Parish-Scrip-scaffold design spec."""
import os

import pytest

import LAC


def test_resolve_generic_setting_prefers_prefixed_key(monkeypatch):
    monkeypatch.setenv("CHURCH_MASTER_DB_NAME", "parish_register.json")
    monkeypatch.delenv("MASTER_DB_NAME", raising=False)
    assert LAC.resolve_generic_setting("Parish", "MASTER_DB_NAME") == "parish_register.json"


def test_resolve_generic_setting_falls_back_to_generic_key(monkeypatch):
    monkeypatch.delenv("CHURCH_MASTER_DB_NAME", raising=False)
    monkeypatch.setenv("MASTER_DB_NAME", "fallback.json")
    assert LAC.resolve_generic_setting("Parish", "MASTER_DB_NAME") == "fallback.json"


def test_resolve_master_db_path_matches_paleographer_convention(monkeypatch, tmp_path):
    monkeypatch.setenv("CHURCH_MASTER_DB_NAME", "parish_register.json")
    monkeypatch.setenv("JSON_DIR", "JSON")
    path = LAC.resolve_master_db_path("Parish", str(tmp_path))
    assert path == str(tmp_path / "JSON" / "parish_register.json")


def test_resolve_master_db_path_raises_on_empty_master_db_name(monkeypatch, tmp_path):
    monkeypatch.delenv("CHURCH_MASTER_DB_NAME", raising=False)
    monkeypatch.delenv("MASTER_DB_NAME", raising=False)
    with pytest.raises(RuntimeError, match="MASTER_DB_NAME"):
        LAC.resolve_master_db_path("Parish", str(tmp_path))


def test_load_master_db_returns_default_shape_when_missing(tmp_path):
    master_db_path = str(tmp_path / "does_not_exist.json")
    data = LAC.load_master_db(master_db_path, "Test Collection", "Parish")
    assert data == {
        "collection_title": "Test Collection", "record_type_name": "Parish", "sheets": [],
        "total_spent": 0.0, "total_pages_processed": 0, "pending_batch_jobs": [],
    }


def test_save_and_load_master_db_round_trip(tmp_path):
    master_db_path = str(tmp_path / "JSON" / "parish_register.json")
    data = {"collection_title": "Test", "record_type_name": "Parish", "sheets": [{"page_id": "p1"}]}
    LAC.save_master_db(master_db_path, data)
    assert LAC.load_master_db(master_db_path, "Test", "Parish") == data


def test_append_scaffold_sheets_adds_new_sheets():
    master_data = {"sheets": []}
    new_sheets = [
        {"page_id": "p1", "document_metadata": {"file_name": "abc.jpg"}, "records": []},
        {"page_id": "p2", "document_metadata": {"file_name": "def.jpg"}, "records": []},
    ]
    LAC.append_scaffold_sheets(master_data, new_sheets)
    assert len(master_data["sheets"]) == 2


def test_append_scaffold_sheets_dedups_by_file_name():
    existing_sheet = {"page_id": "p1", "document_metadata": {"file_name": "abc.jpg"}, "records": []}
    master_data = {"sheets": [existing_sheet]}
    duplicate_sheet = {"page_id": "p1-retry", "document_metadata": {"file_name": "abc.jpg"}, "records": []}
    LAC.append_scaffold_sheets(master_data, [duplicate_sheet])
    assert master_data["sheets"] == [existing_sheet]


def test_validate_master_db_against_commissioner_warns_and_does_not_raise(capsys):
    bad_data = {"collection_title": "Bad", "sheets": [{"records": "not-a-list"}]}
    LAC.validate_master_db_against_commissioner(bad_data, "Parish", "Bad Collection")
    captured = capsys.readouterr()
    assert "[WARN]" in captured.out
    assert "Bad Collection" in captured.out


def test_resolve_record_type_maps_parish_and_scrip():
    assert LAC._resolve_record_type("parish") == "Parish"
    assert LAC._resolve_record_type("scrip") == "Scrip"


def test_resolve_record_type_exits_on_empty(capsys):
    with pytest.raises(SystemExit):
        LAC._resolve_record_type("")
    assert "[ERROR]" in capsys.readouterr().out
