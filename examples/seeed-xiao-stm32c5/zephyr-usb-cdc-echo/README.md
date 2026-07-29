# XIAO STM32C5 USB CDC Echo 1M

This sample tests the USB-C virtual serial port on XIAO STM32C5.

## Pin Meaning

- PA11 is USB DM / D-
- PA12 is USB DP / D+
- These pins carry USB Full Speed differential signaling.
- They are not hardware UART TX/RX pins and should not be tested with a USB-to-TTL adapter.

## Test Method

1. Build and flash `firmware.uf2`.
2. Connect the board to the PC through USB-C.
3. Open the newly enumerated USB CDC COM port at `1000000` baud, 8N1.
4. Type or send ASCII data.
5. Every received byte should be echoed back immediately.

The `1000000` baud setting is the USB CDC ACM line-coding value reported by the host. The physical PA11/PA12 USB bus still uses USB Full Speed signaling.

The sample prints a heartbeat every 5 seconds. The heartbeat includes `dtr`,
`baud`, `rx`, `tx`, and `drop`. If `dtr=0`, the host terminal did not assert
DTR; echo is still handled by the USB CDC interrupt path.

Do not open this port at `1200` baud during the echo test, because the board keeps the UF2 1200-bps bootloader trigger enabled.
