# SPDX-License-Identifier: Apache-2.0
"""
Zephyr framework fixes applier (directory convention -- no registry).

Every file under

    zephyr/boards/arm/<board>/fixes/

is a fix for the installed framework-zephyr package; the directory IS the
registration:

    <framework-relative-path>          full-file override
    <framework-relative-path>.patch    unified-diff patch (idempotent)
    fixes.baseline                     "<target> <sha256>" of the pristine
                                       upstream file this fix was cut against

Content gating replaces version strings: before an override lands (or when a
patch hunk fails to match), the framework package's file is compared against
the recorded baseline -- a mismatch means the tarball changed under us and
the fix must be re-evaluated. Overrides warn (non-blocking, as before);
patch hunk mismatches raise, enriched with baseline context when available.

Executors are the unchanged pure modules zephyr_patch / zephyr_override.
Interface (call site in builder/frameworks/zephyr.py is unchanged):
    apply_all(platform_dir, framework_dir, zephyr_board, version=None)
"""

import hashlib
import os
from os.path import dirname, join

# Executors live next to this module.
_HERE = dirname(__file__)
if _HERE not in os.sys.path:
    os.sys.path.insert(0, _HERE)

import zephyr_override  # noqa: E402
import zephyr_patch  # noqa: E402

BASELINE_NAME = "fixes.baseline"
PATCH_SUFFIX = ".patch"


def apply_all(platform_dir, framework_dir, zephyr_board, version=None):
    """Apply every fix under zephyr/boards/arm/<zephyr_board>/fixes/.

    Boards without a fixes/ directory are a no-op (nRF54 boards ship none).
    """
    fixes_dir = join(platform_dir, "zephyr", "boards", "arm", zephyr_board, "fixes")
    if not os.path.isdir(fixes_dir):
        return  # this board ships no local fixes

    baseline = _load_baseline(fixes_dir)
    applied = []
    no_baseline = []

    for src in _iter_fix_files(fixes_dir):
        rel = os.path.relpath(src, fixes_dir)
        target = rel[: -len(PATCH_SUFFIX)] if rel.endswith(PATCH_SUFFIX) else rel
        expected = baseline.get(target)

        if rel.endswith(PATCH_SUFFIX):
            _apply_patch_with_context(src, framework_dir, target, expected)
        else:
            zephyr_override.apply_override(src, framework_dir, target, expected)

        applied.append(target)
        if not expected:
            no_baseline.append(target)

    stale = sorted(set(baseline) - set(applied))
    if stale:
        print(
            "WARNING: fixes.baseline lists targets with no fix file under "
            "%s: %s" % (fixes_dir, ", ".join(stale))
        )
    if no_baseline:
        print(
            "WARNING: no fixes.baseline entry for %s -- record the pristine "
            "upstream sha256 so framework upgrades are detected" % ", ".join(no_baseline)
        )
    print(
        "Applied %d Zephyr fix(es) for board '%s' (Zephyr %s)"
        % (len(applied), zephyr_board, version)
    )


def _iter_fix_files(fixes_dir):
    for root, dirs, files in os.walk(fixes_dir):
        dirs.sort()
        for fname in sorted(files):
            if fname == BASELINE_NAME:
                continue
            yield join(root, fname)


def _load_baseline(fixes_dir):
    baseline = {}
    path = join(fixes_dir, BASELINE_NAME)
    if not os.path.isfile(path):
        return baseline
    with open(path, "r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(None, 1)
            if len(parts) == 2:
                baseline[parts[0]] = parts[1].strip()
    return baseline


def _apply_patch_with_context(src_patch, framework_dir, target, expected_sha):
    try:
        zephyr_patch.apply_patch(src_patch, framework_dir, target)
    except RuntimeError as exc:
        detail = str(exc)
        dst = join(framework_dir, target)
        if expected_sha and os.path.isfile(dst):
            actual = _sha256(dst)
            if actual != expected_sha:
                detail += (
                    "; baseline drift: %s hashes %s, expected pristine %s -- "
                    "the framework package likely changed, re-evaluate this fix"
                    % (target, actual[:12], expected_sha[:12])
                )
        raise RuntimeError(detail)


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fp:
        for chunk in iter(lambda: fp.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()
