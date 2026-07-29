# XIAO STM32C5 GPIO All Pins CDC Test

USB CDC is used as the command and log port. The test drives XIAO header pins
D0-D15 as independent GPIO outputs.

## Default State

- D0-D14: LOW
- D15/PB14/CAN_STB: HIGH

## Commands

```text
help
map
status
set d0 1
set d0 0
toggle d0
solo d0
solo d15 0
all 0
all 1
idle
walk 500
```

## Measurement

Meter black probe goes to GND. Meter red probe goes to the target D pin.
Expected LOW is near 0 V. Expected HIGH is near 3.3 V.

Open the USB CDC COM port at 1000000 baud, 8N1. Do not open it at 1200 baud
during the test because 1200 baud is reserved for the UF2 bootloader trigger.
