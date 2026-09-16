"""Unit tests for scripts/ci/verify_boards.py.

Each rule is exercised with a passing real-world sample (the copied
manifests under tests/fixtures/boards/valid/) and a failing counterexample
built per rule, per the invariant-gate discipline in
.agents/notes/proposed/2026-08-17-ai-workflow-adaptation.md.
"""

import json

from verify_boards import (
    SUPPORTED_BOARD_IDS,
    load_platform_packages,
    verify_board_manifest,
    verify_boards_dir,
)

TEST_FRAMEWORKS = {"arduino", "zephyr", "espidf"}
TEST_PACKAGES = {"framework-zephyr-test", "tool-openocd"}


def write_manifest(path, manifest):
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path


def minimal_manifest(**overrides):
    manifest = {
        "build": {"mcu": "testmcu", "cpu": "cortex-m0plus", "family": "samd"},
        "frameworks": ["arduino"],
        "name": "Test Board",
        "platform": "SeeedStudio",
        "upload": {"maximum_size": 262144, "protocol": "swd"},
        "url": "https://example.com/test-board",
        "vendor": "Seeed Studio",
    }
    manifest.update(overrides)
    return manifest


class TestRuleManifestIntegrity:
    def test_real_manifests_pass(self, valid_boards_dir, tmp_path):
        errors = []
        for manifest_path in sorted(valid_boards_dir.glob("*.json")):
            errors.extend(
                verify_board_manifest(manifest_path, TEST_FRAMEWORKS)
            )
        assert errors == []

    def test_broken_json_is_reported(self, tmp_path):
        bad = tmp_path / "broken.json"
        bad.write_text("{ not valid json !!", encoding="utf-8")
        errors = verify_board_manifest(bad, TEST_FRAMEWORKS)
        assert any("invalid JSON" in e for e in errors)

    def test_missing_vendor_is_reported(self, tmp_path):
        path = write_manifest(
            tmp_path / "novendor.json", minimal_manifest(vendor="")
        )
        errors = verify_board_manifest(path, TEST_FRAMEWORKS)
        assert any("missing required field 'vendor'" in e for e in errors)


class TestRuleFrameworks:
    def test_unknown_framework_is_reported(self, tmp_path):
        path = write_manifest(
            tmp_path / "freertos.json", minimal_manifest(frameworks=["freertos"])
        )
        errors = verify_board_manifest(path, TEST_FRAMEWORKS)
        assert any("not declared in platform.json" in e for e in errors)

    def test_empty_frameworks_is_reported(self, tmp_path):
        path = write_manifest(
            tmp_path / "empty.json", minimal_manifest(frameworks=[])
        )
        errors = verify_board_manifest(path, TEST_FRAMEWORKS)
        assert any("non-empty list" in e for e in errors)

    def test_missing_frameworks_key_is_reported(self, tmp_path):
        manifest = minimal_manifest()
        del manifest["frameworks"]
        path = write_manifest(tmp_path / "nofw.json", manifest)
        errors = verify_board_manifest(path, TEST_FRAMEWORKS)
        assert any("non-empty list" in e for e in errors)


class TestRuleZephyrObject:
    def test_zephyr_must_be_object(self, tmp_path):
        manifest = minimal_manifest(
            build={"mcu": "testmcu", "zephyr": "nrf54l15"}, frameworks=["zephyr"]
        )
        path = write_manifest(tmp_path / "badzephyr.json", manifest)
        errors = verify_board_manifest(path, TEST_FRAMEWORKS)
        assert any("'build.zephyr' must be an object" in e for e in errors)

    def test_zephyr_object_passes(self, tmp_path):
        manifest = minimal_manifest(
            build={
                "mcu": "testmcu",
                "family": "nrf",
                "zephyr": {
                    "variant": "xiao_test/test/cpuapp",
                    "package": "framework-zephyr-test",
                    "board_name": "xiao_test",
                },
            },
            frameworks=["zephyr"],
        )
        path = write_manifest(tmp_path / "goodzephyr.json", manifest)
        assert (
            verify_board_manifest(
                path, TEST_FRAMEWORKS, platform_packages=TEST_PACKAGES
            )
            == []
        )


