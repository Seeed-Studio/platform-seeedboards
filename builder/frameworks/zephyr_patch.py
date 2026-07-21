# SPDX-License-Identifier: Apache-2.0
"""
Zephyr framework patch applier (执行器 A).

Pure executor: applies one unified-diff patch to the framework-zephyr package.
Reads no manifest, knows nothing about board/version, does no directory scan —
it only receives "which patch, to which framework root". Idempotent: a hunk
already present is skipped.

Dispatched by builder/frameworks/zephyr_fixes.py. Interface:
    apply_patch(src_patch, framework_dir, target_relpath=None)
"""

import os
from os.path import join


def apply_patch(src_patch, framework_dir, target_relpath=None):
    """Apply a unified-diff patch to the framework package (idempotent).

    Each hunk's target file is determined by its ``+++`` line (stripped of a/ b/
    prefixes), relative to framework_dir. target_relpath is informational only
    (for logs); it does not override the patch's own paths.

    Returns: {"applied": int, "already-applied": int}.
    Raises RuntimeError if a hunk does not match (build should fail).
    """
    stats = _apply_unified_patch(src_patch, framework_dir)
    name = os.path.basename(src_patch)
    if stats["applied"] > 0:
        print("Applied Zephyr patch: %s (%d hunk(s))" % (name, stats["applied"]))
    elif stats["already-applied"] > 0:
        print("Patch already applied, skipped: %s" % name)
    return stats


# --- idempotent unified-diff application (unchanged from original impl) ---

def _strip_patch_path(path):
    if path.startswith("a/") or path.startswith("b/"):
        return path[2:]
    return path


def _detect_newline(text):
    if "\r\n" in text:
        return "\r\n"
    if "\r" in text:
        return "\r"
    return "\n"


def _find_block(lines, block):
    if not block:
        return 0

    limit = len(lines) - len(block) + 1
    for index in range(max(limit, 0)):
        if lines[index:index + len(block)] == block:
            return index

    return -1


def _read_text_lines(file_path):
    with open(file_path, "r", encoding="utf-8", newline="") as f:
        text = f.read()

    return text.splitlines(), _detect_newline(text), text.endswith(("\n", "\r"))


def _write_text_lines(file_path, lines, newline, trailing_newline):
    text = newline.join(lines)
    if trailing_newline:
        text += newline

    with open(file_path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def _apply_patch_hunk(file_path, old_lines, new_lines):
    lines, newline, trailing_newline = _read_text_lines(file_path)

    old_index = _find_block(lines, old_lines)
    if old_index >= 0:
        lines[old_index:old_index + len(old_lines)] = new_lines
        _write_text_lines(file_path, lines, newline, trailing_newline)
        return "applied"

    if _find_block(lines, new_lines) >= 0:
        return "already-applied"

    raise RuntimeError("patch hunk did not match %s" % file_path)


def _apply_unified_patch(patch_path, target_root):
    with open(patch_path, "r", encoding="utf-8", newline="") as f:
        patch_lines = f.read().splitlines()

    target_relpath = None
    old_lines = []
    new_lines = []
    stats = {"applied": 0, "already-applied": 0}

    def flush_hunk():
        if target_relpath is None or (not old_lines and not new_lines):
            return

        file_path = join(target_root, target_relpath)
        result = _apply_patch_hunk(file_path, old_lines, new_lines)
        stats[result] += 1
        old_lines.clear()
        new_lines.clear()

    for line in patch_lines:
        if line.startswith("+++ "):
            flush_hunk()
            target = line[4:].strip()
            if target == "/dev/null":
                raise RuntimeError("creating files from patches is not supported: %s" % patch_path)
            target_relpath = _strip_patch_path(target.split("\t", 1)[0])
            continue

        if line.startswith("@@ "):
            flush_hunk()
            continue

        if target_relpath is None:
            continue

        if line.startswith(" "):
            old_lines.append(line[1:])
            new_lines.append(line[1:])
        elif line.startswith("-"):
            old_lines.append(line[1:])
        elif line.startswith("+"):
            new_lines.append(line[1:])
        elif line.startswith("\\ No newline at end of file"):
            continue
        elif line.startswith(("diff --git ", "index ", "--- ")):
            continue

    flush_hunk()
    return stats
