How to build PlatformIO based project
=====================================

Example for a 7.5 inch black-white e-ink display with 800x480 resolution, 4 Grayscale, 24 pins FPC connection, optional FPC connector, communicating via SPI interface, with embedded controller(COG package) and on-chip stored waveform: [GDEW075T7](https://www.e-paper-display.com/products_detail/productId=456.html)

1. [Install PlatformIO Core](https://docs.platformio.org/page/core.html)
2. Download [development platform with examples](https://github.com/Seeed-Studio/platform-seeedboards/archive/refs/heads/main.zip)
3. Extract ZIP archive
4. Run these commands:

```shell
# Change directory to example
$ cd platform-seeedboards/examples/zephyr-epaper/7inch5

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

