"""ADR-0006: framework views are writable copies, never the package cache."""

import hashlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ZEPHYR_DIR = REPO_ROOT / "builder" / "board_build" / "zephyr"
if str(ZEPHYR_DIR) not in sys.path:
    sys.path.insert(0, str(ZEPHYR_DIR))

from zephyr_view import atomic_write_text, digest_paths, ensure_view  # noqa: E402
import zephyr_override  # noqa: E402
import zephyr_patch  # noqa: E402


def _source_package(tmp_path):
    source = tmp_path / "framework"
    (source / "scripts").mkdir(parents=True)
    (source / "package.json").write_text('{"version": "3.40402.0"}\n',
                                          encoding="utf-8")
    (source / "scripts" / "build.py").write_text("UPSTREAM\n", encoding="utf-8")
    return source


def test_ensure_view_reuses_key_and_isolates_writes(tmp_path):
    source = _source_package(tmp_path)
    cache = tmp_path / "views"
    view = Path(ensure_view(source, cache, "key-1", prefix="pkg"))
    assert (view / "scripts" / "build.py").read_text() == "UPSTREAM\n"

    atomic_write_text(view / "scripts" / "build.py", "VIEW\n")
    assert (view / "scripts" / "build.py").read_text() == "VIEW\n"
    assert (source / "scripts" / "build.py").read_text() == "UPSTREAM\n"

    again = Path(ensure_view(source, cache, "key-1", prefix="pkg"))
    assert again == view


def test_digest_changes_with_content(tmp_path):
    source = _source_package(tmp_path)
    first = digest_paths([source / "scripts" / "build.py"])
    atomic_write_text(source / "scripts" / "build.py", "CHANGED\n")
    second = digest_paths([source / "scripts" / "build.py"])
    assert first != second


def test_override_leaves_source_untouched(tmp_path):
    source = _source_package(tmp_path)
    view = Path(ensure_view(source, tmp_path / "views", "key", prefix="pkg"))
    pristine = source / "scripts" / "build.py"
    baseline = hashlib.sha256(pristine.read_bytes()).hexdigest()
    override = tmp_path / "override.py"
    override.write_text("OVERRIDE\n", encoding="utf-8")

    zephyr_override.apply_override(
        str(override), str(view), "scripts/build.py", baseline_sha=baseline)

    assert (view / "scripts" / "build.py").read_text() == "OVERRIDE\n"
    assert pristine.read_text() == "UPSTREAM\n"


def test_patch_leaves_source_untouched(tmp_path):
    source = _source_package(tmp_path)
    target = source / "scripts" / "patch.txt"
    target.write_text("old\n", encoding="utf-8")
    view = Path(ensure_view(source, tmp_path / "views", "key", prefix="pkg"))
    patch = tmp_path / "x.patch"
    patch.write_text(
        "--- a/scripts/patch.txt\n"
        "+++ b/scripts/patch.txt\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n",
        encoding="utf-8",
    )

    zephyr_patch.apply_patch(str(patch), str(view))

    assert (view / "scripts" / "patch.txt").read_text() == "new\n"
    assert target.read_text() == "old\n"