class TestRuleFamily:
    def test_missing_family_is_reported(self, tmp_path):
        manifest = minimal_manifest(build={"mcu": "testmcu"})
        path = write_manifest(tmp_path / "nofamily.json", manifest)
        errors = verify_board_manifest(path, TEST_FRAMEWORKS)
        assert any("missing 'build.family'" in e for e in errors)

    def test_unknown_family_is_reported(self, tmp_path):
        manifest = minimal_manifest(build={"mcu": "testmcu", "family": "mips"})
        path = write_manifest(tmp_path / "badfamily.json", manifest)
        errors = verify_board_manifest(path, TEST_FRAMEWORKS)
        assert any("'build.family' 'mips' is not one of" in e for e in errors)

    def test_family_without_build_dir_is_reported(self, tmp_path):
        manifest = minimal_manifest()  # family=samd, families_root has no samd/
        path = write_manifest(tmp_path / "orphan.json", manifest)
        errors = verify_board_manifest(
            path, TEST_FRAMEWORKS, families_root=tmp_path / "board_build"
        )
        assert any("no builder/board_build/samd/ directory" in e for e in errors)

    def test_family_with_build_dir_passes(self, tmp_path):
        families_root = tmp_path / "board_build"
        (families_root / "samd").mkdir(parents=True)
        path = write_manifest(tmp_path / "ok.json", minimal_manifest())
        assert (
            verify_board_manifest(
                path, TEST_FRAMEWORKS, families_root=families_root
            )
            == []
        )


class TestRuleZephyrRouting:
    @staticmethod
    def zephyr_manifest(**zephyr_overrides):
        zephyr = {
            "variant": "xiao_test/test/cpuapp",
            "package": "framework-zephyr-test",
            "board_name": "xiao_test",
        }
        zephyr.update(zephyr_overrides)
        return minimal_manifest(
            build={"mcu": "testmcu", "family": "nrf", "zephyr": zephyr},
            frameworks=["zephyr"],
        )

    def test_package_not_in_platform_json(self, tmp_path):
        manifest = self.zephyr_manifest(package="framework-ghost")
        path = write_manifest(tmp_path / "ghost.json", manifest)
        errors = verify_board_manifest(
            path, TEST_FRAMEWORKS, platform_packages=TEST_PACKAGES
        )
        assert any("not declared in platform.json" in e for e in errors)

    def test_board_dir_missing(self, tmp_path):
        manifest = self.zephyr_manifest()
        path = write_manifest(tmp_path / "nodir.json", manifest)
        errors = verify_board_manifest(
            path,
            TEST_FRAMEWORKS,
            platform_packages=TEST_PACKAGES,
            zephyr_boards_root=tmp_path / "arm",
        )
        assert any("no zephyr/boards/arm/xiao_test/ directory" in e for e in errors)

    def test_variant_prefix_mismatch(self, tmp_path):
        manifest = self.zephyr_manifest(variant="xiao_other/test/cpuapp")
        path = write_manifest(tmp_path / "mismatch.json", manifest)
        errors = verify_board_manifest(
            path, TEST_FRAMEWORKS, platform_packages=TEST_PACKAGES
        )
        assert any("must start with board_name" in e for e in errors)

    def test_missing_board_name(self, tmp_path):
        manifest = self.zephyr_manifest()
        del manifest["build"]["zephyr"]["board_name"]
        path = write_manifest(tmp_path / "noname.json", manifest)
        errors = verify_board_manifest(
            path, TEST_FRAMEWORKS, platform_packages=TEST_PACKAGES
        )
        assert any("need 'build.zephyr.board_name'" in e for e in errors)


class TestRuleSnapshot:
    def test_dir_matching_snapshot_passes(self, valid_boards_dir):
        expected = ["seeed-xiao-rp2040", "seeed-xiao-samd"]
        assert verify_boards_dir(valid_boards_dir, TEST_FRAMEWORKS, expected) == []

    def test_unexpected_manifest_is_reported(self, valid_boards_dir):
        errors = verify_boards_dir(
            valid_boards_dir, TEST_FRAMEWORKS, ["seeed-xiao-samd"]
        )
        assert any(
            "missing from SUPPORTED_BOARD_IDS" in e for e in errors
        )

    def test_snapshot_without_manifest_is_reported(self, valid_boards_dir):
        errors = verify_boards_dir(
            valid_boards_dir,
            TEST_FRAMEWORKS,
            ["seeed-xiao-rp2040", "seeed-xiao-samd", "seeed-xiao-ghost"],
        )
        assert any("has no manifest" in e for e in errors)


class TestRepoGate:
    """The gate itself, run against the real repository tree (full checks)."""

    def test_repo_boards_are_clean(
        self, repo_root, repo_platform_frameworks
    ):
        assert verify_boards_dir(
            repo_root / "boards",
            repo_platform_frameworks,
            SUPPORTED_BOARD_IDS,
            platform_packages=load_platform_packages(
                repo_root / "platform.json"
            ),
            families_root=repo_root / "builder" / "board_build",
            zephyr_boards_root=repo_root / "zephyr" / "boards" / "arm",
        ) == []

    def test_snapshot_count(self):
        assert len(SUPPORTED_BOARD_IDS) == 23
        assert len(set(SUPPORTED_BOARD_IDS)) == 23
