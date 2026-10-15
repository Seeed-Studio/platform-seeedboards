"""Unit tests for builder/frameworks/zephyr_patch.py (patch executor).

One case per hunk shape -- insertion, replacement, deletion -- each
asserting both the first run and the idempotent re-run. These pin the
hunk-order semantics: insertion must not re-apply (the production-cache
4x duplication bug), deletion must apply at all (empty new block used
to short-circuit as "already applied").
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILDER_FRAMEWORKS = REPO_ROOT / "builder" / "frameworks"
if str(BUILDER_FRAMEWORKS) not in sys.path:
    sys.path.insert(0, str(BUILDER_FRAMEWORKS))

import zephyr_patch  # noqa: E402


def apply(tmp_path, patch_body, content):
    """Write one-target framework tree + patch, apply twice, return states."""
    fw = tmp_path / "fw"
    fw.mkdir()
    (fw / "f.c").write_text(content, encoding="utf-8", newline="\n")
    patch = tmp_path / "f.patch"
    patch.write_text(patch_body, encoding="utf-8", newline="\n")
    stats1 = zephyr_patch.apply_patch(str(patch), str(fw), "f.c")
    after1 = (fw / "f.c").read_text(encoding="utf-8")
    stats2 = zephyr_patch.apply_patch(str(patch), str(fw), "f.c")
    after2 = (fw / "f.c").read_text(encoding="utf-8")
    return stats1, after1, stats2, after2


class TestInsertion:
    # Pure-context insertion: the old block (context only) keeps matching
    # after the hunk lands -- re-runs must not re-insert (4x duplication bug).
    BODY = (
        "--- a/f.c\n+++ b/f.c\n@@ -1,2 +1,3 @@\n"
        " line-a\n+inserted\n line-c\n"
    )

    def test_applies_once_and_is_idempotent(self, tmp_path):
        s1, a1, s2, a2 = apply(tmp_path, self.BODY, "line-a\nline-c\n")
        assert a1 == "line-a\ninserted\nline-c\n"
        assert s1 == {"applied": 1, "already-applied": 0}
        assert s2 == {"applied": 0, "already-applied": 1}
        assert a1 == a2  # no duplication on re-run


class TestReplacement:
    BODY = (
        "--- a/f.c\n+++ b/f.c\n@@ -1,2 +1,2 @@\n"
        " line-a\n-line-old\n+line-new\n line-c\n"
    )

    def test_applies_and_is_idempotent(self, tmp_path):
        s1, a1, s2, a2 = apply(tmp_path, self.BODY, "line-a\nline-old\nline-c\n")
        assert a1 == "line-a\nline-new\nline-c\n"
        assert s2["already-applied"] == 1
        assert a1 == a2


class TestPureDeletion:
    # -U0 style: new block is empty. The empty block must not short-circuit
    # the "already applied" check on the first run.
    BODY = "--- a/f.c\n+++ b/f.c\n@@ -2,1 +2,0 @@\n-line two\n"

    def test_deletes_and_is_idempotent(self, tmp_path):
        s1, a1, s2, a2 = apply(
            tmp_path, self.BODY, "line one\nline two\nline three\n"
        )
        assert "line two" not in a1
        assert a1 == "line one\nline three\n"
        assert s1 == {"applied": 1, "already-applied": 0}
        assert s2["already-applied"] == 1
        assert a1 == a2


class TestDeletionWithContext:
    BODY = (
        "--- a/f.c\n+++ b/f.c\n@@ -1,3 +1,2 @@\n"
        " line-a\n-line-b\n line-c\n"
    )

    def test_deletes_and_is_idempotent(self, tmp_path):
        s1, a1, s2, a2 = apply(tmp_path, self.BODY, "line-a\nline-b\nline-c\n")
        assert a1 == "line-a\nline-c\n"
        assert s2["already-applied"] == 1
        assert a1 == a2


class TestNoMatch:
    def test_drifted_target_raises(self, tmp_path):
        fw = tmp_path / "fw"
        fw.mkdir()
        (fw / "f.c").write_text("totally different content\n", encoding="utf-8")
        patch = tmp_path / "f.patch"
        patch.write_text(
            "--- a/f.c\n+++ b/f.c\n@@ -1,2 +1,2 @@\n"
            " line-a\n-line-old\n+line-new\n line-c\n",
            encoding="utf-8", newline="\n",
        )
        with pytest.raises(RuntimeError, match="patch hunk did not match"):
            zephyr_patch.apply_patch(str(patch), str(fw), "f.c")
