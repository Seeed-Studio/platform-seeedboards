# Examples

Every demo is a small regression contract, grouped by demo rather than by
board so one `platformio.ini` carries all boards of a framework. The CI
matrix builds every env (see `.github/workflows/`).

| Demo | Framework | Boards | Purpose |
| --- | --- | --- | --- |
| `arduino-blink` | Arduino | all Arduino boards (19) | GPIO/LED smoke |
| `arduino-uart` | Arduino | all Arduino boards (19) | serial console/UART smoke |
| `arduino-wifiscan` | Arduino | ESP32-C3/C5/C6/S3 Plus/S3 Sense | WiFi stack canonical demo |
| `arduino-usb-keyboard` | Arduino | ESP32-S3 Plus/Sense | USB HID stack |
| `espidf-blink` | ESP-IDF | all ESP boards (5) | ESP-IDF/CMake smoke |
| `zephyr-blink` | Zephyr | all Zephyr boards (5) | Zephyr/board-tree smoke |
| `zephyr-uart` | Zephyr | all Zephyr boards (5) | USB-UART/console smoke |
| `zephyr-ble` | Zephyr | nRF54L15/LM20A/LM20A V2 | BLE stack + GATT |
| `zephyr-adc` | Zephyr | nRF54L15/LM20A/LM20A V2 | ADC driver + overlays |
| `zephyr-gpio` | Zephyr | nRF54L15/LM20A/LM20A V2 | button + relay GPIO |
| `zephyr-button` | Zephyr | nRF54L15/LM20A/LM20A V2 | button + LED GPIO |
| `zephyr-pwm` | Zephyr | nRF54L15/LM20A/LM20A V2 | PWM LED fade |
| `zephyr-battery` | Zephyr | nRF54L15/LM20A/LM20A V2 | ADC/fuel-gauge battery |
| `zephyr-imu` | Zephyr | nRF54L15/LM20A/LM20A V2 | LSM6DSL accel/gyro |
| `zephyr-tapwake` | Zephyr | nRF54L15/LM20A/LM20A V2 | tap-to-wake + PM |
| `arduino-rmt-blink` | Arduino | ESP32-S3 Plus/Sense | RMT/WS2812 timing |
| `seeed-xiao-stm32c5/zephyr-can/zephyr-can-gpio-reuse` | Zephyr | STM32C5 | FDCAN2 pins as GPIO + UF2 reset |

Total: 47 Arduino + 35 Zephyr + 5 ESP-IDF = **87 envs**. See the
[example parity](../docs/example-parity.md) table for the target-repo map.

Build one demo or one env:

```bash
python scripts/ci/build_examples.py --framework arduino --clean
python scripts/ci/build_examples.py --framework zephyr --clean \
    --only-env seeed-xiao-nrf54lm20a
```

`arduino-blink`/`arduino-uart` are the minimum pair; the WiFi/USB/RMT and
BLE/ADC/GPIO/PWM/battery/IMU/tap/CAN demos cover framework-specific stacks
that blink/uart cannot. Remaining target hardware samples (epaper, GPS,
low-power, audio, expansion boards, edge-AI, ...) are tracked in
[example parity](../docs/example-parity.md), not silently dropped.