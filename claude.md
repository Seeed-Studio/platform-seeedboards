# XIAO nRF54LM20B Sample Adaptation Guide

## Project Overview

This document guides automated development to adapt all existing Zephyr samples from XIAO nRF54LM20A to XIAO nRF54LM20B. The two boards share the same SoC (nRF54LM20A) with nearly identical peripheral pin assignments, making adaptation straightforward in most cases.

## Repository & Branch Strategy

| Target | Repository | Branch |
|--------|-----------|--------|
| Board definitions (20B) | `origin` = `https://github.com/Seeed-Studio/platform-seeedboards.git` | `main` |
| Sample adaptations (20B) | `dev1` = `https://github.com/cumin777/platform-seeedboards.git` | `xiao_nrf54lm20b_dev` |

**Prerequisite:** Board-level definitions for nRF54LM20B must be submitted to `origin/main` FIRST so that PlatformIO can pull them during compilation. This includes:
- `zephyr/boards/arm/xiao_nrf54lm20b/` (all board DTS/YAML/Kconfig files)
- `boards/seeed-xiao-nrf54lm20b.json` (PlatformIO board JSON)

## Key Technical Differences: 20A vs 20B

### Kconfig Macros (used in C code)
- 20A: `CONFIG_BOARD_XIAO_NRF54LM20A` / `CONFIG_BOARD_XIAO_NRF54LM20A_NRF54LM20A_CPUAPP`
- 20B: `CONFIG_BOARD_XIAO_NRF54LM20B` / `CONFIG_BOARD_XIAO_NRF54LM20B_NRF54LM20A_CPUAPP`

### Identical Between Boards (no adaptation needed)
- GPIO connector mapping (seeed_xiao_connector.dtsi): identical D0-D27
- Device aliases: `led0=blue, led1=red, led2=green, sw0=button0, pwm-led0/1/2`
- Peripheral instances: same UART/SPI/I2C/PWM/PDM controller assignments
- Button: same gpio0.9 with PULL_UP | ACTIVE_LOW
- IMU: same lsm6ds3tr_c on i2c30
- Bluetooth HCI SDC: same configuration
- ADC: same 8-channel configuration

### Differences Requiring Attention
| Feature | 20A | 20B |
|---------|-----|-----|
| MCUboot | Not default | Default enabled (`BOOTLOADER_MCUBOOT=y`) |
| Upload protocol | `cmsis-dap` | `nrfutil-mcumgr` (USB serial recovery) |
| Boot partition size | 64KB | 68KB |
| SPI flash | PY25Q64HA 64Mbit | PY25Q128HA 128Mbit |
| LED physical pins | blue=gpio1.22, red=gpio1.23 | red=gpio1.22, blue=gpio1.23 (swapped) |
| PMIC I2C GPIOs | SDA=gpio1.15, SCL=gpio1.16 | SDA=gpio1.18, SCL=gpio1.17 |
| mcuboot-button0 alias | Not present | Present |

**Critical note on LEDs:** The physical LED pins are swapped between 20A and 20B, BUT the device tree aliases keep `led0=blue, led1=red` on both boards. Code using DT aliases (`DT_ALIAS(led0)`) works unchanged. Only code referencing raw GPIO pin numbers needs attention.

## Adaptation Strategy

### Step 1: PlatformIO env configuration
For each sample's `platformio.ini`, add a new env section based on the 20A env:

```ini
[env:seeed-xiao-nrf54lm20b]
platform = https://github.com/Seeed-Studio/platform-seeedboards.git
framework = zephyr
board = seeed-xiao-nrf54lm20b
monitor_speed = 115200
```

Key changes from 20A env: `board = seeed-xiao-nrf54lm20b`

### Step 2: C source code macro adaptation
For each sample, wherever `CONFIG_BOARD_XIAO_NRF54LM20A` is used, add a parallel `CONFIG_BOARD_XIAO_NRF54LM20B` condition:

**Pattern A - Both boards share same code path:**
```c
// Before:
#if defined(CONFIG_BOARD_XIAO_NRF54LM20A)
    // board-specific code
#endif

// After:
#if defined(CONFIG_BOARD_XIAO_NRF54LM20A) || defined(CONFIG_BOARD_XIAO_NRF54LM20B)
    // same board-specific code works for both
#endif
```

**Pattern B - Both boards share same code path (else form):**
```c
// Before:
#if !defined(CONFIG_BOARD_XIAO_NRF54LM20A)
    // nrf54l15 code
#endif

// After:
#if !defined(CONFIG_BOARD_XIAO_NRF54LM20A) && !defined(CONFIG_BOARD_XIAO_NRF54LM20B)
    // nrf54l15 code
#endif
```

