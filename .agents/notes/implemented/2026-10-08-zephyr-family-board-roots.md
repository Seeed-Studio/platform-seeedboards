# Zephyr board definitions live in per-family board roots

Status: implemented

## Context

The wiki (e.g. xiao_nrf54lm20a_ncs and sibling NCS pages) instructs nRF Connect
SDK users to add a path inside this repository as an nRF Connect **Board Root**.
Board-root discovery scans `<root>/boards/*/*/board.yml` and resolves each
board's SoC against the SDK's SoC list. While all boards shared
`zephyr/boards/arm/`, `xiao_stm32c5` was scanned too: its `stm32c5a3xx` SoC does
not exist in NCS v3.3.0 (STM32C5 SoC/driver support is carried inside the
PlatformIO framework package via `zephyr/fixes.yml`), and the extension aborted
with "The SoC stm32c5a3xx was not found in the SDK", blocking nRF development
for those users.

Irreducible constraint: a board whose SoC is missing from the target SDK must
never sit at `<board-root>/boards/*/*/board.yml`. No choice of wiki path can
hide a board that is two levels under a shared `boards/` directory.

## Decision

Board definitions live in per-family board roots:
`zephyr/<family>/boards/seeed/<board>/`.

- `zephyr/nrf` (xiao_nrf54l15, xiao_nrf54lm20a, xiao_nrf54lm20b) is the root
  the wiki adds as nRF Connect Board Root. Only boards whose SoC and drivers
  exist unpatched in the target SDK may live under it.
- `zephyr/stm32` (xiao_stm32c5) holds boards whose build depends on
  `zephyr/fixes.yml` patches/overrides. They reach the framework package only
  through the builder copy step (`builder/frameworks/zephyr.py` globs
  `zephyr/*/boards/*`), never through a board-root scan.
- Adding a family is adding a directory; the builder discovers it without code
  changes.

## Alternatives considered

- Filter boards at copy time and keep one `zephyr/boards/` tree: does not help
  — the nRF Connect extension scans the repository directory directly, not the
  PlatformIO package copy.
- `zephyr/boards/<family>/<board>` (one level shallower): any family under a
  shared `boards/` is scanned when the Board Root is `zephyr`, so the STM32C5
  board re-poisons the SoC cache. Only workable by moving that board outside
  `boards/`, an asymmetric layout.
- A dedicated NCS board-root repository (cleanest PlatformIO vs SDK audience
  separation): rejected as exceeding the intended small refactor; revisit if
  maintaining wiki-visible board paths becomes a burden.

## Consequences

- Wiki NCS pages must point Board Roots at `...\platform-seeedboards\zephyr\nrf`
  (was `...\platform-seeedboards\zephyr`). Users who `git pull` see an empty
  board list until they update the path; the wiki FAQ needs one line.
- The unreferenced overlay `zephyr/boards/xiao_nrf54l15_nrf54l15_cpuapp.overlay`
  was removed with the old layout.
- If a family's SoC support lands in the SDK later (e.g. STM32C5 in NCS), its
  root can be exposed to SDK users as-is.

## Validation

- PlatformIO build of an `xiao_stm32c5` example must log
  `Copied board: xiao_stm32c5 -> ...boards/seeed/xiao_stm32c5` (copy from the
  new family root) and succeed; an `xiao_nrf54lm20b` example must be unchanged.
- In nRF Connect for VS Code with Board Root `zephyr\nrf`, the board list shows
  only XIAO nRF54 boards and the "SoC not found" error is gone.

## Related files

- `builder/frameworks/zephyr.py` (board copy loop, 20B dtsi refresh path)
- `zephyr/README.md` (directory layout and rules)
- `zephyr/fixes.yml` (board-keyed fix registry, unchanged by this decision)
