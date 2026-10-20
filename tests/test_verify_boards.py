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
