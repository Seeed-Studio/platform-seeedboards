
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
if "esp32" in board.id:
    print(f"board id is {board.id}, will call board_build/esp/esp_build.py")
    env.SConscript("../board_build/esp/esp_arduino.py", exports="env")

if board.id == "seeed-xiao-ra4m1":
    print("board id is seeed-xiao-ra4m1,will call board_build/renesas/renesas_arduino.py")
    env.SConscript("../board_build/renesas/renesas_arduino.py", exports="env")


if board.id == "seeed-xiao-rp2040" or board.id == "seeed-xiao-rp2350":
    print("board id is seeed-xiao-rpi,will call ../board_build/rpi/rpi_arduino.py")
    env.SConscript("../board_build/rpi/rpi_arduino.py", exports="env")

if "52840" in board.id:
    print("board id is 52840,will call ../board_build/nrf/nrf_arduino.py")
    env.SConscript("../board_build/nrf/nrf_arduino.py", exports="env")

if "samd" in board.id:
    print("board id is samd,will call ../board_build/nrf/nrf_arduino.py")
    env.SConscript("../board_build/samd/samd_arduino.py", exports="env")

if "mg24" in board.id:
    print("board id is mg24,will call ../board_build/siliconlab/siliconlab_arduino.py")
    env.SConscript("../board_build/siliconlab/siliconlab_arduino.py", exports="env")