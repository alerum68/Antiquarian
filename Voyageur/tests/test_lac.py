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


import lac_client


def test_download_volume_assets_writes_one_scaffold_sheet_per_asset(monkeypatch, tmp_path):
    def fake_download_pid_bundle(pid, media_dir):
        return {
            "pid": pid, "lac_catalog_title": "Test", "reel_numbers": [], "series_code": "RG15-D-II-8-b",
            "source_documents": [
                {"document_type": "Affidavit", "media_path": str(tmp_path / pid / "asset1.jpg"),
                 "lac_pid": pid, "lac_asset_id": "asset1", "source": "LAC"},
            ],
        }
    monkeypatch.setattr(LAC, "download_pid_bundle", fake_download_pid_bundle)

    checkpoint_path = str(tmp_path / "checkpoint.json")
    master_db_path = str(tmp_path / "scrip_records.json")

    result = LAC.download_volume_assets(["pid1"], str(tmp_path), checkpoint_path,
                                        master_db_path, "Scrip", "Test Collection")

    assert result["downloaded_pids"] == ["pid1"]
    master_data = LAC.load_master_db(master_db_path, "Test Collection", "Scrip")
    assert len(master_data["sheets"]) == 1
    assert master_data["sheets"][0]["document_metadata"]["file_name"] == "asset1.jpg"
    assert master_data["sheets"][0]["records"][0]["participants"] == []


def test_download_volume_assets_skips_already_downloaded_pid(monkeypatch, tmp_path):
    calls = []
    def fake_download_pid_bundle(pid, media_dir):
        calls.append(pid)
        return {"source_documents": []}
    monkeypatch.setattr(LAC, "download_pid_bundle", fake_download_pid_bundle)

    checkpoint_path = str(tmp_path / "checkpoint.json")
    LAC.save_checkpoint(checkpoint_path, {"pids": ["pid1"], "downloaded_pids": ["pid1"], "failed_pids": {}})
    master_db_path = str(tmp_path / "scrip_records.json")

    LAC.download_volume_assets(["pid1"], str(tmp_path), checkpoint_path, master_db_path, "Scrip", "Test")

    assert calls == []


def test_download_volume_assets_records_failure_without_writing_scaffold(monkeypatch, tmp_path):
    def fake_download_pid_bundle(pid, media_dir):
        raise lac_client.LacCallError("boom")
    monkeypatch.setattr(LAC, "download_pid_bundle", fake_download_pid_bundle)

    checkpoint_path = str(tmp_path / "checkpoint.json")
    master_db_path = str(tmp_path / "scrip_records.json")

    result = LAC.download_volume_assets(["pid1"], str(tmp_path), checkpoint_path, master_db_path, "Scrip", "Test")

    assert result["failed_pids"] == {"pid1": "boom"}
    assert not os.path.exists(master_db_path)


def test_download_volume_assets_multiworker_no_op_when_all_downloaded(tmp_path):
    checkpoint_path = str(tmp_path / "checkpoint.json")
    LAC.save_checkpoint(checkpoint_path, {"pids": ["pid1"], "downloaded_pids": ["pid1"], "failed_pids": {}})
    master_db_path = str(tmp_path / "scrip_records.json")

    result = LAC.download_volume_assets_multiworker(["pid1"], str(tmp_path), checkpoint_path,
                                                     master_db_path, "Scrip", "Test", max_workers=2)

    assert result["downloaded_pids"] == ["pid1"]


def test_retrieve_volume_threads_master_db_params_to_sequential_path(monkeypatch, tmp_path):
    monkeypatch.setattr(LAC, "retrieve_volume_pids",
                        lambda vol, cookies, checkpoint_path, archival_number: ["pid1"])
    monkeypatch.setattr(LAC, "download_pid_bundle", lambda pid, media_dir: {
        "source_documents": [{"media_path": str(tmp_path / "asset1.jpg"), "lac_asset_id": "asset1"}],
    })
    checkpoint_path = str(tmp_path / "checkpoint.json")
    master_db_path = str(tmp_path / "scrip_records.json")

    LAC.retrieve_volume("1325", {}, str(tmp_path), checkpoint_path, master_db_path, "Scrip", "Test Collection")

    master_data = LAC.load_master_db(master_db_path, "Test Collection", "Scrip")
    assert len(master_data["sheets"]) == 1
