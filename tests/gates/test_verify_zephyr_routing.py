"""Unit tests for scripts/ci/verify_zephyr_routing.py.

Valid mapping tree plus one counterexample per rule, built on synthetic
trees in tmp_path.
"""

import json

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
    dir, fixes.yml section, and patches/overrides dirs."""
    zephyr_root = tmp_path / "zephyr"
    (zephyr_root / "nrf" / "boards" / "seeed" / "xiao_test").mkdir(parents=True)
    (zephyr_root / "nrf" / "boards" / "seeed" / "xiao_test" / "board.yml").write_text(
        "board:\n  name: xiao_test\n", encoding="utf-8"
    )
    (zephyr_root / "patches" / "xiao_test").mkdir(parents=True)
    (zephyr_root / "patches" / "xiao_test" / "0001-demo.patch").write_text(
        "--- a\n+++ b\n", encoding="utf-8"
    )
    (zephyr_root / "overrides" / "xiao_test").mkdir(parents=True)
    override_rel = "drivers/usb/udc_stm32.c"
    override_path = zephyr_root / "overrides" / "xiao_test" / override_rel
    override_path.parent.mkdir(parents=True)
    override_path.write_text("/* override */\n", encoding="utf-8")

    fixes = {
        "boards": {
            "xiao_test": {
                "fixes": [
                    {
                        "id": "demo-patch",
                        "type": "patch",
                        "path": "0001-demo.patch",
                        "target": "drivers/adc/adc_stm32.c",
                    },
                    {
                        "id": "demo-override",
                        "type": "override",
                        "path": override_rel,
                        "target": override_rel,
                    },
                ]
            }
        }
    }
    boards = {"seeed-xiao-test": make_zephyr_board("seeed-xiao-test")}
    return zephyr_root, boards, fixes


class TestValidTree:
    def test_valid_tree_passes(self, routing_tree):
        zephyr_root, boards, fixes = routing_tree
        assert verify_zephyr_routing(boards, PACKAGES, zephyr_root, fixes) == []

    def test_missing_fixes_yml_is_ok(self, routing_tree):
        zephyr_root, boards, _ = routing_tree
        assert verify_zephyr_routing(boards, PACKAGES, zephyr_root, {}) == []


class TestChainClosure:
    def test_package_not_in_platform_json(self, routing_tree):
        zephyr_root, boards, fixes = routing_tree
        boards["seeed-xiao-test"]["package"] = "framework-ghost"
        errors = verify_zephyr_routing(boards, PACKAGES, zephyr_root, fixes)
        assert any("not declared in platform.json" in e for e in errors)

    def test_board_dir_missing(self, routing_tree):
        zephyr_root, boards, fixes = routing_tree
        boards["seeed-xiao-test"]["board_name"] = "xiao_missing"
        boards["seeed-xiao-test"]["variant"] = "xiao_missing/soc/cpuapp"
        errors = verify_zephyr_routing(boards, PACKAGES, zephyr_root, fixes)
        assert any("no zephyr/nrf/boards/seeed/xiao_missing/" in e for e in errors)

    def test_variant_board_name_mismatch(self, routing_tree):
        zephyr_root, boards, fixes = routing_tree
        boards["seeed-xiao-test"]["variant"] = "xiao_other/soc/cpuapp"
        errors = verify_zephyr_routing(boards, PACKAGES, zephyr_root, fixes)
        assert any("does not match the variant-derived" in e for e in errors)

    def test_missing_package_key(self, routing_tree):
        zephyr_root, _, fixes = routing_tree
        boards = {
            "seeed-xiao-test": {
                "package": None,
                "board_name": "xiao_test",
                "family": "nrf",
                "variant": "xiao_test/soc/cpuapp",
            }
        }
        errors = verify_zephyr_routing(boards, PACKAGES, zephyr_root, fixes)
        assert any("no build.zephyr.package" in e for e in errors)


class TestOrphans:
    def test_orphan_fixes_key(self, routing_tree):
        zephyr_root, boards, fixes = routing_tree
        fixes["boards"]["xiao_ghost"] = {"fixes": []}
        errors = verify_zephyr_routing(boards, PACKAGES, zephyr_root, fixes)
        assert any("xiao_ghost" in e and "not a known zephyr board" in e for e in errors)

    def test_orphan_patches_dir(self, routing_tree):
        zephyr_root, boards, fixes = routing_tree
        (zephyr_root / "patches" / "xiao_ghost").mkdir()
        errors = verify_zephyr_routing(boards, PACKAGES, zephyr_root, fixes)
        assert any("orphan fix sources" in e for e in errors)

    def test_orphan_overrides_dir(self, routing_tree):
        zephyr_root, boards, fixes = routing_tree
        (zephyr_root / "overrides" / "xiao_ghost").mkdir()
        errors = verify_zephyr_routing(boards, PACKAGES, zephyr_root, fixes)
        assert any("orphan fix sources" in e for e in errors)


class TestFixTargets:
    def test_absolute_target_rejected(self, routing_tree):
        zephyr_root, boards, fixes = routing_tree
        fixes["boards"]["xiao_test"]["fixes"][0]["target"] = "/etc/passwd"
        errors = verify_zephyr_routing(boards, PACKAGES, zephyr_root, fixes)
        assert any("invalid target" in e for e in errors)

    def test_traversal_target_rejected(self, routing_tree):
        zephyr_root, boards, fixes = routing_tree
        fixes["boards"]["xiao_test"]["fixes"][0]["target"] = "../../outside.c"
        errors = verify_zephyr_routing(boards, PACKAGES, zephyr_root, fixes)
        assert any("invalid target" in e for e in errors)

    def test_missing_fix_source_rejected(self, routing_tree):
        zephyr_root, boards, fixes = routing_tree
        fixes["boards"]["xiao_test"]["fixes"][0]["path"] = "9999-gone.patch"
        errors = verify_zephyr_routing(boards, PACKAGES, zephyr_root, fixes)
        assert any("source missing" in e for e in errors)


class TestFixesLayout:
    @staticmethod
    def add_fixes_dir(zephyr_root, board="xiao_test"):
        fixes_dir = zephyr_root / "nrf" / "boards" / "seeed" / board / "fixes"
        fixes_dir.mkdir(parents=True, exist_ok=True)
        return fixes_dir

    def test_fixes_layout_passes(self, routing_tree):
        zephyr_root, boards, fixes = routing_tree
        fixes_dir = self.add_fixes_dir(zephyr_root)
        (fixes_dir / "drivers").mkdir()
        (fixes_dir / "drivers" / "adc.c.patch").write_text("# fix\n", encoding="utf-8")
        (fixes_dir / "fixes.baseline").write_text(
            "drivers/adc.c " + "a" * 64 + "\n", encoding="utf-8"
        )
        assert verify_zephyr_routing(boards, PACKAGES, zephyr_root, fixes) == []

    def test_fix_without_baseline_entry(self, routing_tree):
        zephyr_root, boards, fixes = routing_tree
        fixes_dir = self.add_fixes_dir(zephyr_root)
        (fixes_dir / "drivers").mkdir()
        (fixes_dir / "drivers" / "adc.c.patch").write_text("# fix\n", encoding="utf-8")
        (fixes_dir / "fixes.baseline").write_text("", encoding="utf-8")
        errors = verify_zephyr_routing(boards, PACKAGES, zephyr_root, fixes)
        assert any("has no fixes.baseline entry" in e for e in errors)

    def test_baseline_without_fix_file(self, routing_tree):
        zephyr_root, boards, fixes = routing_tree
        fixes_dir = self.add_fixes_dir(zephyr_root)
        (fixes_dir / "fixes.baseline").write_text(
            "drivers/ghost.c " + "a" * 64 + "\n", encoding="utf-8"
        )
        errors = verify_zephyr_routing(boards, PACKAGES, zephyr_root, fixes)
        assert any("no fix file" in e for e in errors)

    def test_missing_baseline_file(self, routing_tree):
        zephyr_root, boards, fixes = routing_tree
        self.add_fixes_dir(zephyr_root)
        errors = verify_zephyr_routing(boards, PACKAGES, zephyr_root, fixes)
        assert any("has no fixes.baseline" in e for e in errors)

    def test_fixes_dir_for_unknown_board(self, routing_tree):
        zephyr_root, boards, fixes = routing_tree
        self.add_fixes_dir(zephyr_root, board="xiao_ghost")
        errors = verify_zephyr_routing(boards, PACKAGES, zephyr_root, fixes)
        assert any("no board declares" in e for e in errors)


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
        import yaml

        fixes = yaml.safe_load(
            (repo_root / "zephyr" / "fixes.yml").read_text(encoding="utf-8")
        )
        errors = verify_zephyr_routing(
            load_zephyr_boards(repo_root / "boards"),
            load_platform_packages(repo_root / "platform.json"),
            repo_root / "zephyr",
            fixes,
        )
        assert errors == []
