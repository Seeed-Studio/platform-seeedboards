
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
Arduino

Arduino Wiring-based Framework allows writing cross-platform software to
control devices attached to a wide range of Arduino boards to create all
kinds of creative coding, interactive objects, spaces or physical experiences.

http://arduino.cc/en/Reference/HomePage
"""


from SCons.Script import  DefaultEnvironment

env = DefaultEnvironment()
board = env.BoardConfig()

# Board -> family Arduino script dispatch, keyed by the board manifest's
# build.family (single source of truth -- see .agents/notes/proposed/
# 2026-09-15-board-family-routing-single-source.md). Families without an
# Arduino port are absent on purpose: PlatformIO core rejects framework/
# board mismatches before reaching here, so a missing entry is a loud
# defense-in-depth error rather than the old silent no-op (which the
# divergent "52840" substring key made possible).
FAMILY_ARDUINO_SCRIPTS = {
    "esp": "../board_build/esp/esp_arduino.py",
    "nrf": "../board_build/nrf/nrf_arduino.py",
    "renesas": "../board_build/renesas/renesas_arduino.py",
    "rpi": "../board_build/rpi/rpi_arduino.py",
    "samd": "../board_build/samd/samd_arduino.py",
    "silabs": "../board_build/silabs/silabs_arduino.py",
}

family = board.get("build.family", None)
if not family:
    raise RuntimeError(
        "Board '%s' declares no build.family in its manifest; add one of "
        "%s (see .agents/notes/proposed/"
        "2026-09-15-board-family-routing-single-source.md)."
        % (board.id, ", ".join(sorted(FAMILY_ARDUINO_SCRIPTS)))
    )

arduino_script = FAMILY_ARDUINO_SCRIPTS.get(family)
if arduino_script is None:
    # Unreachable through `pio run` (core rejects framework/board mismatches
    # first) -- loud defense-in-depth instead of the old silent no-op.
    raise RuntimeError(
        "Board '%s' (build.family %r) has no Arduino build script; Arduino "
        "is not supported for this family." % (board.id, family)
    )

print("XIAO Arduino: board %s -> %s build" % (board.id, family))
env.SConscript(arduino_script, exports="env")