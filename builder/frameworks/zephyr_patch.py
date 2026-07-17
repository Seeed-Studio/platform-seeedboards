import os
from os.path import join


def apply_framework_patches(platform_dir, framework_dir):
    patches_root = join(platform_dir, "zephyr", "patches", "framework-zephyr")
    if not os.path.isdir(patches_root):
        return

    for patch_name in sorted(os.listdir(patches_root)):
        if not patch_name.endswith(".patch"):
            continue

        patch_path = join(patches_root, patch_name)
        stats = _apply_unified_patch(patch_path, framework_dir)
        if stats["applied"] > 0:
            print("Applied Zephyr patch: %s" % patch_name)


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
