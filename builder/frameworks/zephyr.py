# Copyright 2019-present PlatformIO <contact@platformio.org>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
The Zephyr Project is a scalable real-time operating system (RTOS) supporting multiple
hardware architectures, optimized for resource constrained devices, and built with
safety and security in mind.

https://github.com/zephyrproject-rtos/zephyr
"""

from os.path import join
import subprocess
import os
import json
import shutil
import sys
from SCons.Script import Import, SConscript
try:
    import yaml
except ImportError:
    subprocess.run(["pip", "install", "pyyaml"], check=True)
    import yaml

Import("env")

platform_name = env.subst("$PIOPLATFORM")
board_name = env.get("BOARD", "")
platform = env.PioPlatform()
framework_package_name = platform.get_zephyr_package_name(board_name)
framework_version = None

if board_name and "nrf" in board_name:
    env.Replace(
        PIOPLATFORM="nordicnrf52"
    )
if board_name and "stm32" in board_name:
    env.Replace(
        PIOPLATFORM="ststm32"
    )
# Clone hal_nordic package from west.yaml if not present
framework_dir = platform.get_package_dir(framework_package_name)
platform_dir = platform.get_dir()
west_yml_path = join(framework_dir, "west.yml")
hal_nordic_dir = join(framework_dir, "_pio", "modules", "hal", "nordic")

# Copy custom board definitions into Zephyr framework boards directory
# so that Zephyr CMake can discover them during build configuration.
# Note: We intentionally use copytree instead of symlink on all platforms.
# Python's pathlib.Path.rglob() (used by Zephyr's list_boards.py) does not
# follow symlink directories by default, which makes symlinked boards
# invisible to CMake on macOS/Linux.
platform_boards_dir = join(platform_dir, "zephyr", "boards", "arm")
framework_boards_dir = join(framework_dir, "boards", "arm")
framework_vendor_boards_dir = join(framework_dir, "boards", "seeed")

def _get_framework_version():
    global framework_version
    if framework_version:
        return framework_version

    package_json = join(framework_dir, "package.json")
    with open(package_json, "r", encoding="utf-8") as fp:
        package_data = json.load(fp)

    raw_version = package_data.get("version", "")
    parts = raw_version.split(".")
    if len(parts) < 2 or not parts[1].isdigit():
        raise RuntimeError(
            f"Unexpected {framework_package_name} version: {raw_version}"
        )

    encoded = parts[1].zfill(5)
    major = int(encoded[0])
    minor = int(encoded[1:3])
    patch = int(encoded[3:5])
    framework_version = f"{major}.{minor}.{patch}"
    return framework_version


def _board_copy_mode():
    version = _get_framework_version()
    try:
        major, minor, _patch = [int(part) for part in version.split(".")]
    except ValueError:
        return "refresh"

    if (major, minor) >= (4, 4):
        return "missing-only"
    return "refresh"


if os.path.isdir(platform_boards_dir):
    os.makedirs(framework_vendor_boards_dir, exist_ok=True)
    import shutil
    board_copy_mode = _board_copy_mode()
    for board_name_dir in os.listdir(platform_boards_dir):
        src = join(platform_boards_dir, board_name_dir)
        dst = join(framework_vendor_boards_dir, board_name_dir)
        stale_arm_dst = join(framework_boards_dir, board_name_dir)
        if not os.path.isdir(src):
            continue
        if os.path.isdir(stale_arm_dst):
            shutil.rmtree(stale_arm_dst)
        if board_copy_mode == "missing-only" and os.path.exists(dst):
            continue
        # Refresh copied board definitions on every build so local DTS/Kconfig
        # changes always override any stale board copies inside the framework.
        if os.path.islink(dst) and not os.path.exists(dst):
            os.remove(dst)
        elif os.path.isdir(dst):
            shutil.rmtree(dst)
        elif os.path.exists(dst):
            os.remove(dst)
        shutil.copytree(src, dst)
        print(f"Copied board: {board_name_dir} -> {dst}")

import re
import time


def _ensure_system_path_available():
    """Keep system tools like git available for west/zephyr helper scripts."""
    current_path = os.environ.get("PATH", "")
    if current_path:
        os.environ["PATH"] = current_path


def _get_zephyr_venv_dir():
    return join(
        env.subst("$PROJECT_CORE_DIR"),
        "penv",
        ".zephyr-" + _get_framework_version(),
    )


def _clear_problematic_pip_cache():
    pip_cache = os.path.join(
        os.environ.get("LOCALAPPDATA", ""),
        "pip",
        "cache",
        "wheels",
    )
    if not os.path.isdir(pip_cache):
        return

    for root, _, files in os.walk(pip_cache):
        for name in files:
            if name.startswith("docopt-") and name.endswith(".whl"):
                try:
                    os.remove(os.path.join(root, name))
                except OSError:
                    pass


def _ensure_zephyr_python_env():
    venv_dir = _get_zephyr_venv_dir()
    venv_data_file = join(venv_dir, "pio-zephyr-venv.json")
    python_exe = join(
        venv_dir,
        "Scripts" if os.name == "nt" else "bin",
        "python" + (".exe" if os.name == "nt" else ""),
    )

    recreate = not os.path.isfile(python_exe)
    if not recreate and os.path.isfile(venv_data_file):
        try:
            with open(venv_data_file, "r", encoding="utf-8") as fp:
                venv_data = json.load(fp)
            recreate = venv_data.get("version") != "1.0.0"
        except Exception:
            recreate = True
    elif not os.path.isfile(venv_data_file):
        recreate = True

    if recreate:
        if os.path.isdir(venv_dir):
            shutil.rmtree(venv_dir, ignore_errors=True)
        subprocess.run(
            [env.subst("$PYTHONEXE"), "-m", "venv", "--clear", venv_dir],
            check=True,
        )
        os.makedirs(venv_dir, exist_ok=True)
        with open(venv_data_file, "w", encoding="utf-8") as fp:
            json.dump({"version": "1.0.0"}, fp, indent=2)

    requirements = join(framework_dir, "scripts", "requirements-base.txt")
    _clear_problematic_pip_cache()
    subprocess.run(
        [
            python_exe,
            "-m",
            "pip",
            "install",
            "--no-cache-dir",
            "--disable-pip-version-check",
            "-r",
            requirements,
        ],
        check=True,
    )
    pinned_deps = [
        "pyelftools~=0.27",
        "PyYAML~=6.0.0",
        "pykwalify~=1.8.0",
        "packaging~=23.1.0",
        "cryptography>=2.6.0",
        "intelhex~=2.3.0",
        "click~=8.1.3",
        "cbor2~=5.4.6",
        "jsonschema~=4.25.1",
    ]
    if os.name == "nt":
        pinned_deps.append("windows-curses")
    subprocess.run(
        [
            python_exe,
            "-m",
            "pip",
            "install",
            "--no-cache-dir",
            "--disable-pip-version-check",
            *pinned_deps,
        ],
        check=True,
    )


def _ensure_minimal_west_workspace(framework_dir):
    """Create the minimum west workspace metadata expected by Zephyr 4.4.

    PlatformIO installs the selected Zephyr framework package as a plain source tree, not as a
    `west init` workspace. Newer Zephyr tooling may still call
    `Manifest.from_file()` and expect a `.west/config` file to exist.
    """
    west_dir = join(framework_dir, ".west")
    west_config = join(west_dir, "config")

    if not os.path.isdir(west_dir):
        os.makedirs(west_dir, exist_ok=True)

    expected = "[manifest]\npath = .\nfile = west.yml\n"
    current = ""
    if os.path.isfile(west_config):
        with open(west_config, "r", encoding="utf-8") as fp:
            current = fp.read()

    if current != expected:
        with open(west_config, "w", encoding="utf-8") as fp:
            fp.write(expected)


def _patch_platformio_path_handling(framework_dir):
    """Make PlatformIO's Zephyr env keep the system PATH and robust pip flags."""
    build_py = join(framework_dir, "scripts", "platformio", "platformio-build.py")
    if not os.path.isfile(build_py):
        return

    with open(build_py, "r", encoding="utf-8") as fp:
        text = fp.read()

    replacements = {
        '    zephyr_env["PATH"] = os.pathsep.join(additional_packages)\n': (
            '    zephyr_env["PATH"] = os.pathsep.join(\n'
            '        additional_packages + [zephyr_env.get("PATH", "")]\n'
            '    )\n'
        ),
        '"%s" -m pip install windows-curses': (
            '"%s" -m pip install --no-cache-dir --disable-pip-version-check windows-curses'
        ),
        '"%s" -m pip install -U ': (
            '"%s" -m pip install --no-cache-dir --disable-pip-version-check -U '
        ),
    }

    for needle, replacement in replacements.items():
        if needle in text and replacement not in text:
            text = text.replace(needle, replacement)

    with open(build_py, "w", encoding="utf-8") as fp:
        fp.write(text)


