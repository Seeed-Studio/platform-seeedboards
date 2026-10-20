# ADR-0004: Upstream reuse decision tree (amended) and validation tiers

## Context

The architecture handbook's reuse ladder (package pin / import /
SConscript+hooks / fork) is directionally right but the predecessor's
implementation proved two gaps: (a) SConscript delegation to upstream
build scripts only works when the script ships INSIDE a framework
package (arduino-pico's tools/platformio-build.py, Zephyr's
scripts/platformio/platformio-build.py) — a platform's own builder/
tree is the platform's build engine and must be adapted into the
family layer; (b) some families have NO upstream at all (SiLabs
Arduino: the only implementation is the predecessor's own). And the
"verify with pio run + upload" step is unaffordable as a per-change
gate — hardware is the slowest, scarcest validator.

## Decision

1. Reuse ladder (each rung keeps the main repo copy-free when it
   applies, and names the exception when it does not):

   | Need | Mechanism | Constraint |
   | --- | --- | --- |
   | Package version/source | platform.json pin | ADR-0002 single-slot rule |
   | Platform.py meta-logic | import upstream function, call + delta | only if upstream exposes importable functions |
   | Build flow, script in framework package | SConscript delegation + hooks | the happy path (arduino-pico, Zephyr) |
   | Build flow, platform's own builder | **adapt into families/ (copy once, own it)** | track upstream by re-diffing on refresh; never pretend to delegate |
   | Framework package content gap | board-directory fixes (ADR-0003) | never edit the package cache ad hoc |
   | No upstream exists | build in the family layer | document provenance; track the closest upstream for cadence |

2. Validation tiers — every change climbs as high as it can afford:
   - **T0 offline** (seconds, every commit): pytest + verify gates +
     `pio boards` smoke. Includes grep-style gates (zero-string
     routing, fixes/baseline correspondence).
   - **T1 build** (minutes, any behavior change): affected boards
     through the local-checkout override, clean build, fresh platform
     cache.
   - **T2 matrix** (per milestone / package-pin change): at least one
     board per consuming family, three frameworks when touched.
   - **T3 hardware** (deliberate, never silent): upload/debug with
     device evidence; otherwise stated "not performed".

## Consequences

- "Copy-free" is a default with two honest exceptions, both documented
  per family, instead of an aspiration that quietly rots into drift.
- Validation cost scales with blast radius; no change ships on T3
  evidence it doesn't need, and no behavior change ships without T1.

## Validation

The predecessor's whole timeline is the evidence: every catch in it
(ldscript regression, stub-package crash, toolchain slot collision)
was caught at T0/T1, never by hardware.

## Related files

- `docs/architecture.md` (decision tree section)
- `scripts/ci/` (gates, to be implemented)
