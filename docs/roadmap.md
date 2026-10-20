# Roadmap — implementation order

Each step is independently validatable; do not start a step before the
previous one is green. Every step ends with a commit (or commits) that
pass the validation tier shown.

| # | Deliverable | Validates | Tier |
| --- | --- | --- | --- |
| 1 | `families/base.py` — ChipFamily ABC + `__init_subclass__` registry + registry unit tests | ADR-0001 | T0 |
| 2 | Offline gates: `verify_boards.py`, `verify_families.py` (registry/zero-string grep), smoke; pytest suites with pass/fail fixtures per rule | ADR-0004 T0 | T0 |
| 3 | `platform.py` + `builder/main.py` zero-string core (empty registry path works, fails loudly on unknown family) | ADR-0001 | T0 + boards smoke |
| 4 | First family: **samd** (smallest, upstream exists, no package collisions) + board manifest + blink/uart demos | ADR-0001 + CI gate | T1 + CI |
| 5 | Family with a package collision: **esp** (brings stub-package machinery + the single-slot decision) | ADR-0002 | T2 (samd + esp) |
| 6 | Zephyr family + board dirs + **fixes mechanism** with baseline gate | ADR-0003 | T2 |
| 7 | Remaining families (rpi, renesas, silabs, nrf52) one at a time, each through its demo matrix | ADR-0005 | per-family CI |
| 8 | First release: full cross-family matrix, tag | everything | T2 |

Rules of the road while executing:

- Docs precede code for each step; amend the relevant ADR instead of
  deviating silently.
- A family is done when its **entire demo matrix** is green in CI
  (ADR-0005), not when blink passes locally.
- Any `platform.json` pin change re-runs the full matrix, even mid-step.
