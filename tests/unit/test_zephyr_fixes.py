"""Unit tests for builder/frameworks/zephyr_fixes.py (fixes walker).

Exercises apply_all against a synthetic platform tree (family board dir
with fixes/) and framework tree: fresh apply must be warning-free with
nested-subdir fix paths (pins the Windows path normalization -- without
it, forward-slash baseline keys never match backslash relpaths), re-runs
must be idempotent, drift and malformed baselines must warn, and boards
without a fixes/ directory must be silent no-ops.
"""

import hashlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILDER_FRAMEWORKS = REPO_ROOT / "builder" / "frameworks"
if str(BUILDER_FRAMEWORKS) not in sys.path:
    sys.path.insert(0, str(BUILDER_FRAMEWORKS))

import zephyr_fixes  # noqa: E402

PRISTINE_PATCH_TARGET = "line-a\nline-b\nline-c\n"
PRISTINE_OVERRIDE_TARGET = "original driver content\n"
PATCH_BODY = (
    "--- a/drivers/adc.c\n+++ b/drivers/adc.c\n@@ -1,3 +1,4 @@\n"
    " line-a\n line-b\n+line-b2\n line-c\n"
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
        zephyr_fixes.apply_all(str(platform), str(fw), "xiao_sim", "4.4.0")
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
        zephyr_fixes.apply_all(str(platform), str(fw), "xiao_sim", "4.4.0")
        assert "Applied 2 Zephyr fix(es)" in capsys.readouterr().out

    def test_rerun_is_idempotent(self, tmp_path, capsys):
        platform, fw, _ = make_tree(tmp_path)
        zephyr_fixes.apply_all(str(platform), str(fw), "xiao_sim", "4.4.0")
        zephyr_fixes.apply_all(str(platform), str(fw), "xiao_sim", "4.4.0")
        adc = (fw / "drivers" / "adc.c").read_text(encoding="utf-8")
        assert adc.count("line-b2") == 1


class TestNoFixesBoard:
    def test_board_without_fixes_dir_is_silent_noop(self, tmp_path, capsys):
        platform, fw, _ = make_tree(tmp_path)
        (tmp_path / "platform" / "zephyr" / "nrf" / "boards" / "seeed" / "xiao_clean").mkdir()
        zephyr_fixes.apply_all(str(platform), str(fw), "xiao_clean", "4.4.0")
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
        zephyr_fixes.apply_all(str(platform), str(fw), "xiao_sim", "4.4.0")
        out = capsys.readouterr().out
        assert out.count("Skipping non-fix artifact") == 3
        assert not (fw / ".DS_Store").exists()
        assert not (fw / "drivers" / "adc.c~").exists()
        # The two real fixes still applied, no baseline complaints about
        # the skipped files.
        assert "Applied 2 Zephyr fix(es)" in out
        assert "WARNING" not in out


class TestBaselineGating:
    def test_override_drift_warns(self, tmp_path, capsys):
        platform, fw, _ = make_tree(tmp_path)
        (fw / "drivers" / "usb" / "udc.c").write_text(
            "drifted upstream content\n", encoding="utf-8", newline="\n"
        )
        zephyr_fixes.apply_all(str(platform), str(fw), "xiao_sim", "4.4.0")
        assert "override baseline mismatch" in capsys.readouterr().out

    def test_patch_drift_raises_loudly(self, tmp_path):
        platform, fw, _ = make_tree(tmp_path)
        (fw / "drivers" / "adc.c").write_text(
            "unrelated upstream rewrite\n", encoding="utf-8", newline="\n"
        )
        try:
            zephyr_fixes.apply_all(str(platform), str(fw), "xiao_sim", "4.4.0")
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
        zephyr_fixes.apply_all(str(platform), str(fw), "xiao_sim", "4.4.0")
        out = capsys.readouterr().out
        assert "invalid fixes.baseline line" in out
        assert "override baseline mismatch" not in out
        assert "no fixes.baseline entry for drivers/adc.c" in out

    def test_stale_baseline_entry_warns(self, tmp_path, capsys):
        platform, fw, fixes_dir = make_tree(tmp_path)
        with open(fixes_dir / "fixes.baseline", "a", encoding="utf-8") as fp:
            fp.write("drivers/ghost.c %s\n" % ("c" * 64))
        zephyr_fixes.apply_all(str(platform), str(fw), "xiao_sim", "4.4.0")
        assert "lists targets with no fix file" in capsys.readouterr().out

    def test_fix_without_baseline_entry_warns(self, tmp_path, capsys):
        platform, fw, fixes_dir = make_tree(tmp_path)
        (fixes_dir / "drivers" / "orphan.c").write_text(
            "x\n", encoding="utf-8", newline="\n"
        )
        zephyr_fixes.apply_all(str(platform), str(fw), "xiao_sim", "4.4.0")
        assert "no fixes.baseline entry for drivers/orphan.c" in capsys.readouterr().out