def _patch_platformio_object_naming(framework_dir):
    """Disambiguate duplicate source basenames inside framework modules.

    Zephyr 4.4's LVGL tree contains duplicate vg_lite_matrix.c files in
    different folders. PlatformIO's stock object naming can collapse them to
    the same .o target. Restrict the workaround to duplicate basenames only.
    """
    build_py = join(framework_dir, "scripts", "platformio", "platformio-build.py")
    if not os.path.isfile(build_py):
        return

    with open(build_py, "r", encoding="utf-8") as fp:
        text = fp.read()

    old_else = """            else:\n                obj_path = os.path.join(\n                    obj_path_temp, os.path.basename(src_path)\n                )\n"""
    new_else = """            else:\n                base_name = os.path.basename(src_path)\n                if base_name in duplicate_basenames:\n                    framework_root = FRAMEWORK_DIR\n                    if src_path.startswith(framework_root):\n                        unique_rel = os.path.relpath(src_path, framework_root)\n                    else:\n                        unique_rel = os.path.join(\n                            os.path.basename(os.path.dirname(src_path)),\n                            base_name,\n                        )\n                    obj_path = os.path.join(obj_path_temp, unique_rel)\n                else:\n                    obj_path = os.path.join(obj_path_temp, base_name)\n"""

    changed = False
    header_pattern = re.compile(
        r"def compile_source_files\(\n"
        r"\s+config, default_env, project_src_dir, prepend_dir=None\n"
        r"\):\n"
        r"\s+build_envs = prepare_build_envs\(config, default_env\)\n"
        r"\s+objects = \[\]\n"
        r"\s+for source in config\.get\(\"sources\", \[\]\):\n"
    )
    header_replacement = (
        "def compile_source_files(\n"
        "    config, default_env, project_src_dir, prepend_dir=None\n"
        "):\n"
        "    build_envs = prepare_build_envs(config, default_env)\n"
        "    objects = []\n"
        "    duplicate_basenames = set()\n"
        "    basename_count = {}\n"
        "    for source in config.get(\"sources\", []):\n"
        "        source_path = source.get(\"path\")\n"
        "        if not source_path or source_path.endswith(\".rule\"):\n"
        "            continue\n"
        "        if not os.path.isabs(source_path):\n"
        "            source_path = os.path.join(PROJECT_DIR, \"zephyr\", source_path)\n"
        "        base = os.path.basename(source_path)\n"
        "        basename_count[base] = basename_count.get(base, 0) + 1\n"
        "    duplicate_basenames = {k for k, v in basename_count.items() if v > 1}\n"
        "    for source in config.get(\"sources\", []):\n"
    )

    if "duplicate_basenames = set()" not in text:
        text, count = header_pattern.subn(header_replacement, text, count=1)
        changed = changed or count > 0
    if old_else in text and new_else not in text:
        text = text.replace(old_else, new_else)
        changed = True
    if changed:
        with open(build_py, "w", encoding="utf-8") as fp:
            fp.write(text)


