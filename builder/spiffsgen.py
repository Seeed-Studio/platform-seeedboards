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

"""Forwarding shim for the upstream pioarduino spiffsgen module.

pioarduino's builder/main.py loads this module from the HOST platform's
builder/ directory (via env.PioPlatform().get_dir()) instead of from its
own package — same host-path expectation as component_manager and
penv_setup. Re-export the locked upstream implementation (see
families/espressif.py); no code duplicated here.
"""

import importlib.util
from os.path import join

from families import ChipFamily

_upstream_dir = ChipFamily.get("esp32")._upstream_platform_dir()
_spec = importlib.util.spec_from_file_location(
    "_upstream_spiffsgen",
    join(_upstream_dir, "builder", "spiffsgen.py"),
)
_upstream = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_upstream)  # type: ignore[attr-defined]

for _name in dir(_upstream):
    if not _name.startswith("_"):
        globals()[_name] = getattr(_upstream, _name)
