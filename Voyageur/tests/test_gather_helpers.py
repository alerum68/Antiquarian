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


def test_cleanup_stale_gather_files_removes_matching_prefix_regardless_of_age(tmp_path):
    old_stale = tmp_path / "TMP_A_2026-08-01 - Ohio.json"
    old_stale.write_text("{}")
    os.utime(old_stale, (1000, 1000))
    old_stale_image = tmp_path / "TMP_A_Images_page1.jpg"
    old_stale_image.write_bytes(b"x")
    os.utime(old_stale_image, (1000, 1000))

    gh.cleanup_stale_gather_files(tmp_path, "TMP_A_")

    assert not old_stale.exists()
    assert not old_stale_image.exists()


def test_cleanup_stale_gather_files_leaves_other_prefixes_and_unrelated_files_alone(tmp_path):
    other_tool = tmp_path / "TMP_FS_2026-08-01 - Ohio.json"
    other_tool.write_text("{}")
    unrelated = tmp_path / "vacation_photo.jpg"
    unrelated.write_bytes(b"x")

    gh.cleanup_stale_gather_files(tmp_path, "TMP_A_")

    assert other_tool.exists()
    assert unrelated.exists()


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
    abs_base = tmp_path / "AbsCensus"

    result = gh.resolve_census_image_dir(str(abs_base), "", "1900 US Federal Census", "USA - Ohio")

    assert result == abs_base / "1900 US Federal Census" / "USA - Ohio"
    assert result.exists()


def test_resolve_census_image_dir_relative_to_media_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_DIR", "Media")
    program_dir = tmp_path / "program"

    result = gh.resolve_census_image_dir("Census", str(program_dir), "1900 US Federal Census", "Ohio")

    assert result == program_dir / "Media" / "Census" / "1900 US Federal Census" / "Ohio"
    assert result.exists()


def test_write_archivist_json_file_writes_expected_key(monkeypatch):
    calls = []
    monkeypatch.setattr(gh, "set_key", lambda p, k, v: calls.append((p, k, v)))

    gh.write_archivist_json_file("1900 - Ohio.json")

    assert len(calls) == 1
    path, key, value = calls[0]
    assert key == "JSON_FILE"
    assert value == "1900 - Ohio.json"
    assert path.endswith(os.path.join("Archivist", ".env"))
