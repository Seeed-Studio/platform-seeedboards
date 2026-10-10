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
- `toolchain-riscv32-esp` stays at the global 14.2 pin for now. The
  pioarduino IDF-6 line pairs IDF 6.1 with gcc 15.2; if builds fail on
  the 14.2 pairing the bump must be global (same shadow-mechanism
  constraint) and validated against the Arduino boards in CI.
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

- S31 espidf projects download the IDF v6.1 tarball (~300 MB) on first
  build; Arduino-only machines never fetch it (the package stays
  `optional` for non-S31 builds).
- Machines with a cached `tool-esptoolpy` 5.1.2 keep using it until the
  package is removed/reinstalled (`_prefer_local_esp_tools` pins the
  local copy). This is the pre-existing direct-link laziness left from
  the ESP shadow-mechanism slimming; it now has a second consumer.
- Adding Arduino later is additive: declare the variant once
  arduino-esp32 4.0.0 ships a pioarduino package pair, and revisit the
  PSRAM octal branch and the upload pre-action in the Arduino path at
  that point.