def _patch_platformio_framework_package_name(framework_dir, framework_package_name):
    """Make PlatformIO's bundled Zephyr script use the selected package name."""
    build_py = join(framework_dir, "scripts", "platformio", "platformio-build.py")
    if not os.path.isfile(build_py):
        return

    with open(build_py, "r", encoding="utf-8") as fp:
        text = fp.read()

    replacements = {
        'platform.get_package_dir("framework-zephyr")': f'platform.get_package_dir("{framework_package_name}")',
        'platform.get_package_version("framework-zephyr")': f'platform.get_package_version("{framework_package_name}")',
        'platform.get_package("framework-zephyr")': f'platform.get_package("{framework_package_name}")',
        'config["name"].replace("framework-zephyr", "")': f'config["name"].replace("{framework_package_name}", "")',
    }

    changed = False
    for needle, replacement in replacements.items():
        if needle in text and replacement not in text:
            text = text.replace(needle, replacement)
            changed = True

    if changed:
        with open(build_py, "w", encoding="utf-8") as fp:
            fp.write(text)


def _patch_platformio_prebuilt_lib_linking(framework_dir):
    """Make PlatformIO link prebuilt static archives from modules correctly.

    PIO's stock codemodel parser (scripts/platformio/platformio-build.py) turns
    an absolute-path `.a` link fragment into a bare basename passed to the
    linker, plus a `-L<dir>`. ld does NOT search `-L` for bare filenames, so
    module prebuilt archives (e.g. sdk-edge-ai's Axon / nRF EdgeAI libraries)
    fail to link with "No such file or directory". Emit `-l<name>` instead so
    the `-L` search path actually resolves them. Only affects absolute-path
    `.a` archives (branch 4); relative archives (branch 5) are untouched.
    """
    build_py = join(framework_dir, "scripts", "platformio", "platformio-build.py")
    if not os.path.isfile(build_py):
        return

    with open(build_py, "r", encoding="utf-8") as fp:
        text = fp.read()

    old = (
        '                link_args["project_libs"]["standard_libs"].extend(\n'
        '                    [\n'
        '                        os.path.basename(lib)\n'
        '                        for lib in args\n'
        '                        if lib.endswith(".a")\n'
        '                    ]\n'
        '                )'
    )
    new = (
        '                link_args["project_libs"]["standard_libs"].extend(\n'
        '                    [\n'
        '                        ("-l" + os.path.basename(lib)[:-2][3:])\n'
        '                        if os.path.basename(lib).startswith("lib")\n'
        '                        else os.path.basename(lib)\n'
        '                        for lib in args\n'
        '                        if lib.endswith(".a")\n'
        '                    ]\n'
        '                )'
    )

    if old in text and new not in text:
        text = text.replace(old, new)
        with open(build_py, "w", encoding="utf-8") as fp:
            fp.write(text)
        print("Patched PlatformIO: prebuilt-archive linking (-l form for abs .a)")


