---
name: add-family
description: Add a new chip family as a ChipFamily module -- subclass with family_ids, family-owned builder directory, one import line in families/__init__.py, packages in platform.json; the routing core never changes (ADR-0001).
---

# Add a chip family

Apply `AGENTS.md` first. A family is a pluggable module (ADR-0001):
everything it needs lands in three places, and the zero-string core
stays untouched.

## 1. Find and study the upstream

Identify the upstream platform this family reuses (pioarduino,
atmelsam, maxgerhardt/platform-renesas, ...). Read its builder and
package table. Decide the reuse altitude per ADR-0004: version pin >
import > build-script delegation > adapted copy -- take the highest
altitude that works. Copy files WITH their attribution headers.

## 2. Implement the family module

`families/<family>.py` subclassing `ChipFamily`:

- `family_ids` -- routing keys; also add the import line to
  `families/__init__.py` (the only side-effecting import)
- `required_packages(board, variables)` -- name -> version override.
  Slot collisions with other families need an explicit ADR-0002
  decision as a comment carrying the evidence (see the GCC 7/8/12
  toolchain notes in `families/nrf.py`)
- `build_script` / `arduino_script` (+ `zephyr_script` if applicable)
- `inject_debug_tools` / `configure_debug_session` -- synthesize the
  probe servers, asserting loudly on missing manifest fields
- `post_activate_packages` -- ONLY if the family consumes stub zips
  (the whole contract is in ADR-0002 "Stub expansion mechanics";
  `families/esp.py` is the reference implementation)

Imports of `platformio` inside family modules stay lazy (function
scope): a module-level import shadows the stdlib `platform` module
when the repo root is on sys.path and breaks the offline gates.

## 3. Port the builder directory

`builder/board_build/<family>/`: the family entry (`<family>_build.py`,
reached via `ChipFamily.build_script`), framework entries, `_bare.py`,
helpers. Silicon specifics live HERE or in the manifest -- never in
`platform.py` / `builder/main.py` (the zero-string gate enforces it).

## 4. Declare packages

Add the family's packages to `platform.json` (optional: true unless
bootstrap-required; the family marks them required per board). A name
collision with an existing slot = ADR-0002 decision, not a silent
override -- if the versions genuinely differ, give the package its own
name (see `tool-openocd-silabs`).

## 5. Boards, demos, gates

Boards via the **add-board** skill. Then the **validate** skill's full
loop; the new family's entire demo matrix must be green before merge
(ADR-0005).
