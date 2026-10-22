---
name: sync-upstream
description: Absorb an upstream change -- framework/toolchain release, builder restructure, or board data update; bump the pin, re-port family-scoped code, expect fixes drift, re-run every framework matrix.
---

# Sync an upstream change

Apply `AGENTS.md` first. Upstream changes come in three shapes; each
has a bounded path. The invariant: upstream upgrades never auto-apply
(ADR-0002 conscious-version rule) and a pin change re-runs EVERY
family's matrix, not just the one you touched.

## Shape 1: a package release (most common)

Framework tarball, toolchain, uploader -- usually just a pin:

1. Bump `version` (and `package-version` for stub zips) in
   `platform.json`. Record WHY in the commit body.
2. Watch for allowlist coupling: a framework may hard-require one
   exact toolchain build (ESP-IDF's `tool_version_check.cmake`
   FATAL_ERRORs on a mismatch). If the pins fight, the family narrows
   its slot per framework with evidence (see `families/esp.py`).
3. For Zephyr: expect fixes drift, continue with the **zephyr-fixes**
   skill.
4. Run the full matrix (all three frameworks).

## Shape 2: upstream restructured its builder

pioarduino rewrote `main.py`, a core renamed its entry points:

1. The affected family is `builder/board_build/<family>/` -- diff it
   against the upstream's new version. Attribution headers in each
   file name the upstream and version it was cut from.
2. Re-port into the family directory. Touch nothing outside it and
   `families/<family>.py`.
3. If PlatformIO core semantics moved (package manager, manifest
   lookup), check ADR-0002's "Stub expansion mechanics" section still
   matches reality; amend the ADR if core behavior changed.
4. Full matrix again.

## Shape 3: upstream board data (new flags, fields)

Board-manifest level: edit `boards/*.json` facts. Routing keys never
change shape; if upstream invents a per-board package selector, extend
the generic router in `platform.py` (see `build.<framework>.package`)
-- data-driven, zero-string.

## Verification bar

The sync is done when: T0 gates green, all three framework matrices
green, and the commit message says what moved and why. If a matrix
env regresses and cannot be fixed within the family, revert the pin
and report -- a red matrix never merges (ADR-0005).
