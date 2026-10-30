# SPDX-License-Identifier: Apache-2.0
"""
Zephyr module provisioner (directory convention).

Every directory under zephyr/modules/ is a Zephyr module this platform may
inject into the build:

    zephyr/modules/<name>/            vendored module source (copied into
                                      the framework cache every build)
    zephyr/modules/<name>/pin.yml     provisioning descriptor
    zephyr/modules/<name>/fixes/      fixes for the module itself (v2
                                      convention, applied to the module tree
                                      right after it lands in the cache)

pin.yml fields (all optional; no pin.yml = vendored, gated on all boards):

    gate.boards          Zephyr board names (build.zephyr.variant's first
                         component) this module applies to
    gate.families        chip family ids (build.chip_family)
    gate.prj_conf_tokens any of these tokens in the project's prj.conf opts
                         the module in
    remote / revision    external git source; with these the directory is a
                         stub and the module is cloned (pinned) into the
                         framework cache on first use
    override_env         environment variable carrying a developer-provided
                         module tree (checked before remote)

Gates AND across fields, OR within one list. Provisioned modules are
appended to ZEPHYR_EXTRA_MODULES -- Zephyr's own official injection channel
(consumed by zephyr_module.cmake from the environment), which unlike a
CMake-cache injection also reaches sysbuild child images (mcuboot).

Adding a module = dropping a directory; removing one = deleting it. The
builder never changes.
"""

import json
import os
import re
import shutil
import subprocess
import time
from os.path import basename, isdir, isfile, join

try:
    import yaml
except ImportError:
    import sys
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "pyyaml"], check=True)
    import yaml

# fixes.py lives next to this module; main.py puts this directory on
# sys.path before importing.
import fixes

PIN_NAME = "pin.yml"
_PRJ_CONF_CANDIDATES = ("zephyr/prj.conf", "prj.conf")


def provision(platform_dir, framework_dir, zephyr_board, family_id="",
              project_dir=""):
    """Provision every gated module and return the ZEPHYR_EXTRA_MODULES list.

    Also merges the result into os.environ["ZEPHYR_EXTRA_MODULES"] so the
    engine's cmake invocation (and any sysbuild child) discovers the modules.
    """
    modules_root = join(platform_dir, "zephyr", "modules")
    registered = []
    if not isdir(modules_root):
        return registered

    for entry in sorted(os.listdir(modules_root)):
        source = join(modules_root, entry)
        if not isdir(source):
            continue
        spec = _load_pin(source)
        if not _gate_passes(spec.get("gate") or {}, zephyr_board, family_id,
                            project_dir):
            continue

        if spec.get("remote"):
            module_dir = _ensure_pinned(entry, spec, platform_dir, framework_dir)
        else:
            module_dir = _refresh_vendored(entry, source, framework_dir)
        if module_dir:
            registered.append(module_dir)

    if registered:
        _register(registered)
    return registered


# --- registration -----------------------------------------------------------

def _register(module_dirs):
    """Deduplicate and append to os.environ["ZEPHYR_EXTRA_MODULES"]."""
    existing = [
        value for value in os.environ.get("ZEPHYR_EXTRA_MODULES", "").split(";")
        if value
    ]
    seen, ordered = set(), []
    for module in existing + module_dirs:
        norm = os.path.normcase(os.path.normpath(module))
        if module and norm not in seen:
            seen.add(norm)
            ordered.append(module)
    os.environ["ZEPHYR_EXTRA_MODULES"] = ";".join(ordered)
    print("XIAO modules registered via ZEPHYR_EXTRA_MODULES: %s"
          % ";".join(basename(m) for m in ordered))


# --- gating -----------------------------------------------------------------

def _load_pin(source):
    pin = join(source, PIN_NAME)
    if not isfile(pin):
        return {}
    with open(pin, "r", encoding="utf-8") as fp:
        data = yaml.safe_load(fp) or {}
    return data if isinstance(data, dict) else {}


def _gate_passes(gate, zephyr_board, family_id, project_dir):
    """AND across fields, OR within a list; unknown fields are ignored."""
    boards = gate.get("boards")
    if boards and zephyr_board not in boards:
        return False
    families = gate.get("families")
    if families and family_id not in families:
        return False
    tokens = gate.get("prj_conf_tokens")
    if tokens and not any(
            _prj_conf_has(project_dir, t) for t in tokens):
        return False
    return True


def _prj_conf_has(project_dir, token):
    """True if the project's prj.conf contains the given CONFIG token."""
    for rel in _PRJ_CONF_CANDIDATES:
        conf = join(project_dir, rel) if project_dir else rel
        if not isfile(conf):
            continue
        try:
            with open(conf, "r", encoding="utf-8", errors="ignore") as fp:
                if token in fp.read():
                    return True
        except OSError:
            pass
    return False


# --- vendored modules -------------------------------------------------------

