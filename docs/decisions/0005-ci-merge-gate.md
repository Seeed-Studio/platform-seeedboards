# ADR-0005: CI gate policy — a family merges only through green CI

## Context

The predecessor's discipline was "commit only after full local testing"
— effective but self-enforced. The recurring failure mode was partial
validation: a family passed its own builds while a shared-package change
silently broke another family (the toolchain-range bump that moved samd
and renesas onto an untested GCC default; the stub-package collision
that emptied bin/cmake for the Zephyr builds). A unified platform's CI
must make cross-family breakage visible before merge, and board coverage
must be broad enough that per-family claims mean something: one blink
per board is a smoke, not a validation.

## Decision

1. **Merge gate**: a family PR merges only when the full CI matrix for
   that family is green. CI is the authority; local runs are the fast
   pre-loop. PR bodies record what was run locally and what is left to
   CI.

2. **Per-board demo matrix** — every board/framework pair has at least one
   demo env; the Arduino/Zephyr smoke projects carry `blink` + `uart`,
   ESP-IDF carries `blink`. Before release, each family still needs at
   least one demo exercising each upload protocol, debug-tool injection,
   and fix it ships (a board with fixes must have a demo that builds ONLY
   because the fix applied — USB CDC for the STM32C5 overrides, XSPI flash
   for the flash overrides).
   - demos live under `examples/<demo>/platformio.ini` (demo-grouped: one
     file carries all boards of a framework). Board-specific hardware
     samples may live under `examples/<board-id>/<sample>/`; discovery is
     by the `framework =` line, never directory naming.
   **Amendment 1 (2026-10-22)** — the v3 automated gate enforces and builds
   the one-env-per-board/framework minimum (`verify_examples.py` plus the
   per-framework workflows). The tree now ships canonical demos:
   `arduino-wifiscan` (ESP WiFi), `arduino-usb-keyboard` (ESP32-S3 USB HID),
   `arduino-rmt-blink` (ESP32-S3 RMT), `zephyr-ble`, `zephyr-adc`,
   `zephyr-gpio`, `zephyr-button`, `zephyr-pwm`, `zephyr-battery`,
   `zephyr-imu`, `zephyr-tapwake`, `zephyr-gps`, `zephyr-lowpower`,
   `zephyr-npm1300-register-read`, `zephyr-rfsw`, `zephyr-ble-lbs`,
   expansion-base RTC/OLED, both e-paper sizes, and the STM32C5 CAN
   GPIO-reuse sample. Remaining per-protocol, per-debug, per-fix and hardware
   samples stay release criteria, tracked in the roadmap. This amendment
   narrows the automated merge gate, not the release bar. The predecessor's
   blink-only CI remains rejected.

3. **Cross-family guard**: any PR touching `platform.json` (any package
   pin) or a shared gate runs the FULL matrix — every family, every
   demo. This is the only reliable detector of single-slot package
   collisions (ADR-0002).

4. **Workflows** (mirroring the gates, run on push/PR):
   - `ci-verify`: offline gates — pytest, `verify_boards.py`,
     `verify_core.py` (zero-string routing), `verify_zephyr_routing.py`
     (zephyr chain + fixes), `verify_platform.py` (family/package/debug
     runtime contract), `verify_examples.py` (demo matrix + URL pin),
     `verify_workflows.py` (YAML/permissions/branch), and the platform-load
     smoke.
   - `build-<framework>-examples` (one per declared framework):
     discovers demos by the `framework =` line, builds every env
     through the local-checkout override.
   - PR template: `.github/pull_request_template.md` — Why / What Changed /
     Validation.

5. **Gate tests**: every verify-gate rule ships with a passing sample
   and a failing counterexample under `tests/` (fixtures); a rule
   without both is not ready to gate CI. Snapshots inside gates
   (board id set, family vocabulary) are deliberate forcing functions
   — the failure message says so.

## Consequences

- Adding a family costs: the family class, boards, AND the demo matrix —
  the matrix is part of the definition of done, not a follow-up.
- CI time grows with the platform; the per-framework workflow split and
  path filters keep unrelated PRs cheap.
- The registry and zero-string constraints are machine-enforced (grep
  gates), so the handbook's self-check cannot rot into ritual.

## Validation

Predecessor evidence: every serious catch in its timeline (ldscript
regression, stub-package crash, toolchain slot collision, CI-wrapper
URL drift) was caught by exactly these tiers — the ADR formalizes them
as the merge authority rather than local habit.

## Related files

- `docs/architecture.md` §6 (validation tiers), `AGENTS.md` (loop)
- `scripts/ci/`, `tests/`, `.github/workflows/` (to be implemented)
