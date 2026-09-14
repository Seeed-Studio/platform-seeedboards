# XIAO nRF54LM20A V2 — USB DFU recovery tour

The V2 board ships the same three-image recovery scheme as the XIAO
nRF54LM20B: an **MCUboot firmware-updater** bootloader (24 KiB) plus a **USB
MCUmgr loader** image in slot1 (116 KiB). Applications are signed with the
factory Ed25519 key (`--pure`) and updated over USB — an application can
never brick the board.

This demo prints a banner describing the recovery paths, blinks the blue
LED as a heartbeat, and logs a counter over the USB CDC ACM console.

## USB identities

| State | VID:PID | Notes |
| --- | --- | --- |
| Running application | `2886:8068` | the console/monitor port |
| DFU loader (slot1) | `2886:0068` | MCUmgr upload target |

## Update an application

```console
pio run -t upload
```

PlatformIO signs `zephyr.signed.bin` (imgtool, Ed25519 + `--pure`, 0x800
header), touches the application CDC port at 1200 bps, waits for the board
to reboot into the loader, and uploads over MCUmgr.

## The three DFU entry paths

1. **Automatic (1200-bps touch)** — `pio run -t upload` performs it for
   you. The `xiao_dfu_reset` module (on by default) watches the CDC ACM
   port; a 1200-bps line-coding request records the boot-mode in retained
   GPREGRET memory and cold-reboots into the loader.
2. **Manual (button)** — hold **BTN** (the back-pad button, P0.09) while
   pressing **RESET**; MCUboot detects the GPIO entrance and chains the
   loader.
3. **Empty slot** — with no valid application in slot0, MCUboot chains the
   loader by itself (`NO_APPLICATION` mode), so a crashed or erased app is
   always recoverable over USB.

## Hardware notes

- The bootloader/loader area (0x0–0x1E0FFF) is **not** written by USB DFU;
  only the application slot is updated. Do not program the loader area over
  USB — a debug probe (CMSIS-DAP/J-Link, external) is needed for that.
- Back-pad mapping on V2: `EX_RX`/`EX_TX` = uart20 (P1.10/P1.11), `LDO2` =
  nPM1300 LDO2 rail (off by default), `BTN` = button0 (P0.09).
