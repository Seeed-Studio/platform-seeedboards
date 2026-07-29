# XIAO STM32C5 I2C Speed Test with BME280

This sample measures the fastest stable I2C speed supported by the current
XIAO STM32C5 board, bus wiring, pull-ups, and BME280/BMP280 module.

## Wiring

Use I2C1 on the XIAO header:

- SCL: XIAO D5 / PB6 / I2C1_SCL
- SDA: XIAO D4 / PB7 / I2C1_SDA
- 3V3 and GND

The firmware auto-detects the sensor at `0x76` or `0x77`.

## Run

```sh
pio run -t upload
pio device monitor -b 115200
```

The log first searches from the highest test speed down, then runs a detailed
100-transaction test at each speed. Unsupported speeds are skipped by the I2C
driver; unstable speeds are reported with failure counts.
