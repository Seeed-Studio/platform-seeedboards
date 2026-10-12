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


from SCons.Script import DefaultEnvironment


env = DefaultEnvironment()
board = env.BoardConfig()

# Board -> family build-script dispatch. The family comes from the board
# manifest (build.family, the single source of truth -- see
# .agents/notes/proposed/2026-09-15-board-family-routing-single-source.md).
# Adding a family means adding builder/board_build/<family>/ and one table
# entry here; adding a board means only a manifest with build.family.
FAMILY_BUILD_SCRIPTS = {
    "esp": "board_build/esp/esp_build.py",
    "nrf": "board_build/nrf/nrf_build.py",
    "renesas": "board_build/renesas/renesas_build.py",
    "rpi": "board_build/rpi/rpi_build.py",
    "samd": "board_build/samd/samd_build.py",
    "siliconlab": "board_build/siliconlab/siliconlab_build.py",
    "stm32": "board_build/stm32/stm32_build.py",
}

family = board.get("build.family", None)
if not family:
    raise RuntimeError(
        "Board '%s' declares no build.family in its manifest; add one of "
        "%s (see .agents/notes/proposed/"
        "2026-09-15-board-family-routing-single-source.md)."
        % (board.id, ", ".join(sorted(FAMILY_BUILD_SCRIPTS)))
    )

build_script = FAMILY_BUILD_SCRIPTS.get(family)
if build_script is None:
    raise RuntimeError(
        "Board '%s' declares unknown build.family %r; expected one of %s."
        % (board.id, family, ", ".join(sorted(FAMILY_BUILD_SCRIPTS)))
    )

print("XIAO platform: board %s -> %s build via %s"
      % (board.id, family, build_script))
env.SConscript(build_script, exports="env")
