# XIAO STM32C5 BMP280 SPI sample

This Zephyr sample reads temperature and pressure from a BMP280 over the XIAO
STM32C5's SPI3 bus using Zephyr's built-in BME280/BMP280 sensor driver.

## Wiring

| BMP280 SPI pin | XIAO STM32C5 pin | STM32C5 pin |
| --- | --- | --- |
| SCK | D8 | PE2 / SPI3_SCK |
| SDO / MISO | D9 | PB0 / SPI3_MISO |
| SDI / MOSI | D10 | PB15 / SPI3_MOSI |
| CSB / CS | D3 | PA3 / GPIO |
| VCC | 3V3 | 3.3 V |
| GND | GND | GND |

The chip select assignment is local to
`zephyr/boards/xiao_stm32c5.overlay`. To use a different GPIO, change only
that overlay's `cs-gpios` property and wire the sensor accordingly.

This sample requires a BMP280/BME280 breakout that exposes SPI pins. The
standard four-wire Grove BME280 module uses I2C and is not compatible with this
SPI wiring.

## Build and run

```sh
pio run -t upload
pio device monitor -b 115200
```

The serial console prints temperature in degrees Celsius and pressure in kPa
once per second.
