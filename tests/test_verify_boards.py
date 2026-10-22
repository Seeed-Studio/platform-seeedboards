"""Unit tests for scripts/ci/verify_boards.py.

Each rule ships a passing sample and a failing counterexample (ADR-0005
gate discipline). The gate functions are pure so tests import them and
run against tmp trees.
"""

import json
from pathlib import Path

import pytest

from verify_boards import (
    verify_board_manifest,
    verify_boards_dir,
    verify_families_concreteness,
)


KNOWN = {"samd", "esp"}
KNOWN_ALL = {"samd", "esp", "zephyr"}
PLATFORM = {
    "frameworks": {"arduino": {}, "zephyr": {}},
    "packages": {
        "framework-arduino-x": {},
        "framework-zephyr-x": {},
    },
}


def write_manifest(path, manifest):
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path


def good_manifest(**overrides):
    manifest = {
        "build": {"mcu": "testmcu", "chip_family": "samd"},
        "frameworks": ["arduino"],
        "name": "Test Board",
        "url": "https://example.com",
        "vendor": "Test",
    }
    manifest.update(overrides)
    return manifest


def full_manifest():
    manifest = good_manifest()
    manifest["build"] = {
        "mcu": "testmcu",
        "chip_family": "samd",
        "arduino": {"package": "framework-arduino-x"},
    }
    manifest["upload"] = {
        "protocol": "sam-ba",
        "protocols": ["sam-ba", "jlink"],
    }
    return manifest