def _is_commit_hash(value):
    return value and re.match(r"[0-9a-f]{7,}$", value) is not None


def _git_clone_with_retry(url, dst, revision, max_retries=3, retry_delay=5):
    """Clone a git repository with retry logic for unstable networks."""
    for attempt in range(1, max_retries + 1):
        args = ["git", "clone"]
        is_commit = _is_commit_hash(revision)
        if not is_commit and revision:
            args.extend(["--branch", revision, "--depth", "1"])
        elif not is_commit:
            args.extend(["--depth", "1"])

        try:
            print(f"  Cloning {url} (attempt {attempt}/{max_retries})")
            subprocess.run(args + [url, dst], check=True,
                           capture_output=True, text=True)
            if is_commit and revision:
                subprocess.run(
                    ["git", "-C", dst, "checkout", revision],
                    check=True, capture_output=True, text=True)
            print(f"  OK: {os.path.basename(dst)}")
            return True
        except subprocess.CalledProcessError as e:
            if os.path.isdir(dst):
                import shutil
                shutil.rmtree(dst, ignore_errors=True)
            if attempt < max_retries:
                print(f"  Failed (attempt {attempt}): {e.stderr.strip() if e.stderr else e}")
                print(f"  Retrying in {retry_delay}s...")
                time.sleep(retry_delay)
            else:
                print(f"  FAILED after {max_retries} attempts: {url}")
                return False
    return False


