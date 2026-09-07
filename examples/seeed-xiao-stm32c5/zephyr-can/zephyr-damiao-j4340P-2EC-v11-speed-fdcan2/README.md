# DM-J4340P-2EC V1.1 speed-mode CAN driver using FDCAN2

Single-file Zephyr example that drives a **Damiao DM-J4340P-2EC V1.1**
24 V integrated motor over Classic CAN at 1 Mbps on the XIAO STM32C5. The
sample uses FDCAN2 and the XIAO's onboard CAN transceiver.

- Motor CAN ID: `0x007`
- Master ID:    `0x017`
- CAN bitrate:  1 Mbps (classic CAN 2.0B)
- CAN controller: FDCAN2 (`RX=PB5`, `TX=PB13`)
- CAN_STB (`PB14`): managed by the board-level transceiver node (`can_phy0`)
- Console: USB CDC ACM virtual COM port (`printk`)
- Demo: cycles speed gears `0 → 3 → 6 → 10 → 6 → 3 → 0` rad/s, 5 s per gear

## Wiring

Connect the differential bus only — do **not** wire the MCU CAN_TX/CAN_RX
logic pins straight to the motor:

```
XIAO CANH  ->  motor CANH
XIAO CANL  ->  motor CANL
XIAO GND   ->  motor GND (24V-)
24V+       ->  motor VCC
```

Use the CANH/CANL pads or terminal behind the XIAO's onboard transceiver.
Add a **120 Ω terminator at each end** of the bus. The motor needs its own
24 V supply.

## CAN protocol (Damiao speed mode)

| Frame | CAN ID | Payload |
| --- | --- | --- |
| Speed command | `0x200 + motor_id` (`0x207`) | `D[0..3]` = `v_des` float32 LE (rad/s), DLC=4 |
| Control cmd | `0x200 + motor_id` (`0x207`) | `D[0..6]` = `0xFF`, `D[7]` = cmd, DLC=8 |
| Parameter write | `0x7FF` | `D[0..1]` = motor_id LE, `D[2]` = `0x55`, `D[3]` = reg, `D[4..7]` = u32 LE |

Control commands (`D[7]`): `0xFC` = enable, `0xFD` = disable, `0xFB` = clear
error. Startup writes `CTRL_MODE = 3` (speed mode) before enabling.

The **Master ID** (`0x017`) is a parameter stored in the motor and is used by
the motor to address parameter/feedback responses back to this host; it does
not appear in the speed-mode command frame IDs.

## Build & flash

```powershell
pio run -e seeed-xiao-stm32c5
```

Flash the UF2 (`double-tap RESET` to enter bootloader, then copy
`.pio\build\seeed-xiao-stm32c5\firmware.uf2` into the `XIAOC5BOOT` drive), or:

```powershell
pio run -e seeed-xiao-stm32c5 -t upload
```

## Monitor

```powershell
pio device monitor -e seeed-xiao-stm32c5
```

The XIAO enumerates a USB CDC ACM COM port. Logs print a `FB` line every 500 ms
with decoded position / velocity / torque / temperatures.

## Fixed speed instead of the gear sequence

To drive a constant speed, replace the `gears[]` / `gear_sequence[]` tables
with a single value and call `dm_send_speed(v)` in the loop. The command must
be repeated faster than the motor's CAN-loss timeout (typically ≥ 200 Hz is
safe; this example uses 50 Hz with a 500 ms timeout window).

## Reference

- Damiao DM-J4340P-2EC V1.1 manual:
  https://wiki.aifitlab.com/damiao-docs/dm-j4340p-2ec-v11-motor-instruction-manual
