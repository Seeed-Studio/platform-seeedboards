# nPM1300 power sequencing on xiao nrf54lm20a/b (charger before LDO1, no power_en)

Status: implemented

## Context

The nPM1300 VBUS input current limit is 100 mA from power-on reset until the
npm13xx charger driver raises it to `vbus-limit-microamp` during its init
(`CONFIG_SENSOR_INIT_PRIORITY`, default 90). LDO1's soft-start inrush exceeds
100 mA, so enabling LDO1 inside the default nPM13xx regulator init window
(priorities 85/86) trips the PMIC overcurrent protection and the board
power-cycles in a loop. The charger driver is also gated behind `if SENSOR`,
so builds without `SENSOR=y` never raise the limit at all — with no build
warning (see GitHub issue #81 and PRs #82/#83).

Separately, the board dtsis carried a ghost `power_en` node: P1.12 is not
connected on either schematic, yet `regulator-fixed` + `regulator-boot-on`
drove the floating pin high on every boot. Upstream Zephyr removed it from
xiao_nrf54lm20b (zephyr#117551, commit 0e110df1d); the 20a upstream PR is
still pending.

## Decision

Board-level, in `Kconfig.xiao_nrf54lmXX` and the `*-common.dtsi` of both
boards (mirrors the `nrf93m1dk` precedent):

1. `SENSOR`/`REGULATOR` default y for cpuapp non-MCUboot images, so the
   charger is always compiled in.
2. `REGULATOR_NPM13XX_COMMON_INIT_PRIORITY=91` and
   `REGULATOR_NPM13XX_INIT_PRIORITY=92` — both after the charger at 90.
3. LDO1 carries `regulator-boot-on` + `regulator-allowed-modes`
   (`NPM13XX_LDSW_MODE_LDO`), so the rail comes up with the kernel and
   samples no longer hand-roll `regulator_enable()`.
4. The ghost `power_en` node is deleted from both boards; samples' manual
   power-up code, stale `/delete-property/` overlays and settle delays were
   removed with it.
5. nrf54lm20a additionally enables `&vregusb` (20b already did): the USB
   stack references that supply as a device once REGULATOR is on, and a
   REGULATOR=y build fails at link without it.
6. IMU samples keep `zephyr,deferred-init` and the `device_init()` dance:
   sensor init still runs at 90, before the rail at 92.

## Alternatives considered

- Per-sample `regulator_enable()` (the old state): scattered boilerplate,
  invisible failure modes, every new sample repeats it. Deleted.
- Moving `CONFIG_SENSOR_INIT_PRIORITY` below the regulators instead:
  rejected — it reorders every sensor on the board; nrf93m1dk moves the
  consumer, not the provider.
- `regulator-always-on` instead of `regulator-boot-on`: rejected — it would
  weld the rail on and remove the low-power opt-out (zephyr-lowpower's
  overlay deletes boot-on for exactly that reason).

## Consequences

- A prj.conf that sets `CONFIG_SENSOR=n` overrides the board default,
  compiles the charger out and silently reintroduces the 100 mA window with
  the rail still enabled — do not trim SENSOR on these boards.
- Non-IMU apps now link the charger and LSM6DSL stack (~10 KB) and the IMU's
  boot-time WHO_AM_I probe at 90 fails benignly until a deferred-init
  overlay or `device_init()` call probes it after the rail is up. A
  board-level `zephyr,deferred-init` on the IMU is the known follow-up.
- The 91/92 ordering and LDO1 block are duplicated across the two board
  dirs — keep them in sync; the values are load-bearing.
- Hardware validation: 20b verified on-device (gesture sample streams
  predictions); 20a is build-verified only.