def _preinstall_west_deps(framework_dir, platform_name_hint):
    """Pre-install west.yml dependencies with retry so that install-deps.py
    can skip them later. This avoids the clean_up() wiping everything on
    a single clone failure."""
    west_yml = join(framework_dir, "west.yml")
    if not os.path.isfile(west_yml):
        return

    pio_dir = join(framework_dir, "_pio")

    with open(west_yml, "r", encoding="utf-8") as f:
        west_data = yaml.safe_load(f)
    manifest = west_data.get("manifest", {})
    remotes = {r["name"]: r for r in manifest.get("remotes", [])}
    default_remote = manifest.get("defaults", {}).get("remote", "")

    hal_modules_by_platform = {
        "nordicnrf52": {"hal_nordic"},
        "nordicnrf51": {"hal_nordic"},
        "ststm32": {"hal_st", "hal_stm32"},
    }
    required_hal_modules = hal_modules_by_platform.get(platform_name_hint)
    if not required_hal_modules:
        return

    print("Pre-installing Zephyr west dependencies (with retry)...")

    for proj in manifest.get("projects", []):
        name = proj.get("name", "")
        proj_path = proj.get("path", name)

        # Skip tool packages
        if proj_path.startswith("tool") or name.startswith("nrf_hw_"):
            continue

        # Only install HAL packages needed by the selected platform. Core
        # west modules, including cmsis and cmsis_6, are installed normally.
        if name.startswith("hal_") and name not in required_hal_modules:
            continue

        dst = join(pio_dir, proj_path)
        if os.path.isdir(dst):
            continue

        # Build URL
        if "url" in proj:
            proj_url = proj["url"]
            if not proj_url.startswith("http"):
                url_base = remotes.get(
                    proj.get("remote", default_remote), {}
                ).get("url-base", "")
                proj_url = url_base.rstrip("/") + "/" + proj_url.lstrip("/")
        else:
            url_base = remotes.get(
                proj.get("remote", default_remote), {}
            ).get("url-base", "")
            repo_path = proj.get("repo-path", name)
            proj_url = url_base.rstrip("/") + "/" + repo_path + ".git"

        revision = proj.get("revision")
        print(f"Pre-installing: {name}")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        _git_clone_with_retry(proj_url, dst, revision)

    print("Pre-install complete.")


# ---------------------------------------------------------------------------
# Edge AI (sdk-edge-ai) integration
#
# edge-AI samples reuse Nordic's Edge AI Add-on (sdk-edge-ai v2.1.0), a Zephyr
# module whose heavy lifting is prebuilt static archives (Axon NPU driver +
# nRF EdgeAI runtime). It is registered only for samples that opt in via
# `CONFIG_NRF_EDGEAI=y` in prj.conf, so non-edge-AI samples (e.g. zephyr-blink)
# are unaffected. The module source is provisioned three ways, in order:
#   1. XIAO_EDGE_AI_DIR / XIAO_EDGE_IMPULSE_DIR env override (local clone)
#   2. a developer's local clone at the well-known NCS add-on path
#   3. a one-time git clone (tag) into the framework cache (turnkey, 方案 3)
# This keeps the integration off the (live) framework package and off the shared
# board JSON, and reproducible on a fresh machine.
# ---------------------------------------------------------------------------

_EDGE_AI_REMOTE = "https://github.com/nrfconnect/sdk-edge-ai.git"
_EDGE_AI_REVISION = "v2.1.0"
_EDGE_AI_CACHE = join(framework_dir, "_pio", "modules", "sdk-edge-ai")
_EDGE_AI_LOCAL = "D:/workspace/ncs/edge_add_on_2/edge-ai"

_EDGE_IMPULSE_REMOTE = "https://github.com/edgeimpulse/edge-impulse-sdk-zephyr.git"
_EDGE_IMPULSE_REVISION = "v1.88.1"
_EDGE_IMPULSE_CACHE = join(framework_dir, "_pio", "modules", "edge-impulse-sdk-zephyr")
_EDGE_IMPULSE_LOCAL = "D:/workspace/ncs/edge_add_on_2/modules/edge-impulse-sdk-zephyr"


def _prj_conf_has(token):
    """True if the project's prj.conf contains the given CONFIG token."""
    project_dir = env.subst("$PROJECT_DIR")
    for rel in ("zephyr/prj.conf", "prj.conf"):
        conf = join(project_dir, rel)
        if os.path.isfile(conf):
            try:
                with open(conf, "r", encoding="utf-8", errors="ignore") as fp:
                    if token in fp.read():
                        return True
            except OSError:
                pass
    return False


def _is_edge_ai_sample():
    # An edge-AI sample opts in via either the nRF EdgeAI runtime or the bare
    # Axon NPU driver (e.g. person_detection uses CONFIG_NRF_AXON directly).
    return _prj_conf_has("CONFIG_NRF_EDGEAI=y") or _prj_conf_has(
        "CONFIG_NRF_AXON=y"
    )


