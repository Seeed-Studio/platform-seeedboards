# Contributing

Thanks for improving the Seeed XIAO PlatformIO platform. This repository
has a strict layering; most fixes land in exactly one layer.

## Before you start

- Read [AGENTS.md](AGENTS.md) -- the ownership table and the compatibility
  contract (board ids, example paths, framework choices, package versions,
  upload/debug behavior, firmware formats) are binding.
- Read the `AGENTS.md` inside the directory you are changing
  (`boards/`, `platform_cfg/`, `builder/`, `zephyr/`, `examples/`,
  `scripts/ci/`).
- Search [`.agents/notes/`](.agents/notes/README.md) for an active note
  covering the area before designing cross-layer changes.

## Development loop

1. Run the offline gates from the repository root (fast, no downloads):

   ```bash
   pytest tests/ -q                      # NOTE: console script, not python -m pytest
   python scripts/ci/verify_boards.py
   python scripts/ci/verify_zephyr_routing.py
   python scripts/ci/smoke_pio_boards.py
   ```

2. For behavior changes, validate against your fork of this platform with
   a representative example environment (`pio run -t clean`, then build).
   Example: `examples/arduino-blink` covers six families in one project.
3. Adding a board is metadata-driven -- follow
   [.agents/skills/platformio-add-board/SKILL.md](.agents/skills/platformio-add-board/SKILL.md).

## Pull requests

- One reviewable unit per PR; conventional-commit titles
  (`fix(builder): ...`, `refactor(zephyr): ...`, `test(ci): ...`).
- Describe **why** before **what**; limit the body to the net change.
- Include a *Validation* section only for behavioral evidence: the exact
  commands run, the PlatformIO package path used, and remaining risk.
  State hardware validation as *not performed* unless you ran it.
- CI must be green: the offline gates (`ci-verify`) plus the example
  build workflows for the frameworks you touched.

## Reporting issues

Include the board id, `framework`, PlatformIO version, and the build log
(`pio run -v`). For upload/debug problems, note the probe/tool used.
