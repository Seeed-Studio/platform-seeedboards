# XIAO STM32C5 IMU Temperature PID + 6-Axis Interrupt Test

This sample verifies that the onboard LSM6DS3TR-C IMU can keep reporting six-axis data while the IMU heater PID temperature compensation loop is running.

It checks:

- IMU temperature readback
- heater PWM PID output
- six-axis accelerometer and gyroscope readback
- IMU INT1 data-ready interrupt counting

## Hardware Mapping

No external wiring is required.

| Signal | XIAO STM32C5 |
| --- | --- |
| IMU | LSM6DS3TR-C |
| I2C bus | I2C2 |
| I2C address | 0x6A |
| SCL | PB3 / I2C2_SCL |
| SDA | PB4 / I2C2_SDA |
| INT1 | PC13 / active-high data-ready interrupt |
| Heater PWM | PA8 / TIM1_CH1 |

## Build

```powershell
cd D:\workspace\platform-seeedboards\examples\seeed-xiao-stm32c5\zephyr-imu-temp-pid-6axis
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
IMU WHO_AM_I=0x6a OK
IMU data-ready interrupt configured on PC13 / INT1
[PID] temp=...
[IRQ] data-ready total=...
[IMU] irq=... accel(m/s^2) ... gyro(rad/s) ...
```

The PID control step runs every 500 ms. Runtime logs are rate-limited to about once per second for temperature, interrupt summary, and six-axis data.
