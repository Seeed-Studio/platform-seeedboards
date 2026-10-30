"""Unit tests for builder/frameworks/modules.py (module provisioner).

Gate semantics (AND across fields, OR within a list), vendored refresh
(pin.yml stays out of the copied tree), ZEPHYR_EXTRA_MODULES dedup, and the
prj.conf token opt-in.
"""

import hashlib
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BUILDER_FRAMEWORKS = REPO_ROOT / "builder" / "frameworks" / "zephyr"
if str(BUILDER_FRAMEWORKS) not in sys.path:
    sys.path.insert(0, str(BUILDER_FRAMEWORKS))

import modules  # noqa: E402

MOD_YML = "build:\n  cmake: .\n  kconfig: Kconfig\n"


def make_module(platform, name, pin="", module_yml=MOD_YML, src="int x;\n"):
    mod = platform / "zephyr" / "modules" / name
    (mod / "zephyr").mkdir(parents=True)
    (mod / "zephyr" / "module.yml").write_text(module_yml, encoding="utf-8")
    (mod / "src.c").write_text(src, encoding="utf-8")
    if pin:
        (mod / "pin.yml").write_text(pin, encoding="utf-8")
    return mod


def make_tree(tmp_path, board="xiao_sim", family="nrf", prj_conf=""):
    platform = tmp_path / "platform"
    framework = tmp_path / "framework"
    framework.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    if prj_conf:
        (project / "prj.conf").write_text(prj_conf, encoding="utf-8")
    return platform, framework, project


class TestVendoredProvisioning:
    def test_ungated_module_provisioned_and_registered(self, tmp_path):
        platform, framework, project = make_tree(tmp_path)
        make_module(platform, "mod_a")
        registered = modules.provision(
            str(platform), str(framework), "xiao_sim", "nrf", str(project))
        target = framework / "_pio" / "modules" / "mod_a"
        assert (target / "zephyr" / "module.yml").is_file()
        assert registered == [str(target)]
        assert os.path.normcase(str(target)) in os.path.normcase(
            os.environ["ZEPHYR_EXTRA_MODULES"])

    def test_board_gate_blocks_other_boards(self, tmp_path):
        platform, framework, project = make_tree(tmp_path)
        make_module(platform, "mod_a", pin="gate:\n  boards: [xiao_other]\n")
        registered = modules.provision(
            str(platform), str(framework), "xiao_sim", "nrf", str(project))
        assert registered == []
        assert not (framework / "_pio" / "modules" / "mod_a").exists()

    def test_pin_yml_not_copied_into_cache(self, tmp_path):
        platform, framework, project = make_tree(tmp_path)
        make_module(platform, "mod_a", pin="gate:\n  boards: [xiao_sim]\n")
        modules.provision(
            str(platform), str(framework), "xiao_sim", "nrf", str(project))
        assert not (framework / "_pio" / "modules" / "mod_a" / "pin.yml").exists()

    def test_family_gate(self, tmp_path):
        platform, framework, project = make_tree(tmp_path)
        make_module(platform, "mod_a", pin="gate:\n  families: [stm32]\n")
        registered = modules.provision(
            str(platform), str(framework), "xiao_sim", "nrf", str(project))
        assert registered == []

    def test_prj_conf_token_opt_in(self, tmp_path):
        platform, framework, project = make_tree(
            tmp_path, prj_conf="CONFIG_FOO=y\nCONFIG_BAR=y\n")
        make_module(platform, "mod_a",
                    pin="gate:\n  prj_conf_tokens: [CONFIG_BAR=y]\n")
        registered = modules.provision(
            str(platform), str(framework), "xiao_sim", "nrf", str(project))
        assert len(registered) == 1

    def test_prj_conf_token_absent_blocks(self, tmp_path):
        platform, framework, project = make_tree(
            tmp_path, prj_conf="CONFIG_FOO=y\n")
        make_module(platform, "mod_a",
                    pin="gate:\n  prj_conf_tokens: [CONFIG_BAR=y]\n")
        registered = modules.provision(
            str(platform), str(framework), "xiao_sim", "nrf", str(project))
        assert registered == []

    def test_gates_and_across_fields(self, tmp_path):
        # boards matches but family does not -> blocked.
        platform, framework, project = make_tree(tmp_path)
        make_module(
            platform, "mod_a",
            pin="gate:\n  boards: [xiao_sim]\n  families: [stm32]\n")
        registered = modules.provision(
            str(platform), str(framework), "xiao_sim", "nrf", str(project))
        assert registered == []

    def test_registration_merges_and_dedups(self, tmp_path):
        platform, framework, project = make_tree(tmp_path)
        make_module(platform, "mod_a")
        make_module(platform, "mod_b")
        os.environ["ZEPHYR_EXTRA_MODULES"] = str(
            framework / "_pio" / "modules" / "mod_a")
        try:
            modules.provision(
                str(platform), str(framework), "xiao_sim", "nrf", str(project))
            value = os.environ["ZEPHYR_EXTRA_MODULES"].split(";")
            assert len(value) == 2  # mod_a appeared once, mod_b appended
        finally:
            del os.environ["ZEPHYR_EXTRA_MODULES"]

    def test_vendored_without_module_yml_raises(self, tmp_path):
        platform, framework, project = make_tree(tmp_path)
        mod = platform / "zephyr" / "modules" / "broken"
        mod.mkdir(parents=True)
        (mod / "src.c").write_text("x\n", encoding="utf-8")
        try:
            modules.provision(
                str(platform), str(framework), "xiao_sim", "nrf", str(project))
        except RuntimeError as exc:
            assert "module.yml" in str(exc)
        else:
            raise AssertionError("missing module.yml must raise")


