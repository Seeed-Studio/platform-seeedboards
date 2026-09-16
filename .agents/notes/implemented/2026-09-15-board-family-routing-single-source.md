# Board family routing single source

Status: implemented

## Context

Board identity currently routes to an MCU family through four hand-maintained
dispatch sites with divergent rules, plus a module-global:

- `platform.py` `configure_default_packages()` (substring if-chain on the
  board id, e.g. `"nrf" in board_name`) sets the module-global
  `Architecture` declared at `platform.py:43`.
- `platform.py` `_add_dynamic_options()` duplicates the same if-chain; an
  unmatched board returns `None`, which makes PlatformIO core's
  `pio boards` listing crash (`get_brief_data()` on `None`), and in listing
  mode the never-reset global leaks the previous board's family.
- `builder/main.py:21-47` re-implements the chain with `board.id` substring
  tests to pick `board_build/<family>/<family>_build.py`.
- `builder/frameworks/arduino.py:31-54` re-implements it again with a
  *different* nrf key (`"52840" in board.id`) and no stm32 branch —
  unreachable today only because core rejects framework/board mismatches
  first (`piobuild.py` "This board doesn't support %s framework").

Separately, Zephyr routing lives in two hand-synced dicts in `platform.py`
(`ZEPHYR_PACKAGE_BY_BOARD`, `ZEPHYR_BOARD_NAME_BY_BOARD`) that must stay
consistent with `zephyr/boards/arm/<name>/` directories and the
`boards/*.json` manifests by discipline alone.

Adding a board today therefore requires touching several Python dispatch
sites and hoping its id matches the substrings; a mismatch fails silently
or crashes listing.

## Decision

Board->family / board->Zephyr-package facts live in the board manifest,
which `AGENTS.md` already names as the owning layer for board
capabilities. PlatformIO core accepts arbitrary manifest keys (it requires
only `name`/`url`/`vendor` and the repo already ships custom keys such as
`build.zephyr.variant` and `build.softdevice`).

1. Every `boards/*.json` gains `"family"` under `build`, with values
   `esp | nrf | renesas | rpi | samd | silabs | stm32`.
   - `platform.py` resolves the family through one accessor,
     `get_board_family(board)`.
   - `builder/main.py` and `builder/frameworks/arduino.py` read
     `board.get("build.family")` from the `env.BoardConfig()` they already
     hold, replacing the substring if-chains with small family->script
     tables.
2. The four Zephyr boards extend their existing `build.zephyr` object with
   `package` (framework package name) and `board_name` (Zephyr board.name).
   `get_zephyr_package_name()` / `get_zephyr_board_name()` read the
   manifest, falling back to `platform.json`'s
   `frameworks.zephyr.package` and `""` respectively — numerically the same
   defaults the dicts have today. The dicts are deleted.
3. `platform.py`'s `Architecture` global is removed; the three lifecycle
   methods resolve the family explicitly (`configure_default_packages`
   from `variables["board"]`, `_add_dynamic_options` from the board object,
   `configure_debug_session` from `debug_config.board_config`). The
   `platform_cfg/<family>_cfg.py` three-hook contract is untouched.
4. Fail-loud policy: a repo manifest missing `build.family` raises with the
   manifest path. Manifests loaded from outside the platform's `boards/`
   directory (user-custom boards) get a one-line warning and no family
   handling, preserving today's de-facto behavior for custom boards.
5. `scripts/ci/verify_boards.py` enforces the new invariants: valid
   `build.family` with an existing `builder/board_build/<family>/`
   directory, and for Zephyr boards a closed
   `build.zephyr.package` (declared in `platform.json`) ->
   `zephyr/boards/arm/<board_name>/` chain. A second gate,
   `verify_zephyr_routing.py`, additionally keeps `zephyr/fixes.yml` keys
   and `zephyr/{patches,overrides}/` directories free of orphans.

Rollout is inert-data-first: keys and accessor land with no consumer
reading them; consumers flip one PR each afterwards.

## Alternatives considered

- **A central `{board_id: family}` dict in platform.py.** Rejected: builder
  SCons scripts would need to import `platform.py` (no precedent, new
  coupling), it violates the AGENTS.md ownership rule that board facts
  live in board metadata, and it remains a hand-synced 24th file.
- **Deriving the family from `build.mcu` / `build.cpu` / `build.core`.**
  Rejected: `seeed-xiao-mg24`'s `build.mcu` is `cortex-m33` (a CPU name
  shared with other boards' `build.cpu`), esp32 boards omit `build.cpu`,
  and `build.core` overlaps across families (`arduino` for both
  mbed-nrf52840 and ra4m1).
- **Keep the substring chains and add a lint.** Rejected: the divergence
  (`"nrf"` vs `"52840"`) is the proven failure mode; a lint cannot fix the
  silent-noop or the global-state leak, only detect some of them.
- **A `provision:` section in `zephyr/fixes.yml` for the nRF54LM20B
  provisioning.** Rejected: fixes.yml entries are version-gated patches of
  upstream files; provisioning is an unconditional refresh of our own
  content. Gating on the canonical Zephyr board name is sufficient.

## Consequences

- Adding a same-family board becomes a metadata-only change: manifest
  (+`zephyr/boards/arm/<name>/` and the `verify_boards` snapshot when the
  board uses Zephyr) plus an example; no `platform.py`, `builder/`, or
  `platform_cfg/` edits. The `platformio-add-board` skill will document
  exactly this boundary.
- `build.family` becomes visible in `pio boards --json-output` output
  (manifests are serialized whole) — accepted as quasi-public surface.
- A new MCU *family* still requires a `board_build/<family>/` tree and a
  `platform_cfg/<family>_cfg.py` module; the gates then require both to
  exist for any manifest declaring that family.
- Removing the global makes missing-family-module ImportErrors raise
  instead of printing and continuing with wrong packages; all seven
  current family modules implement all three hooks, so this only affects
  currently unreachable failure paths.

## Validation

Recorded evidence (all through the local-checkout platform override, one
`pio run -t clean` per build, fresh platform-package install per phase):

- Offline gates green throughout: `pytest tests/ -q` (62 tests at close,
  including per-family probe boards, full 23-board listing assertions,
  zephyr routing from manifests), `scripts/ci/verify_boards.py`,
  `scripts/ci/verify_zephyr_routing.py`, `scripts/ci/smoke_pio_boards.py`.
- Inert-data phase: 24/24 builds (all 20 arduino example envs across 6
  families + zephyr-blink for nrf54l15/nrf54lm20a/nrf54lm20b/stm32c5).
- Consumer flips: arduino-blink all 17 envs per builder commit; zephyr
  sets per platform.py/zephyr.py commit, including nrf54l15 (the only
  board on the framework-zephyr-nrf54l15 tarball), the stm32c5
  shared-tarball case, and edgeai-hello-ei for the 20B provisioning gate.
- Hardware upload/debug: not performed.

## Related files

- [`AGENTS.md`](../../../AGENTS.md)
- [`platform.py`](../../../platform.py)
- [`builder/main.py`](../../../builder/main.py)
- [`builder/frameworks/arduino.py`](../../../builder/frameworks/arduino.py)
- [`builder/frameworks/zephyr.py`](../../../builder/frameworks/zephyr.py)
- [`verify_boards.py`](../../../scripts/ci/verify_boards.py)
- [`AI workflow adaptation`](../proposed/2026-08-17-ai-workflow-adaptation.md)
