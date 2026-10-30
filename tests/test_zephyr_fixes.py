"""Unit tests for builder/frameworks/zephyr/fixes.py (fixes walker).

Exercises apply_all against a synthetic platform tree (family board dir
with fixes/) and framework tree: fresh apply must be warning-free with
nested-subdir fix paths (pins the Windows path normalization -- without
it, forward-slash baseline keys never match backslash relpaths), re-runs
must be idempotent, drift must fail loudly (override and patch alike),
and boards without a fixes/ directory must be silent no-ops.
"""

import hashlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
BUILDER_FRAMEWORKS = REPO_ROOT / "builder" / "frameworks" / "zephyr"
if str(BUILDER_FRAMEWORKS) not in sys.path:
    sys.path.insert(0, str(BUILDER_FRAMEWORKS))

import fixes  # noqa: E402

PRISTINE_PATCH_TARGET = "line-a\nline-b\nline-c\n"
PRISTINE_OVERRIDE_TARGET = "original driver content\n"
PATCH_BODY = (
    "--- a/drivers/adc.c\n+++ b/drivers/adc.c\n@@ -1,3 +1,4 @@\n"
    " line-a\n line-b\n+line-b2\n line-c\n"
)
# Two engine-style patches whose file names are labels, both editing the
# SAME target; the +++ header is the target of record.
ENGINE_PATCH_1 = (
    "--- a/scripts/engine.py\n+++ b/scripts/engine.py\n@@ -1,2 +1,3 @@\n"
    " head\n+engine-one\n tail\n"
)
ENGINE_PATCH_2 = (
    "--- a/scripts/engine.py\n+++ b/scripts/engine.py\n@@ -1,3 +1,4 @@\n"
    " head\n engine-one\n+engine-two\n tail\n"
)
PATCHED_OVERRIDE = "patched driver content\n"


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def make_tree(tmp_path, family="nrf", board="xiao_sim"):
    """Synthetic platform (board fixes dir) + pristine framework tree."""
    fixes_dir = tmp_path / "platform" / "zephyr" / family / "boards" / "seeed" / board / "fixes"
    (fixes_dir / "drivers" / "usb").mkdir(parents=True)
    (fixes_dir / "drivers" / "adc.c.patch").write_text(
        PATCH_BODY, encoding="utf-8", newline="\n"
    )
    (fixes_dir / "drivers" / "usb" / "udc.c").write_text(
        PATCHED_OVERRIDE, encoding="utf-8", newline="\n"
    )
    (fixes_dir / "fixes.baseline").write_text(
        "drivers/adc.c %s\ndrivers/usb/udc.c %s\n"
        % (sha(PRISTINE_PATCH_TARGET), sha(PRISTINE_OVERRIDE_TARGET)),
        encoding="utf-8", newline="\n",
    )

    fw = tmp_path / "framework"
    (fw / "drivers" / "usb").mkdir(parents=True)
    (fw / "drivers" / "adc.c").write_text(
        PRISTINE_PATCH_TARGET, encoding="utf-8", newline="\n"
    )
    (fw / "drivers" / "usb" / "udc.c").write_text(
        PRISTINE_OVERRIDE_TARGET, encoding="utf-8", newline="\n"
    )
    return tmp_path / "platform", fw, fixes_dir


class TestFreshApply:
    def test_applies_all_fixes_without_warnings(self, tmp_path, capsys):
        # Nested fix paths (drivers/...) must match the forward-slash
        # baseline keys on every platform; a mismatch here would print
        # "no fixes.baseline entry" + "stale" warnings on every build.
        platform, fw, _ = make_tree(tmp_path)
        fixes.apply_all(str(platform), str(fw), "xiao_sim", "4.4.0")
        out = capsys.readouterr().out
        assert "WARNING" not in out
        assert (fw / "drivers" / "adc.c").read_text(encoding="utf-8") == (
            "line-a\nline-b\nline-b2\nline-c\n"
        )
        assert (
            (fw / "drivers" / "usb" / "udc.c").read_text(encoding="utf-8")
            == PATCHED_OVERRIDE
        )

    def test_family_root_discovered_by_glob(self, tmp_path, capsys):
        # Same tree under a different family root: discovery is the
        # zephyr/*/boards/*/<board> glob, not a hardcoded family.
        platform, fw, _ = make_tree(tmp_path, family="esp")
        fixes.apply_all(str(platform), str(fw), "xiao_sim", "4.4.0")
        assert "Applied 2 Zephyr fix(es)" in capsys.readouterr().out

    def test_rerun_is_idempotent(self, tmp_path, capsys):
        platform, fw, _ = make_tree(tmp_path)
        fixes.apply_all(str(platform), str(fw), "xiao_sim", "4.4.0")
        fixes.apply_all(str(platform), str(fw), "xiao_sim", "4.4.0")
        adc = (fw / "drivers" / "adc.c").read_text(encoding="utf-8")
        assert adc.count("line-b2") == 1


