# Seeed Studio XIAO: development platform for [PlatformIO](https://platformio.org)

The [Seeed Studio XIAO series](https://wiki.seeedstudio.com/SeeedStudio_XIAO_Series_Introduction/) is a family of thumb-sized MCUs for space-conscious projects. This repository is the PlatformIO platform package that lets you build for every XIAO board with one `platformio.ini` entry -- Arduino, ESP-IDF, or Zephyr, from compile to flash to debug.

* [Platform Registry page](https://platformio.org/platforms/seeedxiao) · [Documentation](https://docs.platformio.org/page/platforms/seeedxiao.html)
* Apache-2.0 licensed. ESP32 integration is based in part on [pioarduino](https://github.com/pioarduino/platform-espressif32) -- see Attribution below.

## Quick start

```ini
[env:xiao]
platform = https://github.com/Seeed-Studio/platform-seeedboards.git
board = seeed-xiao-nrf54lm20b   ; any board id below
framework = zephyr               ; arduino | espidf | zephyr
```

```bash
pio run -e xiao        # build
pio run -t upload      # flash
```

## Supported boards

| Family | Boards (`board =` ids) | Frameworks |
| --- | --- | --- |
| ESP32 | `seeed-xiao-esp32-c3` `-c5` `-c6` `-s3-plus` `-s3-sense` | Arduino, ESP-IDF |
| Nordic nRF52 | `seeed-xiao-mbed-nrf52840{,-plus,-sense,-sense-plus}`, `seeed-xiao-afruitnrf52-nrf52840{,-plus,-sense,-sense-plus}` | Arduino |
| Nordic nRF54 | `seeed-xiao-nrf54l15`, `seeed-xiao-nrf54lm20a`, `seeed-xiao-nrf54lm20b` | Zephyr |
| Raspberry Pi | `seeed-xiao-rp2040`, `seeed-xiao-rp2350` | Arduino |
| SAMD | `seeed-xiao-samd` | Arduino |
| STM32 | `seeed-xiao-stm32c5` | Zephyr |
| Renesas | `seeed-xiao-ra4m1` | Arduino |
| Silicon Labs | `seeed-xiao-mg24`, `seeed-xiao-mg24-sense` | Arduino |

Zephyr boards route to per-generation framework packages automatically (Zephyr 4.2 for nRF54L15, 4.4 for nRF54LM20/STM32C5); upstream gaps are covered by per-board fixes under [`zephyr/boards/arm/<board>/fixes/`](zephyr/) that expire on their own as upstream catches up.

The `examples/` tree doubles as the regression suite (CI builds every environment) -- from `zephyr-blink` to a full Nordic Edge AI sample set.

## Repository map

| Path | Owns |
| --- | --- |
| `boards/` | board manifests incl. the `build.family` routing key |
| `platform.py` / `platform.json` | PlatformIO lifecycle entry; package & framework declarations |
| `platform_cfg/` | per-family package defaults and debug tools |
| `builder/` | family build/upload scripts + framework integrations (arduino / espidf / zephyr) |
| `zephyr/` | Zephyr board definitions, bundled modules, per-board upstream fixes |
| `examples/`, `scripts/ci/`, `.github/workflows/` | regression contracts and offline gates |
| `.agents/` | engineering notes and agent workflow rules (see `AGENTS.md`) |

## Developing this platform

```bash
pytest tests/ -q                      # unit tests (console script; see scripts/ci/AGENTS.md)
python scripts/ci/verify_boards.py    # offline board-manifest gate
python scripts/ci/verify_zephyr_routing.py
python scripts/ci/smoke_pio_boards.py # pio boards listing smoke
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the change workflow, and the per-directory `AGENTS.md` files for layer-specific rules.

## Recovery tools

**XIAO nRF54L15** -- mass erase / factory firmware when the board is
bricked by NVM write protection (APPROTECT): `scripts/factory_reset/factory_reset.{sh,bat}`,
recover-only variant `recover_only.{sh,bat}`.

**XIAO nRF54LM20A** -- removes APPROTECT, erases application flash and
programs a known-good Zephyr blink image (built from `examples/zephyr-blink`,
checksum in `firmware_lm20a_blink.sha256`):
`scripts/factory_reset/factory_reset_lm20a.{sh,bat}`. Pass a CMSIS-DAP
probe unique id as the first argument when several probes are connected.

## Attribution

The ESP32 platform/build integration is based in part on work from the
pioarduino project (https://github.com/pioarduino/platform-espressif32).
We acknowledge and thank the pioarduino maintainers and contributors.

## License

Apache-2.0 -- see [LICENSE](LICENSE).
