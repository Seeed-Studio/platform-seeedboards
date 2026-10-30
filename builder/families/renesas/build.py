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

"""Board-level build wrapper for the renesas family.

The skeleton (environment assembly, toolchain defaults, target_firm
matrix, upload dispatch) is the locked platform-renesas-ra v1.9.0
builder/main.py, executed via env.SConscript below with
env.PioPlatform() wrapped in an UpstreamPlatformProxy (the router in
builder/main.py mounts it around this script).

Family deltas are applied around the upstream execution (upload.py,
this directory): the pyocd protocol is taken over — upstream has no
pyocd branch — by pre-configuring the uploader command, rewriting
UPLOAD_PROTOCOL to "custom" passthrough, and grafting the hex artifact
chain after the upstream script registers its upload target; the
sam-ba branch is re-hardened after the fact (explicit bossac path,
--verify, --offset). The pyocd/r7fa4m1ab installer logic moved verbatim
(debt R1 keeps it unpinned).

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
# way the nordic wrapper reaches its upload.py (SCons deletes __file__
# in SConscript frames, so the host path comes from family.host_dir()).
sys.path.insert(0, join(family.host_dir(), "builder", "families", "renesas"))
from upload import (  # noqa: E402
    graft_sam_ba_hardening,
    resolve as resolve_upload_protocol,
)

platform = env.PioPlatform()  # the UpstreamPlatformProxy while in here

takeover = resolve_upload_protocol(env.subst("$UPLOAD_PROTOCOL"))
if takeover:
    takeover.configure(env, platform, board)
    env.Replace(UPLOAD_PROTOCOL="custom")

env.SConscript(join(family._upstream_platform_dir(), "builder", "main.py"),
               exports="env")

if takeover:
    takeover.graft(env, board)
graft_sam_ba_hardening(env, platform, board)