class TestFrameworkLevel:
    """zephyr/fixes/ applies to every board, before board-level fixes."""

    @staticmethod
    def make_framework_tree(tmp_path):
        fixes_root = tmp_path / "platform" / "zephyr" / "fixes"
        fwdir = fixes_root / "scripts"
        fwdir.mkdir(parents=True)
        (fwdir / "engine.py.01-one.patch").write_text(
            ENGINE_PATCH_1, encoding="utf-8", newline="\n")
        (fwdir / "engine.py.02-two.patch").write_text(
            ENGINE_PATCH_2, encoding="utf-8", newline="\n")
        (fixes_root / "fixes.baseline").write_text(
            "scripts/engine.py %s\n" % sha("head\ntail\n"),
            encoding="utf-8", newline="\n")
        fw = tmp_path / "framework"
        (fw / "scripts").mkdir(parents=True)
        (fw / "scripts" / "engine.py").write_text(
            "head\ntail\n", encoding="utf-8", newline="\n")
        return tmp_path / "platform", fw

    def test_label_named_patches_share_one_target(self, tmp_path, capsys):
        # Both .01/.02 files land on scripts/engine.py (their +++ header),
        # applied in sorted name order; the single baseline key covers both.
        platform, fw = self.make_framework_tree(tmp_path)
        fixes.apply_all(str(platform), str(fw), "xiao_any", "4.4.0")
        out = capsys.readouterr().out
        assert "WARNING" not in out
        assert (fw / "scripts" / "engine.py").read_text(
            encoding="utf-8") == "head\nengine-one\nengine-two\ntail\n"

    def test_framework_level_applies_for_board_without_board_fixes(
            self, tmp_path, capsys):
        # A board with no board-level fixes dir still gets framework fixes.
        platform, fw = self.make_framework_tree(tmp_path)
        fixes.apply_all(str(platform), str(fw), "xiao_nofixes", "4.4.0")
        assert (fw / "scripts" / "engine.py").read_text(
            encoding="utf-8") == "head\nengine-one\nengine-two\ntail\n"

    def test_drifted_engine_target_reports_baseline(self, tmp_path):
        platform, fw = self.make_framework_tree(tmp_path)
        (fw / "scripts" / "engine.py").write_text(
            "rewritten upstream\n", encoding="utf-8", newline="\n")
        with pytest.raises(RuntimeError) as excinfo:
            fixes.apply_all(str(platform), str(fw), "xiao_any", "4.4.0")
        assert "baseline drift" in str(excinfo.value)

    def test_patch_without_plus_target_header_raises(self, tmp_path):
        platform, fw = self.make_framework_tree(tmp_path)
        (platform / "zephyr" / "fixes" / "scripts"
         / "engine.py.03-bad.patch").write_text(
            "not a patch at all\n", encoding="utf-8", newline="\n")
        with pytest.raises(RuntimeError) as excinfo:
            fixes.apply_all(str(platform), str(fw), "xiao_any", "4.4.0")
        assert "+++ target header" in str(excinfo.value)


class TestNoFixesBoard:
    def test_board_without_fixes_dir_is_silent_noop(self, tmp_path, capsys):
        platform, fw, _ = make_tree(tmp_path)
        (tmp_path / "platform" / "zephyr" / "nrf" / "boards" / "seeed" / "xiao_clean").mkdir()
        fixes.apply_all(str(platform), str(fw), "xiao_clean", "4.4.0")
        out = capsys.readouterr().out
        assert out == ""


class TestArtifactSkip:
    def test_local_artifacts_are_skipped_not_applied(self, tmp_path, capsys):
        # .DS_Store / editor backups sit on disk but not in git; os.walk
        # must not turn them into overrides at their relative path.
        platform, fw, fixes_dir = make_tree(tmp_path)
        (fixes_dir / ".DS_Store").write_text("junk\n", encoding="utf-8")
        (fixes_dir / "drivers" / "adc.c~").write_text("junk\n", encoding="utf-8")
        (fixes_dir / "drivers" / "adc.c.orig").write_text("junk\n", encoding="utf-8")
        fixes.apply_all(str(platform), str(fw), "xiao_sim", "4.4.0")
        out = capsys.readouterr().out
        assert out.count("Skipping non-fix artifact") == 3
        assert not (fw / ".DS_Store").exists()
        assert not (fw / "drivers" / "adc.c~").exists()
        # The two real fixes still applied, no baseline complaints about
        # the skipped files.
        assert "Applied 2 Zephyr fix(es)" in out
        assert "WARNING" not in out


