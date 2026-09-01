# XIAO STM32C5 SLCAN USB-to-CAN/CAN FD Bridge

This firmware turns the XIAO STM32C5 into a USB CDC SLCAN/LAWICEL adapter for
SavvyCAN. It supports Classic CAN and the SavvyCAN CAN FD extension. The
recommended CAN FD configuration is a 500 kbit/s nominal bitrate and a
2 Mbit/s data bitrate.

## Hardware

- CAN controller: on-board FDCAN2 (PB5 RX / PB13 TX)
- CAN transceiver standby: PB14, controlled by the Zephyr CAN driver
- Host interface: USB CDC ACM at 115200 baud
- CAN bus: connect CANH to CANH, CANL to CANL, and GND to GND
- Termination: use 120 ohm at each physical end of the CAN bus

A real transmit test requires a second active CAN node to acknowledge frames.
For the SavvyCAN peer test, flash this firmware to both XIAO boards.

## Build and flash

```bash
pio run
pio run -t upload
```

The UF2 file is generated at:

```text
.pio/build/seeed-xiao-stm32c5/firmware.uf2
```

## SavvyCAN configuration

Use SavvyCAN V220 or later. Open **Connection -> Open Connection Window**, then
add a **LAWICEL / SLCAN Serial** connection and select the XIAO serial port.
Set the serial baud rate to **115200**.

In the bus settings, set the nominal CAN speed to **500000**, enable **CAN FD**,
and set the CAN FD data speed to **2000000**. Leave **Listen Only** disabled,
enable the bus, save the bus settings, and connect.

SavvyCAN V220 may omit the CAN FD data-rate command because of an upstream
LAWICEL connection bug. The firmware therefore defaults to CAN FD at 500 kbit/s
nominal and 2 Mbit/s data rate. Both of these startup sequences are accepted:

```text
C
S6
Y2
O
```

```text
C
S6
O
```

`S6` selects the 500 kbit/s nominal bitrate. When present, `Y2` explicitly
selects the 2 Mbit/s data bitrate. Omitting `Y2` retains the firmware's 2 Mbit/s
default. Each accepted command is acknowledged by a carriage return; an invalid
command returns BEL (`0x07`).

## CAN FD frame format

The firmware implements SavvyCAN's LAWICEL CAN FD extension:

- `d`: standard-ID CAN FD frame without bit-rate switching
- `b`: standard-ID CAN FD frame with bit-rate switching
- `D`: extended-ID CAN FD frame without bit-rate switching
- `B`: extended-ID CAN FD frame with bit-rate switching
- `Y1`, `Y2`, `Y4`, `Y5`: select a 1, 2, 4, or 5 Mbit/s data bitrate

The CAN FD DLC codes `9` through `F` represent 12, 16, 20, 24, 32, 48, and
64 data bytes. Classic `t/T/r/R` frames remain supported.

## Test with SavvyCAN and a second board

Connect both boards to the same correctly terminated CAN bus and flash this
firmware to both. Connect one board to SavvyCAN. Close every other program that
may hold its serial port, then run the peer script on the other board:

```text
python -m pip install pyserial
python savvycan_fd_peer.py send
```

SavvyCAN Bus Traffic should display IDs `0x200`, `0x201`, and `0x1ABCDE`.
The `0x201` and `0x1ABCDE` test frames use bit-rate switching; the `0x201`
frame carries 64 bytes.

To test transmission from SavvyCAN, run:

```text
python savvycan_fd_peer.py receive
```

Then use SavvyCAN **Send Frames** to send a CAN FD frame. For example, use
standard ID `0x123`, enable CAN FD and BRS, select 12 data bytes, and send
`00 01 02 03 04 05 06 07 08 09 0A 0B`.

## Notes

SLCAN represents every byte with two ASCII characters, so its practical
throughput is lower than a binary `gs_usb` adapter. It is suitable for SavvyCAN
inspection and moderate CAN FD traffic, but sustained high bus utilization may
overflow the USB text stream.
