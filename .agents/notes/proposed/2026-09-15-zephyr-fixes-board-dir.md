# Zephyr fixes: directory convention (fixes v2)

Status: proposed

## Context

Since its introduction, local Zephyr framework fixes were registered in
`zephyr/fixes.yml` and dispatched by `builder/frameworks/zephyr_fixes.py`
to two pure executors (`zephyr_patch.py`, `zephyr_override.py`). The
mechanism works (STM32C5's five fixes are battle-tested) but carries
avoidable weight:

- a YAML registry whose fields are almost all derivable from the file
  layout (for overrides, `path` duplicated `target` verbatim);
- two board-name vocabularies (PIO board id in manifests vs Zephyr
  board.name in fixes.yml keys);
- version-string gating (`applies_to`) that guesses framework drift from
  version numbers instead of detecting it from content;
- fixes for a board scattered across three places (fixes.yml,
  patches/<board>/, overrides/<board>/) while the board's own definition
  lives in `zephyr/boards/arm/<board>/`.

## Proposal

Move fixes into the board's directory; the directory IS the registration:

```
zephyr/boards/arm/<board>/
├── board.yml, *.dts, Kconfig*          # unchanged upstream-style board files
└── fixes/
    ├── fixes.baseline                  # "<target> <sha256>" of the pristine
    │                                   # upstream file each fix was cut against
    ├── drivers/usb/udc/udc_stm32.c           # no suffix: full-file override
    ├── drivers/adc/adc_stm32.c.patch         # .patch: unified diff (idempotent)
    └── cmake/modules/FindGnuLd.cmake.patch
```

- A fix file's location names its framework-package target; no registry.
- Provenance and exit conditions live as header comments inside each fix
  file (upstream PR links, validated Zephyr version, "delete when...").
- Content gating replaces version gating: `fixes.baseline` records the
  pristine sha256 per target. Overrides warn on drift (unchanged
  semantics); patch hunk failures raise enriched with baseline context.
  A framework tarball change is detected from content, not guessed from
  a version string.
- `zephyr_fixes.py` shrinks to a ~100-line directory walker;
  `zephyr_patch.py` / `zephyr_override.py` are reused unchanged (except
  one hunk-order bug fix, below). The call site in `builder/frameworks/
  zephyr.py` is untouched.
- `scripts/ci/verify_zephyr_routing.py` validates the new layout:
  baseline entries and fix files must correspond in both directions.

Migration for xiao_stm32c5 (the only fixes consumer): the five entries
move verbatim, baselines seeded from the existing fixes.yml values (the
three override baselines were verified to match a pristine re-download
of the pinned tarball byte-for-byte) plus freshly computed shas for the
two patch targets.

### Executor bug found and fixed during migration

`zephyr_patch._apply_patch_hunk` checked the "old" block before the
"already applied" (new) block. For pure-context insertion hunks the old
block keeps matching after the hunk lands, so every rebuild re-inserted
it: a production package cache was found carrying the FindGnuLd.cmake
insertion four times (benign only because the duplicated CMake `if` is
idempotent). The check order is now new-block-first, which is correct
for replacement hunks as well. Existing polluted caches self-heal on the
next fresh framework install and no longer grow in place.

## Alternatives considered

- **Keep fixes.yml, slim its fields.** Rejected: leaves the registry,
  the dual naming, and the scattered-fixes problem intact.
- **Host a patched framework tarball (pioarduino model).** Rejected:
  every upstream Zephyr release would require merging and hosting a full
  fork; the platform deliberately consumes registry tarballs plus tiny
  deltas.
- **Zephyr-native mechanisms only (modules / overlays / Kconfig).**
  Rejected: they can add files but cannot fix existing upstream driver
  sources, which is exactly what all five current fixes do.

## Consequences

- Everything about a Zephyr board lives under one directory: board
  definition plus its upstream deltas.
- Adding a fix = dropping a file (+ a baseline line); removing one when
  upstreamed = deleting the file. No registry to edit.
- Framework upgrades are detected by content drift on first build after
  the tarball changes, for both patches and overrides.
- The intended end state is an empty fixes/ directory per board as
  upstream catches up.

## Validation

- Equivalence proof: old mechanism (git HEAD) and new mechanism applied
  to two pristine extractions of the pinned 4.4.0 tarball; patch targets
  byte-identical, override targets differ only by the added provenance
  header (zero removed lines); two consecutive re-runs of the new
  mechanism are no-ops for patches (idempotence).
- stm32c5 zephyr-blink build against a fresh framework package install;
  one nRF54 zephyr build (no-fixes path).
- Offline gates + pytest suites stay green throughout.

## Related files

- [`zephyr/boards/arm/xiao_stm32c5/fixes/`](../../../zephyr/boards/arm/xiao_stm32c5/fixes/)
- [`builder/frameworks/zephyr_fixes.py`](../../../builder/frameworks/zephyr_fixes.py)
- [`builder/frameworks/zephyr_patch.py`](../../../builder/frameworks/zephyr_patch.py)
- [`builder/frameworks/zephyr_override.py`](../../../builder/frameworks/zephyr_override.py)
- [`scripts/ci/verify_zephyr_routing.py`](../../../scripts/ci/verify_zephyr_routing.py)
- [`Board family routing single source`](2026-09-15-board-family-routing-single-source.md)
