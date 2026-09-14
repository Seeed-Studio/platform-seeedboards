# XIAO nRF54LM20A V2 — blink + USB CDC console

Blinks the on-board green LED and prints a line to the USB CDC ACM console
on every toggle. On the V2 board the console is the nRF54 **native USB**
CDC ACM device (`zephyr,console = &cdc_acm_uart`): the V1 SAMD11 USB-UART
bridge is gone, so no wiring or bridge firmware is involved — connect the
USB-C connector and open the serial monitor.

## Build / flash / monitor

```console
pio run -e seeed-xiao-nrf54lm20a-v2 -t upload
pio device monitor -e seeed-xiao-nrf54lm20a-v2
```

`upload` signs the image with the factory Ed25519 key (`zephyr.signed.bin`),
touches the app CDC port at 1200 bps (VID `0x2886`, PID `0x8068`) so the
board reboots into the USB firmware loader, and uploads over MCUmgr.

## Expected output

```console
XIAO nRF54LM20A V2 blink + USB CDC ACM console ready
toggle 0
toggle 1
...
```

See [`../zephyr-dfu-recovery/`](../zephyr-dfu-recovery/) for a tour of the
three USB DFU recovery paths.
