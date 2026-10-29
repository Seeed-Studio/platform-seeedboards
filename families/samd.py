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

"""Microchip SAMD (SAM D21/D51) chip family."""

from os.path import join

from platform_cfg import samd_cfg
from .base import ChipFamily


class SamdFamily(ChipFamily):
    family_ids = ("samd",)
    # Uploader pruning in samd_cfg walks packages dynamically by
    # type == "uploader"; nothing statically enumerable to declare here.
    owned_packages = ()

    def configure_default_packages(self, platform, variables, targets):
        samd_cfg.configure_samd_default_packages(platform, variables, targets)

    def add_default_debug_tools(self, platform, board):
        return samd_cfg._add_samd_default_debug_tools(platform, board)

    def configure_debug_session(self, platform, debug_config):
        samd_cfg.configure_samd_debug_session(debug_config)

    def build_script(self, platform, board):
        return join(platform.get_dir(), "builder", "families", "samd", "samd_build.py")

    def framework_script(self, platform, framework, board):
        if framework != "arduino":
            return None
        return join(platform.get_dir(), "builder", "families", "samd", "samd_arduino.py")
