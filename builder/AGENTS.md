# builder/ rules

- Keep the framework vs family split: builder/frameworks/<fw>.py owns
  framework integration; builder/board_build/<family>/ owns family build,
  artifact, and upload adaptation; builder/main.py only dispatches
  families via the FAMILY_BUILD_SCRIPTS table.
- No board-id substring special cases anywhere. Gate on
  board.get("build.family") or the canonical Zephyr board name
  (platform.get_zephyr_board_name()); unknown/missing values fail loudly.
- Adding a family = board_build/<family>/ tree + one table entry in
  main.py (and arduino.py if Arduino-capable) + a platform_cfg module.
  Adding a board = manifest only (see boards/AGENTS.md).
- Zephyr fixes are registered by directory, not code: drop files under
  zephyr/boards/arm/<board>/fixes/ (see zephyr/AGENTS.md); do not add
  fix logic to builder/frameworks/zephyr.py.
- The PIOPLATFORM masquerade in zephyr.py intentionally keeps its
  exception-window semantics (restore skipped if the framework build
  script raises) -- do not "fix" it silently.
- Validate through the platformio-development flow: sync the platform
  package cache, `pio run -t clean`, then build; offline gates first
  (`pytest tests/ -q`, scripts/ci/verify_*.py).
