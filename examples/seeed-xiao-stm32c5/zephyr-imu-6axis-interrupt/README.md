# XIAO STM32C5 IMU 6-Axis Interrupt Test

This sample verifies the onboard LSM6DS3TR-C IMU on XIAO STM32C5.

It checks:

- USB UF2 flashing workflow
- six-axis accelerometer and gyroscope readback
- IMU data-ready interrupt on INT1

## Hardware Mapping

No external wiring is required.

| Signal | XIAO STM32C5 |
| --- | --- |
| IMU | LSM6DS3TR-C |
| I2C bus | I2C2 |
| I2C address | 0x6A |
| SCL | PB3 / I2C2_SCL |
| SDA | PB4 / I2C2_SDA |
| INT1 | PC13 / active-high |

## Build

```powershell
cd D:\workspace\platform-seeedboards\examples\seeed-xiao-stm32c5\zephyr-imu-6axis-interrupt
pio run
```

## Flash

Connect the board to the PC by USB, enter UF2 bootloader mode, then copy:

```text
.pio\build\seeed-xiao-stm32c5\firmware.uf2
```

to the UF2 drive.

## Expected Log

```text
IMU WHO_AM_I=0x6a
IMU data-ready interrupt configured
[IMU] irq=1 accel(m/s^2) x=... y=... z=... gyro(rad/s) x=... y=... z=...
```

The `irq=` counter should increase continuously. Move or rotate the board to see the six-axis values change.
