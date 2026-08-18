import os
import time as time_module

import pytest

import _gather_helpers as gh


def test_build_gather_launch_url_appends_auto_and_run_id_with_existing_query():
    result = gh.build_gather_launch_url("https://example.com/record?id=1", "abc123")
    assert result == "https://example.com/record?id=1&mgs_auto=1&mgs_run=abc123"


def test_build_gather_launch_url_appends_auto_and_run_id_with_no_existing_query():
    result = gh.build_gather_launch_url("https://example.com/record", "abc123")
    assert result == "https://example.com/record?mgs_auto=1&mgs_run=abc123"


def test_launch_gather_browser_opens_url_and_returns_start_time(monkeypatch, capsys):
    opened = {}
    monkeypatch.setattr(gh.webbrowser, "open", lambda url: opened.setdefault("url", url))
    monkeypatch.setattr(gh.time, "time", lambda: 12345.0)

    start_time = gh.launch_gather_browser("https://example.com/record?id=1", "abc123")

    assert start_time == 12345.0
    assert opened["url"] == "https://example.com/record?id=1&mgs_auto=1&mgs_run=abc123"
    captured = capsys.readouterr()
    assert "[System] Launching browser..." in captured.out
    assert "Waiting for Tampermonkey downloads" in captured.out


def test_wait_for_final_json_event_finds_already_existing_file(tmp_path, capsys):
    (tmp_path / "TMP_A_abc123_final.json").write_text("{}")

    result = gh.wait_for_final_json_event(tmp_path, "TMP_A_abc123_", "Final JSON")

    assert result.name == "TMP_A_abc123_final.json"
    assert "[System] Detected Final JSON: TMP_A_abc123_final.json" in capsys.readouterr().out


def test_wait_for_final_json_event_detects_file_created_after_call(tmp_path):
    import threading as _threading
    import time as _time

    def create_after_delay():
        _time.sleep(0.2)
        (tmp_path / "TMP_A_abc123_[checkpoint through page 1].json").write_text("{}")
        _time.sleep(0.1)
        (tmp_path / "TMP_A_abc123_final.json").write_text("{}")

    _threading.Thread(target=create_after_delay, daemon=True).start()

    result = gh.wait_for_final_json_event(tmp_path, "TMP_A_abc123_", "Final JSON")

    assert result.name == "TMP_A_abc123_final.json"


def test_wait_for_final_json_event_detects_crdownload_rename_to_final(tmp_path):
    import threading as _threading
    import time as _time

    def stage_then_rename():
        _time.sleep(0.2)
        staging = tmp_path / "TMP_A_abc123_final.json.crdownload"
        staging.write_text("{}")
        _time.sleep(0.1)
        staging.replace(tmp_path / "TMP_A_abc123_final.json")

    _threading.Thread(target=stage_then_rename, daemon=True).start()

    result = gh.wait_for_final_json_event(tmp_path, "TMP_A_abc123_", "Final JSON")

    assert result.name == "TMP_A_abc123_final.json"


def test_wait_for_final_json_event_ignores_checkpoint_and_other_prefix_files(tmp_path):
    import threading as _threading
    import time as _time

    (tmp_path / "TMP_A_abc123_[checkpoint through page 1].json").write_text("{}")
    (tmp_path / "TMP_FS_xyz789_final.json").write_text("{}")

    def create_real_final():
        _time.sleep(0.2)
        (tmp_path / "TMP_A_abc123_final.json").write_text("{}")

    _threading.Thread(target=create_real_final, daemon=True).start()

    result = gh.wait_for_final_json_event(tmp_path, "TMP_A_abc123_", "Final JSON")

    assert result.name == "TMP_A_abc123_final.json"


def test_wait_for_final_json_event_keyboard_interrupt_exits(tmp_path, monkeypatch, capsys):
    def raise_interrupt(_ready):
        raise KeyboardInterrupt

    monkeypatch.setattr(gh, "_block_until_ready", raise_interrupt)

    with pytest.raises(SystemExit) as exc_info:
        gh.wait_for_final_json_event(tmp_path, "TMP_A_abc123_", "Final JSON")

    assert exc_info.value.code == 0
    assert "Operation cancelled by user" in capsys.readouterr().out


def test_move_with_retry_overwrites_existing_destination_by_default(tmp_path):
    src = tmp_path / "src.json"
    src.write_text("new")
    dst = tmp_path / "dst.json"
    dst.write_text("old")

    status = gh.move_with_retry(src, dst)

    assert status == "moved"
    assert dst.read_text() == "new"
    assert not src.exists()


