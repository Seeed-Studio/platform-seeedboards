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

"""Arduino-framework deltas for the Nordic family.

The adafruit-BSP build script is the upstream platform-nordicnrf52
builder/frameworks/arduino/adafruit.py; the two behavioral deltas of the
retired local nrf_arduino.py are reapplied here as post-script hooks
(families/nordic.py get_build_hooks):

* BSP libraries ship prebuilt archives in nested directories without a
  flat libmap, so every library directory carrying sources or headers
  joins LIBPATH (the upstream script only links the core);
* the malloc/free wrappers are kept, but realloc/calloc wrapping is
  dropped (the retired local script's link shape, preserved verbatim
  until a decision is made to adopt the full upstream wrap set).

The mbed-BSP script (arduino-core-mbed.py in this directory) stays a
family-owned copy: it is a fork of an older upstream revision carrying
two real fixes (variant-dir linker-script resolution, FPU flags off)
whose upstream adoption changes behavior and is deliberately deferred.
"""

from os import walk
from os.path import isdir, join

_WRAP_FLAGS_TO_DROP = ("-Wl,--wrap=realloc", "-Wl,--wrap=calloc")


def bsp_libraries_on_libpath(env, board):
    framework_dir = env.PioPlatform().get_package_dir(
        "framework-arduinoadafruitnrf52")
    if not framework_dir or not isdir(framework_dir):
        return
    libraries_dir = join(framework_dir, "libraries")
    libpaths = set()
    for root, _dirs, files in walk(libraries_dir):
        if any(f.endswith((".c", ".cpp", ".h", ".a")) for f in files):
            libpaths.add(root)
    env.Append(LIBPATH=list(libpaths))


def keep_local_wrap_set(env, board):
    env.Replace(LINKFLAGS=[
        f for f in env.get("LINKFLAGS", [])
        if f not in _WRAP_FLAGS_TO_DROP])
