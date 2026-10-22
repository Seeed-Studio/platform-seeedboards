# ADR-0003: Board-directory fixes with baseline drift detection

## Context

"Reuse upstream" has a blind spot: when a *framework package* (a binary
tarball like framework-zephyr) lacks support for your SoC, no amount of
version pinning, importing, SConscript delegation, or forking the
platform reaches inside the package. The predecessor faced exactly this:
vanilla Zephyr 4.4.2 carries zero STM32C5 USB/XSPI support, and the C5
support had silently shipped inside a custom Seeed tarball — invisible
until a vanilla upgrade broke the build. The upgrade procedure also
proved that fixes must be re-evaluated per tarball (some upstreamed and
die, some stay, and "byte-identical to pristine" can mean your
comparison base was itself patched).

## Decision

1. Fixes live in the owning board directory:
   `zephyr/boards/arm/<board>/fixes/` (per-framework equivalents if a
   second framework ever needs it). **The directory is the
   registration** — file location = target path inside the framework
   package; `.patch` suffix = idempotent unified diff; no suffix =
   full-file override carrying a provenance header (source, upstream
   link, validated version, exit condition).
2. `fixes.baseline` records the pristine upstream sha256 per target.
   Before applying: overrides warn on mismatch, patch hunks fail with
   baseline context. Baselines point at VANILLA upstream content —
   never at custom tarballs (a baseline matching custom content can
   never fire).
3. Framework upgrade procedure: bump pin → expect drift → re-evaluate
   each fix (upstreamed = delete; still needed = refresh against the
   new base) → re-cut baselines → full build matrix. A fix without a
   current consumer dies.
4. A verify gate enforces two-way correspondence between fix files and
   baseline entries, and that fixes directories belong to known boards.

## Consequences

- Framework-package dependencies become visible, auditable, and
   drift-detecting — the opposite of the magic-tarball status quo.
- Custom framework builds are permitted only as fix *sources* (content
   extracted into explicit override files), never as invisible pins.
- The mechanism is designed to shrink: the intended end state is empty
   fixes/ directories as upstream catches up.

## Validation

Predecessor: full 4.4.0-custom → 4.4.2-vanilla upgrade cycle executed
end to end (patches carried, overrides extracted, baselines re-cut,
4/4 matrix green). Re-proven in this repo on the STM32C5 board:
patches apply idempotently across rebuilds, overrides land against
the vanilla 3.40402.0 tarball, and verify_zephyr_routing gates the
two-way fix/baseline correspondence.

## Related files

- `zephyr/boards/arm/<board>/fixes/` (populated)
- `scripts/ci/verify_zephyr_routing.py` (implemented)
- `docs/decisions/0006-zephyr-framework-views.md` (fixes write to a
  per-build bridge view, never the package cache)
- `builder/board_build/zephyr/zephyr_fixes.py`
