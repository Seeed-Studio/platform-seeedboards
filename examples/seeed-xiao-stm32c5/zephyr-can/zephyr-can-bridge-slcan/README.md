# XIAO STM32C5 — SLCAN (Lawicel) USB<->CAN bridge

Turns the XIAO STM32C5 into a **USB-to-CAN adapter** speaking the Lawicel
**SLCAN** ASCII protocol over USB CDC ACM. One firmware, three host tools:

| Host tool | How to connect |
|---|---|
| **python-can** (any OS) | `can.Bus(interface='slcan', channel='/dev/ttyACM0', bitrate=500000)` |
| **SavvyCAN** (any OS) | *Add Connection → Lawicel / SLCAN*, pick the board's COM/tty port |
| **SocketCAN** (Linux) | `slcand -o -s5 -c /dev/ttyACM0 can0 && sudo ip link set can0 up` |

> Classic CAN only in this build — Lawicel SLCAN has no standard CAN-FD framing.
> For CAN FD use the **gs_usb** firmware variant (firmware A, a.k.a. CANnectivity
> port) which gives a native SocketCAN interface and efficient binary FD frames.

## Hardware

- CAN controller: on-board **FDCAN2** (RX=PB5 / TX=PB13), classic mode here.
- Transceiver: on-board, standby = PB14 — managed automatically by the Zephyr
  CAN driver via the board's `can_phy0` `phys` binding (no manual GPIO needed).
- USB: the MCU's own USB DRD Full-Speed (PA11/PA12) → CDC ACM virtual serial.

Wire CANH/CANL (and a 120 Ω terminator as needed) to the board's CAN pins.

## Build & flash

```bash
cd examples/seeed-xiao-stm32c5/zephyr-can-bridge-slcan
pio run                       # build -> firmware.uf2
pio run -t upload             # UF2 upload (double-tap RESET, or auto 1200-bps touch)
```

## Bring-up sequence (SLCAN is request/response)

On power-up the CAN controller is **stopped** at a default 500 kbps. From the
host, send (CR-terminated):

```
S5        select 500 kbps   (S0..S8 presets: 10k/20k/50k/100k/125k/250k/500k/800k/1M)
O         go on-bus
t1238DEADBEEFCAFE   send std frame id=0x123, dlc=8, data=...
C         go off-bus
```

Success → `CR` (`\r`); error → `BEL` (`\x07`).
Received frames appear as `tiiildd...\r` (std) or `TiiiiiiiiLdd...\r` (ext).

## Implemented Lawicel subset

| Cmd | Action | Cmd | Action |
|---|---|---|---|
| `Sn` | set bitrate preset | `tiiildd` | TX std 11-bit |
| `O` | open (on-bus) | `TiiiiiiiiLdd` | TX ext 29-bit |
| `C` | close (off-bus) | `riiiL` / `RiiiiiiiiL` | TX RTR |
| `V` | version | `N` | serial number |
| `F` | flags | `Z`/`M`/`m`/`L`/`l` | accepted, no-op |

## TODO / next

- [ ] CAN-FD via a SLCAN-FD extension (or rely on the gs_usb variant for FD).
- [ ] Timestamp (`Z1`) — currently a no-op.
- [ ] Acceptance filtering (`M`/`m`) — currently accept-all.
- [ ] TX-drop accounting when the CDC ring backs up under CAN-FD burst load.
- [ ] Factor the CAN<->transport core into a shared `can_bridge` module reused
  by the gs_usb variant (firmware A).
