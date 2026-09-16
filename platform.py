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

from platformio.public import PlatformBase, to_unix_path
from importlib import import_module



IS_WINDOWS = sys.platform.startswith("win")
# Set Platformio env var to use windows_amd64 for all windows architectures
# only windows_amd64 native espressif toolchains are available
# needs platformio core >= 6.1.16b2 or pioarduino core 6.1.16+test
if IS_WINDOWS:
    os.environ["PLATFORMIO_SYSTEM_TYPE"] = "windows_amd64"

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Zephyr routing (framework package + Zephyr board.name per board) lives in
# the board manifests: build.zephyr.package and build.zephyr.board_name.
# Cross-checked by scripts/ci/verify_zephyr_routing.py; see
# .agents/notes/proposed/2026-09-15-board-family-routing-single-source.md.

class SeeedstudioPlatform(PlatformBase):
    def configure_default_packages(self, variables, targets):

        if not variables.get("board"):
            return super().configure_default_packages(variables, targets)

        board_name = variables.get("board")
        self._configure_zephyr_package_for_board(board_name, variables)

        family = self.get_board_family(board_name)

        if family:
            board_module = import_module(f"platform_cfg.{family}_cfg")
            configure_board = getattr(board_module, f"configure_{family}_default_packages")
            configure_board(self, variables, targets)

        return super().configure_default_packages(variables, targets)

    def _get_repo_board_config(self, board_name):
        """Board manifest config for a PIO board id.

        Uses the PlatformBase implementation on purpose: no
        _add_dynamic_options side effects during package configuration.
        """
        return PlatformBase.get_boards(self, board_name)

    def _configure_zephyr_package_for_board(self, board_name, variables):
        frameworks = variables.get("pioframework", [])
        if "zephyr" not in frameworks or "zephyr" not in self.frameworks:
            return

        package_name = self.get_zephyr_package_name(board_name)
        if package_name != self.frameworks["zephyr"].get("package"):
            self.frameworks["zephyr"]["package"] = package_name

    def get_zephyr_package_name(self, board_name=None):
        """Framework package for a board's Zephyr builds.

        Reads build.zephyr.package from the board manifest. Boards without
        one fall back to the platform.json default (frameworks.zephyr.package,
        currently framework-zephyr-nrf54lm20). Note seeed-xiao-stm32c5
        deliberately reuses the nrf54lm20 Zephyr 4.4 tarball (identical
        content; PlatformIO would URL-dedupe a same-versioned package into
        the nrf54lm20 dir anyway) -- its specifics arrive per-board via the
        board directory's fixes/ tree.
        """
        default = self.frameworks.get("zephyr", {}).get(
            "package", "framework-zephyr-nrf54lm20"
        )
        if not board_name:
            return default

        board = self._get_repo_board_config(board_name)
        zephyr = board.get("build.zephyr", None) if board else None
        if isinstance(zephyr, dict) and zephyr.get("package"):
            return zephyr["package"]
        return default

    def get_zephyr_board_name(self, board_name):
        """Return the Zephyr board.name (e.g. 'xiao_stm32c5') for a PIO board id.

        Reads build.zephyr.board_name from the board manifest. Used to locate
        the board's tree under zephyr/boards/arm/<board>/ (including its
        fixes/ directory). Returns '' if the board declares none.
        """
        if not board_name:
            return ""
        board = self._get_repo_board_config(board_name)
        zephyr = board.get("build.zephyr", None) if board else None
        if isinstance(zephyr, dict) and zephyr.get("board_name"):
            return zephyr["board_name"]
        return ""

    def get_board_family(self, board):
        """Resolve the MCU family for a board id or board-config object.

        build.family in the board manifest is the single source of truth for
        board -> family routing (see .agents/notes/proposed/
        2026-09-15-board-family-routing-single-source.md). Platform manifests
        missing the key fail loudly with the manifest path; manifests loaded
        from outside this platform's boards/ directory (user-custom boards)
        warn once and return None, preserving their historical no-family
        handling.
        """
        if isinstance(board, str):
            board = self._get_repo_board_config(board_name=board)
        if board is None:
            return None

        family = board.get("build.family", None)
        if family:
            return family

        manifest_dir = os.path.dirname(os.path.abspath(board.manifest_path))
        platform_boards_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "boards"
        )
        if os.path.normpath(manifest_dir) != os.path.normpath(platform_boards_dir):
            print(
                "Warning: board '%s' declares no build.family in %s; "
                "skipping family handling" % (board.id, board.manifest_path)
            )
            return None
        raise KeyError(
            "Board '%s' is missing 'build.family' in %s. Add it to the "
            "manifest -- one of esp, nrf, renesas, rpi, samd, silabs, "
            "stm32 (see .agents/notes/proposed/"
            "2026-09-15-board-family-routing-single-source.md)."
            % (board.id, board.manifest_path)
        )

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
        """Inject family default debug tools into a board manifest.

        Resolves the family from the board manifest itself (single source of
        truth); user-custom external boards (no build.family) are returned
        unchanged. Always returns the board object -- PlatformIO core calls
        get_brief_data() on every entry of get_boards(), so a None return
        crashes `pio boards` listing.
        """
        family = self.get_board_family(board)
        if not family:
            return board

        board_module = import_module(f"platform_cfg.{family}_cfg")
        configure_tool = getattr(board_module, f"_add_{family}_default_debug_tools")
        return configure_tool(self, board)


    def configure_debug_session(self, debug_config):
        board_config = getattr(debug_config, "board_config", None)
        if not board_config:
            return

        family = self.get_board_family(board_config)
        if not family:
            return

        board_module = import_module(f"platform_cfg.{family}_cfg")
        configure_debug_session = getattr(
            board_module, f"configure_{family}_debug_session"
        )
        configure_debug_session(self, debug_config)
