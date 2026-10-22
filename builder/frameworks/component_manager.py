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

"""Forwarding shim for the upstream pioarduino component_manager.

pioarduino's espidf.py loads this module from the HOST platform's
builder/frameworks/ directory (via env.PioPlatform().get_dir()) instead
of from its own package, and its arduino.py plain-imports it when SCons
puts the upstream dir on sys.path. The real implementation lives in the
locked upstream espressif32 platform package (see
families/espressif.py); re-export it here so both loading styles
resolve to exactly that copy — no code duplicated in this repo.

This file is ESP32-family-only by construction: only the upstream ESP32
builders load a component_manager from the host platform.
"""

import importlib.util
from os.path import join

from families import ChipFamily

_upstream_dir = ChipFamily.get("esp32")._upstream_platform_dir()
_spec = importlib.util.spec_from_file_location(
    "_upstream_component_manager",
    join(_upstream_dir, "builder", "frameworks", "component_manager.py"),
)
_upstream = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_upstream)  # type: ignore[attr-defined]

for _name in dir(_upstream):
    if not _name.startswith("_"):
        globals()[_name] = getattr(_upstream, _name)
