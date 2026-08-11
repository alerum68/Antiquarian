import os
import time as time_module

import pytest

import _gather_helpers as gh


def test_launch_gather_browser_opens_url_and_returns_start_time(monkeypatch, capsys):
    opened = {}
    monkeypatch.setattr(gh.webbrowser, "open", lambda url: opened.setdefault("url", url))
    monkeypatch.setattr(gh.time, "time", lambda: 12345.0)

    start_time = gh.launch_gather_browser("https://example.com/record?id=1")

    assert start_time == 12345.0
    assert opened["url"] == "https://example.com/record?id=1&mgs_auto=1"
    captured = capsys.readouterr()
    assert "[System] Launching browser..." in captured.out
    assert "Waiting for Tampermonkey downloads" in captured.out


def test_wait_for_downloaded_json_finds_newest_matching_file(tmp_path, capsys):
    start_time = time_module.time()

    old = tmp_path / "TMP_A_old.json"
    old.write_text("{}")
    os.utime(old, (start_time - 100, start_time - 100))

    checkpoint = tmp_path / "TMP_A_run[checkpoint].json"
    checkpoint.write_text("{}")
    os.utime(checkpoint, (start_time + 1, start_time + 1))

    wrong_prefix = tmp_path / "TMP_FS_other.json"
    wrong_prefix.write_text("{}")
    os.utime(wrong_prefix, (start_time + 1, start_time + 1))

    newest = tmp_path / "TMP_A_final.json"
    newest.write_text("{}")
    os.utime(newest, (start_time + 2, start_time + 2))

    result = gh.wait_for_downloaded_json(tmp_path, "TMP_A_", start_time, "Final JSON")

    assert result == newest
    assert "[System] Detected Final JSON: TMP_A_final.json" in capsys.readouterr().out


def test_wait_for_downloaded_json_keyboard_interrupt_exits(tmp_path, monkeypatch, capsys):
    def raise_interrupt(_):
        raise KeyboardInterrupt

    monkeypatch.setattr(gh.time, "sleep", raise_interrupt)

    with pytest.raises(SystemExit) as exc_info:
        gh.wait_for_downloaded_json(tmp_path, "TMP_A_", time_module.time(), "Final JSON")

    assert exc_info.value.code == 0
    assert "Operation cancelled by user" in capsys.readouterr().out


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

    count = gh.move_downloaded_images(downloads, "TMP_A_Images_", start_time, target)

    assert count == 2
    assert (target / "page1.jpg").exists()
    assert (target / "page2.jpg").exists()
    assert unrelated.exists()


def test_move_downloaded_images_tolerates_failed_move(tmp_path, monkeypatch, capsys):
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    target = tmp_path / "target"
    target.mkdir()
    start_time = time_module.time()
    (downloads / "TMP_A_Images_bad.jpg").write_bytes(b"x")
    os.utime(downloads / "TMP_A_Images_bad.jpg", (start_time + 5, start_time + 5))

    def fail_move(src, dst):
        raise OSError("locked")

    monkeypatch.setattr(gh, "move_with_retry", fail_move)

    count = gh.move_downloaded_images(downloads, "TMP_A_Images_", start_time, target)

    assert count == 0
    assert "[ERROR] Could not move" in capsys.readouterr().out


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
    monkeypatch.setattr(gh, "set_key", lambda path, key, value: calls.append((path, key, value)))

    gh.write_archivist_json_file("1900 - Ohio.json")

    assert len(calls) == 1
    path, key, value = calls[0]
    assert key == "JSON_FILE"
    assert value == "1900 - Ohio.json"
    assert path.endswith(os.path.join("Archivist", ".env"))
