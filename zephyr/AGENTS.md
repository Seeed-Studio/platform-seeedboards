# zephyr/ rules

Everything a Zephyr board needs beyond the stock framework-zephyr package
lives here, keyed by upstream-style board directories.

- zephyr/boards/arm/<board>/ mirrors the upstream Zephyr board layout
  (board.yml, dts/dtsi, Kconfig, board.cmake, defconfig).
- Fixes live in zephyr/boards/arm/<board>/fixes/: file location = target
  path inside the framework package; `.patch` suffix = unified diff, no
  suffix = full-file override. The directory is the registration -- there
  is no registry file and no builder edit needed to add or remove a fix.
- Every fix file carries a provenance header (upstream link, validated
  Zephyr version, exit condition) and a fixes.baseline entry (pristine
  upstream sha256). The gate enforces the two-way correspondence.
- Upstream framework upgrades surface as baseline drift (override warning
  / patch failure with context) on the first build: re-evaluate each fix
  -- upstreamed means deleted, still needed means refreshed plus a new
  baseline.
- The package cache is never the source of truth; this directory is.
- zephyr/modules/<name>/ modules are auto-discovered (no edit needed to
  add one); see zephyr/README.md.
- Run `python scripts/ci/verify_zephyr_routing.py` before committing.
