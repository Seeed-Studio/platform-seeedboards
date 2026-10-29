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

"""Chip family registry.

Importing a family module registers its ChipFamily subclass (via
__init_subclass__). Adding a family = one new module under families/ plus
one import line below.
"""

from .base import ChipFamily, FamilyResolutionError, resolve_board_family  # noqa: F401
from . import espressif  # noqa: F401
from . import nordic  # noqa: F401
from . import stm32  # noqa: F401
from . import samd  # noqa: F401
from . import rpi  # noqa: F401
from . import renesas  # noqa: F401
from . import siliconlab  # noqa: F401