class TestExternalStubProvisioning:
    def test_remote_module_skipped_without_clone(self, tmp_path, monkeypatch,
                                                 capsys):
        # A pin with remote= but a failing clone (no network here) returns
        # None for that module and does not kill the walk.
        platform, framework, project = make_tree(
            tmp_path, prj_conf="CONFIG_EDGE=y\n")
        make_module(
            platform, "ext_mod",
            pin=("remote: https://example.invalid/x.git\n"
                 "revision: deadbee\n"
                 "gate:\n  prj_conf_tokens: [CONFIG_EDGE=y]\n"))
        monkeypatch.setattr(modules, "git_clone_with_retry",
                            lambda url, dst, rev: False)
        registered = modules.provision(
            str(platform), str(framework), "xiao_sim", "nrf", str(project))
        assert registered == []

    def test_override_env_wins(self, tmp_path, monkeypatch):
        platform, framework, project = make_tree(
            tmp_path, prj_conf="CONFIG_EDGE=y\n")
        make_module(
            platform, "ext_mod",
            pin=("remote: https://example.invalid/x.git\n"
                 "revision: deadbee\n"
                 "override_env: XIAO_EXT_DIR\n"
                 "gate:\n  prj_conf_tokens: [CONFIG_EDGE=y]\n"))
        override = tmp_path / "dev_tree"
        (override / "zephyr").mkdir(parents=True)
        (override / "zephyr" / "module.yml").write_text(
            MOD_YML, encoding="utf-8")
        monkeypatch.setenv("XIAO_EXT_DIR", str(override))
        monkeypatch.setattr(modules, "git_clone_with_retry",
                            lambda url, dst, rev: False)
        registered = modules.provision(
            str(platform), str(framework), "xiao_sim", "nrf", str(project))
        assert registered == [str(override)]

    def test_module_fixes_applied_to_clone(self, tmp_path, monkeypatch):
        # Fresh clone -> the module's fixes/ directory is applied to the
        # cloned tree (v2 convention reuse).
        platform, framework, project = make_tree(
            tmp_path, prj_conf="CONFIG_EDGE=y\n")
        make_module(
            platform, "ext_mod",
            pin=("remote: https://example.invalid/x.git\n"
                 "revision: deadbee\n"
                 "gate:\n  prj_conf_tokens: [CONFIG_EDGE=y]\n"))
        fixes = platform / "zephyr" / "modules" / "ext_mod" / "fixes"
        fixes.mkdir(parents=True)
        (fixes / "file.c").write_text("patched content\n",
                                      encoding="utf-8", newline="\n")
        (fixes / "fixes.baseline").write_text(
            "file.c %s\n" % hashlib.sha256(b"original\n").hexdigest(),
            encoding="utf-8", newline="\n")

        def fake_clone(url, dst, rev):
            Path(dst).mkdir(parents=True)
            (Path(dst) / "zephyr").mkdir()
            (Path(dst) / "zephyr" / "module.yml").write_text(
                MOD_YML, encoding="utf-8")
            (Path(dst) / "file.c").write_text(
                "original\n", encoding="utf-8", newline="\n")
            return True

        monkeypatch.setattr(modules, "git_clone_with_retry",
                            fake_clone)
        registered = modules.provision(
            str(platform), str(framework), "xiao_sim", "nrf", str(project))
        cached = framework / "_pio" / "modules" / "ext_mod"
        assert (cached / "file.c").read_text(encoding="utf-8") == (
            "patched content\n")
        assert registered == [str(cached)]

    @staticmethod
    def _pin_tree(tmp_path, monkeypatch, clone_calls):
        """External-module tree with a fake clone that records calls."""
        platform, framework, project = make_tree(
            tmp_path, prj_conf="CONFIG_EDGE=y\n")
        make_module(
            platform, "ext_mod",
            pin=("remote: https://example.invalid/x.git\n"
                 "revision: deadbee\n"
                 "gate:\n  prj_conf_tokens: [CONFIG_EDGE=y]\n"))

        def fake_clone(url, dst, rev):
            clone_calls.append(rev)
            Path(dst).mkdir(parents=True)
            (Path(dst) / "zephyr").mkdir()
            (Path(dst) / "zephyr" / "module.yml").write_text(
                MOD_YML, encoding="utf-8")
            return True

        monkeypatch.setattr(modules, "git_clone_with_retry",
                            fake_clone)
        return platform, framework, project

    def test_matching_pin_reuses_cache_without_clone(self, tmp_path,
                                                      monkeypatch):
        calls = []
        platform, framework, project = self._pin_tree(tmp_path, monkeypatch,
                                                       calls)
        modules.provision(
            str(platform), str(framework), "xiao_sim", "nrf", str(project))
        assert calls == ["deadbee"]  # first clone
        modules.provision(
            str(platform), str(framework), "xiao_sim", "nrf", str(project))
        assert calls == ["deadbee"]  # cache hit: no second clone

    def test_revision_bump_triggers_exactly_one_reclone(self, tmp_path,
                                                        monkeypatch):
        calls = []
        platform, framework, project = self._pin_tree(tmp_path, monkeypatch,
                                                       calls)
        modules.provision(
            str(platform), str(framework), "xiao_sim", "nrf", str(project))
        pin = platform / "zephyr" / "modules" / "ext_mod" / "pin.yml"
        pin.write_text(
            pin.read_text(encoding="utf-8").replace(
                "revision: deadbee", "revision: cafef00"),
            encoding="utf-8")
        modules.provision(
            str(platform), str(framework), "xiao_sim", "nrf", str(project))
        assert calls == ["deadbee", "cafef00"]  # re-cloned once, new rev
        record = json.loads(
            (framework / "_pio" / "modules" / "ext_mod" / ".pin").read_text(
                encoding="utf-8"))
        assert record["revision"] == "cafef00"

    def test_legacy_cache_without_pin_record_self_heals(self, tmp_path,
                                                        monkeypatch):
        calls = []
        platform, framework, project = self._pin_tree(tmp_path, monkeypatch,
                                                       calls)
        modules.provision(
            str(platform), str(framework), "xiao_sim", "nrf", str(project))
        # Simulate a cache written before .pin existed.
        (framework / "_pio" / "modules" / "ext_mod" / ".pin").unlink()
        modules.provision(
            str(platform), str(framework), "xiao_sim", "nrf", str(project))
        assert calls == ["deadbee", "deadbee"]  # re-cloned once
        assert (framework / "_pio" / "modules" / "ext_mod" / ".pin").is_file()
        modules.provision(
            str(platform), str(framework), "xiao_sim", "nrf", str(project))
        assert calls == ["deadbee", "deadbee"]  # then stable
