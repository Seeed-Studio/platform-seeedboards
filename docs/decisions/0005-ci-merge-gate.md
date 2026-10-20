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

2. **Per-board demo matrix** — every board ships with multiple demos,
   and CI builds all of them:
   - mandatory, per board: `blink` (GPIO), `uart` (console), and one
     framework-canonical sample (e.g. `ble` for zephyr boards, `wifi`
     for esp);
   - per family, at least one board exercising: each upload protocol
     the family enables, each debug tool injection it implements, and
     each fix it carries (a board with fixes must have a demo that
     builds ONLY because the fix applied — USB CDC for the STM32C5
     overrides, XSPI flash for the flash overrides);
   - demos live under `examples/<board-id>/<demo>/` (board-grouped so
     discovery is by declared framework, never directory naming).
   The blink-only CI of the predecessor is explicitly rejected: demos
     are regression contracts, not decoration.

3. **Cross-family guard**: any PR touching `platform.json` (any package
   pin) or a shared gate runs the FULL matrix — every family, every
   demo. This is the only reliable detector of single-slot package
   collisions (ADR-0002).

4. **Workflows** (mirroring the gates, run on push/PR):
   - `ci-verify`: offline gates — pytest, `verify_boards.py`,
     `verify_families.py` (registry/zero-string checks),
     `verify_routing.py` (zephyr chain + fixes), `pio boards` smoke.
   - `build-<framework>-examples` (one per declared framework):
     discovers demos by the `framework =` line, builds every env
     through the local-checkout override.
   - PR template: Why / What Changed / Validation.

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
