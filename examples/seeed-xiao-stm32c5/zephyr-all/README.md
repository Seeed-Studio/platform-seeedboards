# XIAO STM32C5 USB CDC Blink ADC

Small bring-up sample with only:

- USB CDC ACM UART output, not Zephyr console
- User LED blink
- A0-A3 ADC voltage printing every 5 seconds
- A4/D4/PB7 PWM output at 1 kHz, 50% duty
- IMU temperature PI compensation with direct polled I2C temperature reads and PA8/TIM1_CH1 heater PWM
- IMU accel/gyro raw readout using the LSM6DS3TR-C INT1 data-ready GPIO interrupt
- CAN FD two-board test at 1 Mbps arbitration / 8 Mbps data, using normal-mode FD+BRS frames at 2 fps
- Node A sends standard ID `0x701` and checks `0x702`; node B sends `0x702` and checks `0x701`
- Battery voltage readout through BAT_EN/PE2 and BAT_Reading/PA4
- External flash erase/write/read/verify every 5 seconds

Build node A for the first board:

```sh
pio run -e xiao-c5-can-node-a
```

Build node B for the second board:

```sh
pio run -e xiao-c5-can-node-b
```

Connect CAN_H to CAN_H and CAN_L to CAN_L, with a 120-ohm terminator at each end
of the bus. The 5-second USB report must show increasing TX `success` and RX
`valid` counters, with `invalid=0`, `lost=0`, and both loss rates at `0.00%`.
The packet counters are cumulative since boot. TX `lost` equals TX `failed`;
RX `lost` is inferred from gaps in the peer sequence number.

Monitor either board:

```sh
pio device monitor -b 1000000
```

Behavior:

- No banner is printed.
- The user LED toggles in its own thread every 500 ms and does not depend on the USB CDC port being open.
- USB CDC output is attempted every 5 seconds; DTR is printed only as a diagnostic state.
- Each 5-second report is grouped as `[USB]`, `[BUS ENABLE]`, `[LED]`, `[ADC A0-A3]`, `[PWM]`, `[HEATER PWM]`, `[CAN PHY]`, `[IMU TEMP]`, `[IMU DATA IRQ]`, `[BAT]`, and `[FLASH]`.
- A4/D4 is the XIAO header PB7 pin. Battery sense uses internal PA4/ADC1_IN4, not PB7.
- Heater PWM uses the board `imu-heater` alias on PA8/TIM1_CH1.
- CAN transceiver standby uses the board `can_phy0` standby GPIO. PB14 is active-high standby, so the sample drives it inactive/low to enable the transceiver.
- `CONFIG_I2C`, `CONFIG_SPI`, `CONFIG_CAN`, and `CONFIG_CAN_FD_MODE` are explicitly enabled. The sample reports I2C2, XSPI1/external flash, and FDCAN2 status without requiring external I2C/SPI/CAN peripherals to be connected.
- IMU temperature compensation runs every 500 ms, targets 40 C, and limits heater duty to 60%.
- IMU temperature uses direct I2C register polling on the board `imu0` alias. It initializes `CTRL1_XL` to 12.5 Hz when the IMU is in power-down and converts temperature as `25 + raw / 256`, matching the Zephyr LSM6DSL temperature driver behavior.
- IMU accel/gyro data uses the board `imu0` `irq-gpios` pin, PC13, as a GPIO edge interrupt. INT1 is configured for accel data-ready only; the work handler reads raw accel and gyro registers over I2C.
- This does not enable Zephyr sensor drivers or sensor triggers.
- Flash test uses external flash offset `0x00100000`, writes 256 bytes, reads them back, and prints verify status.
