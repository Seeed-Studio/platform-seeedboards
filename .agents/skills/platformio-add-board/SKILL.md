---
name: platformio-add-board
description: Add or formalize a Seeed XIAO board in this platform through the metadata-driven flow; collect the missing pieces and hand off to platformio-development for fork validation.
---

# Add a board

Apply the repository rules in `AGENTS.md` first, plus the owning
directories' rules (`boards/AGENTS.md`, `zephyr/AGENTS.md`,
`examples/AGENTS.md` as applicable). Do not invent packages, Zephyr
patches, or upload strategies: reuse what the family already ships.

## 1. Collect

Before writing anything, require from the developer: board ID
(`seeed-xiao-<name>`), display name, vendor URL, MCU, frameworks to
support, upload protocol(s), onboard-debug tooling, and -- for Zephyr
boards -- the Zephyr board sources. If any item is missing, ask; do not
guess hardware facts.

## 2. Same-family board (metadata-only)

After Phase 2 of the board-family routing note, adding a board to an
existing family touches no Python:

1. `boards/<board-id>.json` -- manifest with `build.family` (and for
   Zephyr boards `build.zephyr.package` + `build.zephyr.board_name` +
   `variant`). Copy the closest sibling manifest and edit; do not
   fabricate upload/debug values.
2. Add the board id to `SUPPORTED_BOARD_IDS` in
   `scripts/ci/verify_boards.py` (the gate fails until you do -- that is
   deliberate).
3. Zephyr boards: add `zephyr/boards/arm/<board_name>/` (upstream-style
   board.yml, dts/dtsi, Kconfig, board.cmake, defconfig). Fixes for
   upstream gaps go in that directory's `fixes/` (see
   `zephyr/AGENTS.md`) -- never into builder code.
4. Add at least one example env (extend an existing example's
   platformio.ini) so CI builds the board.
5. Run the gates: `python scripts/ci/verify_boards.py`,
   `python scripts/ci/verify_zephyr_routing.py`, `pytest tests/ -q`.

If step 2 leads you to edit `platform.py`, `builder/`, or
`platform_cfg/`, stop: either the family is new (next section) or the
fact belongs in the manifest. Ask which.

## 3. New family (the boundary where metadata-only ends)

A new MCU family requires, in this order: platform.json package
declarations (framework/toolchain/uploader), a
`builder/board_build/<family>/` tree (modeled on the closest existing
family), a `platform_cfg/<family>_cfg.py` module implementing the
three-hook contract, one table entry in `builder/main.py`
(`FAMILY_BUILD_SCRIPTS`) plus `builder/frameworks/arduino.py` if
Arduino-capable, the family added to `VALID_FAMILIES` in
`verify_boards.py`, and a representative example env. Record the family
decision in a `.agents/notes/` note.

## 4. Validate

Hand off to the `platformio-development` skill for the fork-branch
build loop (`pio run -t clean` then build the new board's example env).
Report hardware upload/debug as not performed unless the developer
supplies evidence.
