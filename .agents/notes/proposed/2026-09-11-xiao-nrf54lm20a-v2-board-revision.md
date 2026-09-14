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
| `Kconfig.defconfig` | revision-gated `ROM_START_OFFSET` / `BOOTLOADER_MCUBOOT` / CDC ACM serial defaults (VID `0x2886`, PID `0x8068`, product `XIAO_NRF54LM20A_V2`) |
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
no `_1_0_0` files and no bare `.overlay`, so the V1 input file set is
bit-identical to before. The revision-gated Kconfig block is inert for
revision 1.0.0, and `cpuflpr` builds are untouched (revision files are
cpuapp-qualified).

### Board-directory-root `mcuboot.conf` / `mcuboot.overlay`

These files are **not** revision-gated, so they also sit in front of V1
builds. They are only consumed by MCUboot child-image flows (NCS sysbuild);
a V1 user explicitly enabling MCUboot gets a config that does not match the
V1 partition layout — an unsupported usage today (unsigned app, mismatched
slots), so no supported behavior changes. The PlatformIO build never builds
the MCUboot child image at all (it only signs the application with imgtool
via the `mcuboot-image` target; the bootloader binary is the factory
`USB_DFU.hex`), so for PIO these files are inert documentation.

### Deliberate scope boundary: no NCS sysbuild zero-config for V2 here

20B's `Kconfig.xiao_nrf54lm20b`/`Kconfig.defconfig` `if MCUBOOT` blocks and
`Kconfig.sysbuild` (PR #86) make a plain NCS `west build` reproduce the
factory signing. **Mirroring that for `xiao_nrf54lm20a@2.0.0` is not part
of this change**, for a structural reason: 20B's mcuboot child fits 24 KiB
because the 20B base defconfig *omits* `SERIAL`/`CONSOLE` (letting
`if MCUBOOT default n` win), while the shared 20A V1 base defconfig sets
`CONFIG_SERIAL=y` explicitly and cannot change (V1 isolation). An explicit
fragment value beats every Kconfig default, so the 20B trick is not
directly transferable; it needs its own design (e.g. per-image
`child_image/mcuboot.conf` guidance or a base defconfig restructure). The
NCS V2 bootloader pipeline is owned by the firmware team's test-plan
repository, which already builds it with its own sysbuild project.

### Implementation notes (verified against code, 2026-09-14)

- `builder/frameworks/zephyr.py` `_board_copy_mode()` is unconditional
  **refresh** (whole board directory re-copied every build), so new/changed
  revision files propagate to the framework package automatically; the
  `missing-only` behavior mentioned in `_patch_cdc_vidpid` is historical.
  `_patch_cdc_vidpid` stays 20B-only: V2's PID lives in its own
  `Kconfig.defconfig`, which the refresh copy delivers.
- The V2 overlay omits `&vregusb { status = "okay"; }` — the base
  `nrf54lm20a_cpuapp_common.dtsi` already enables it (PR #82).
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
- Hardware (1200-bps touch, button entry, loader enumerating `2886:0068`):
  **not performed** until V2 prototypes are available.
