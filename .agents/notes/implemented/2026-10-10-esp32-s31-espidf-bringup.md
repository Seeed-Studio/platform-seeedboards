# ESP32-S31 rides the ESP-IDF v6.1 line until Arduino 4.0.0 lands

Status: implemented

## Context

The XIAO ESP32-S31 Sense is the first board in this platform whose chip
(ESP32-S31NRV32) is only supported by ESP-IDF v6.1 and later; the 5.5 line
pinned globally in `platform.json` does not know the `esp32s31` target.
Arduino support does not exist yet in any pin-able release: the S31 variant
lands with arduino-esp32 4.0.0 (espressif/arduino-esp32#12677, open at the
time of writing), so the board manifest declares `frameworks: ["espidf"]`
only.

Two version constraints follow from the chip rather than from our choices:

- esptool must be >= 5.3 for the `esp32s31` chip id (`elf2image --chip
  esp32s31` runs at build time, so old esptool breaks builds, not just
  uploads);
- the bootloader image lives at 0x2000 like ESP32-C5/P4 (ROM layout), now
  encoded in the `espidf.py` `FLASH_EXTRA_IMAGES` tuple.

## Decision

- `platform_cfg/esp_cfg.py` swaps the `framework-espidf` version to the
  pioarduino `v6.1.0.260922` build **per MCU** (`esp32s31` + espidf
  projects). Other boards keep resolving the global 5.5 pin that the
  prebuilt Arduino libs are compiled against; PlatformIO stores the two
  framework package versions side by side, so no other board changes
  behavior.
- `tool-esptoolpy` moves to 5.5.0 globally (pioarduino ships 5.4/5.5 for
  every chip on both their IDF 5.5 and IDF 6.1 lines). A per-MCU swap was
  rejected because `platform.py::_prefer_local_esp_tools` pins any
  locally installed `tool*`/`toolchain*` package to its local directory,
  which would defeat a per-MCU spec on machines with a cached 5.1.2 —
  that shadow mechanism assumes one version per tool package.
- `toolchain-riscv32-esp` is swapped to the gcc 15.2 build (pioarduino
  registry, 15.2.0+20251204) for `esp32s31` + espidf, mirroring the
  framework swap. The 14.2 pin does not work with IDF 6.1: its newlib
  headers conflict with IDF 6.1's `esp_libc` platform shims (`_REENT`
  undeclared, `cookie_io_functions_t` redefinition inside
  `esp_ota_ops.c`). Both IDF lines keep their paired toolchain: 5.5/14.2
  for the Arduino boards, 6.1/15.2 for S31.
- The board manifest carries no `debug` section: the pinned
  `tool-openocd-esp32` predates the chip and its `esp32s31.cfg` support
  is unverified. JTAG signals exist on the B2B connector (MTMS/MTCK/
  MTDO/MTDI on P2-P5); enable debug when the openocd package is verified
  or bumped.

## Alternatives considered

- Bumping the global `framework-espidf` pin to 6.1: rejected — the
  Arduino custom-sdkconfig recompile path and any existing espidf user
  would silently move IDF lines.
- Per-project `platform_packages` overrides in the example instead of
  platform wiring: rejected — every user would have to know and repeat
  the override; the board would not be self-contained.

## Consequences

- S31 espidf projects download the IDF v6.1 tarball (~300 MB) and the
  gcc 15.2 toolchain on first build; Arduino-only machines never fetch
  them (both packages stay `optional` for non-S31 builds).
- Machines with a cached `tool-esptoolpy` 5.1.2 keep using it until the
  package is removed/reinstalled (`_prefer_local_esp_tools` pins the
  local copy). This is the pre-existing direct-link laziness left from
  the ESP shadow-mechanism slimming; it now has a second consumer.
- Adding Arduino later is additive: declare the variant once
  arduino-esp32 4.0.0 ships a pioarduino package pair, and revisit the
  PSRAM octal branch and the upload pre-action in the Arduino path at
  that point.

## IDF 6.1 builder fixes required for the first espidf build

The espidf SCons integration had never compiled a full IDF project
before (zero espidf examples). Beyond the package wiring, IDF 6.1
needed these `espidf.py` / `platform.py` fixes, all mirroring the
pioarduino IDF-6 line where one exists:

- `espidf.py install_python_deps`: IDF >= 6 pairs with
  idf-component-manager ~=3.1.0 and esp-idf-kconfig ~=3.13.0 (interface
  version 5; the 2.4.x manager cannot be driven by IDF 6.1), and the
  dependency check must re-run on every build instead of only at venv
  creation, so a venv left over from older pins self-heals.
- `espidf.py`: GCC response files (`@toolchain/{asm,c}flags`, IDF
  5.5.3+) must be expanded in `get_app_flags` and skipped in
  `prepare_build_envs`, and `get_app_flags` must be merged into the
  environment **before** `build_components` — IDF 6.1 selects picolibc
  via `-specs=.../picolibc.specs` inside those response files, so
  compiling components without them mixes newlib and picolibc headers.
- `espidf.py` bootloader preprocessing must add the shared
  `main/ld` dir to the include path (per-target
  `bootloader.sections.ld.in` includes `bootloader.sections.common.ld`
  from the parent directory).
- `espidf.py` ldgen: resolve the objdump path from `$CC` without
  re-joining an absolute path under `TOOLCHAIN_DIR/bin`, and retry the
  ldgen action a bounded number of times — on some Windows machines
  antivirus/endpoint-security software intermittently strips objdump
  output while a build spawns many toolchain processes
  (espressif#18665/#18727).
- `espidf.py` tfpsa-crypto: IDF 6.1 merges mbedtls port glue objects
  into `libtfpsacrypto.a` at an interim CMake step; the archive must be
  built with its dependency objects inlined and appended to `LIBS`
  explicitly (pioarduino `build_tfpsacrypto`).
- `platform.py _expand_and_link_esp_tool`: the IDF-6-line tool zips are
  idf_tools stubs (package.json + tools.json only). Follow the
  pioarduino contract: replace the stub with the expanded core-tools
  directory and align the expanded metadata's package name with the
  platform key, so `get_package_dir()` returns a toolchain with `bin/`.

## Validation (2026-10-10, Windows 10, PIO Core 6.2.0)

Fork-based builds via `cumin777/platform-seeedboards#feature/esp32-s31-espidf`
(cached platform package `~/.platformio/platforms/SeeedStudio`):

- `examples/seeed-xiao-esp32-s31/espidf-blink -e seeed-xiao-esp32-s31`: SUCCESS — firmware.bin
  (elf2image `--chip esp32s31`, esptool 5.5.0), RAM 18236/557056,
  flash 198192/33554432.
- `examples/arduino-blink -e seeed-xiao-esp32-c6` and
  `-e seeed-xiao-esp32-s3-sense` (both toolchain families, esptoolpy
  5.5.0): SUCCESS.
- Hardware validation (flashing, boot, LED) not performed — no board at
  the validation machine; also pending the hardware team's decision on
  the VDD_SPI 1.8 V errata (SPI-855), which decides whether the flash
  part changes on the board.

Local-machine note: `_prefer_local_esp_tools` pins one local
`toolchain-riscv32-esp` directory for all boards, so a machine that
switches between the S31 (15.2) and Arduino (14.2) lines must swap the
bare package directory manually until the prefer-local logic becomes
version-aware (follow-up work; CI and fresh machines are unaffected).
