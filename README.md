# platform-seeed

**The PlatformIO platform for the Seeed Studio XIAO family.**

One `platform =` line builds for every XIAO board — 24 boards across 7 chip
families and 3 frameworks — with toolchains, uploaders and debug support
resolved per board.

[![CI Verify](https://github.com/Seeed-Studio/platform-seeedboards/actions/workflows/ci-verify.yml/badge.svg?branch=v3)](https://github.com/Seeed-Studio/platform-seeedboards/actions/workflows/ci-verify.yml)
[![Arduino Matrix](https://github.com/Seeed-Studio/platform-seeedboards/actions/workflows/build-arduino-examples.yml/badge.svg?branch=v3)](https://github.com/Seeed-Studio/platform-seeedboards/actions/workflows/build-arduino-examples.yml)
[![Zephyr Matrix](https://github.com/Seeed-Studio/platform-seeedboards/actions/workflows/build-zephyr-examples.yml/badge.svg?branch=v3)](https://github.com/Seeed-Studio/platform-seeedboards/actions/workflows/build-zephyr-examples.yml)

## Quick start

**1.** Install [VS Code](https://code.visualstudio.com/) and the
[PlatformIO extension](https://marketplace.visualstudio.com/items?itemName=platformio.platformio-idi)
(or the [PlatformIO CLI](https://docs.platformio.org/en/latest/core/index.html)).

**2.** Create a `platformio.ini` — this is the whole setup:

```ini
[env:seeed-xiao-esp32-c3]
platform = https://github.com/Seeed-Studio/platform-seeedboards.git#v3
board = seeed-xiao-esp32-c3
framework = arduino
```

**3.** Build and upload (`Upload` button, or `pio run -t upload`). The first
build downloads the toolchain for that board's chip family; switching to
another XIAO board later only changes the `board =` line.

Working examples for every board — blink, UART, WiFi scan, USB HID, BLE,
ADC and STM32C5 CAN pin reuse — live under [`examples/`](examples/). See the
[examples index](examples/README.md) for the demo/board matrix.

## Supported boards

| Board ID | Board | MCU | Frameworks |
| --- | --- | --- | --- |
| `seeed-xiao-samd` | XIAO SAMD21 | SAMD21 | Arduino |
| `seeed-xiao-ra4m1` | XIAO RA4M1 | RA4M1 | Arduino |
| `seeed-xiao-rp2040` | XIAO RP2040 | RP2040 | Arduino |
| `seeed-xiao-rp2350` | XIAO RP2350 | RP2350 | Arduino |
| `seeed-xiao-mg24` | XIAO MG24 | EFR32MG24 | Arduino |
| `seeed-xiao-mg24-sense` | XIAO MG24 Sense | EFR32MG24 | Arduino |
| `seeed-xiao-esp32-c3` | XIAO ESP32-C3 | ESP32-C3 | Arduino, ESP-IDF |
| `seeed-xiao-esp32-c5` | XIAO ESP32-C5 | ESP32-C5 | Arduino, ESP-IDF |
| `seeed-xiao-esp32-c6` | XIAO ESP32-C6 | ESP32-C6 | Arduino, ESP-IDF |
| `seeed-xiao-esp32-s3-sense` | XIAO ESP32-S3 Sense | ESP32-S3 | Arduino, ESP-IDF |
| `seeed-xiao-esp32-s3-plus` | XIAO ESP32-S3 Plus | ESP32-S3 | Arduino, ESP-IDF |
| `seeed-xiao-nrf54l15` | XIAO nRF54L15 | nRF54L15 | Zephyr |
| `seeed-xiao-nrf54lm20a` | XIAO nRF54LM20A | nRF54LM20A | Zephyr |
| `seeed-xiao-nrf54lm20a-v2` | XIAO nRF54LM20A V2 | nRF54LM20A | Zephyr |
| `seeed-xiao-nrf54lm20b` | XIAO nRF54LM20B | nRF54LM20B | Zephyr |
| `seeed-xiao-stm32c5` | XIAO STM32C5 | STM32C5 | Zephyr |
| `seeed-xiao-afruitnrf52-nrf52840` | XIAO nRF52840 (Adafruit core) | nRF52840 | Arduino |
| `seeed-xiao-afruitnrf52-nrf52840-plus` | XIAO nRF52840 Plus (Adafruit core) | nRF52840 | Arduino |
| `seeed-xiao-afruitnrf52-nrf52840-sense` | XIAO nRF52840 Sense (Adafruit core) | nRF52840 | Arduino |
| `seeed-xiao-afruitnrf52-nrf52840-sense-plus` | XIAO nRF52840 Sense Plus (Adafruit core) | nRF52840 | Arduino |
| `seeed-xiao-mbed-nrf52840` | XIAO nRF52840 (mbed core) | nRF52840 | Arduino |
| `seeed-xiao-mbed-nrf52840-plus` | XIAO nRF52840 Plus (mbed core) | nRF52840 | Arduino |
| `seeed-xiao-mbed-nrf52840-sense` | XIAO nRF52840 Sense (mbed core) | nRF52840 | Arduino |
| `seeed-xiao-mbed-nrf52840-sense-plus` | XIAO nRF52840 Sense Plus (mbed core) | nRF52840 | Arduino |

The two nRF52840 variants build the same hardware against different Arduino
cores (Adafruit nRF52 vs. ArduinoCore-mbed); pick the one matching your
sketch's library expectations.

The nRF54LM20A V2 is the same SKU as the nRF54LM20A but revision 2.0: it
uses the nRF54LM20B PCB with the LM20A SoC, native USB CDC console, and the
MCUboot firmware-loader flash layout. It is a separate board id so uploads
can never select the wrong loader CDC (see `upload.cdc` in the manifest).

### Frameworks

- **Arduino** — the default on most boards; each family uses the upstream
  core that its vendor ships (earlephilhower for RP2040/RP2350, Adafruit or
  mbed for nRF52840, espressif for ESP32, …).
- **ESP-IDF** — on the ESP32 boards, `framework = espidf` builds through
  ESP-IDF 5.5 with regular `CMakeLists.txt` projects; see
  [`examples/espidf-blink`](examples/espidf-blink).
- **Zephyr** — the nRF54 and STM32C5 boards build with Zephyr (west-managed
  dependencies, devicetree overlays and `prj.conf` as usual); see
  [`examples/zephyr-blink`](examples/zephyr-blink).

### Uploading and debugging

Upload and debug tooling is wired per board: `picotool` on RP2040/RP2350,
`esptool` on ESP32, MCUboot-over-USB-CDC on nRF54LM20B, UF2 mass-storage on
STM32C5, `dfu-util` on RA4M1, `bossac` on SAMD/nRF52 — plus SWD debugging
via OpenOCD (`cmsis-dap`, `picoprobe`, `stlink`, …) or J-Link where the chip
supports it. `pio run -t upload` and the Debug button work out of the box
with the board's default protocol; override with `upload_protocol =` /
`debug_tool =` as on any PlatformIO platform.

## FAQ

**Does it support non-XIAO Seeed boards (Wio Terminal, Wio Lite, Zero, …)?**
No — this platform is scoped to the XIAO family on purpose. For other Seeed
boards use the upstream platforms that already carry them, e.g. Wio Terminal
builds on the official [`atmelsam`](https://github.com/platformio/platform-atmelsam)
platform (`board = seeed_wio_terminal`).

**How does this relate to `platform-seeedboards`?**
This is the next generation of that repository (the `v3` branch): same board
coverage, rebuilt on a chip-family architecture where every family is a
pluggable module and nothing is hard-coded in the routing core. The
predecessor remains the production line until this one is released.

**What Zephyr version do the nRF54/STM32C5 boards use?**
nRF54L15 uses the pinned Zephyr 4.2.1 tarball; nRF54LM20A/B and STM32C5 use
the pinned Zephyr 4.4.2 tarball. Where vanilla lacks support (e.g. STM32C5
USB/XSPI), the gap is covered by explicit per-board fixes with recorded
baselines that expire as upstream catches up — see
[ADR-0003](docs/decisions/0003-fixes-mechanism.md) and
[ADR-0006](docs/decisions/0006-zephyr-framework-views.md).

## Documentation

- [Examples](examples/) — runnable projects for every board
- [Authoring](docs/authoring.md) — adding a board or family, field by field
- [Architecture](docs/architecture.md) — how the platform is put together
- [Decision records](docs/decisions/) — binding ADRs (registry, package
  slots, fixes mechanism, validation tiers, CI merge gate)
- [Contributing](docs/contributing.md) — change workflow and CI gates
- [Governance](AGENTS.md) — principles and commit rules (for contributors
  and coding agents)

## License

Apache-2.0 — see [LICENSE](LICENSE).

This platform reuses and adapts work from several upstream projects,
including [pioarduino/platform-espressif32](https://github.com/pioarduino/platform-espressif32),
[earlephilhower/arduino-pico](https://github.com/earlephilhower/arduino-pico),
[maxgerhardt/platform-renesas](https://github.com/maxgerhardt/platform-renesas),
[ArduinoCore-mbed](https://github.com/arduino/ArduinoCore-mbed) and the
[Zephyr Project](https://github.com/zephyrproject-rtos/zephyr) — attribution
headers are preserved in the adapted files.
