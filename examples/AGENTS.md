# examples/ rules

Examples are the user-visible regression contracts, not just CI fodder.

- Preserve example paths; changes must keep or explicitly migrate stable
  paths (users copy them from documentation).
- Every board should be buildable by at least one example env; every
  framework the platform declares needs at least one example (arduino,
  espidf, zephyr each have discoverer wrappers in scripts/ci/).
- Project selection in CI is by declared `framework =` line, not
  directory naming; board-grouped layouts (examples/<board>/<sample>)
  are supported -- keep them discoverable.
- New boards add samples only under `examples/seeed-xiao-<board>/`
  (board-grouped); the historical flat `zephyr-*` / `arduino-*` samples
  stay where they are because wikis reference their paths. Extend a flat
  sample to more boards only via board-neutral mechanisms (devicetree
  aliases, overlays, Kconfig) -- never per-board `#ifdef` in sample code;
  board-specific variants live in the board's own directory.
- platformio.ini references the repository platform URL; CI rewrites it
  to the local checkout. Never commit local paths or test-only overrides.
- Edge AI samples follow the env-var dependency pattern
  (XIAO_EDGE_AI_DIR / XIAO_EDGE_IMPULSE_DIR) with pinned revisions
  checked out in CI; see the workflow for the pins.
- Customer-facing content (README, comments, sample output) in English.