class TestManifestRules:
    def test_valid_manifest_passes(self, tmp_path):
        path = write_manifest(tmp_path / "ok.json", good_manifest())
        assert verify_board_manifest(path, KNOWN) == []

    def test_broken_json(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{ nope", encoding="utf-8")
        assert any("invalid JSON" in e for e in verify_board_manifest(bad, KNOWN))

    def test_missing_vendor(self, tmp_path):
        path = write_manifest(
            tmp_path / "v.json", good_manifest(vendor="")
        )
        assert any("vendor" in e for e in verify_board_manifest(path, KNOWN))

    def test_missing_routing_key(self, tmp_path):
        manifest = good_manifest()
        manifest["build"].pop("chip_family")
        path = write_manifest(tmp_path / "nf.json", manifest)
        assert any("chip_family" in e for e in verify_board_manifest(path, KNOWN))

    def test_unknown_family(self, tmp_path):
        path = write_manifest(
            tmp_path / "uf.json", good_manifest(build={"chip_family": "mips"})
        )
        assert any("not a registered family" in e for e in verify_board_manifest(path, KNOWN))

    def test_full_manifest_with_platform_passes(self, tmp_path):
        path = write_manifest(tmp_path / "full.json", full_manifest())
        assert verify_board_manifest(path, KNOWN_ALL, PLATFORM) == []

    def test_top_level_extra_flags_rejected(self, tmp_path):
        manifest = full_manifest()
        manifest["extra_flags"] = "-DWRONG=1"
        path = write_manifest(tmp_path / "flags.json", manifest)
        errors = verify_board_manifest(path, KNOWN_ALL, PLATFORM)
        assert any("top level" in e for e in errors)

    def test_unknown_framework_rejected(self, tmp_path):
        manifest = full_manifest()
        manifest["frameworks"] = ["mbed"]
        path = write_manifest(tmp_path / "fw.json", manifest)
        errors = verify_board_manifest(path, KNOWN_ALL, PLATFORM)
        assert any("not declared in platform.json" in e for e in errors)

    def test_undeclared_per_board_package_rejected(self, tmp_path):
        manifest = full_manifest()
        manifest["build"]["arduino"]["package"] = "framework-missing"
        path = write_manifest(tmp_path / "pkg.json", manifest)
        errors = verify_board_manifest(path, KNOWN_ALL, PLATFORM)
        assert any("framework-missing" in e for e in errors)

    def test_upload_protocol_must_be_in_protocols(self, tmp_path):
        manifest = full_manifest()
        manifest["upload"]["protocol"] = "dfu"
        path = write_manifest(tmp_path / "proto.json", manifest)
        errors = verify_board_manifest(path, KNOWN_ALL, PLATFORM)
        assert any("not listed in upload.protocols" in e for e in errors)

    def test_zephyr_requires_routing_fields(self, tmp_path):
        manifest = full_manifest()
        manifest["build"] = {"mcu": "nrf54lm20a", "chip_family": "zephyr",
                             "zephyr": {}}
        manifest["frameworks"] = ["zephyr"]
        path = write_manifest(tmp_path / "z.json", manifest)
        errors = verify_board_manifest(path, KNOWN_ALL, PLATFORM)
        assert any("build.zephyr.package" in e for e in errors)
        assert any("build.zephyr.variant" in e for e in errors)

    def test_zephyr_board_name_must_match_variant(self, tmp_path):
        manifest = full_manifest()
        manifest["build"] = {
            "mcu": "nrf54lm20a",
            "chip_family": "zephyr",
            "zephyr": {
                "package": "framework-zephyr-x",
                "variant": "xiao_a/nrf54lm20a/cpuapp",
                "board_name": "xiao_b",
            },
        }
        manifest["frameworks"] = ["zephyr"]
        path = write_manifest(tmp_path / "zname.json", manifest)
        errors = verify_board_manifest(path, KNOWN_ALL, PLATFORM)
        assert any("does not match" in e for e in errors)

    def test_nrfutil_mcumgr_requires_cdc(self, tmp_path):
        manifest = full_manifest()
        manifest["upload"] = {
            "protocol": "nrfutil-mcumgr",
            "protocols": ["nrfutil-mcumgr"],
        }
        path = write_manifest(tmp_path / "cdc.json", manifest)
        errors = verify_board_manifest(path, KNOWN_ALL, PLATFORM)
        assert any("upload.cdc.app_vidpid" in e for e in errors)
        assert any("upload.cdc.loader_vidpids" in e for e in errors)

    def test_nrfutil_mcumgr_valid_cdc_passes(self, tmp_path):
        manifest = full_manifest()
        manifest["upload"] = {
            "protocol": "nrfutil-mcumgr",
            "protocols": ["nrfutil-mcumgr"],
            "cdc": {
                "app_vidpid": "2886:8068",
                "loader_vidpids": ["2886:0068"],
            },
        }
        path = write_manifest(tmp_path / "cdc-ok.json", manifest)
        assert verify_board_manifest(path, KNOWN_ALL, PLATFORM) == []


class TestDirRules:
    def test_bootstrap_empty_passes(self, tmp_path):
        assert verify_boards_dir(tmp_path, KNOWN, []) == []

    def test_snapshot_without_manifests(self, tmp_path):
        errors = verify_boards_dir(tmp_path, KNOWN, ["ghost-board"])
        assert any("no manifests" in e for e in errors)

    def test_manifest_outside_snapshot(self, tmp_path):
        write_manifest(tmp_path / "extra.json", good_manifest())
        errors = verify_boards_dir(tmp_path, KNOWN, [])
        assert any("SUPPORTED_BOARD_IDS" in e for e in errors)

    def test_dir_matching_snapshot(self, tmp_path):
        write_manifest(tmp_path / "b.json", good_manifest())
        assert verify_boards_dir(tmp_path, KNOWN, ["b"]) == []


class _Stub:
    """Duck-typed ChipFamily stand-in with configurable children."""

    def __init__(self, children):
        self._children = children

    def __subclasses__(self):
        return list(self._children)


class TestConcretenessGuard:
    @staticmethod
    def _cls(abstract=True, family_ids=()):
        cls = type("_C", (), {"family_ids": family_ids})
        cls.__abstractmethods__ = frozenset({"x"}) if abstract else frozenset()
        return cls

    def test_concrete_without_ids_flagged(self):
        probe = _Stub([self._cls(abstract=False)])
        errors = verify_families_concreteness(probe)
        assert any("empty family_ids" in e for e in errors)

    def test_concrete_with_ids_clean(self):
        probe = _Stub([self._cls(abstract=False, family_ids=("samd",))])
        assert verify_families_concreteness(probe) == []

    def test_abstract_intermediate_skipped(self):
        probe = _Stub([self._cls(abstract=True)])
        assert verify_families_concreteness(probe) == []
