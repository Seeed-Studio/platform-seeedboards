# boards/ rules

Board manifests are the public PlatformIO interface and the single source
of truth for board identity routing.

- Every manifest carries `build.family` (one of esp, nrf, renesas, rpi,
  samd, silabs, stm32); builder/platform dispatch reads only this key.
- Zephyr-capable boards carry `build.zephyr.package` (declared in
  platform.json) and `build.zephyr.board_name` (matching a
  zephyr/<family>/boards/seeed/<name>/ directory); `build.zephyr.variant`
  starts with board_name.
- Manifests hold PlatformIO board capabilities (build/upload/debug/
  connectivity/frameworks) plus exactly the routing keys named above
  (`build.family`, `build.zephyr.*`); do not encode any other builder
  behavior here -- if dispatch needs a new fact, add it as a named
  routing key with a gate check, not a builder special case.
- Never paper over a missing manifest value with builder special cases --
  add the value to the manifest.
- Adding or removing a board is a deliberate edit: update the
  SUPPORTED_BOARD_IDS snapshot in scripts/ci/verify_boards.py in the same
  change; the gate fails until you do.
- Adding a same-family board requires no platform.py / builder/ /
  platform_cfg/ edits. If you find yourself editing them, stop and check
  whether the manifest should carry the fact instead.
- Board IDs, framework lists, upload/debug declarations are protected user
  contracts: preserve them unless the change explicitly alters that
  contract.
- Run `python scripts/ci/verify_boards.py` before committing (offline,
  seconds); it enforces all of the above.
