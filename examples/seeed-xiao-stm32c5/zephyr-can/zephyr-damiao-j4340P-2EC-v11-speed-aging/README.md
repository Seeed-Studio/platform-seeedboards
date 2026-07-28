# XIAO STM32C5 Damiao DM-J4340P-2EC V1.1 24V Speed Aging Sample

This sample is copied from the known-working DM-J4340P-2EC V1.1 speed sample
and keeps the same CAN startup/control path. It runs a conservative 15-minute
speed aging profile continuously for long-run testing.

## Wiring

```text
XIAO CAN_H  -> motor CAN_H
XIAO CAN_L  -> motor CAN_L
XIAO GND    -> motor GND / 24V-
24V+        -> motor VCC
24V-        -> motor GND
```

Use the XIAO board CANH/CANL pins behind the CAN transceiver. Do not connect
MCU CAN_TX/CAN_RX logic pins directly to the motor CANH/CANL differential bus.

## Aging Profile

The firmware sends speed commands every 20 ms and repeats this conservative
15-minute profile:

| Step | Duration | Speed |
| --- | ---: | ---: |
| run | 5 min | 3.0 rad/s |
| cooldown | 10 min | 0.0 rad/s |

For a 7-day aging test, leave the firmware running continuously. The profile
will loop until power is removed or the firmware is reset.

The feedback log prints once per second and includes `rev`, an accumulated
rotation count estimated from the motor position feedback. During normal
operation this value should keep increasing while the motor is commanded to run.

## CAN Protocol

The sample writes the runtime control mode at startup:

```text
CTRL_MODE = 3       speed mode
```

In speed mode the command frame is:

```text
CAN ID: 0x200 + motor_id
D[0..3]: v_des float, little-endian, rad/s
DLC: 4
```

The default `DAMIAO_MOTOR_ID` is `1`.

At startup the sample also reads `ACC`, `DEC`, `MAX_SPD`, `VMAX`, `KP_ASR`,
`KI_ASR`, `Deta`, and `VBus` for diagnostics. It does not write speed-loop or
speed-limit parameters and does not send Damiao's "store parameters" command.

## Build

```powershell
cd D:\workspace\platform-seeedboards\examples\seeed-xiao-stm32c5\zephyr-damiao-j4340P-2EC-v11-speed-aging
pio run
```

The build output includes:

```text
.pio\build\seeed-xiao-stm32c5\firmware.uf2
```
