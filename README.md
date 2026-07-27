# Seeed Xiao Series: development platform for [PlatformIO](http://platformio.org)

The [Seeed Studio XIAO Series](https://wiki.seeedstudio.com/SeeedStudio_XIAO_Series_Introduction/) is a collection of thumb-sized, powerful microcontroller units (MCUs) tailor-made for space-conscious projects requiring high performance and wireless connectivity.

* [Home](http://platformio.org/platforms/seeedxiao) (home page in PlatformIO Platform Registry)
* [Documentation](http://docs.platformio.org/page/platforms/seeedxiao.html) (advanced usage, packages, boards, frameworks, etc.)

## Usage

1. [Install PlatformIO](http://platformio.org)
2. Create PlatformIO project and configure a platform option in [platformio.ini](http://docs.platformio.org/page/projectconf.html) file:

```ini
[env:development]
platform = https://github.com/Seeed-Studio/platform-seeedboards.git
board = ...
framework = arduino
...
```

## Configuration

Please navigate to [documentation](http://docs.platformio.org/page/platforms/seeedxiao.html).

## Attribution (ESP32)

The ESP32-related platform/build integration in this repository is based in part on work from the pioarduino project:

- https://github.com/pioarduino/platform-espressif32

We acknowledge and thank the pioarduino maintainers and contributors.

## Factory Reset for XIAO nRF54L15

For XIAO nRF54L15 boards, a factory reset script is provided to recover the board from a bad state (e.g., when it's can not upload due to the internal NVM write protection). This script will perform a mass erase of the flash and program a factory firmware.

### Location

The scripts are located in the `scripts/factory_reset/` directory.

### Usage

The script will automatically create and manage a local Python virtual environment to install the necessary tools, so it can be run out-of-the-box.

*   **For Windows:**
    Navigate to the `scripts/factory_reset` directory and run:
    ```powershell
    .\factory_reset.bat
    ```

*   **For Linux and macOS:**
    Navigate to the `scripts/factory_reset` directory and run:
    ```shell
    bash factory_reset.sh
    ```

### Mass Erase Only (Recover Mode)

If you only need to remove APPROTECT and wipe the device (without programming factory firmware), use the "Recover Only" scripts.

#### Usage Examples

Windows:
```powershell
cd scripts\factory_reset
./recover_only.bat
```

Linux / macOS:
```bash
cd scripts/factory_reset
bash recover_only.sh
```

## Recovery Firmware for XIAO nRF54LM20A

For XIAO nRF54LM20A boards, use the dedicated recovery scripts to remove
APPROTECT, erase application flash, and program a known-good Zephyr blink
firmware. This is a recovery image, not the factory test firmware and not a
full restoration of manufacturing data.

The recovery image is built from `examples/zephyr-blink` using the
`seeed-xiao-nrf54lm20a` environment. Its SHA-256 checksum is recorded in
`scripts/factory_reset/firmware_lm20a_blink.sha256`.

The scripts reuse PlatformIO Core's `tool-openocd` package. If it is not
already present, PlatformIO installs that package; no separate pyOCD virtual
environment is created.

Windows:

```powershell
cd scripts\factory_reset
.\factory_reset_lm20a.bat
```

Linux / macOS:

```bash
cd scripts/factory_reset
bash factory_reset_lm20a.sh
```

When more than one CMSIS-DAP probe is connected, pass its unique ID as the
first argument to the script.