class TestBaselineGating:
    def test_override_drift_fails_hard(self, tmp_path):
        # Drift on a whole-file override is the most destructive silent
        # failure (an old fork clobbers a newer upstream file); it must
        # raise, symmetric with the patch path, not warn-and-copy.
        platform, fw, _ = make_tree(tmp_path)
        (fw / "drivers" / "usb" / "udc.c").write_text(
            "drifted upstream content\n", encoding="utf-8", newline="\n"
        )
        try:
            fixes.apply_all(str(platform), str(fw), "xiao_sim", "4.4.0")
        except RuntimeError as exc:
            assert "override baseline mismatch" in str(exc)
        else:
            raise AssertionError("drifted override target must raise")
        assert (fw / "drivers" / "usb" / "udc.c").read_text(
            encoding="utf-8") == "drifted upstream content\n"  # not clobbered

    def test_deletion_patch_against_pristine_target_raises(self, tmp_path):
        # A deletion-only hunk whose old block is missing while the target
        # still hashes pristine was never applied by anything: the patch
        # does not match the tree it claims to be cut against.
        platform, fw, fixes_dir = make_tree(tmp_path)
        (fixes_dir / "drivers" / "gone.c.patch").write_text(
            "--- a/drivers/gone.c\n+++ b/drivers/gone.c\n@@ -1,2 +0,0 @@\n"
            "-line-a\n-line-b\n",
            encoding="utf-8", newline="\n")
        # Target holds DIFFERENT pristine content: old block can never match,
        # and the file still equals its recorded baseline sha.
        other_pristine = "other-a\nother-b\n"
        (fw / "drivers" / "gone.c").write_text(
            other_pristine, encoding="utf-8", newline="\n")
        with open(fixes_dir / "fixes.baseline", "a", encoding="utf-8") as fp:
            fp.write("drivers/gone.c %s\n" % sha(other_pristine))
        try:
            fixes.apply_all(str(platform), str(fw), "xiao_sim", "4.4.0")
        except RuntimeError as exc:
            assert "patch/baseline mismatch" in str(exc)
        else:
            raise AssertionError("deletion miss on pristine target must raise")

    def test_deletion_patch_idempotent_rerun_is_silent(self, tmp_path, capsys):
        # After the deletion really landed, the file no longer equals the
        # pristine baseline: the miss is a legitimate re-run and stays quiet.
        platform, fw, fixes_dir = make_tree(tmp_path)
        (fixes_dir / "drivers" / "gone.c.patch").write_text(
            "--- a/drivers/gone.c\n+++ b/drivers/gone.c\n@@ -1,2 +0,0 @@\n"
            "-line-a\n-line-b\n",
            encoding="utf-8", newline="\n")
        target = fw / "drivers" / "gone.c"
        target.write_text("line-a\nline-b\n", encoding="utf-8", newline="\n")
        with open(fixes_dir / "fixes.baseline", "a", encoding="utf-8") as fp:
            fp.write("drivers/gone.c %s\n" % sha("line-a\nline-b\n"))
        fixes.apply_all(str(platform), str(fw), "xiao_sim", "4.4.0")
        assert target.read_text(encoding="utf-8") == "\n"  # deletion landed
        fixes.apply_all(str(platform), str(fw), "xiao_sim", "4.4.0")
        out = capsys.readouterr().out
        assert "patch/baseline mismatch" not in out

    def test_patch_drift_raises_loudly(self, tmp_path):
        platform, fw, _ = make_tree(tmp_path)
        (fw / "drivers" / "adc.c").write_text(
            "unrelated upstream rewrite\n", encoding="utf-8", newline="\n"
        )
        try:
            fixes.apply_all(str(platform), str(fw), "xiao_sim", "4.4.0")
        except RuntimeError as exc:
            assert "patch hunk did not match" in str(exc)
        else:
            raise AssertionError("drifted patch target must raise")

    def test_invalid_baseline_line_degrades_to_no_baseline(self, tmp_path, capsys):
        # Trailing junk in the sha must not become a never-matching
        # expected value (permanent false "upgraded" warnings); it drops
        # the entry instead.
        platform, fw, fixes_dir = make_tree(tmp_path)
        baseline = fixes_dir / "fixes.baseline"
        baseline.write_text(
            "drivers/adc.c %s # cut vs 4.4.0\ndrivers/usb/udc.c %s\n"
            % (sha(PRISTINE_PATCH_TARGET), sha(PRISTINE_OVERRIDE_TARGET)),
            encoding="utf-8", newline="\n",
        )
        fixes.apply_all(str(platform), str(fw), "xiao_sim", "4.4.0")
        out = capsys.readouterr().out
        assert "invalid fixes.baseline line" in out
        assert "override baseline mismatch" not in out
        assert "no fixes.baseline entry for drivers/adc.c" in out

    def test_stale_baseline_entry_warns(self, tmp_path, capsys):
        platform, fw, fixes_dir = make_tree(tmp_path)
        with open(fixes_dir / "fixes.baseline", "a", encoding="utf-8") as fp:
            fp.write("drivers/ghost.c %s\n" % ("c" * 64))
        fixes.apply_all(str(platform), str(fw), "xiao_sim", "4.4.0")
        assert "lists targets with no fix file" in capsys.readouterr().out

    def test_fix_without_baseline_entry_warns(self, tmp_path, capsys):
        platform, fw, fixes_dir = make_tree(tmp_path)
        (fixes_dir / "drivers" / "orphan.c").write_text(
            "x\n", encoding="utf-8", newline="\n"
        )
        fixes.apply_all(str(platform), str(fw), "xiao_sim", "4.4.0")
        assert "no fixes.baseline entry for drivers/orphan.c" in capsys.readouterr().out
