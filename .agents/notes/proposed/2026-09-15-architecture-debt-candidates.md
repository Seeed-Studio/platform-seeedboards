# Architecture debt candidates (post board-routing refactor)

Status: proposed

## Context

The board-routing consolidation and fixes-v2 refactor landed
(see the two implemented notes from 2026-09-15). The layering now holds:
board facts in manifests, one dispatch source, directory-convention
fixes with content gating, offline gates enforcing consistency. Three
residuals were identified during the work and deliberately left in
scope-limited place; this note records them so the next rounds have a
mandate and an order.

## Proposal (ordered candidates)

1. **zephyr.py's `_patch_platformio_*` family should migrate into the
   fixes mechanism.** Five functions string-patch the framework
   package's own `scripts/platformio/platformio-build.py` (path
   handling, object naming, framework package name, MCUboot signing,
   prebuilt lib linking, extra modules). Conceptually identical to
   fixes -- modifications of upstream files -- but without directory
   registration, baseline gating, or upgrade drift detection. Migrating
   them gives the same "framework upgraded -> loud re-evaluation"
   behavior the five STM32C5 fixes already have.
2. **platform.py's ~150 lines of ESP tool assembly belong in
   platform_cfg/esp_cfg.py.** `_prefer_local_esp_tools`,
   `_prepare_esp_tools`, `_ensure_esp_installer`,
   `_expand_and_link_esp_tool`, `_ensure_esptoolpy_runtime_dependencies`
   run inside the `configure_default_packages` window that esp_cfg
   already owns. Moving them keeps platform.py a pure lifecycle shim.
3. **Leaf hardcodes in family scripts** (each small, family-owned, so
   not layering violations): nrf_build.py CDC VID/PID constants and the
   missing nrf54lm20b OpenOCD upload branch (the hardware-dependent
   item deferred since P3.3), stm32_build.py `XIAOC5BOOT` default
   volume label, silabs VARIANT_DIR hardcoding `xiao_mg24` instead of
   reading `build.variant`.

## Alternatives considered

- Doing nothing: all three are documented and gate-visible; but (1) is
  the same fragility class the fixes mechanism was built to remove.

## Consequences

- (1) removes the last ungated mutation of framework-package files;
  (2) completes the entry-layer/family-layer split; (3) is polish.
- Each candidate is independently shippable and revertible; none
  changes user-facing contracts.

## Validation

Each candidate lands with its own offline-gate updates and the
representative build matrix from the routing note's evidence pattern
(arduino-blink for family dispatch, zephyr set for framework paths).

## Related files

- [`board-family-routing-single-source`](../implemented/2026-09-15-board-family-routing-single-source.md)
- [`zephyr-fixes-board-dir`](../implemented/2026-09-15-zephyr-fixes-board-dir.md)
- [`builder/frameworks/zephyr.py`](../../../builder/frameworks/zephyr.py)
- [`platform.py`](../../../platform.py)
