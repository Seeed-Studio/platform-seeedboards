# gs_usb CAN FD 2 Mbit/s Test Guide

## Test conditions

- Two XIAO STM32C5 boards flashed with this gs_usb firmware
- Both adapters connected to the same CANH, CANL, and GND
- 120-ohm termination at each physical end of the bus
- 500 kbit/s nominal bitrate on both nodes
- 2 Mbit/s CAN FD data bitrate on both nodes

## Python test

```text
python -m pip install python-can python-can-candle
python canfd_2m_test.py receive --channel 1
python canfd_2m_test.py send --channel 0
```

The sender transmits 12-byte and 64-byte CAN FD BRS frames. The receiver prints
the frame ID, length, FD flag, BRS flag, and complete payload.

For a single-board controller loopback test:

```text
python canfd_2m_test.py loopback --channel 0
```

The test passes only when every transmitted frame is received with the expected
identifier, payload, CAN FD flag, and BRS flag.

## Troubleshooting

- TX errors: confirm another active node is present to acknowledge the frame.
- No BRS frames: verify that both nodes use a 2 Mbit/s data-phase bitrate.
- Bus-off: correct the bitrate or wiring, then reconnect the adapter.
