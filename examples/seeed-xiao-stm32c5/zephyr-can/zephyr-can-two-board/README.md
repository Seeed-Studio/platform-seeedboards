# XIAO STM32C5 Two-Board CAN Round-Trip Test

This sample verifies Classic CAN and CAN FD communication between two XIAO
STM32C5 boards without a USB-to-CAN adapter. Both boards run the same firmware
and expose a command interface through the on-board USB CDC ACM port.

One board acts as the initiator and the other as the responder. The initiator
sends numbered frames, the responder returns each frame without modifying its
format or payload, and the initiator checks the returned data byte for byte.

## Hardware setup

```text
Board A CANH ---- Board B CANH
Board A CANL ---- Board B CANL
Board A GND  ---- Board B GND
```

- Install one 120-ohm termination resistor at each physical end of the bus.
- Use a short twisted pair for initial validation.
- Connect each board to the host through its own USB-C cable.
- FDCAN2 uses the on-board transceiver (`RX=PB5`, `TX=PB13`). The board
  devicetree controls the transceiver standby signal on PB14.

## Build and flash

```powershell
cd examples\seeed-xiao-stm32c5\zephyr-can\zephyr-can-two-board
pio run
```

Flash the same generated `firmware.uf2` image to both boards. Open both CDC ACM
ports with a serial terminal. The configured terminal baud rate does not affect
USB CDC throughput. Do not select 1200 baud because that line-coding value
requests the UF2 bootloader.

## Commands

```text
init <nominal> <data> <can|fd|fd-brs> [count] [fps]
reply <nominal> <data> <can|fd|fd-brs>
stop
status
id [init_id] [echo_id]
clock
regs
help
```

- `init` starts the initiator. The default frame count is 1000; `fps=0` sends
  as fast as the bus permits.
- `reply` starts the responder and continues until `stop` is entered.
- `id` displays or sets the standard CAN identifiers. Values are hexadecimal
  from `0x000` through `0x7ff`; the identifiers must differ.
- `clock` reports the CAN kernel clock.
- `regs` reports the relevant FDCAN2 and RCC diagnostic registers.

Configure both boards with identical bit rates and frame formats:

```text
Board A: init  500000 2000000 fd-brs
Board B: reply 500000 2000000 fd-brs
```

The default initiator and echo identifiers are `0x504` and `0x505`. The
payload contains a magic value, sequence number, timestamp, and deterministic
test pattern. Separate identifiers prevent local loopback traffic from being
mistaken for responder traffic.

## Recommended validation sequence

Start with `500000/2000000 fd-brs`, then test the required timing combinations:

```text
Board A: init  1000000 1000000 fd-brs
Board B: reply 1000000 1000000 fd-brs

Board A: init  500000 5000000 fd-brs
Board B: reply 500000 5000000 fd-brs

Board A: init  1000000 0 can
Board B: reply 1000000 0 can
```

Run `stop` on both boards before changing timing. A test passes only when every
transmitted frame is returned, no payload error is detected, and neither
controller enters the stopped or bus-off state. If a test fails, compare
`status`, `clock`, and `regs` from both boards. Verify the nominal and data
timing registers, protocol status, error counters, and transmitter delay
compensation when using high data-phase rates with BRS.
