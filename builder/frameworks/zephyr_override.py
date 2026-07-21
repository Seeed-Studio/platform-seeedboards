# SPDX-License-Identifier: Apache-2.0
"""
Zephyr framework override applier (执行器 B).

Pure executor: copies one override file over a target path inside the
framework-zephyr package. Reads no manifest, knows nothing about board/version —
it only receives "source file, framework root, target relpath, optional baseline".
Includes baseline_sha verification to catch silent regressions when the framework
package is upgraded (a whole-file override could silently clobber a newer upstream
file).

Dispatched by builder/frameworks/zephyr_fixes.py. Interface:
    apply_override(src_override, framework_dir, target_relpath, baseline_sha=None)
"""

import hashlib
import os
import shutil
from os.path import join


def apply_override(src_override, framework_dir, target_relpath, baseline_sha=None):
    """Copy src_override over framework_dir/target_relpath (whole file).

    baseline_sha handling (guards against framework upgrades silently clobbering
    a newer upstream file):
      - target already equals our override source (re-run build after a previous
        apply) → idempotent, no warning;
      - target equals baseline_sha (upstream original) → about to apply, ok;
      - target matches neither → WARN (upstream likely upgraded; re-evaluate).
      A missing target (upstream file absent) is the typical override case and
      produces no baseline warning. Non-blocking in all cases.
    """
    dst = join(framework_dir, target_relpath)
    warning = None
    baseline_ok = None
    override_src_sha = _sha256(src_override)

    if baseline_sha and os.path.isfile(dst):
        actual = _sha256(dst)
        if actual == override_src_sha:
            # Already our override version (previous build applied it) — idempotent.
            baseline_ok = None
        elif actual != baseline_sha:
            warning = (
                "override baseline mismatch for %s: expected upstream %s, got %s "
                "(framework package may have been upgraded; re-evaluate whether "
                "this override still applies)" % (target_relpath, baseline_sha, actual)
            )
            print("WARNING: " + warning)
            baseline_ok = False
        else:
            baseline_ok = True

    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    shutil.copy2(src_override, dst)
    print("Applied Zephyr override: %s -> %s" % (target_relpath, os.path.basename(src_override)))

    return {"applied": True, "baseline_ok": baseline_ok, "warning": warning}


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
