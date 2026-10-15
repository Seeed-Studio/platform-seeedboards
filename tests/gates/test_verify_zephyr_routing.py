"""Unit tests for scripts/ci/verify_zephyr_routing.py.

Valid routing/fixes tree plus one counterexample per rule, built on
synthetic trees in tmp_path.
"""

import json
import shutil

import pytest

from verify_zephyr_routing import (  # noqa: E402  (conftest sys.path)
    load_platform_packages,
    load_zephyr_boards,
    verify_zephyr_routing,
)

PACKAGES = {"framework-zephyr-test", "framework-zephyr-other"}


def make_zephyr_board(board_id, package="framework-zephyr-test", board_name="xiao_test"):
    return {
        "board_id": board_id,
        "package": package,
        "board_name": board_name,
        "family": "nrf",
        "variant": board_name + "/soc/cpuapp",
    }


@pytest.fixture()
def routing_tree(tmp_path):
    """A valid synthetic repo: one zephyr board, matching per-family board
    dir with a fixes/ directory (one patch + one override + baseline)."""
    zephyr_root = tmp_path / "zephyr"
    board_dir = zephyr_root / "nrf" / "boards" / "seeed" / "xiao_test"
    board_dir.mkdir(parents=True)
    (board_dir / "board.yml").write_text("board:\n  name: xiao_test\n", encoding="utf-8")

    fixes_dir = board_dir / "fixes"
    (fixes_dir / "drivers" / "adc").mkdir(parents=True)
    (fixes_dir / "drivers" / "adc" / "adc_stm32.c.patch").write_text(
        "--- a\n+++ b\n", encoding="utf-8"
    )
    override_rel = "drivers/usb/udc_stm32.c"
    (fixes_dir / "drivers" / "usb").mkdir(parents=True)
    (fixes_dir / "drivers" / "usb" / "udc_stm32.c").write_text(
        "/* override */\n", encoding="utf-8"
    )
    sha = "a" * 64
    sha2 = "b" * 64
    (fixes_dir / "fixes.baseline").write_text(
        "drivers/adc/adc_stm32.c %s\ndrivers/usb/udc_stm32.c %s\n" % (sha, sha2),
        encoding="utf-8",
    )

    boards = {"seeed-xiao-test": make_zephyr_board("seeed-xiao-test")}
    return zephyr_root, boards


class TestValidTree:
    def test_valid_tree_passes(self, routing_tree):
        zephyr_root, boards = routing_tree
        assert verify_zephyr_routing(boards, PACKAGES, zephyr_root) == []

    def test_board_without_fixes_dir_is_ok(self, routing_tree):
        zephyr_root, boards = routing_tree
        # A board whose directory ships no fixes/ is a no-op, not an error
        # (nRF54 boards ship none).
        shutil.rmtree(zephyr_root / "nrf" / "boards" / "seeed" / "xiao_test" / "fixes")
        assert verify_zephyr_routing(boards, PACKAGES, zephyr_root) == []


class TestChainClosure:
    def test_package_not_in_platform_json(self, routing_tree):
        zephyr_root, boards = routing_tree
        boards["seeed-xiao-test"]["package"] = "framework-ghost"
        errors = verify_zephyr_routing(boards, PACKAGES, zephyr_root)
        assert any("not declared in platform.json" in e for e in errors)

    def test_board_dir_missing(self, routing_tree):
        zephyr_root, boards = routing_tree
        boards["seeed-xiao-test"]["board_name"] = "xiao_missing"
        boards["seeed-xiao-test"]["variant"] = "xiao_missing/soc/cpuapp"
        errors = verify_zephyr_routing(boards, PACKAGES, zephyr_root)
        assert any("no zephyr/nrf/boards/seeed/xiao_missing/" in e for e in errors)

    def test_variant_board_name_mismatch(self, routing_tree):
        zephyr_root, boards = routing_tree
        boards["seeed-xiao-test"]["variant"] = "xiao_other/soc/cpuapp"
        errors = verify_zephyr_routing(boards, PACKAGES, zephyr_root)
        assert any("does not match the variant-derived" in e for e in errors)

    def test_missing_package_key(self, routing_tree):
        zephyr_root, _ = routing_tree
        boards = {
            "seeed-xiao-test": {
                "package": None,
                "board_name": "xiao_test",
                "family": "nrf",
                "variant": "xiao_test/soc/cpuapp",
            }
        }
        errors = verify_zephyr_routing(boards, PACKAGES, zephyr_root)
        assert any("no build.zephyr.package" in e for e in errors)


