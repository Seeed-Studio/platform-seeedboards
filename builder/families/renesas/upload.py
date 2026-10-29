# Copyright 2026-present Seeed Studio
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Upload-layer deltas for the renesas family (moved from the retired
renesas_build.py; behavior is unchanged).

The locked upstream platform-renesas-ra v1.9.0 builder dispatches the
protocols it knows (mbed, dfu, sam-ba, jlink, OpenOCD-via-debug-tools,
custom). Two deltas are applied around it:

- pyocd: the upstream dispatch has NO pyocd branch — without a takeover
  the build falls through to "unknown upload protocol" and registers an
  upload alias with no actions. The takeover registry below
  pre-configures the full uploader command and rewrites UPLOAD_PROTOCOL
  to "custom" (pure passthrough) before the upstream script runs, then
  grafts the artifact chain after it: the upstream custom branch rides
  target_firm = the plain .bin, but pyocd must flash the .hex — its
  records embed the 0x4000 app offset, while `pyocd flash -a 0x0` on a
  raw .bin writes the app over the bootloader.

- sam-ba: NOT a takeover — the upstream branch carries the BeforeUpload
  port/touch sequence that the custom passthrough lacks. The build rides
  the upstream branch and graft_sam_ba_hardening() re-hardens it after
  the fact: an explicit tool-bossac executable path, a quoted absolute
  SOURCE in UPLOADCMD, --verify, and separate --usb-port/--offset flags
  (upstream hard-codes a bare "bossac", always --usb-port --erase, and
  appends no --offset — the XIAO RA4M1 needs offset 0x4000).

The pyocd/r7fa4m1ab installers moved verbatim from renesas_build.py and
stay unpinned on purpose (debt R1 in the family bug backlog).

This module is a regular Python import (not SCons-exec'd), so plain
``__file__`` anchors would be safe here.
"""

import subprocess
import sys
from os.path import join
from platform import system


def install_pyocd():
    # Kept verbatim from the retired renesas_build.py, including the
    # unpinned pip install — do not "fix" here; tracked as debt R1.
    try:
        import pyocd
        print("pyocd is already installed")
    except ImportError:
        print("pyocd is not installed, installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyocd"])
        print("pyocd installed successfully")


def install_r7fa4m1ab():
    # Kept verbatim from the retired renesas_build.py (debt R1).
    try:
        output = subprocess.check_output(
            [sys.executable, "-m", "pyocd", "pack", "show"], text=True)
        if "r7fa4m1ab" not in output:
            print("r7fa4m1ab not installed, installing...")
            subprocess.check_call(
                [sys.executable, "-m", "pyocd", "pack", "install", "r7fa4m1ab"])
            print("r7fa4m1ab installed successfully")
        else:
            print("r7fa4m1ab is already installed")
    except subprocess.CalledProcessError as e:
        print(f"Error installing r7fa4m1ab: {e}")
        print(f"Return code: {e.returncode}")
        print(f"Output: {e.output.decode() if e.output else 'None'}")
        print(f"Error: {e.stderr.decode() if e.stderr else 'None'}")
        sys.exit(1)


class Protocol:
    """One takeover upload protocol as registered in PROTOCOLS.

    ``configure`` (env, platform, board) — pre-set
                 UPLOADER/UPLOADERFLAGS/UPLOADCMD; the wrapper rewrites
                 UPLOAD_PROTOCOL to "custom" right after this call, so
                 the upstream dispatch degrades to a pure
                 ``VerboseAction("$UPLOADCMD")`` passthrough.
    ``graft``    (env, board) — attach the real artifact chain after
                 the upstream script registered its upload target.
    """

    def __init__(self, configure, graft):
        self.configure = configure
        self.graft = graft


def _configure_pyocd(env, platform, board):
    # Same timing as the retired script's elif-branch: the installers
    # run at SConscript time whenever the protocol is selected, even
    # for a plain build.
    install_pyocd()
    install_r7fa4m1ab()
    env.Replace(
        UPLOADER="pyocd",
        # The retired script flashed "$SOURCE" — the upload alias's
        # source, which its main.py had already switched to the hex for
        # pyocd builds. The upstream dispatch always registers the .bin
        # there, so the artifact enters via $FLASH_IMAGE instead (the
        # grafted hex); the runtime command line is identical.
        UPLOADERFLAGS=[
            "flash",
            "-e",
            "sector",
            "-a",
            "0x0",
            "-t",
            "r7fa4m1ab",
            "$FLASH_IMAGE"
        ],
        UPLOADCMD="$UPLOADER $UPLOADERFLAGS",
    )


def _graft_pyocd_hex(env, board):
    """pyocd flashes the hex: build it via ElfToHex (records embed the
    0x4000 app offset) and make it the upload artifact."""
    elf = "$BUILD_DIR/${PROGNAME}.elf"
    hex_file = env.ElfToHex(join("$BUILD_DIR", "${PROGNAME}"), elf)
    _attach(env, hex_file)
    env.Replace(FLASH_IMAGE=str(hex_file[0]))


def _attach(env, artifact):
    upload_alias = env.Alias("upload")
    env.Depends(upload_alias, artifact)
    # keep plain `pio run` producing the real artifact too (the pre-
    # upstream behavior: target_firm WAS this artifact)
    env.Depends(env.Alias("buildprog"), artifact)


def graft_sam_ba_hardening(env, platform, board):
    """Re-apply the bossac hardening on top of the upstream sam-ba
    branch (samd-family pattern: a get_build_hooks graft would run
    BEFORE the upstream script and be overwritten by its env.Replace).
    No-op for any other protocol — including "custom" after a takeover
    rewrote it."""
    from SCons.Script import ARGUMENTS

    if env.subst("$UPLOAD_PROTOCOL") != "sam-ba":
        return
    bossac = join(platform.get_package_dir("tool-bossac") or "", "bossac")
    if system() == "Windows":
        bossac += ".exe"
    env.Replace(
        UPLOADER=bossac,
        UPLOADERFLAGS=[
            "--port", '"$UPLOAD_PORT"',
            "--write",
            "--verify",
            "--reset"
        ],
        UPLOADCMD='$UPLOADER $UPLOADERFLAGS "${SOURCE.get_abspath()}"'
    )

    env.Append(UPLOADERFLAGS=["--erase"])
    if board.get("upload.native_usb", False):
        env.Append(UPLOADERFLAGS=["--usb-port"])

    upload_offset = board.get("upload.offset_address")
    if upload_offset:
        env.Append(UPLOADERFLAGS=["--offset", upload_offset])

    if int(ARGUMENTS.get("PIOVERBOSE", 0)):
        env.Prepend(UPLOADERFLAGS=["--info", "--debug"])


# The takeover registry: protocols whose ENTIRE upstream branch is ours
# because the upstream dispatch does not know them. sam-ba is not here
# (post-hardening keeps its upstream branch — and BeforeUpload —
# intact, see graft_sam_ba_hardening); everything else (mbed, dfu,
# jlink, OpenOCD-via-debug-tools, custom) rides the upstream dispatch
# unchanged.
PROTOCOLS = {
    # upstream main.py has no pyocd branch (an upstream anchor pins
    # this absence)
    "pyocd": Protocol(_configure_pyocd, _graft_pyocd_hex),
}


def resolve(upload_protocol):
    """The Protocol driving this build's upload, or None to ride the
    upstream dispatch unchanged."""
    return PROTOCOLS.get(upload_protocol)
