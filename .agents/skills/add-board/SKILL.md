---
name: add-board
description: Add a Seeed XIAO board to an existing chip family through the manifest-driven flow -- board JSON with the chip_family routing key, demo envs, snapshot update, full matrix; ends by handing off to the validate skill.
---

# Add a board to an existing family

Apply `AGENTS.md` first. A board is data: one manifest plus demo lines.
If the flow demands code changes outside `builder/board_build/<family>/`
or `families/<family>.py`, the board does not fit the family -- stop and
reassess (maybe it needs the add-family skill instead).

## 1. Collect hardware facts first

Require from the developer before writing anything: board ID
(`seeed-xiao-<name>`), display name, vendor/product URL, MCU,
framework(s), flash/RAM sizes, upload protocol(s) and default, debug
probes it supports, and -- for Zephyr boards -- the board tree sources
(DTS/bindings). If any item is missing, ask; do not guess hardware
facts.

## 2. Write the manifest

`boards/<board-id>.json`. Start from the closest existing board of the
same family and change facts, keeping:

- `build.chip_family` -- the routing key; must be a registered family id
- `build.arduino.package` / `build.zephyr.*` -- family routing data as
  the family's module documents (see `families/<family>.py` docstring)

Never invent packages or pins: reuse what the family declares.

## 3. Add demo environments

Every board appears in every demo of its framework(s)
(`examples/<demo>/platformio.ini`) -- the ADR-0005 merge gate builds the
full matrix. Blink + uart are the minimum pair.

## 4. Update the snapshot

Add the board id to `SUPPORTED_BOARD_IDS` in
`scripts/ci/verify_boards.py` -- the gate failure message says exactly
this. For Zephyr boards also check `verify_zephyr_routing.py` output:
the `build.zephyr.board_name` must have a matching
`zephyr/boards/arm/<name>/` tree.

## 5. Validate

Hand off to the **validate** skill: T0 gates, then the new board's
framework matrix (at minimum its own envs; a full framework matrix if
any pin moved). Commit per `AGENTS.md` rules with the board id in the
subject.
