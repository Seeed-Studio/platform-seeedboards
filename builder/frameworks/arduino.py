# Copyright 2014-present PlatformIO <contact@platformio.org>
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
Arduino framework wrapper.

Thin dispatcher: the board manifest's build.chip_family selects the chip
family; the family decides which Arduino build script runs — an upstream
platform-package script (SConscript-dynamically loaded, no local copy) or
a local builder/families/<family>/ script — and which hooks apply afterwards.
"""


from SCons.Script import DefaultEnvironment


env = DefaultEnvironment()
platform = env.PioPlatform()
board = env.BoardConfig()

# The board-level dispatch router (builder/main.py) keeps this repo's
# root on sys.path for the whole SCons run, so the families registry
# import works here even while PioPlatform is wrapped for an
# upstream-backed family (get_dir() = the upstream package). SCons
# deletes __file__ in SConscript frames, so host paths below come from
# family.host_dir() only.
from families import resolve_board_family

family = resolve_board_family(board, board.id)
script = family.framework_script(platform, "arduino", board)
if script:
    print("board %s: family '%s' arduino -> %s"
          % (board.id, family.family_ids[0], script))
    wrap = getattr(family, "wrap_platform", None)
    restore = wrap(platform, env) if wrap else None
    try:
        env.SConscript(script, exports="env")
    finally:
        if wrap and restore:
            env.PioPlatform = restore
    for hook in family.get_build_hooks("arduino"):
        hook(env, board)
