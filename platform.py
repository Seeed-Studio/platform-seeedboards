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
# ESP32-related package/toolchain selection logic in this repository is
# based in part on pioarduino project work:
# https://github.com/pioarduino/platform-espressif32
# Modified by Seeed Studio.

import os
import sys

from platformio.public import PlatformBase


IS_WINDOWS = sys.platform.startswith("win")
# Set Platformio env var to use windows_amd64 for all windows architectures
# only windows_amd64 native espressif toolchains are available
# needs platformio core >= 6.1.16b2 or pioarduino core 6.1.16+test
if IS_WINDOWS:
    os.environ["PLATFORMIO_SYSTEM_TYPE"] = "windows_amd64"

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Family routing goes through the families/ registry keyed by each board's
# build.chip_family manifest field — no board-id substring matching here.
from families import resolve_board_family  # noqa: E402

# The Zephyr framework builds against the single pinned framework-zephyr
# package from platform.json; the Zephyr board.name lives in each board's
# manifest (build.zephyr.variant). See get_zephyr_board_name below and
# zephyr/README.md.


class SeeedstudioPlatform(PlatformBase):
    def configure_default_packages(self, variables, targets):

        if not variables.get("board"):
            return super().configure_default_packages(variables, targets)

        board_name = variables.get("board")

        family = resolve_board_family(self.board_config(board_name), board_name)
        family.configure_default_packages(self, variables, targets)

        result = super().configure_default_packages(variables, targets)

        if family.post_configure_packages(self, variables, targets):
            result = super().configure_default_packages(variables, targets)

        return result

    def get_zephyr_board_name(self, board_name):
        """Return the Zephyr board.name (e.g. 'xiao_stm32c5') for a PIO board id.

        Derived from the board manifest's build.zephyr.variant: the first
        component of `board[@revision]/soc/...` is the board.name, which keys
        the per-board fixes under zephyr/{patches,overrides}/<board>/ and in
        zephyr/fixes.yml (a board revision collapses to its shared board dir).
        Returns '' if the board declares no variant (no local fixes to apply).
        """
        if not board_name:
            return ""
        variant = self.board_config(board_name).get("build.zephyr.variant", "")
        return variant.split("/")[0].split("@")[0] if variant else ""

    def get_boards(self, id_=None):
        result = super().get_boards(id_)
        if not result:
            return result
        if id_:
            return self._add_dynamic_options(result)
        else:
            for key in result:
                result[key] = self._add_dynamic_options(result[key])
        return result


    def _add_dynamic_options(self, board):
        family = resolve_board_family(board, board.id)
        return family.add_default_debug_tools(self, board)


    def configure_debug_session(self, debug_config):
        board_config = getattr(debug_config, "board_config", None)
        if board_config is None:
            return
        board_id = debug_config.env_options.get("board", "")
        family = resolve_board_family(board_config, board_id)
        family.configure_debug_session(self, debug_config)

    def setup_python_env(self, env):
        """Called by upstream builders we SConscript (e.g. pioarduino's
        builder/main.py) that expect THEIR platform object; forward to
        the board's family adapter, which owns the upstream specifics."""
        from families import resolve_board_family
        board = env.BoardConfig()
        family = resolve_board_family(board, env.subst("$BOARD"))
        adapter = getattr(family, "setup_python_env", None)
        if adapter is None:
            return None, None
        return adapter(self, env)