class TestFixesLayout:
    def test_fix_without_baseline_entry(self, routing_tree):
        zephyr_root, boards = routing_tree
        fixes_dir = zephyr_root / "nrf" / "boards" / "seeed" / "xiao_test" / "fixes"
        (fixes_dir / "drivers" / "ghost.c").write_text("x\n", encoding="utf-8")
        errors = verify_zephyr_routing(boards, PACKAGES, zephyr_root)
        assert any("has no fixes.baseline entry" in e for e in errors)

    def test_baseline_without_fix_file(self, routing_tree):
        zephyr_root, boards = routing_tree
        fixes_dir = zephyr_root / "nrf" / "boards" / "seeed" / "xiao_test" / "fixes"
        with open(fixes_dir / "fixes.baseline", "a", encoding="utf-8") as fp:
            fp.write("drivers/ghost.c %s\n" % ("c" * 64))
        errors = verify_zephyr_routing(boards, PACKAGES, zephyr_root)
        assert any("no fix file" in e for e in errors)

    def test_missing_baseline_file(self, routing_tree):
        zephyr_root, boards = routing_tree
        fixes_dir = zephyr_root / "nrf" / "boards" / "seeed" / "xiao_test" / "fixes"
        (fixes_dir / "fixes.baseline").unlink()
        errors = verify_zephyr_routing(boards, PACKAGES, zephyr_root)
        assert any("has no fixes.baseline" in e for e in errors)

    def test_fixes_dir_for_unknown_board(self, routing_tree):
        zephyr_root, boards = routing_tree
        ghost = zephyr_root / "nrf" / "boards" / "seeed" / "xiao_ghost" / "fixes"
        ghost.mkdir(parents=True)
        (ghost / "fixes.baseline").write_text("", encoding="utf-8")
        errors = verify_zephyr_routing(boards, PACKAGES, zephyr_root)
        assert any("no board declares" in e for e in errors)

    def test_unparseable_baseline_line(self, routing_tree):
        zephyr_root, boards = routing_tree
        fixes_dir = zephyr_root / "nrf" / "boards" / "seeed" / "xiao_test" / "fixes"
        with open(fixes_dir / "fixes.baseline", "a", encoding="utf-8") as fp:
            fp.write("garbage-line-without-sha\n")
        errors = verify_zephyr_routing(boards, PACKAGES, zephyr_root)
        assert any("unparseable baseline line" in e for e in errors)


class TestLoader:
    def test_load_zephyr_boards(self, tmp_path):
        (tmp_path / "a.json").write_text(
            json.dumps(
                {
                    "name": "A", "url": "https://x", "vendor": "V",
                    "frameworks": ["zephyr"],
                    "build": {
                        "family": "nrf",
                        "zephyr": {
                            "package": "p",
                            "board_name": "n",
                            "variant": "n/soc/cpuapp",
                        },
                    },
                }
            ),
            encoding="utf-8",
        )
        (tmp_path / "b.json").write_text(
            json.dumps(
                {"name": "B", "url": "https://x", "vendor": "V", "frameworks": ["arduino"]}
            ),
            encoding="utf-8",
        )
        boards = load_zephyr_boards(tmp_path)
        assert set(boards) == {"a"}
        assert boards["a"] == {
            "package": "p",
            "board_name": "n",
            "family": "nrf",
            "variant": "n/soc/cpuapp",
        }


class TestRepoGate:
    def test_repo_routing_is_clean(self, repo_root):
        errors = verify_zephyr_routing(
            load_zephyr_boards(repo_root / "boards"),
            load_platform_packages(repo_root / "platform.json"),
            repo_root / "zephyr",
        )
        assert errors == []