def _ensure_module(label, cache_dir, remote, revision, override_env, local_dir):
    """Return a valid module root (with zephyr/module.yml), cloning on demand.

    Order: env override -> local dev clone -> cached clone -> git fetch.
    """
    marker = join(cache_dir, "zephyr", "module.yml")

    override = os.environ.get(override_env, "")
    if override and os.path.isfile(join(override, "zephyr", "module.yml")):
        return os.path.normpath(override)

    if local_dir and os.path.isfile(join(local_dir, "zephyr", "module.yml")):
        return os.path.normpath(local_dir)

    if os.path.isfile(marker):
        return os.path.normpath(cache_dir)

    print(f"XIAO Edge AI: cloning {label} {revision} -> {cache_dir}")
    if os.path.isdir(cache_dir):
        shutil.rmtree(cache_dir, ignore_errors=True)
    if not _git_clone_with_retry(remote, cache_dir, revision):
        return None
    if not os.path.isfile(marker):
        print(f"XIAO Edge AI: {label} cloned but zephyr/module.yml missing")
        return None
    return os.path.normpath(cache_dir)


def _patch_xiao_dfu_quiet(framework_dir):
    """Silence the xiao_dfu_reset per-event debug printk.

    The module prints "[xiao_dfu] msg type=... baud=..." on EVERY CDC ACM
    line-coding event (every host serial-port open/close), flooding the console
    in normal use. Neuter the two deferred debug work submissions so they never
    fire; the real "1200 touch" LOG_INF (actual DFU entry) in the callback is
    untouched.
    """
    src = join(framework_dir, "_pio", "modules", "xiao_dfu_reset",
               "src", "xiao_dfu_reset.c")
    if not os.path.isfile(src):
        return
    with open(src, "r", encoding="utf-8") as fp:
        text = fp.read()
    subs = {
        "k_work_submit(&xiao_dfu_init_work);":
            "/* XIAO: armed-notification printk silenced (console spam) */",
        "k_work_submit(&xiao_dfu_dbg_work);":
            "/* XIAO: per-event debug printk silenced (console spam) */",
    }
    changed = False
    for old, new in subs.items():
        if old in text:
            text = text.replace(old, new)
            changed = True
    if changed:
        with open(src, "w", encoding="utf-8") as fp:
            fp.write(text)
        print("XIAO: silenced xiao_dfu_reset per-event debug printk")


def _patch_cdc_vidpid(framework_dir):
    """Force the XIAO nRF54LM20B app CDC to Seeed 0x2886:0x8013.

    The VID/PID override belongs in the board's Kconfig.defconfig, but the
    board-copy step is 'missing-only' for Zephyr >=4.4 (see commit f629163),
    so a framework copy made before the override was added is never refreshed
    and the device enumerates with Zephyr's stock 0x2fe3:0x0004 -- which the
    1200-bps DFU upload path (nrf_build.py _APP_CDC_VIDPID="2886:8013") cannot
    find, so auto-flashing falls back to manual DFU. Inject the override into
    the framework's copied Kconfig.defconfig on every build (idempotent), so
    new and existing installs both get 2886:8013 without touching the
    missing-only copy logic.
    """
    path = join(framework_dir, "boards", "seeed", "xiao_nrf54lm20b",
                "Kconfig.defconfig")
    if not os.path.isfile(path):
        return
    with open(path, "r", encoding="utf-8") as fp:
        text = fp.read()

    # Fresh copy from a platform source that already carries the override ->
    # nothing to do (idempotent on repeat builds too).
    if "CDC_ACM_SERIAL_PID" in text:
        return

    override = (
        "\n"
        "config CDC_ACM_SERIAL_VID\n"
        "\thex\n"
        "\tdefault 0x2886\n"
        "\n"
        "config CDC_ACM_SERIAL_PID\n"
        "\thex\n"
        "\tdefault 0x8013\n"
        "\n"
        "config CDC_ACM_SERIAL_PRODUCT_STRING\n"
        "\tstring\n"
        "\tdefault \"XIAO_NRF54LM20B\"\n"
    )
    src_line = 'source "boards/common/usb/Kconfig.cdc_acm_serial.defconfig"'
    if src_line in text:
        text = text.replace(src_line, src_line + override, 1)
    elif "endif # BOARD_XIAO_NRF54LM20B_NRF54LM20B_CPUAPP" in text:
        text = text.replace(
            "endif # BOARD_XIAO_NRF54LM20B_NRF54LM20B_CPUAPP",
            override + "endif # BOARD_XIAO_NRF54LM20B_NRF54LM20B_CPUAPP", 1)
    else:
        # Unrecognised file shape; leave it untouched rather than corrupt it.
        return

    with open(path, "w", encoding="utf-8") as fp:
        fp.write(text)
    print("XIAO: ensured CDC ACM VID:PID = 2886:8013 in board Kconfig.defconfig")


