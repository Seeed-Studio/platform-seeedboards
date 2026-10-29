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

"""Board-level build wrapper for the rpi family.

The skeleton (environment assembly, toolchain selection, target_firm
matrix, upload dispatch, filesystem targets) is the locked
maxgerhardt/platform-raspberrypi builder/main.py, executed via
env.SConscript below with env.PioPlatform() wrapped in an
UpstreamPlatformProxy (the router in builder/main.py mounts it around
this script).

Family delta applied around the upstream execution: the two places the
upstream builder invokes a tool by bare name — generate_uf2() runs
"picotool" and the OpenOCD upload branch sets UPLOADER="openocd" — are
healed by PATH-prepending the earlephilhower tool packages afterwards,
preserving what the retired local snapshot (absolute paths in both
spots) did, without touching the upstream file.

Neither the upstream file nor the framework package is modified.
"""

from os.path import join

from SCons.Script import Import

Import("env")

from families import resolve_board_family  # noqa: E402  (sys.path: host platform dir)


board = env.BoardConfig()
family = resolve_board_family(board, env.get("BOARD", ""))

env.SConscript(join(family._upstream_platform_dir(), "builder", "main.py"),
               exports="env")

# PATH heal for the upstream bare tool names ("picotool" in
# generate_uf2, "openocd" as UPLOADER): picotool ships in the package
# root, openocd in both the root and bin/ — prepend both dirs. Missing
# package (never for a build that needs it) degrades to the unhealed
# upstream behavior.
platform = env.PioPlatform()  # the UpstreamPlatformProxy while in here
for package in ("tool-picotool-rp2040-earlephilhower",
                "tool-openocd-rp2040-earlephilhower"):
    package_dir = platform.get_package_dir(package)
    if package_dir:
        env.PrependENVPath("PATH", [package_dir, join(package_dir, "bin")])
