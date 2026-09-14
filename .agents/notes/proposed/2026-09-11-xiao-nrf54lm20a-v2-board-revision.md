# XIAO nRF54LM20A V2.0 as a board revision (not a separate board)

Status: proposed

## Context

XIAO nRF54LM20A revision 2.0 (issue #84, ECN on the same SKU) reuses the
XIAO nRF54LM20B PCB with the nRF54LM20A SoC: the SAMD11 USB-UART debugger is
deleted (nRF54 native USB CDC ACM replaces it), the SPI NOR becomes the
128 Mbit PY25Q128HA, and the flash layout moves to the shipped MCUboot
firmware-loader scheme. V1.0 support must stay 100% unchanged.

## Proposal

Model V2.0 as a **board revision** in the existing `xiao_nrf54lm20a` board
directory (`board.yml` revisions `1.0.0` default + `2.0.0`), with all V2
deltas in revision-suffixed files:

| File | Role |
| --- | --- |
| `board.yml` | revision block (the anchor; `runners:` untouched) |
| `…_cpuapp_2_0_0.overlay` | chosen → `&cdc_acm_uart`, `boot_mode0` (GPREGRET1 retention), `mcuboot-button0` alias, 20B load caps (16 pF LFXO), partition delete/re-add (mcuboot 24K / image-0 1784K / image-1 116K / storage 16K, no NS mirrors), `py25q64` → `py25q128ha` swap, BUCK2 comment, nPM1300 LDO2 node |
| `…_cpuapp_2_0_0_defconfig` | `CONFIG_BOOTLOADER_MCUBOOT=y` |
| `…_cpuapp_2_0_0.yaml` | `xiao_nrf54lm20a@2.0.0/nrf54lm20a/cpuapp`, flash 1784 |
| `Kconfig.defconfig` | revision-gated `ROM_START_OFFSET` / `BOOTLOADER_MCUBOOT` / `if MCUBOOT` serial-off block / CDC ACM serial defaults (VID `0x2886`, PID `0x8068`, product `XIAO_NRF54LM20A_V2`) |
| `Kconfig.xiao_nrf54lm20a` | revision-gated `if MCUBOOT` firmware-loader entrance + 24K size levers (20B mirror) |
| `Kconfig.sysbuild` | new: revision-gated NCS sysbuild zero-config defaults (20B mirror) |
| `mcuboot.conf` / `mcuboot.overlay` | record of the factory loader configuration (see below) |

PlatformIO side: new board id `seeed-xiao-nrf54lm20a-v2`
(`build.zephyr.variant = xiao_nrf54lm20a@2.0.0/nrf54lm20a/cpuapp`,
`build.mcu = nrf54lm20a`, same bootloader/signing block as 20B), mapped in
`platform.py` to the **same** `xiao_nrf54lm20a` board directory and the
`framework-zephyr-nrf54lm20` package. The 1200-bps DFU upload path keys its
CDC identities by board id (`_BOARD_APP_CDC_VIDPID` /
`_BOARD_LOADER_CDC_VIDPIDS` in `builder/board_build/nrf/nrf_build.py`,
20B values as the fallback for unknown boards), so uploading to V2 can
never grab a 20B loader port and vice versa.

### USB CDC identities

| Identity | VID:PID | Owned by |
| --- | --- | --- |
| V2 running app | `2886:8068` | board `Kconfig.defconfig` (`CDC_ACM_SERIAL_PID`) |
| V2 DFU loader | `2886:0068` | prebuilt factory `USB_DFU.hex` (firmware-team deliverable, not in this repo) |

If the shipped loader enumerates a different PID, only the
`_BOARD_LOADER_CDC_VIDPIDS` entry changes.

## Alternatives considered

- **Separate board directory** (`xiao_nrf54lm20a_v2`): rejected — it
  duplicates ~1.5 K lines of unchanged V1 board definition, doubles the
  framework copy, and splits sample overlays (`boards/
  xiao_nrf54lm20a_nrf54lm20a_cpuapp.overlay` in samples matches the
  revision-less board name, so existing overlays automatically apply to
  V2; a separate directory would break that).
- **V2 as a pure overlay in each sample**: rejected — the hardware delta is
  the board's, not the application's; 25+ samples would each carry a copy.

## Consequences

### V1 isolation

V1 builds resolve to the default revision `1.0.0`; the directory contains
no `_1_0_0` files and no bare `.overlay`, and every V2-only Kconfig block
is gated on `BOARD_REVISION_2_0_0`, so the revision-gated inputs cannot
reach a V1 build. Two files shared by V1/V2 did change, both
value-preserving for V1:

- the base `xiao_nrf54lm20a_nrf54lm20a_cpuapp_defconfig` no longer sets
  `SERIAL/CONSOLE/UART_CONSOLE` explicitly (the 20B form, required for the
  mcuboot child); the identical values now come from the `if !MCUBOOT`
  defaults in `Kconfig.xiao_nrf54lm20a` — the resulting V1 `.config` is
  unchanged (verified by diffing the full `.config` before/after).
- `Kconfig.xiao_nrf54lm20a` gained the `!MCUBOOT` serial defaults and the
  revision-gated `if MCUBOOT` levers; for a V1 app build the only new
  effect is the serial trio defaulting to the same `y` it previously got
  from the defconfig.

`cpuflpr` builds are untouched (all revision files and serial defaults are
cpuapp-qualified/gated).

### Board-directory-root `mcuboot.conf` / `mcuboot.overlay`

These files are **not** revision-gated, so they also sit in front of V1
builds. They are only consumed by MCUboot child-image flows (NCS sysbuild);
a V1 user explicitly enabling MCUboot gets a config that does not match the
V1 partition layout — an unsupported usage today (unsigned app, mismatched
slots), so no supported behavior changes. The PlatformIO build never builds
the MCUboot child image at all (it only signs the application with imgtool
via the `mcuboot-image` target; the bootloader binary is the factory
`USB_DFU.hex`), so for PIO these files are inert documentation.

### NCS sysbuild zero-config (mirrors 20B, revision-gated)

NCS users build against this board directory too, so `west build -b
xiao_nrf54lm20a@2.0.0/nrf54lm20a/cpuapp` must produce a matching signed
image with zero per-application configuration — the same Thingy:53-style
model 20B got in PR #86. Mirrored from 20B, all gates include
`BOARD_REVISION_2_0_0` so V1.0 NCS builds keep their current behavior:

- `Kconfig.xiao_nrf54lm20a`: `if MCUBOOT && BOARD_REVISION_2_0_0` block
  with the firmware-loader entrance defaults and the 24 KiB size levers
  (LTO, no banners/malloc arena/system timer).
- `Kconfig.defconfig`: `if MCUBOOT` counter-block (SERIAL/CONSOLE/
  CLOCK_CONTROL `default n`) inside the revision-gated block, ahead of the
  `source` of `boards/common/usb/Kconfig.cdc_acm_serial.defconfig`.
- new `Kconfig.sysbuild`: bootloader/mode/signature choices,
  `PARTITION_MANAGER n`, `MCUBOOT_SIGNATURE_USING_KMU`,
  `BOOT_SIGNATURE_TYPE_PURE`.

Two structural fixes were required beyond the plain 20B copy:

1. **Sysbuild has no per-revision Kconfig booleans.** The auto-generated
   `config BOARD_REVISION_2_0_0 def_bool y` exists only in the per-image
   Kconfig context (generated `boards/Kconfig`); sysbuild sources the
   static `boards/Kconfig.v2` template and exposes `BOARD_REVISION` only
   as a string. `Kconfig.sysbuild` therefore synthesizes the boolean with
   the same preprocessor idiom `boards/Kconfig.v2` uses for board symbols:
   `BOARD_REVISION_NORMALIZED := $(normalize_upper,$(BOARD_REVISION))`
   followed by `config BOARD_REVISION_$(BOARD_REVISION_NORMALIZED)
   def_bool y`. Revision-less (V1.0) sysbuild builds produce an inert
   `BOARD_REVISION_` symbol that nothing references. No upstream board
   combines revisions with `Kconfig.sysbuild` yet (nrf54h20dk has both
   pieces but a single revision, so it does not need the gate).
2. **The V1 base defconfig's explicit serial trio blocked the mcuboot
   child.** `xiao_nrf54lm20a_nrf54lm20a_cpuapp_defconfig` set
   `CONFIG_SERIAL/CONSOLE/UART_CONSOLE=y` explicitly, and an explicit
   fragment value beats every Kconfig `default` — the child image
   inherited them, compiled `uart_console.c` against the CDC ACM node and
   failed to link (`undefined reference to __device_dts_ord`, USB stack
   off in MCUboot builds). 20B avoids this by *omitting* the trio from its
   base defconfig, so the 20A base defconfig now does the same (with the
   matching comment). V1.0 values are restored by new `if !MCUBOOT`
   `SERIAL/CONSOLE/UART_CONSOLE default y` defaults in
   `Kconfig.xiao_nrf54lm20a`, which the child skips — the 20B structure
   exactly. Verified value-preserving: the V1 `.config` is identical
   before/after the change.

Verified on NCS v3.3.0 (Zephyr 4.3.99): `west build -p always -b
xiao_nrf54lm20a@2.0.0/nrf54lm20a/cpuapp zephyr/samples/hello_world` with
zero per-app configuration builds both images — mcuboot child 22 364 B
(91% of the 24 KiB boot partition), application at `ROM_START_OFFSET
0x800` with `CDC_ACM_SERIAL_PID 0x8068`, Partition Manager off,
Ed25519/KMU signing, and `zephyr.signed.bin` + `dfu_application.zip`
artifacts.

### Implementation notes (verified against code, 2026-09-14)

- `builder/frameworks/zephyr.py` `_board_copy_mode()` is unconditional
  **refresh** (whole board directory re-copied every build), so new/changed
  revision files propagate to the framework package automatically; the
  `missing-only` behavior mentioned in `_patch_cdc_vidpid` is historical.
  `_patch_cdc_vidpid` stays 20B-only: V2's PID lives in its own
  `Kconfig.defconfig`, which the refresh copy delivers.
- The V2 overlay restates `&vregusb { status = "okay"; }` even though the
  base `nrf54lm20a_cpuapp_common.dtsi` already enables it (PR #82), so the
  V2 delta stays self-contained and line-comparable with 20B's base dtsi.
- One intentional divergence from 20B's DT: the `vsys_3v3`/BUCK2 regulator
  node stays present for V2 (the V1 base defines it always-on; 20B's base
  has no such node and relies on the PMIC hardware default). Deleting it
  from V2 would match 20B more literally but risks the always-on system
  rail if the hardware default assumption is wrong; the node is harmless
  and documents the V2 system rail.
- Partition/NOR replacement uses top-level `/delete-node/ &label;` followed
  by re-adding the nodes, the in-tree `scobc_a1_1_0_0.overlay` idiom.
- The upload wiring needs no board gating: `DfuUpload1200` attaches through
  `upload.protocol = nrfutil-mcumgr`, and the OpenOCD flashing adapter
  branches on `build.mcu == nrf54lm20a`, which the V2 manifest sets.
- `zephyr/modules/xiao_dfu_reset/Kconfig` defaults to `y` for the V2
  revision as well; the module is provisioned board-agnostically by
  `_provision_xiao_dfu_module`.

## Validation

- V1 regression: `pio run -d examples/zephyr-blink -e seeed-xiao-nrf54lm20a`
  — `zephyr.dts` keeps the V1 partitions + `&uart20` console, no
  `cdc_acm_uart`/LDO2/`boot_mode0`; `.config` has `BOARD_REVISION_1_0_0=y`
  and no `BOOTLOADER_MCUBOOT`/`CDC_ACM_SERIAL_*`/`XIAO_DFU_RESET`.
- V2 correctness: `pio run -d examples/zephyr-blink -e seeed-xiao-nrf54lm20a-v2`
  — `BOARD=xiao_nrf54lm20a@2.0.0/...`, 20B partition set, CDC chosen,
  `CDC_ACM_SERIAL_PID=0x8068`, `XIAO_DFU_RESET=y`, `zephyr.signed.bin`
  produced.
- 20B regression after the VID/PID refactor (error-message strings must be
  byte-identical for the 20B board).
- NCS zero-config smoke (v3.3.0, Zephyr 4.3.99), **passed**:
  `west build -p always -b xiao_nrf54lm20a@2.0.0/nrf54lm20a/cpuapp
  zephyr/samples/hello_world` → mcuboot child 22 364 B ≤ 24 KiB with the
  size levers, `SB_CONFIG_BOOTLOADER_MCUBOOT=y`,
  `SB_CONFIG_PARTITION_MANAGER` off, app `ROM_START_OFFSET=0x800` +
  `CDC_ACM_SERIAL_PID=0x8068`, `zephyr.signed.bin` +
  `dfu_application.zip`. NCS V1.0 regression (`west build -p always -b
  xiao_nrf54lm20a/nrf54lm20a/cpuapp zephyr/samples/hello_world`), also
  **passed**: `SB_CONFIG_BOARD_REVISION="1.0.0"` with no
  `SB_CONFIG_BOOTLOADER_MCUBOOT` (the sysbuild gate does not leak to V1)
  and `SERIAL/CONSOLE/UART_CONSOLE=y` unchanged.
- Hardware (1200-bps touch, button entry, loader enumerating `2886:0068`):
  **not performed** until V2 prototypes are available.
