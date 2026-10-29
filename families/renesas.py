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

"""Renesas RA chip family (RA4M1)."""

from os.path import join

from platform_cfg import renesas_cfg
from .base import ChipFamily


class RenesasFamily(ChipFamily):
    family_ids = ("renesas",)
    # Uploader pruning in renesas_cfg selects uploaders dynamically.
    owned_packages = ()

    def configure_default_packages(self, platform, variables, targets):
        renesas_cfg.configure_renesas_default_packages(platform, variables, targets)

    def add_default_debug_tools(self, platform, board):
        return renesas_cfg._add_renesas_default_debug_tools(platform, board)

    def configure_debug_session(self, platform, debug_config):
        renesas_cfg.configure_renesas_debug_session(debug_config)

    def build_script(self, platform, board):
        return join(platform.get_dir(), "builder", "families", "renesas", "renesas_build.py")

    def framework_script(self, platform, framework, board):
        if framework != "arduino":
            return None
        return join(platform.get_dir(), "builder", "families", "renesas", "renesas_arduino.py")