def test_move_with_retry_skips_when_destination_exists_and_on_collision_skip(tmp_path):
    src = tmp_path / "src.json"
    src.write_text("new")
    dst = tmp_path / "dst.json"
    dst.write_text("old")

    status = gh.move_with_retry(src, dst, on_collision="skip")

    assert status == "skipped"
    assert dst.read_text() == "old"
    assert not src.exists()


def test_move_downloaded_images_moves_matches_and_counts(tmp_path):
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    target = tmp_path / "target"
    target.mkdir()
    start_time = time_module.time()

    (downloads / "TMP_A_Images_page1.jpg").write_bytes(b"x")
    os.utime(downloads / "TMP_A_Images_page1.jpg", (start_time + 5, start_time + 5))
    (downloads / "TMP_A_Images_page2.jpg").write_bytes(b"x")
    os.utime(downloads / "TMP_A_Images_page2.jpg", (start_time + 5, start_time + 5))
    unrelated = downloads / "other.jpg"
    unrelated.write_bytes(b"x")

    moved, skipped, failed = gh.move_downloaded_images(downloads, "TMP_A_Images_", start_time, target)

    assert moved == 2
    assert skipped == []
    assert failed == []
    assert (target / "page1.jpg").exists()
    assert (target / "page2.jpg").exists()
    assert unrelated.exists()


def test_move_downloaded_images_skips_existing_destination_when_on_collision_skip(tmp_path):
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    target = tmp_path / "target"
    target.mkdir()
    start_time = time_module.time()
    (downloads / "TMP_A_Images_page1.jpg").write_bytes(b"new")
    os.utime(downloads / "TMP_A_Images_page1.jpg", (start_time + 5, start_time + 5))
    (target / "page1.jpg").write_bytes(b"old")

    moved, skipped, failed = gh.move_downloaded_images(
        downloads, "TMP_A_Images_", start_time, target, on_collision="skip")

    assert moved == 0
    assert skipped == ["page1.jpg"]
    assert failed == []
    assert (target / "page1.jpg").read_bytes() == b"old"
    assert not (downloads / "TMP_A_Images_page1.jpg").exists()