def _patch_edge_impulse_sdk(ei_dir):
    """Stop the Edge Impulse SDK from building Espressif (ESP32) sources on ARM.

    Its ARM branch globs "*.s" under the whole SDK; on case-insensitive Windows
    that also matches the ESP32 Xtensa "*.S" files (porting/espressif/ESP-NN),
    which (a) are wrong-target assembly for Cortex-M and (b) produce object
    paths longer than Windows MAX_PATH (260). Exclude the espressif tree. This
    mirrors how the upstream ESP32 branch already excludes it.
    """
    cmake = join(ei_dir, "edge-impulse-sdk", "cmake", "zephyr", "CMakeLists.txt")
    if not os.path.isfile(cmake):
        return
    with open(cmake, "r", encoding="utf-8") as fp:
        text = fp.read()
    old = '        RECURSIVE_FIND_FILE_APPEND(EI_SOURCE_FILES "${EI_SDK_FOLDER}" "*.s")\n'
    new = (
        '        # XIAO nRF54LM20B: exclude the Espressif (ESP32) tree so its\n'
        '        # Xtensa .S is not built for ARM (Windows "*.s" matches "*.S")\n'
        '        # and the object path stays under Windows MAX_PATH (260).\n'
        '        RECURSIVE_FIND_FILE_EXCLUDE_DIR(EI_SOURCE_FILES '
        '"${EI_SDK_FOLDER}" "espressif" "*.s")\n'
    )
    if old in text and new not in text:
        text = text.replace(old, new)
        with open(cmake, "w", encoding="utf-8") as fp:
            fp.write(text)
        print("XIAO Edge AI: patched edge-impulse-sdk to exclude ESP32 sources (ARM)")

    # The EXCLUDE_DIR macro matches ".*\/<dir>\/.*" with forward slashes, which
    # never matches Windows backslash paths -> excludes silently no-op on
    # Windows. Normalise to forward slashes before matching.
    utils_cmake = join(ei_dir, "edge-impulse-sdk", "cmake", "utils.cmake")
    if os.path.isfile(utils_cmake):
        with open(utils_cmake, "r", encoding="utf-8") as fp:
            utext = fp.read()
        u_old = '    IF (file_path MATCHES ".*\\/${exclude_dir}\\/.*")\n'
        u_new = (
            '    STRING(REPLACE "\\\\" "/" _fp_norm "${file_path}")\n'
            '    IF (_fp_norm MATCHES ".*/${exclude_dir}/.*")\n'
        )
        if u_old in utext and u_new not in utext:
            utext = utext.replace(u_old, u_new)
            with open(utils_cmake, "w", encoding="utf-8") as fp:
                fp.write(utext)
            print("XIAO Edge AI: patched edge-impulse-sdk EXCLUDE_DIR macro (Win path-sep)")


