# Example parity with platform-seeedboards

The predecessor (`origin/main` of the same repository) contains **104
`platformio.ini` projects / 144 envs** covering 24 boards. Much of that
count is board-grouped duplication of the same sample (V2/LM20B/STM32C5/
edge-AI directories), not 104 distinct regressions.

This tree deliberately ports the **demo-grouped** structure first, then
board-grouped hardware samples when they can be built and maintained.

## Counts

| | predecessor `main` | this tree |
| --- | --- | --- |
| boards | 24 | 24 |
| frameworks | 3 | 3 |
| example projects | 104 | 27 |
| example envs | 144 | 110 |
| offline tests | 2 files | 66 tests / 11 files |

## Ported (27 projects)

| Demo | Framework | Status |
| --- | --- | --- |
| `arduino-blink`, `arduino-uart` | Arduino | ported (uart is ours) |
| `arduino-wifiscan` | Arduino | ported, 5 ESP boards |
| `arduino-usb-keyboard` | Arduino | ported, 2 S3 boards |
| `arduino-rmt-blink` | Arduino | ported, 2 S3 boards |
| `espidf-blink` | ESP-IDF | ported, 5 boards |
| `zephyr-blink`, `zephyr-uart` | Zephyr | ported, 5 boards |
| `zephyr-ble`, `zephyr-adc` | Zephyr | ported, L15/LM20A/V2 |
| `zephyr-gpio`, `zephyr-button`, `zephyr-pwm` | Zephyr | ported, L15/LM20A/V2 |
| `zephyr-battery`, `zephyr-imu`, `zephyr-tapwake` | Zephyr | ported, L15/LM20A/V2 |
| `zephyr-gps`, `zephyr-lowpower` | Zephyr | ported, L15/LM20A/V2 |
| `zephyr-npm1300-register-read` | Zephyr | ported, LM20A/V2 |
| `zephyr-rfsw` | Zephyr | ported, L15 |
| `zephyr-ble-lbs` (central/peripheral) | Zephyr | ported, L15 |
| expansion-base `rtc`, `oled` | Zephyr | ported, L15/LM20A/V2 |
| `zephyr-epaper/2inch13`, `5inch83` | Zephyr | ported, L15/LM20A/V2 |
| STM32C5 `zephyr-can-gpio-reuse` | Zephyr | ported, 1 board |

## Follow-ups (borrow when buildable)

- **Zephyr demo-grouped**: `zephyr-dmic`, `zephyr-dmic-recorder`,
  expansion-base `buzzer` / `oled-lvgl` / `sd_card`,
  `zephyr-xiao-round-display`, `xiao_nrf54lm20a_ble`.
- **Board-grouped**: the V2, nRF54LM20B and STM32C5 sample directories
  (including `power_measure/*`) are duplicates of the above with
  board-specific overlays; port them as `examples/<board-id>/<sample>/`
  only when they add a distinct regression.
- **Edge AI**: the seven nRF54LM20B `edgeai-*` samples depend on
  sdk-edge-ai / Edge Impulse prebuilt assets; treat them as optional
  board-grouped samples, not part of the default matrix.

## Policy

- Port the **sample logic + overlay**, not the predecessor's stale platform
  URL or `platform_packages` pins.
- Every ported env must be clean-built locally before it enters the matrix;
  hardware upload/debug remains T3 and is never claimed from a compile.
- Batch 3 (GPS/low-power/PMIC/RFSW/LBS/RTC/OLED/e-paper) was compiled 23/23
  locally; Batch 2 was 20/20.
- Keep this table updated when a follow-up lands; the counts are the
  coverage contract.