How to build PlatformIO based project
=====================================

1. [Install PlatformIO Core](https://docs.platformio.org/page/core.html)
2. Download [development platform with examples](https://github.com/Seeed-Studio/platform-seeedboards/archive/refs/heads/main.zip)
3. Extract ZIP archive
4. Run these commands:

```shell
# Change directory to example
$ cd platform-seeedboards/examples/zephyr-button

# Build project
$ pio run

# Upload firmware
$ pio run --target upload

# Build specific environment
$ pio run -e seeed-xiao-nrf54l15

# Upload firmware for the specific environment
$ pio run -e seeed-xiao-nrf54l15 --target upload

# Clean build files
$ pio run --target clean
```

---
**Note for XIAO_nRF54L15 users:**  
Due to the internal NVM write protection mechanism of the nRF54L15 chip, you may encounter issues where uploading with OpenOCD fails. To unlock the chip and upload firmware, please use the provided Python script. After using the script, you can use OpenOCD to upload normally.
Add the following lines to your `platformio.ini` to enable the script:

```ini
upload_protocol = custom
upload_command = python "${platformio.platforms_dir}/Seeed Studio/scripts/xiao_nrf54l15_recover_flash.py" --hex $SOURCE --mass-erase
```

**Tips:** This script cannot determine the target device by serial port. If you have more than one debug probe connected, you must specify the probe ID explicitly using the `--probe` option.
