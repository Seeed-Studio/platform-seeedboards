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

"""STM32 chip family (STM32C5, Zephyr).

No upstream: STM32C5 does not exist in platformio/platform-ststm32 (no
board, package, or builder reference), so this family keeps local builder
scripts — the handbook's "override" route rather than upstream loading.
"""

from os.path import join

from platform_cfg import stm32_cfg
from .base import ChipFamily


class Stm32Family(ChipFamily):
    family_ids = ("stm32",)
    owned_packages = ("tool-jlink",)

    def configure_default_packages(self, platform, variables, targets):
        stm32_cfg.configure_stm32_default_packages(platform, variables, targets)

    def add_default_debug_tools(self, platform, board):
        return stm32_cfg._add_stm32_default_debug_tools(platform, board)

    def configure_debug_session(self, platform, debug_config):
        stm32_cfg.configure_stm32_debug_session(debug_config)

    def build_script(self, platform, board):
        return join(platform.get_dir(), "builder", "board_build", "stm32", "stm32_build.py")

    def framework_script(self, platform, framework, board):
        return None  # no Arduino support

    def zephyr_pioplatform(self):
        return "ststm32"
