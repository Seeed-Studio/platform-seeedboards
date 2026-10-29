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
# limitations under the License under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
# express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Board-level build wrapper for the Nordic family.

The skeleton (environment assembly, toolchain defaults, target_firm
matrix, upload dispatch, size/erase targets) is the upstream
platform-nordicnrf52 builder/main.py, executed via env.SConscript below
with env.PioPlatform() wrapped in an UpstreamPlatformProxy (the router
in builder/main.py mounts it around this script).

Family-specific deltas are applied around the upstream execution: a
takeover upload protocol (the PROTOCOLS registry in upload.py, this
directory) is configured and rewritten into the upstream "custom"
passthrough branch before the upstream script runs, and its real
artifact chain (signed image / raw binary) is grafted afterwards.

Neither the upstream file nor the framework package is modified.
"""

import sys
from os.path import join

from SCons.Script import Import

Import("env")

from families import resolve_board_family  # noqa: E402  (sys.path: host platform dir)


board = env.BoardConfig()
family = resolve_board_family(board, env.get("BOARD", ""))

# builder/ is not a package: sibling modules come into reach the same
# way builder/frameworks/zephyr.py reaches zephyr_fixes — this family's
# builder dir on sys.path (SCons deletes __file__ in SConscript frames,
# so the host path comes from family.host_dir()).
sys.path.insert(0, join(family.host_dir(), "builder", "families", "nordic"))
from upload import resolve as resolve_upload_protocol  # noqa: E402

platform = env.PioPlatform()  # the UpstreamPlatformProxy while in here

takeover = resolve_upload_protocol(env.subst("$UPLOAD_PROTOCOL"), board, env)
if takeover:
    takeover.configure(env, platform, board)
    env.Replace(UPLOAD_PROTOCOL="custom")

env.SConscript(join(family._upstream_platform_dir(), "builder", "main.py"),
               exports="env")

if takeover:
    takeover.graft(env, board)
