# zephyr/ rules

Everything a Zephyr board needs beyond the stock framework-zephyr package
lives here, organized as per-family board roots.

- Board definitions live in per-family roots:
  zephyr/<family>/boards/seeed/<board>/ (board.yml, dts/dtsi, Kconfig,
  board.cmake, defconfig). zephyr/nrf is the root the wiki tells users to
  add to nRF Connect Board Roots, so it may only contain boards whose SoC
  and drivers exist unpatched in the target SDK.
- Local fixes to the framework package are registered in
  zephyr/fixes.yml (single registry): `patch` sources under
  zephyr/patches/<board>/, `override` sources under
  zephyr/overrides/<board>/. For overrides, `path` is also the target
  path inside the framework package; a `baseline_sha` guards against
  silent regressions after a framework upgrade (mismatch warns).
- After a framework package upgrade, re-evaluate every fix whose
  applies_to matches: upstreamed means delete the entry, still needed
  means refresh the source and re-cut the baseline sha.
- The package cache is never the source of truth; this directory is.
- zephyr/modules/<name>/ modules are copied into the framework and
  registered via ZEPHYR_EXTRA_MODULES (see zephyr.py); no builder edit is
  needed to add one.
- Run `python scripts/ci/verify_zephyr_routing.py` (chain: board ->
  package -> board dir -> fixes) and
  `python scripts/ci/verify_board_manifests.py` (fixes.yml keys vs
  manifests) before committing.
