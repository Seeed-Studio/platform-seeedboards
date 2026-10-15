# zephyr/ rules

Everything a Zephyr board needs beyond the stock framework-zephyr package
lives here, organized as per-family board roots.

- Board definitions live in per-family roots:
  zephyr/<family>/boards/seeed/<board>/ (board.yml, dts/dtsi, Kconfig,
  board.cmake, defconfig). zephyr/nrf is the root the wiki tells users to
  add to nRF Connect Board Roots, so it may only contain boards whose SoC
  and drivers exist unpatched in the target SDK.
- Local fixes to the framework package live in the owning board's
  directory -- the directory IS the registration, there is no registry
  file: zephyr/<family>/boards/seeed/<board>/fixes/<framework-path> for
  full-file overrides, zephyr/<family>/boards/seeed/<board>/fixes/
  <framework-path>.patch for unified diffs. A fix file's location inside
  fixes/ is its target path inside the framework package. fixes.baseline
  records the pristine upstream sha256 per target; a mismatch warns
  (overrides) or fails with baseline-drift context (patches) after a
  framework upgrade.
- Every fix file carries a provenance header (upstream link, validated
  Zephyr version, exit condition). After a framework package upgrade,
  re-evaluate every fix the baseline flags: upstreamed means delete the
  file and its baseline line, still needed means refresh the source and
  re-cut the baseline sha.
- The package cache is never the source of truth; this directory is.
- zephyr/modules/<name>/ modules are copied into the framework and
  registered via ZEPHYR_EXTRA_MODULES (see zephyr.py); no builder edit is
  needed to add one.
- Run `python scripts/ci/verify_zephyr_routing.py` (chain: board ->
  package -> board dir -> fixes layout) before committing.