def test_move_downloaded_images_retries_once_and_recovers_from_transient_failure(tmp_path, monkeypatch, capsys):
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    target = tmp_path / "target"
    target.mkdir()
    start_time = time_module.time()
    (downloads / "TMP_A_Images_flaky.jpg").write_bytes(b"x")
    os.utime(downloads / "TMP_A_Images_flaky.jpg", (start_time + 5, start_time + 5))

    real_move_with_retry = gh.move_with_retry
    call_count = {"n": 0}

    def flaky_move(src, dst, *args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise OSError("transient lock")
        return real_move_with_retry(src, dst, *args, **kwargs)

    monkeypatch.setattr(gh, "move_with_retry", flaky_move)
    monkeypatch.setattr(gh.time, "sleep", lambda seconds: None)

    moved, skipped, failed = gh.move_downloaded_images(downloads, "TMP_A_Images_", start_time, target)

    assert moved == 1
    assert skipped == []
    assert failed == []
    assert (target / "flaky.jpg").exists()
    assert "retrying" in capsys.readouterr().out.lower()


def test_move_downloaded_images_reports_final_failures_after_retry(tmp_path, monkeypatch, capsys):
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    target = tmp_path / "target"
    target.mkdir()
    start_time = time_module.time()
    (downloads / "TMP_A_Images_bad.jpg").write_bytes(b"x")
    os.utime(downloads / "TMP_A_Images_bad.jpg", (start_time + 5, start_time + 5))

    def fail_move(_src, _dst, *_args, **_kwargs):
        raise OSError("locked")

    monkeypatch.setattr(gh, "move_with_retry", fail_move)
    monkeypatch.setattr(gh.time, "sleep", lambda seconds: None)

    moved, skipped, failed = gh.move_downloaded_images(downloads, "TMP_A_Images_", start_time, target)

    assert moved == 0
    assert skipped == []
    assert failed == ["bad.jpg"]
    out = capsys.readouterr().out
    assert "[ERROR] Could not move" in out
    assert "[WARN]" in out
    assert "bad.jpg" in out


def test_find_orphaned_gather_runs_groups_by_run_id_and_finds_complete_run(tmp_path):
    (tmp_path / "TMP_A_stale1_1880 - USA - Ohio - ANC.json").write_text("{}")
    (tmp_path / "TMP_A_stale1_Images_00130.jpg").write_text("x")
    (tmp_path / "TMP_A_stale1_Images_00131.jpg").write_text("x")
    (tmp_path / "TMP_A_stale2_checkpoint_20.json").write_text("{}")
    (tmp_path / "TMP_A_current_1880 - USA - Ohio - ANC.json").write_text("{}")
    (tmp_path / "TMP_FS_other_final.json").write_text("{}")

    result = gh.find_orphaned_gather_runs(tmp_path, "TMP_A_", "current")

    assert set(result.keys()) == {"stale1", "stale2"}
    assert result["stale1"]["final"] == tmp_path / "TMP_A_stale1_1880 - USA - Ohio - ANC.json"
    assert sorted(p.name for p in result["stale1"]["images"]) == [
        "TMP_A_stale1_Images_00130.jpg", "TMP_A_stale1_Images_00131.jpg"]
    assert result["stale2"]["final"] is None
    assert len(result["stale2"]["checkpoints"]) == 1


def test_find_orphaned_gather_runs_returns_empty_dict_when_nothing_stale(tmp_path):
    (tmp_path / "TMP_A_current_1880 - USA - Ohio - ANC.json").write_text("{}")

    result = gh.find_orphaned_gather_runs(tmp_path, "TMP_A_", "current")

    assert result == {}


def test_find_orphaned_gather_runs_classifies_by_checkpoint_substring_not_name_shape(tmp_path):
    (tmp_path / "TMP_A_stale1_1880 - checkpointed notes - ANC.json").write_text("{}")
    (tmp_path / "TMP_A_stale2_FS - Some Family.json").write_text("{}")

    result = gh.find_orphaned_gather_runs(tmp_path, "TMP_A_", "current")

    assert set(result.keys()) == {"stale1", "stale2"}
    assert result["stale1"]["final"] is None
    assert [p.name for p in result["stale1"]["checkpoints"]] == [
        "TMP_A_stale1_1880 - checkpointed notes - ANC.json"]
    assert result["stale1"]["images"] == []
    assert result["stale2"]["final"] == tmp_path / "TMP_A_stale2_FS - Some Family.json"
    assert result["stale2"]["checkpoints"] == []
    assert result["stale2"]["images"] == []


def test_atomic_write_bytes_writes_content_and_leaves_no_temp_file(tmp_path):
    dest = tmp_path / "out.jpg"

    gh.atomic_write_bytes(dest, b"hello")

    assert dest.read_bytes() == b"hello"
    assert not dest.with_suffix(".jpg.tmp").exists()


def test_atomic_write_bytes_leaves_no_truncated_file_at_dest_on_failure(tmp_path, monkeypatch):
    dest = tmp_path / "out.jpg"

    def fail_replace(_self, _target):
        raise OSError("disk full")

    monkeypatch.setattr(gh.Path, "replace", fail_replace)

    with pytest.raises(OSError):
        gh.atomic_write_bytes(dest, b"hello")

    assert not dest.exists()
    assert not dest.with_suffix(".jpg.tmp").exists()


def test_resolve_census_image_dir_absolute_base(tmp_path):
    abs_base = tmp_path / "AbsMedia"
    abs_base.mkdir()
    result = gh.resolve_census_image_dir(str(abs_base), "", "", "1900", "USA", "Ohio")
    assert result == abs_base / "USA" / "1900" / "Ohio"
    assert result.exists()


def test_resolve_census_image_dir_relative_to_media_dir(tmp_path, monkeypatch):
    program_dir = tmp_path / "Program"
    monkeypatch.setenv("MEDIA_DIR", "TestMedia")
    result = gh.resolve_census_image_dir("Census", str(program_dir), "", "1900", "USA", "Ohio")
    assert result == program_dir / "TestMedia" / "Census" / "USA" / "1900" / "Ohio"


def test_resolve_census_image_dir_nests_state_county_city(tmp_path):
    abs_base = tmp_path / "AbsMedia"
    result = gh.resolve_census_image_dir(str(abs_base), "", "", "1880", "USA", "Michigan - Kent County")
    assert result == abs_base / "USA" / "1880" / "Michigan" / "Kent County"


def test_census_collection_folder_name_generic_country_no_collection_name():
    """Not a fixed US-or-Canada choice - any country plugs into the same "{year}
    {country} Census" template, uniform format, no country list to maintain."""
    assert gh.census_collection_folder_name("1880", "USA") == "1880 USA Census"
    assert gh.census_collection_folder_name("1871", "Canada") == "1871 Canada Census"
    assert gh.census_collection_folder_name("1901", "England") == "1901 England Census"
    # Absent/unrecognized country defaults to USA, this project's long-standing default.
    assert gh.census_collection_folder_name("1880", "") == "1880 USA Census"


def test_census_collection_folder_name_prefers_real_collection_name():
    """The gather's own real collection_name (Ancestry's scraped citation text, or FS's
    own collection_title) beats the generated template when one was actually captured -
    needs no country-detection logic of its own to be correct for any country."""
    assert (gh.census_collection_folder_name("1871", "Canada", "1871 Census of Canada")
           == "1871 Census of Canada")
    # Forbidden Windows path characters get stripped, same as FS.py's own
    # build_clean_census_filename() convention.
    assert (gh.census_collection_folder_name("1860", "USA", 'United States, Census: 1860')
           == "United States, Census- 1860")


def test_write_archivist_json_file_writes_expected_key(monkeypatch):
    calls = []
    monkeypatch.setattr(gh, "set_key", lambda p, k, v: calls.append((p, k, v)))

    gh.write_archivist_json_file("1900 - Ohio.json")

    assert len(calls) == 1
    path, key, value = calls[0]
    assert key == "JSON_FILE"
    assert value == "1900 - Ohio.json"
    assert path.endswith(os.path.join("Archivist", ".env"))


def test_print_incomplete_pages_warning_prints_bordered_banner(capsys):
    entries = [{"page_number": 12, "image_id": "4240106-00130"}, {"page_number": 15, "image_id": "4240106-00133"}]
    gh.print_incomplete_pages_warning(entries, "page(s)")
    out = capsys.readouterr().out
    assert "2 page(s) incomplete" in out
    assert "page 12 (image 4240106-00130)" in out
    assert "page 15 (image 4240106-00133)" in out
    assert "!" * 70 in out


def test_print_incomplete_pages_warning_prints_item_id_when_no_page_number(capsys):
    gh.print_incomplete_pages_warning([{"item_id": "1:1:MCVW-DP2"}], "item(s)")
    out = capsys.readouterr().out
    assert "item 1:1:MCVW-DP2" in out


def test_print_incomplete_pages_warning_no_output_when_empty(capsys):
    gh.print_incomplete_pages_warning([], "page(s)")
    assert capsys.readouterr().out == ""


def test_build_detailed_census_filename_with_all_fields():
    normalized_data = {
        "sheets": [{
            "records": [{
                "type_specific_fields": {
                    "country": "USA",
                    "state": "North Dakota",
                    "county": "Pembina",
                    "city": "Walhalla",
                    "enumeration_district": "34-36"
                }
            }]
        }]
    }
    result = gh.build_detailed_census_filename("1950", normalized_data, "FamilySearch")
    assert result == "Census-1950-USA-North Dakota-Pembina-Walhalla-34-36-FS.json"


def test_build_detailed_census_filename_with_missing_fields():
    normalized_data = {
        "sheets": [{
            "records": [{
                "type_specific_fields": {
                    "country": "USA",
                    "state": "",
                    "county": "",
                    "city": ""
                }
            }]
        }]
    }
    result = gh.build_detailed_census_filename("1950", normalized_data, "Ancestry")
    assert result == "Census-1950-USA-ANC.json"


from unittest.mock import patch
from pathlib import Path


def test_resolve_census_image_dir_builds_structured_path(tmp_path):
    """census_folder is a distinct level between base and country/year."""
    with patch("_gather_helpers.os.getenv", return_value=""):
        result = gh.resolve_census_image_dir(
            str(tmp_path), "", "United States Census 1880",
            "1880", "USA", "North Dakota - Pembina"
        )
    assert result == tmp_path / "United States Census 1880" / "USA" / "1880" / "North Dakota" / "Pembina"


def test_resolve_census_image_dir_no_location_parts(tmp_path):
    """Empty location_folder still produces a valid path."""
    with patch("_gather_helpers.os.getenv", return_value=""):
        result = gh.resolve_census_image_dir(
            str(tmp_path), "", "1880 USA Census", "1880", "USA", ""
        )
    assert result == tmp_path / "1880 USA Census" / "USA" / "1880"


def test_resolve_census_image_dir_omits_empty_segments(tmp_path):
    """Absent country or year are skipped, not added as empty path segments."""
    with patch("_gather_helpers.os.getenv", return_value=""):
        result = gh.resolve_census_image_dir(
            str(tmp_path), "", "Some Collection", "", "", "Pembina"
        )
    assert result == tmp_path / "Some Collection" / "Pembina"
