# XIAO STM32C5 FDCAN2 GPIO Reuse Command Test

This sample simulates using XIAO STM32C5 as an onboard module where the user does not use the onboard CAN transceiver and reuses the FDCAN2 pins as normal GPIO.

## Test Purpose

- Put the onboard CAN transceiver into standby by driving `CAN_STB/PB14` high.
- Disable `FDCAN2` in the sample overlay so PB5/PB13 are not claimed by CAN pinctrl.
- Configure `TP7/PB5/FDCAN2_RX` and `TP8/PB13/FDCAN2_TX` as GPIO outputs.
- Provide serial commands so TE can manually drive PB5/PB13 and verify the level with a multimeter while PB14 stays high.

## Pins

| Signal | MCU pin | Function in this sample |
| --- | --- | --- |
| TP7 | PB5 | GPIO output, formerly FDCAN2_RX |
| TP8 | PB13 | GPIO output, formerly FDCAN2_TX |
| CAN_STB | PB14 | GPIO output high, CAN transceiver standby |

## Build

```powershell
cd D:\workspace\platform-seeedboards\examples\seeed-xiao-stm32c5\zephyr-can-gpio-reuse
pio run
```

## Serial Commands

Serial protocol:

- ASCII text
- `115200 8N1`
- Preferred command ending: Enter, CR, LF, or CRLF
- If the serial tool sends no line ending, the sample accepts the buffered command after 1 second with no new RX byte

The program prints this command list at startup:

```text
help
status
pb5 0
pb5 1
pb13 0
pb13 1
set 0 0
set 1 0
set 0 1
set 1 1
toggle pb5
toggle pb13
toggle both
```

Use a multimeter with black probe on GND and red probe on TP7/PB5 or TP8/PB13. A low command should measure near 0 V, and a high command should measure near 3.3 V.

For a valid command, the log prints `RX command: ...` and `OK: ...`. For an invalid command, it prints `ERROR: ...`.

The heartbeat is intentionally short:

```text
[heartbeat] PB5=0(read 0) PB13=0(read 0) PB14/STB=HIGH(read 1)
```
