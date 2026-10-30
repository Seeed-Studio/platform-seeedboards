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

"""Board-level build wrapper for the samd family.

The skeleton (environment assembly, toolchain defaults, target_firm
matrix, upload dispatch) is the locked platform-atmelsam v9.0.0
builder/main.py, executed via env.SConscript below with
env.PioPlatform() wrapped in an UpstreamPlatformProxy (the router in
builder/main.py mounts it around this script).

Family delta applied AFTER the upstream execution: the bossac upload
hardening from 7b3b9e5 (2026-01), re-applied on the upstream sam-ba
state because a get_build_hooks graft would run BEFORE the upstream
sam-ba branch and be overwritten by its env.Replace. The hardening:
an explicit tool-bossac executable path, a quoted absolute SOURCE in
UPLOADCMD, and -U/--offset as separate flags (upstream folds
native_usb into a "-U true|false" pair and appends no --offset).

Neither the upstream file nor the framework package is modified.
"""

import sys
from os.path import join

from SCons.Script import Import

Import("env")

from families import resolve_board_family  # noqa: E402  (sys.path: host platform dir)


board = env.BoardConfig()
family = resolve_board_family(board, env.get("BOARD", ""))

env.SConscript(join(family._upstream_platform_dir(), "builder", "main.py"),
               exports="env")


def _graft_bossac_hardening():
    if env.subst("$UPLOAD_PROTOCOL") != "sam-ba":
        return
    platform = env.PioPlatform()  # the UpstreamPlatformProxy while in here
    bossac = join(platform.get_package_dir("tool-bossac") or "", "bossac")
    if sys.platform.startswith("win"):
        bossac += ".exe"
    env.Replace(
        UPLOADER=bossac,
        UPLOADCMD='$UPLOADER $UPLOADERFLAGS "${SOURCE.get_abspath()}"',
    )
    # Upstream's else-branch (non-samd51 cores) appended
    # ["--erase", "-U", "true|false"]; normalize to the hardened shape:
    # "--erase", then "-U" only for native_usb boards, then
    # ["--offset", addr] when the board declares one. Other branches
    # (samd51 fork, sam3x8e --boot, verbose prepend) match the retired
    # snapshot already and keep their flags untouched.
    flags = list(env["UPLOADERFLAGS"])
    if flags[-2:] in (["-U", "true"], ["-U", "false"]):
        native_usb = flags.pop() == "true"
        flags.pop()  # the "-U" literal
        if native_usb:
            flags.append("-U")
        upload_offset = board.get("upload.offset_address")
        if upload_offset:
            flags.extend(["--offset", upload_offset])
        env.Replace(UPLOADERFLAGS=flags)


_graft_bossac_hardening()
