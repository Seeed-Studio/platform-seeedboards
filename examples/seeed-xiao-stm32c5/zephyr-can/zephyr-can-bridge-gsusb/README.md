# XIAO STM32C5 — gs_usb / CANnectivity bridge (firmware A)

Turns the XIAO STM32C5 into a **native SocketCAN** USB-CAN adapter using the
[CANnectivity](https://github.com/CANnectivity/cannectivity) gs_usb device
class (vendored at `zephyr/modules/cannectivity/`, pinned v1.4.0).

On Linux the kernel `gs_usb` host driver **auto-binds** VID `0x1209`:PID
`0xCA01` — plug in and you get a real `can0`:

```bash
modprobe gs_usb                  # usually already loaded / auto-loaded
ip link set can0 up type can bitrate 500000   # or the host tool sets it
candump can0                     # or python-can: can.Bus(interface='gs_usb', channel=0, bitrate=500000)
```

python-can reaches it cross-platform via the `gs_usb` interface. CAN FD is
supported (up to the board's 8 Mbps data phase).

## Hardware
- FDCAN2 (RX=PB5 / TX=PB13), on-board transceiver (standby=PB14, managed by the
  CAN driver). `zephyr,canbus = &fdcan2` in the board DTS, so this example needs
  **no channel overlay** — CANnectivity auto-binds it.
- USB DRD Full-Speed (PA11/PA12).

## Build & flash
```bash
cd examples/seeed-xiao-stm32c5/zephyr-can-bridge-gsusb
pio run                 # build -> firmware.uf2
# flash: double-tap RESET, drag firmware.uf2 onto the XIAOC5BOOT volume
```
This firmware owns the USB device stack, so the CDC 1200-bps UF2 trigger does
**not** apply — use the double-tap RESET method (or `pio run -t upload` which
auto-detects; if the 1200-bps touch fails, double-tap RESET manually).

## How it's wired
- `zephyr/modules/cannectivity/` — vendored CANnectivity module (gs_usb class +
  binding + module.yml). Discovered via `ZEPHYR_EXTRA_MODULES`; see the
  generalized module-copy block in `builder/frameworks/zephyr.py`.
- `src/{main.c,usb.c,cannectivity.h}` — copied from CANnectivity's app.
- `zephyr/Kconfig` — CANnectivity app Kconfig (provides `CANNECTIVITY_*`).
- `zephyr/app.overlay` — just the `gs_usb0` node.
- Optional features (LED, HW timestamp, termination, DFU-app) are OFF; to enable,
  copy the matching `app/src/*.c` and turn on the Kconfig.