**Pattern C - Using longer CPUAPP macro:**
```c
// Before:
#if defined(CONFIG_BOARD_XIAO_NRF54LM20A_NRF54LM20A_CPUAPP)
    // regulator/power code
#endif

// After:
#if defined(CONFIG_BOARD_XIAO_NRF54LM20A_NRF54LM20A_CPUAPP) || defined(CONFIG_BOARD_XIAO_NRF54LM20B_NRF54LM20A_CPUAPP)
    // same regulator/power code
#endif
```

### Step 3: Build verification
After adaptation, compile with:
```bash
cd /home/seeed/workspace/nrf54lm20a_pio/platform-seeedboards/examples/<sample-path>
pio run -e seeed-xiao-nrf54lm20b
```

### Step 4: Commit
After verifying build passes, commit sample changes to `dev1` remote (`xiao_nrf54lm20b_dev` branch).

## Samples to Adapt

The following 27 samples have `[env:seeed-xiao-nrf54lm20a]` and need 20B adaptation:

### Category 1: No code changes needed (only platformio.ini + overlay)
- [x] `zephyr-blink` - LED blink, uses DT aliases only
- [x] `zephyr-gpio` - GPIO demo, uses DT aliases only
- [x] `zephyr-button` - Button demo, uses DT aliases only
- [x] `zephyr-pwm` - PWM LED, uses DT aliases + overlay
- [x] `zephyr-ble` - BLE GATT, overlay for HCI controller
- [x] `zephyr-gps` - GPS UART, no board-specific code
- [x] `zephyr-uart` - UART loopback + overlay
- [x] `zephyr-ble-lbs/lbs-central` - BLE LBS central + overlay
- [x] `zephyr-ble-lbs/lbs-peripheral` - BLE LBS peripheral + overlay
- [x] `zephyr-expansion-base-for-xiao/buzzer` - Buzzer via PWM + overlay
- [x] `zephyr-expansion-base-for-xiao/i2c-sht31` - I2C sensor
- [x] `zephyr-expansion-base-for-xiao/oled` - OLED display + macro for board model text
- [x] `zephyr-expansion-base-for-xiao/oled-lvgl` - LVGL OLED
- [x] `zephyr-expansion-base-for-xiao/rtc` - RTC via I2C + overlay
- [x] `zephyr-expansion-base-for-xiao/sd_card` - SD card via SPI + macro for banner text

### Category 2: Code changes needed (macro adaptation required)
- [x] `zephyr-adc` - 8-ch ADC, uses `CONFIG_BOARD_XIAO_NRF54LM20A` to exclude PWM + overlay
- [x] `zephyr-battery` - NPM1300 fuel gauge, uses `CONFIG_BOARD_XIAO_NRF54LM20A` for PMIC + overlay
- [x] `zephyr-dmic` - DMIC, uses `CONFIG_BOARD_XIAO_NRF54LM20A_NRF54LM20A_CPUAPP` for power + overlay
- [x] `zephyr-dmic-recorder` - DMIC recorder, same macro pattern as dmic + overlay
- [x] `zephyr-imu` - IMU sensor, uses DT_N_NODELABEL (no macro change) + overlay
- [x] `zephyr-lowpower` - Low power mode, uses `CONFIG_BOARD_XIAO_NRF54LM20A` for reset cause + overlay
- [x] `zephyr-tapwake` - Tap wake, uses `CONFIG_BOARD_XIAO_NRF54LM20A_NRF54LM20A_CPUAPP` for regulators + overlay
- [x] `zephyr-epaper/2inch13` - e-paper display, no board-specific code
- [x] `zephyr-epaper/5inch83` - e-paper display, no board-specific code

### Samples NOT to adapt (no 20A env)
These do NOT have `[env:seeed-xiao-nrf54lm20a]` and are excluded:
- `zephyr-epaper/7inch5` - Only has nrf54l15 env
- `zephyr-rfsw` - Only has nrf54l15 env
- `zephyr-xiao-round-display/watchface` - Only has nrf54l15 env
- All `arduino-*` examples - Not Zephyr, different platform

## Development Workflow (SuperPow MCP)

Follow this loop for each sample:

1. **Read** - Read the sample's `platformio.ini` and source code
2. **Analyze** - Identify all `CONFIG_BOARD_XIAO_NRF54LM20A` macro usages
3. **Adapt** - Add `[env:seeed-xiao-nrf54lm20b]` to platformio.ini, modify C macros
4. **Build** - Run `pio run -e seeed-xiao-nrf54lm20b` to verify compilation
5. **Record** - Log result in the Adaptation Results section below
6. **Commit** - Commit to `dev1/xiao_nrf54lm20b_dev` after every 3-5 samples

### Build Command
```bash
cd /home/seeed/workspace/nrf54lm20a_pio/platform-seeedboards
pio run -d examples/<sample-path> -e seeed-xiao-nrf54lm20b
```

### Commit Guidelines
- Commit message format: `feat(<sample>): adapt XIAO nRF54LM20B for <sample-name>`
- Push to: `git push dev1 xiao_nrf54lm20b_dev`

## Adaptation Results

### Prerequisite: Board Definition Submission
- [x] Submit nRF54LM20B board definitions to `origin/main` (Seeed-Studio repo) - DONE 2025-05-27

| Status | Date | Action | Notes |
|--------|------|--------|-------|
| DONE | 2025-05-27 | Pushed 4 commits to origin/main | Board defs, MCUboot config, PIO board JSON, upload protocol |

### Sample Adaptation Progress

| # | Sample | Category | Status | Build | Notes |
|---|--------|----------|--------|-------|-------|
| 1 | zephyr-blink | 1 | DONE | PASS | platformio.ini only |
| 2 | zephyr-gpio | 1 | DONE | PASS | platformio.ini only |
| 3 | zephyr-button | 1 | DONE | PASS | platformio.ini only |
| 4 | zephyr-pwm | 1 | DONE | PASS | platformio.ini + overlay copy |
| 5 | zephyr-ble | 1 | DONE | PASS | platformio.ini + overlay copy |
| 6 | zephyr-gps | 1 | DONE | PASS | platformio.ini only |
| 7 | zephyr-uart | 1 | DONE | PASS | platformio.ini + overlay copy |
| 8 | zephyr-ble-lbs/lbs-central | 1 | DONE | PASS | platformio.ini + overlay copy |
| 9 | zephyr-ble-lbs/lbs-peripheral | 1 | DONE | PASS | platformio.ini + overlay copy |
| 10 | zephyr-expansion-base-for-xiao/buzzer | 1 | DONE | PASS | platformio.ini + overlay copy |
| 11 | zephyr-expansion-base-for-xiao/i2c-sht31 | 1 | DONE | PASS | platformio.ini only |
| 12 | zephyr-expansion-base-for-xiao/oled | 1 | DONE | PASS | platformio.ini + macro (board model text) |
| 13 | zephyr-expansion-base-for-xiao/oled-lvgl | 1 | DONE | PASS | platformio.ini only |
| 14 | zephyr-expansion-base-for-xiao/rtc | 1 | DONE | PASS | platformio.ini + overlay copy |
| 15 | zephyr-expansion-base-for-xiao/sd_card | 1 | DONE | PASS | platformio.ini + macro (banner text) |
| 16 | zephyr-adc | 2 | DONE | PASS | macro adaptation + overlay copy |
| 17 | zephyr-battery | 2 | DONE | PASS | macro adaptation (NPM1300 fuel gauge) + overlay copy |
| 18 | zephyr-dmic | 2 | DONE | PASS | macro adaptation (regulator power) + overlay copy |
| 19 | zephyr-dmic-recorder | 2 | DONE | PASS | macro adaptation (regulator power) + overlay copy |
| 20 | zephyr-imu | 2 | DONE | PASS | uses DT_N_NODELABEL (no macro change needed) + overlay copy |
| 21 | zephyr-lowpower | 2 | DONE | PASS | macro adaptation (reset cause, GPIO interrupt) + overlay copy |
| 22 | zephyr-tapwake | 2 | DONE | PASS | macro adaptation (regulator power) + overlay copy |
| 23 | zephyr-epaper/2inch13 | 2 | DONE | PASS | platformio.ini only (no board-specific code) |
| 24 | zephyr-epaper/5inch83 | 2 | DONE | PASS | platformio.ini only (no board-specific code) |

### Cannot Adapt (with reasons)
| Sample | Reason |
|--------|--------|
| zephyr-epaper/7inch5 | No 20A env, only nrf54l15 |
| zephyr-rfsw | No 20A env, only nrf54l15 |
| zephyr-xiao-round-display/watchface | No 20A env, only nrf54l15 |
| arduino-* | Not Zephyr platform |
