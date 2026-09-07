# XIAO STM32C5 gs_usb CAN FD Bridge

This firmware turns the XIAO STM32C5 into a native USB-to-CAN/CAN FD adapter
using the CANnectivity `gs_usb` device class. On Linux, the kernel `gs_usb`
driver registers the board directly as a SocketCAN interface such as `can0`.

The CAN FD examples use:

- Nominal/arbitration bitrate: 500 kbit/s
- Data-phase bitrate: 2 Mbit/s
- Bit-rate switching: enabled for the CAN FD test frames

The 2 Mbit/s value is the CAN FD data-phase rate, not the nominal arbitration
rate. Every active node on the test bus must use the same two rates.

## Hardware

- CAN controller: on-board FDCAN2 (PB5 RX / PB13 TX)
- CAN transceiver standby: PB14, controlled by the Zephyr CAN driver
- USB interface: native `gs_usb`, VID `0x1209`, PID `0xCA01`
- Wiring: CANH to CANH, CANL to CANL, and GND to GND
- Termination: 120 ohm at each physical end of the bus

## Build and flash

```text
pio run
```

Double-tap RESET to open the `XIAOC5BOOT` drive, then copy:

```text
.pio/build/seeed-xiao-stm32c5/firmware.uf2
```

The firmware uses a vendor-class USB interface and does not expose CDC ACM, so
the 1200-baud serial reset method is not available.

## Cross-platform Python test

Install the CAN FD-capable candle backend:

```text
python -m pip install python-can python-can-candle
```

Connect two flashed boards to the same CAN bus. Run the receiver for one board:

```text
python canfd_2m_test.py receive --channel 1
```

Run the sender for the other board:

```text
python canfd_2m_test.py send --channel 0
```

The script sends ID `0x200` with 12 bytes and ID `0x201` with 64 bytes. Both
frames use CAN FD with BRS and a 2 Mbit/s data phase. If channel numbering is
ambiguous, pass each board's USB serial number with `--serial-number`.

For a single-board controller loopback test, run:

```text
python canfd_2m_test.py loopback --channel 0
```

Loopback verifies the USB path, firmware, and CAN controller without requiring
a second node. It does not verify the external transceiver or physical CAN bus.
