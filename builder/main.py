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


import sys

from SCons.Script import DefaultEnvironment


env = DefaultEnvironment()
platform = env.PioPlatform()
board = env.BoardConfig()

if platform.get_dir() not in sys.path:
    # tail-append only: the repo root must never shadow stdlib `platform`
    sys.path.append(platform.get_dir())
from families import resolve_board_family

# Zero-string routing: the board manifest's build.chip_family selects the
# family; the family owns which board-level build script runs (a local
# board_build/<family>/ script or an upstream-platform one).
family = resolve_board_family(board, board.id)
script = family.build_script(platform, board)
if script:
    print("board %s: family '%s' -> %s"
          % (board.id, family.family_ids[0], script))
    env.SConscript(script, exports="env")
