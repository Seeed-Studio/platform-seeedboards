# XIAO STM32C5 I2C Speed Test with DHT20

This sample validates the Temperature & Humidity I2C sensor on the Seeed Studio
Arduino Sensor Kit BASE. The sensor driver target is DHT20.

## Sensor IDs

- Driver/model: `DHT20`
- I2C 7-bit address: `0x38`
- STM32 HAL shifted address: `0x70`
- Read address byte: `0x71`

The DHT20 does not expose a BME280-style chip ID register. The firmware detects
the sensor by reading its status byte at the fixed I2C address `0x38`.

## Wiring

Use I2C1 on the XIAO header:

- SCL: XIAO D5 / PB6 / I2C1_SCL
- SDA: XIAO D4 / PB7 / I2C1_SDA
- 3V3 and GND

For the Arduino Sensor Kit BASE, connect XIAO I2C to the BASE I2C bus used by
the Temperature & Humidity module.

## Run

```sh
pio run -v
pio device monitor -b 115200
```

The test starts at 100 kHz and steps upward through 400 kHz, 1 MHz, and
3.4 MHz. DHT20-class devices are normally expected to work at standard/fast I2C
speeds; unsupported or unstable higher modes are reported in the log.