def _provision_edge_ai():
    """Register sdk-edge-ai (and edge-impulse-sdk-zephyr if needed) as Zephyr
    modules for edge-AI samples before the Zephyr build runs."""
    if not _is_edge_ai_sample():
        return

    ea_dir = _ensure_module(
        "sdk-edge-ai", _EDGE_AI_CACHE, _EDGE_AI_REMOTE, _EDGE_AI_REVISION,
        "XIAO_EDGE_AI_DIR", _EDGE_AI_LOCAL)
    if not ea_dir:
        print("XIAO Edge AI: sdk-edge-ai not available (set XIAO_EDGE_AI_DIR or "
              "allow network for the one-time clone); skipping registration.")
        return

    modules = [ea_dir]
    # The hello_ei sample (26) also needs the Edge Impulse SDK Zephyr module.
    if _prj_conf_has("CONFIG_EDGE_IMPULSE_SDK=y"):
        ei_dir = _ensure_module(
            "edge-impulse-sdk-zephyr", _EDGE_IMPULSE_CACHE,
            _EDGE_IMPULSE_REMOTE, _EDGE_IMPULSE_REVISION,
            "XIAO_EDGE_IMPULSE_DIR", _EDGE_IMPULSE_LOCAL)
        if ei_dir:
            _patch_edge_impulse_sdk(ei_dir)
            modules.append(ei_dir)
        else:
            print("XIAO Edge AI: edge-impulse-sdk-zephyr not available; "
                  "sample 26 (hello_ei) will fail to build.")

    existing = env.get("PIO_NCS_MODULES", "")
    ordered = existing.split(";") + modules if existing else list(modules)
    seen, deduped = set(), []
    for m in ordered:
        if m and m not in seen:
            seen.add(m)
            deduped.append(m)
    env["PIO_NCS_MODULES"] = ";".join(deduped)
    os.environ["XIAO_EDGE_AI_DIR"] = ea_dir
    print(f"XIAO Edge AI: registered modules -> {env['PIO_NCS_MODULES']}")


# Pre-install west dependencies with retry before platformio-build.py runs
# This ensures they exist when install-deps.py checks, avoiding its
# destructive clean_up() on any single failure.
_ensure_system_path_available()
_ensure_zephyr_python_env()
_ensure_minimal_west_workspace(framework_dir)
_preinstall_west_deps(framework_dir, env.subst("$PIOPLATFORM"))
_patch_platformio_path_handling(framework_dir)
_patch_platformio_object_naming(framework_dir)
_patch_platformio_framework_package_name(framework_dir, framework_package_name)
_patch_platformio_prebuilt_lib_linking(framework_dir)
_patch_xiao_dfu_quiet(framework_dir)
_patch_cdc_vidpid(framework_dir)
_provision_edge_ai()

if board_name == "seeed-xiao-stm32c5":
    # Copy every bundled Zephyr module under zephyr/modules/ into the framework
    # package and register each via ZEPHYR_EXTRA_MODULES, which is Zephyr's
    # official way to inject modules outside the west manifest (each module's
    # zephyr/module.yml is then discovered normally). Add a new module by
    # simply dropping it under zephyr/modules/<name>/ — no edit needed here.
    modules_root = join(platform_dir, "zephyr", "modules")
    if os.path.isdir(modules_root):
        extra_modules = [
            value for value in os.environ.get("ZEPHYR_EXTRA_MODULES", "").split(";")
            if value
        ]
        for entry in os.listdir(modules_root):
            source_module_dir = join(modules_root, entry)
            if not os.path.isdir(source_module_dir):
                continue
            target_module_dir = join(framework_dir, "_pio", "modules", entry)
            if os.path.exists(target_module_dir):
                if os.path.isdir(target_module_dir):
                    shutil.rmtree(target_module_dir)
                else:
                    os.remove(target_module_dir)
            shutil.copytree(source_module_dir, target_module_dir)
            extra_modules.append(target_module_dir)
        os.environ["ZEPHYR_EXTRA_MODULES"] = ";".join(extra_modules)

# Apply per-board Zephyr fixes (patches + overrides) registered in
# zephyr/fixes.yml. Dispatched by zephyr_fixes.py — boards absent from the
# manifest get no fixes, so there is no coupling across boards/packages.
sys.path.insert(0, join(platform_dir, "builder", "frameworks"))
from zephyr_fixes import apply_all

apply_all(platform_dir, framework_dir,
          platform.get_zephyr_board_name(board_name),
          _get_framework_version())

SConscript(
    join(framework_dir, "scripts", "platformio", "platformio-build.py"), exports="env")
    
if board_name and "nrf" in board_name:
    env.Replace(
        PIOPLATFORM=platform_name
    )
if board_name and "stm32" in board_name:
    env.Replace(
        PIOPLATFORM=platform_name
    )