def _refresh_vendored(name, source, framework_dir):
    """Copy the vendored module into the framework cache (refresh).

    pin.yml is provisioning metadata for this platform, not module content;
    it stays out of the copied tree.
    """
    target = join(framework_dir, "_pio", "modules", name)
    if isdir(target):
        shutil.rmtree(target)
    elif os.path.exists(target):
        os.remove(target)
    shutil.copytree(source, target,
                    ignore=shutil.ignore_patterns(PIN_NAME))
    if not isfile(join(target, "zephyr", "module.yml")):
        raise RuntimeError(
            "vendored module '%s' has no zephyr/module.yml" % name)
    return os.path.normpath(target)


# --- pinned external modules ------------------------------------------------

def _is_commit_hash(value):
    return value and re.match(r"[0-9a-f]{7,}$", value) is not None


def git_clone_with_retry(url, dst, revision, max_retries=3, retry_delay=5):
    """Clone a git repository with retry logic for unstable networks.

    Shared helper: west-dependency pre-install in the zephyr builder uses it
    as well.
    """
    for attempt in range(1, max_retries + 1):
        args = ["git", "clone"]
        is_commit = _is_commit_hash(revision)
        if not is_commit and revision:
            args.extend(["--branch", revision, "--depth", "1"])
        elif not is_commit:
            args.extend(["--depth", "1"])

        try:
            print("  Cloning %s (attempt %d/%d)" % (url, attempt, max_retries))
            subprocess.run(args + [url, dst], check=True,
                           capture_output=True, text=True)
            if is_commit and revision:
                subprocess.run(
                    ["git", "-C", dst, "checkout", revision],
                    check=True, capture_output=True, text=True)
            print("  OK: %s" % basename(dst))
            return True
        except subprocess.CalledProcessError as e:
            if isdir(dst):
                shutil.rmtree(dst, ignore_errors=True)
            if attempt < max_retries:
                print("  Failed (attempt %d): %s"
                      % (attempt, e.stderr.strip() if e.stderr else e))
                print("  Retrying in %ds..." % retry_delay)
                time.sleep(retry_delay)
            else:
                print("  FAILED after %d attempts: %s" % (max_retries, url))
                return False
    return False


PIN_RECORD = ".pin"


def _load_pin_record(cache_dir):
    """The remote/revision a cached clone was cut from ({} if absent)."""
    try:
        with open(join(cache_dir, PIN_RECORD), "r", encoding="utf-8") as fp:
            data = json.load(fp)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_pin_record(cache_dir, remote, revision):
    with open(join(cache_dir, PIN_RECORD), "w", encoding="utf-8") as fp:
        json.dump({"remote": remote, "revision": revision}, fp, indent=2)


def _ensure_pinned(name, spec, platform_dir, framework_dir):
    """Return a valid module root (with zephyr/module.yml), cloning on demand.

    Order: explicit developer override (override_env, returned untouched --
    a developer tree manages its own patches) -> cached clone whose .pin
    record still matches the pin.yml spec (fixes already applied,
    re-checked idempotently) -> git clone of the pinned revision followed
    by the module's own fixes/ and a fresh .pin record. A cache that was
    cut from a different remote/revision (or predates .pin entirely) is
    re-cloned, so bumping revision in a pin.yml actually lands on machines
    that already have a cache.
    """
    cache_dir = join(framework_dir, "_pio", "modules", name)
    marker = join(cache_dir, "zephyr", "module.yml")
    label = spec.get("label", name)
    remote = spec.get("remote")
    revision = spec.get("revision", "")

    override_env = spec.get("override_env", "")
    override = os.environ.get(override_env, "") if override_env else ""
    if override and isfile(join(override, "zephyr", "module.yml")):
        return os.path.normpath(override)

    fixes_dir = join(platform_dir, "zephyr", "modules", name, "fixes")

    if isfile(marker):
        recorded = _load_pin_record(cache_dir)
        if (recorded.get("remote") == remote
                and recorded.get("revision") == revision):
            # Cached clone matches the pin: fixes were applied when it
            # landed; the v2 walkers are idempotent, so re-checking costs
            # nothing and self-heals a cache that predates a fix.
            if override_env:
                os.environ[override_env] = os.path.normpath(cache_dir)
            fixes.apply_fixes_dir(fixes_dir, cache_dir,
                                  "module '%s'" % name, None)
            return os.path.normpath(cache_dir)
        print("XIAO module: pin changed for %s (%s -> %s), re-cloning"
              % (name, recorded.get("revision") or "?", revision or "?"))

    print("XIAO module: cloning %s %s -> %s" % (label, revision, cache_dir))
    if isdir(cache_dir):
        shutil.rmtree(cache_dir, ignore_errors=True)
    if not git_clone_with_retry(remote, cache_dir, revision):
        return None
    if not isfile(marker):
        print("XIAO module: %s cloned but zephyr/module.yml missing" % label)
        return None
    _save_pin_record(cache_dir, remote, revision)
    if override_env:
        # Publish the cache path so sample CMakeLists (which read e.g.
        # XIAO_EDGE_AI_DIR directly) work without a developer override.
        os.environ[override_env] = os.path.normpath(cache_dir)
    fixes.apply_fixes_dir(fixes_dir, cache_dir,
                          "module '%s'" % name, None)
    return os.path.normpath(cache_dir)
