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

Architecture = ""

class SeeedstudioPlatform(PlatformBase):
    def configure_default_packages(self, variables, targets):
        
        global Architecture
        if not variables.get("board"):
            return super().configure_default_packages(variables, targets)
        
        board_name = variables.get("board")

        if "esp32" in board_name:
            Architecture = "esp"
        if board_name == "seeed-xiao-ra4m1":
            Architecture = "renesas"
        if board_name == "seeed-xiao-rp2040" or board_name == "seeed-xiao-rp2350":
            Architecture = "rpi"
        if "nrf" in board_name:
            Architecture = "nrf"
        if "samd" in board_name:
            Architecture = "samd"
        if "mg24" in board_name:
            Architecture = "siliconlab"

        if Architecture:
            try:
                board_module = import_module(f"platform_cfg.{Architecture}_cfg")
                configure_board = getattr(board_module, f"configure_{Architecture}_default_packages")
                configure_board(self, variables, targets)
            except (ImportError, AttributeError) as e:
                
                print(f"Error: {e} for board {board_name}")

        return super().configure_default_packages(variables, targets)
    

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
        global Architecture   
        board_name = board.id
        if "esp32" in board_name:
            Architecture = "esp"
        if board_name == "seeed-xiao-ra4m1":
            Architecture = "renesas"
            
        if board_name == "seeed-xiao-rp2040" or board_name == "seeed-xiao-rp2350":
            Architecture = "rpi"
        
        if "nrf" in board_name:
            Architecture = "nrf"
        if "samd" in board_name:
            Architecture = "samd"
        if "mg24" in board_name:
            Architecture = "siliconlab"
           
        if Architecture:
        # 动态导入板子配置函数
            try:
                board_module = import_module(f"platform_cfg.{Architecture}_cfg")
                configure_tool = getattr(board_module, f"_add_{Architecture}_default_debug_tools")
                return configure_tool(self, board)
            except (ImportError, AttributeError) as e:
                print(f"Error: in _add_dynamic_options {e} for board {board_name}")
        else:
            print("no config Architecture")
            return 



    def configure_debug_session(self, debug_config):
        global Architecture
        board_name = board.id
        if "esp32" in board_name:
            Architecture = "esp"
        if board_name == "seeed-xiao-ra4m1":
            Architecture = "renesas"
            
        if board_name == "seeed-xiao-rp2040" or board_name == "seeed-xiao-rp2350":
            Architecture = "rpi"
        
        if "nrf" in board_name:
            Architecture = "nrf"
        if "samd" in board_name:
            Architecture = "samd"
        if "mg24" in board_name:
            Architecture = "siliconlab"
            
        if Architecture:
        # 动态导入板子配置函数
            try:
                board_module = import_module(f"platform_cfg.{Architecture}_cfg")
                configure_debug_seesion = getattr(board_module, f"configure_{Architecture}_debug_session")
                configure_debug_seesion(self, debug_config)
            except (ImportError, AttributeError) as e:
                print(f"Error: in configure_debug_session {e} for board {Architecture}")

