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

import json
import os
import sys
from platformio import util

IS_WINDOWS = sys.platform.startswith("win")


openocd_path = {
    # Windows
    "windows": "https://files.seeedstudio.com/arduino/platformio/forsilicon-openocd-win.zip",
    # Linux
    "linux": "https://files.seeedstudio.com/arduino/platformio/forsilicon-openocd-linux.tar.gz",
    # Mac
    "mac": "https://files.seeedstudio.com/arduino/platformio/forsilicon-openocd-apple.tar.gz"
}



def configure_siliconlab_default_packages(self, variables, targets):
    self.packages["toolchain-gccarmnoneeabi"]["version"] = '1.120301.0'
    self.packages["toolchain-gccarmnoneeabi"]["optional"] = False

    self.packages["framework-arduino-silabs"]["optional"] = False
    self.packages["tool-openocd"]["optional"] = False

    sys_type = util.get_systype()
    if "darwin" in sys_type:
        self.packages["tool-openocd"]["version"] = "https://files.seeedstudio.com/arduino/platformio/forsilicon-openocd-apple.tar.gz"
    elif "linux" in sys_type:
        self.packages["tool-openocd"]["version"] = "https://files.seeedstudio.com/arduino/platformio/forsilicon-openocd-linux.tar.gz"
    else:
        self.packages["tool-openocd"]["version"] = "https://files.seeedstudio.com/arduino/platformio/forsilicon-openocd-win.zip"

    if "tool-mklittlefs-rp2040-earlephilhower" in self.packages:
        del self.packages["tool-mklittlefs-rp2040-earlephilhower"]
    if "tool-openocd-rp2040-earlephilhower" in self.packages:
        del self.packages["tool-openocd-rp2040-earlephilhower"]
    if "tool-bossac-nordicnrf52" in self.packages:
        del self.packages["tool-bossac-nordicnrf52"]
    if "tool-esptoolpy" in self.packages:
        del self.packages["tool-esptoolpy"]
    if "tool-picotool-rp2040-earlephilhower" in self.packages:
        del self.packages["tool-picotool-rp2040-earlephilhower"]



def _add_siliconlab_default_debug_tools(self, board):

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

def configure_siliconlab_debug_session(self, debug_config):
    if debug_config.speed:
        if "jlink" in (debug_config.server or {}).get("executable", "").lower():
            debug_config.server["arguments"].extend(
                ["-speed", debug_config.speed]
            )
