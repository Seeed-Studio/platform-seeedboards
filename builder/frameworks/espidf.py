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
#
# Attribution:
# The previous local ESP-IDF builder was a 55.03.37-era snapshot of
# pioarduino project work (https://github.com/pioarduino/platform-
# espressif32), since removed: the build now loads the upstream script
# from the locked espressif32 platform package. Modified by Seeed Studio.


"""
ESP-IDF framework wrapper.

Thin dispatcher, same pattern as the Arduino wrapper: the board
manifest's build.chip_family selects the chip family, and the family
decides which ESP-IDF build script runs — here the upstream pioarduino
package's builder/frameworks/espidf.py, SConscript-dynamically loaded
(no local copy), followed by the family's build hooks.
"""

import sys

from SCons.Script import DefaultEnvironment


env = DefaultEnvironment()
platform = env.PioPlatform()
board = env.BoardConfig()

if platform.get_dir() not in sys.path:
    # tail-append only: the repo root must never shadow stdlib `platform`
    sys.path.append(platform.get_dir())
from families import resolve_board_family

family = resolve_board_family(board, board.id)
script = family.framework_script(platform, "espidf", board)
if script:
    print("board %s: family '%s' espidf -> %s"
          % (board.id, family.family_ids[0], script))
    env.SConscript(script, exports="env")
    for hook in family.get_build_hooks("espidf"):
        hook(env, board)
