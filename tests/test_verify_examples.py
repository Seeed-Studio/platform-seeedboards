"""Unit tests for scripts/ci/verify_examples.py."""

import json

from verify_examples import check_examples

URL = "https://github.com/Seeed-Studio/platform-seeedboards.git#v3"


def _board(path, board_id, frameworks):
    path.write_text(json.dumps({
        "name": board_id,
        "url": "https://example.com",
        "vendor": "Test",
        "build": {"chip_family": "samd", "mcu": "test"},
        "frameworks": frameworks,
    }), encoding="utf-8")


def _ini(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_every_pair_has_demo(tmp_path):
    boards = tmp_path / "boards"
    boards.mkdir()
    _board(boards / "b.json", "b", ["arduino"])
    _ini(tmp_path / "examples" / "blink" / "platformio.ini",
         "[env:b]\nplatform = %s\nframework = arduino\nboard = b\n" % URL)
    assert check_examples(tmp_path / "examples", boards) == []


def test_shared_env_inheritance(tmp_path):
    boards = tmp_path / "boards"
    boards.mkdir()
    _board(boards / "b.json", "b", ["espidf"])
    _ini(tmp_path / "examples" / "blink" / "platformio.ini",
         "[env]\nplatform = %s\nframework = espidf\n\n[env:b]\nboard = b\n" % URL)
    assert check_examples(tmp_path / "examples", boards) == []


def test_missing_demo_is_an_error(tmp_path):
    boards = tmp_path / "boards"
    boards.mkdir()
    _board(boards / "b.json", "b", ["arduino"])
    _board(boards / "c.json", "c", ["arduino"])
    _ini(tmp_path / "examples" / "blink" / "platformio.ini",
         "[env:b]\nplatform = %s\nframework = arduino\nboard = b\n" % URL)
    errors = check_examples(tmp_path / "examples", boards)
    assert any("'c' has no demo" in e for e in errors)


def test_wrong_platform_url_is_an_error(tmp_path):
    boards = tmp_path / "boards"
    boards.mkdir()
    _board(boards / "b.json", "b", ["arduino"])
    _ini(tmp_path / "examples" / "blink" / "platformio.ini",
         "[env:b]\nplatform = https://example.com/old.git\n"
         "framework = arduino\nboard = b\n")
    errors = check_examples(tmp_path / "examples", boards)
    assert any("maintained repo URL" in e for e in errors)


def test_unknown_board_is_an_error(tmp_path):
    boards = tmp_path / "boards"
    boards.mkdir()
    _board(boards / "b.json", "b", ["arduino"])
    _ini(tmp_path / "examples" / "blink" / "platformio.ini",
         "[env:ghost]\nplatform = %s\nframework = arduino\nboard = ghost\n" % URL)
    errors = check_examples(tmp_path / "examples", boards)
    assert any("unknown board" in e for e in errors)