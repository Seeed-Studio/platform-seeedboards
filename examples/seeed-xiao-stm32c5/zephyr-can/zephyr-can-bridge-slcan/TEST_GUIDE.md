# SavvyCAN CAN FD Test Guide

## Requirements

- Two XIAO STM32C5 boards flashed with this firmware
- CANH-to-CANH, CANL-to-CANL, and GND-to-GND wiring
- Correct 120-ohm termination at both ends of the bus
- SavvyCAN V220 or later
- Python 3 and pyserial for the peer script

## SavvyCAN board

Create a LAWICEL / SLCAN Serial connection using these settings:

- Serial port: the first XIAO CDC port
- Serial baud rate: 115200
- Nominal CAN bitrate: 500000 bit/s
- CAN FD: enabled
- CAN FD data bitrate: 2000000 bit/s
- Listen Only: disabled
- Enable Bus: enabled

Enable the device console while connecting. SavvyCAN V220 may send only `C`,
`S6`, and `O` even when CAN FD is selected. This firmware treats that sequence
as 500 kbit/s nominal and 2 Mbit/s data by default. If SavvyCAN sends `Y2`, the
explicit data-rate command is accepted as well.

## Peer board sends to SavvyCAN

Leave SavvyCAN connected to the first board and run the following command on the
second board's host port:

```text
python savvycan_fd_peer.py send --port COM4

# Linux example
python savvycan_fd_peer.py send --port /dev/ttyACM1
```

Omit `--port` to select the first available Seeed CDC port. SavvyCAN Bus Traffic
must show IDs `0x200`, `0x201`, and `0x1ABCDE`. ID `0x200` is a 12-byte FD frame
without BRS. ID `0x201` is a 64-byte FD frame with BRS. ID `0x1ABCDE` is an
extended 12-byte FD frame with BRS.

The script reports only frames acknowledged by the SLCAN firmware. The count
printed by the script should match the new frames captured by SavvyCAN when all
three frame IDs are enabled in the frame filter.

## SavvyCAN sends to the peer board

Run:

```text
python savvycan_fd_peer.py receive --port COM4

# Linux example
python savvycan_fd_peer.py receive --port /dev/ttyACM1
```

In SavvyCAN Send Frames, create a standard frame with ID `0x123`, enable CAN FD
and BRS, select 12 data bytes, and use this payload:

```text
00 01 02 03 04 05 06 07 08 09 0A 0B
```

The peer terminal should print a line beginning with `b1239`. Lowercase `b`
means standard CAN FD with BRS, and DLC `9` means 12 bytes.

## Troubleshooting

- No serial port: use a data-capable USB cable and confirm the application, not
  the UF2 bootloader, is running.
- Port busy: close SavvyCAN or any serial monitor that owns that exact port.
- No traffic: verify both nominal and data bitrates on both boards, CANH/CANL,
  common ground, and termination.
- Only 40 of 60 frames visible: enable all IDs in SavvyCAN Frame Filtering. The
  test sends three IDs, so hiding one ID removes one third of the frames.
- TX errors or repeated frames: a CAN transmitter requires another active node
  to acknowledge the frame.
- Missing 64-byte frames: confirm CAN FD is enabled and SavvyCAN is V220 or later.
