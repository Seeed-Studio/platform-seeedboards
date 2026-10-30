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

"""Silicon Labs EFR32 (MG24) chip family.

Local-keep: there is no platform-layer upstream to load —
platformio/platform-siliconlabsefm32 v11.0.0 has no mg24 board and no
arduino framework (mbed/zephyr only; arduino support died as a draft
PR), and the real framework upstream lives in SiliconLabsSoftware/
arduino (see siliconlab_arduino.py's header). The builder scripts stay
local: siliconlab_build.py (fork of the upstream v11.0.0 skeleton, see
its header for the fork point and delta list) and siliconlab_arduino.py.

Owns the package matrix and the default debug-tools table, inlined
from the retired platform_cfg/siliconlab_cfg.py. Package notes:
toolchain-gccarmnoneeabi pinned to exactly 1.120301.0;
framework-arduino-silabs (the SiliconLabsSoftware/arduino core as a
Seeed package) and tool-openocd are mandatory; tool-openocd is
redirected to the Seeed for-silicon openocd build per host OS.
"""

from os.path import join

from platformio import util

from .base import ChipFamily


class SiliconlabFamily(ChipFamily):
    family_ids = ("siliconlab",)
    owned_packages = ()

    # -- package matrix --------------------------------------------------

    def configure_default_packages(self, platform, variables, targets):
        platform.packages["toolchain-gccarmnoneeabi"]["version"] = (
            "1.120301.0"
        )
        platform.packages["toolchain-gccarmnoneeabi"]["optional"] = False

        platform.packages["framework-arduino-silabs"]["optional"] = False
        platform.packages["tool-openocd"]["optional"] = False

        # The Seeed for-silicon openocd build carries the efm32s2 flash
        # loader; the registry tool-openocd does not (upstream v11.0.0
        # pinned it the same way, by per-OS tarball URL).
        sys_type = util.get_systype()
        if "darwin" in sys_type:
            platform.packages["tool-openocd"]["version"] = (
                "https://files.seeedstudio.com/arduino/platformio/"
                "forsilicon-openocd-apple.tar.gz"
            )
        elif "linux" in sys_type:
            platform.packages["tool-openocd"]["version"] = (
                "https://files.seeedstudio.com/arduino/platformio/"
                "forsilicon-openocd-linux.tar.gz"
            )
        else:
            platform.packages["tool-openocd"]["version"] = (
                "https://files.seeedstudio.com/arduino/platformio/"
                "forsilicon-openocd-win.zip"
            )

        # No uploader pruning by design: the tools are optional here
        # (never installed for mg24 builds), while other family configs
        # access them unconditionally — deleting them from the shared
        # packages dict used to leave rpi/nrf/esp configuration crashing
        # with KeyError in one process.

    # -- debug -----------------------------------------------------------

    def add_default_debug_tools(self, platform, board):
        debug = board.manifest.get("debug", {})
        upload_protocols = board.manifest.get("upload", {}).get(
            "protocols", [])
        if "tools" not in debug:
            debug["tools"] = {}

        openocd_target = debug.get("openocd_target")
        assert openocd_target, ("Missing target configuration for %s" %
                                board.id)
        debug["tools"]["cmsis-dap"] = {
            "server": {
                "executable": "bin/openocd",
                "package": "tool-openocd",
                "arguments": [
                    "-s", "$PACKAGE_DIR/share/openocd/scripts",
                    "-f", "interface/cmsis-dap.cfg",
                    "-f", "target/%s" % openocd_target,
                    "-c", "adapter speed 1000",
                ]
            },
            "load_cmds": "preload",
            "init_cmds": [
                "target extended-remote $DEBUG_PORT",
                "$LOAD_CMDS",
                "pio_reset_halt_target",
                "$INIT_BREAK",
            ],
        }

        board.manifest["debug"] = debug
        return board

    def configure_debug_session(self, platform, debug_config):
        if debug_config.speed:
            if "jlink" in (debug_config.server or {}).get(
                    "executable", "").lower():
                debug_config.server["arguments"].extend(
                    ["-speed", debug_config.speed]
                )

    # -- builder side ----------------------------------------------------

    def build_script(self, platform, board):
        # Local-keep family: the board-level skeleton is our own
        # siliconlab_build.py (fork of the upstream v11.0.0 builder).
        return join(self.host_dir(), "builder", "families", "siliconlab",
                    "siliconlab_build.py")

    def framework_script(self, platform, framework, board):
        if framework != "arduino":
            return None
        return join(self.host_dir(), "builder", "families", "siliconlab",
                    "siliconlab_arduino.py")
