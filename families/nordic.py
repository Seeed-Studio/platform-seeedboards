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

"""Nordic nRF chip family (nRF52 Arduino BSPs + nRF54 Zephyr/NCS)."""

from os.path import join

from platform_cfg import nrf_cfg
from .base import ChipFamily


class NordicFamily(ChipFamily):
    family_ids = ("nrf",)
    owned_packages = ("tool-nrfjprog", "tool-jlink")

    def configure_default_packages(self, platform, variables, targets):
        nrf_cfg.configure_nrf_default_packages(platform, variables, targets)

    def add_default_debug_tools(self, platform, board):
        return nrf_cfg._add_nrf_default_debug_tools(platform, board)

    def configure_debug_session(self, platform, debug_config):
        nrf_cfg.configure_nrf_debug_session(debug_config)

    def build_script(self, platform, board):
        return join(platform.get_dir(), "builder", "board_build", "nrf", "nrf_build.py")

    def framework_script(self, platform, framework, board):
        # mbed-BSP boards never reach the wrapper: configure_default_packages
        # repoints frameworks["arduino"]["script"] at arduino-core-mbed.py.
        # Adafruit-BSP boards load the local nrf_arduino.py; nRF54 boards
        # are zephyr-only and declare no build.bsp.name.
        if framework != "arduino":
            return None
        if board.get("build.bsp.name", "") != "adafruit":
            return None
        return join(platform.get_dir(), "builder", "board_build", "nrf", "nrf_arduino.py")

    def zephyr_pioplatform(self):
        return "nordicnrf52"
