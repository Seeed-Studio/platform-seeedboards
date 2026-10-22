"""Unit tests for scripts/ci/build_examples.py helpers."""

from pathlib import Path

from build_examples import (
    extract_envs,
    find_projects,
    has_repo_platform,
    localize_platform,
    uses_framework,
)

URL = "https://github.com/Seeed-Studio/platform-seeedboards.git#v3"


def test_localize_repo_url(tmp_path):
    text = "[env:b]\nplatform = %s\nboard = b\n" % URL
    localized = localize_platform(text, tmp_path)
    assert "platform = %s" % tmp_path in localized
    assert URL not in localized


def test_has_repo_platform():
    assert has_repo_platform("platform = %s\n" % URL)
    assert not has_repo_platform("platform = https://example.com/x.git\n")
    assert not has_repo_platform("board = b\n")


def test_extract_envs(tmp_path):
    ini = tmp_path / "platformio.ini"
    ini.write_text(
        "[env]\nplatform = %s\n\n[env:a]\nboard = a\n\n[env:b]\nboard = b\n"
        % URL, encoding="utf-8")
    assert extract_envs(ini) == ["a", "b"]


def test_find_projects_skips_pio(tmp_path):
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "platformio.ini").write_text("[env:a]\n")
    (tmp_path / "demo" / ".pio" / "build").mkdir(parents=True)
    (tmp_path / "demo" / ".pio" / "build" / "platformio.ini").write_text("[env:x]\n")
    assert find_projects(tmp_path) == [tmp_path / "demo"]


def test_uses_framework():
    text = "[env:a]\nframework = arduino, zephyr\n"
    assert uses_framework(text, "arduino")
    assert uses_framework(text, "zephyr")
    assert not uses_framework(text, "espidf")