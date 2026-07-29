# XIAO STM32C5 DHT20 Continuous Read

This sample continuously reads the DHT20 Temperature & Humidity I2C sensor on
the Seeed Studio Arduino Sensor Kit BASE. The I2C bus is configured at 400 kHz.

## Sensor IDs

- Driver/model: `DHT20`
- I2C 7-bit address: `0x38`
- STM32 HAL shifted address: `0x70`
- Read address byte: `0x71`

## Wiring

- SCL: XIAO D5 / PB6 / I2C1_SCL
- SDA: XIAO D4 / PB7 / I2C1_SDA
- VCC: XIAO 3V3
- GND: XIAO GND

## Build

```powershell
pio run -v
```

UF2 output:

```text
.pio\build\seeed-xiao-stm32c5\firmware.uf2
```

## Monitor

```powershell
pio device monitor -b 115200
```

The firmware prints one sample per second.
