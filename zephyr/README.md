# Zephyr local content (boards, modules, fixes)

This directory carries everything Zephyr needs beyond the stock
`framework-zephyr` package: board definitions, bundled west modules, and
fixes for upstream gaps. Applied before the build by
`builder/frameworks/zephyr/` (main + fixes + modules + patch + override).

## Layout

```
zephyr/
├── fixes/                              # FRAMEWORK-level fixes (every board):
│   │                                   #   engine patches under scripts/platformio/
│   ├── fixes.baseline                  #   "<target> <sha256>" of the pristine
│   │                                   #   upstream file each fix was cut against
│   ├── <target-path>                   #   full-file override (provenance in header)
│   └── <target-path>.patch             #   unified-diff patch (idempotent)
├── <family>/                           # per-family standalone board root
│   └── boards/seeed/<board>/           # board definition (upstream-style:
│       │                              #   board.yml, dts/dtsi, Kconfig,
│       │                              #   board.cmake, defconfig)
│       └── fixes/                     # this board's fixes for the framework
│           ├── fixes.baseline         #   same shape as the framework level
│           ├── <target-path>
│           └── <target-path>.patch
└── modules/<name>/                    # west modules this platform injects
    ├── ...module files...             #   vendored module source, or a stub
    ├── pin.yml                        #   provisioning descriptor (see below)
    └── fixes/                         #   fixes for an external module itself
```

## Fixes

A fix file's location inside a `fixes/` directory IS its target path
inside the framework package -- the directory is the registration. There
is no registry file. Every fix file carries a header comment (or patch
prologue) with the upstream link, the validated Zephyr version, and its
exit condition.

A `.patch` file's NAME is only a label (several patches may edit the same
file, e.g. the numbered engine patches); the target of record is the
patch's own `+++` header, and that path keys `fixes.baseline`.

Apply order: framework level first, board level on top -- a board fix may
re-shape a framework file by landing after it.

| Scenario | Mechanism |
|---|---|
| Upstream file exists, change is focused (a few hunks) | `<target>.patch` (unified diff) |
| Upstream file missing, or the change spans the whole file | `<target>` (full-file override) |

Content gating replaces version strings: `fixes.baseline` records the
pristine sha256 each fix was cut against. A mismatch means the tarball
changed under us -- overrides warn, patch hunks fail with baseline-drift
context, and the fix must be re-evaluated.

> Historical pollution note: caches patched by the pre-v2 walker may carry
> a repeated `FindGnuLd.cmake` insertion block (the idempotence bug). The
> fix prevents new duplication but does not clean existing caches;
> `pio pkg uninstall framework-zephyr` (or delete the package dir) and the
> next build reinstalls a pristine package.

## Board roots

Each `zephyr/<family>` is a standalone Zephyr board root. `zephyr/nrf` is
the root the wiki tells nRF Connect users to add under **Board Roots**, so
it may only contain boards whose SoC and drivers exist unpatched in the
target SDK — a board referencing a SoC missing from the SDK (e.g.
`xiao_stm32c5`'s `stm32c5a3xx` in NCS) breaks the extension's SoC cache for
every board. Boards that depend on framework fixes belong in their own
family root (`zephyr/stm32`); they reach the framework package only through
the builder's copy step, never through a board-root scan.

`<board>` = the Zephyr board name (the directory name under
`zephyr/<family>/boards/seeed/<same name>/`, equal to the `board.yml`
`board.name`), derived by `platform.get_zephyr_board_name()` from the board
manifest's `build.zephyr.variant`: the first component of
`board[@revision]/soc/...` (before any `/` and `@`); a board revision
(e.g. `xiao_nrf54lm20a@2.0.0/...`) collapses to its shared board directory
`xiao_nrf54lm20a`.

## Modules

Every directory under `zephyr/modules/` is a module this platform may
inject; the directory is the registration. `pin.yml` (optional) describes
how it is provisioned:

```yaml
gate:                # AND across fields, OR within a list; no gate = all boards
  boards: [xiao_stm32c5]
  families: [nrf]
  prj_conf_tokens: [CONFIG_NRF_AXON=y]   # any token in prj.conf opts in
remote: https://github.com/nrfconnect/sdk-edge-ai.git   # external source
revision: 3733b1b87c41fb560be1f2a2de646b4e405f156d      # pinned commit
override_env: XIAO_EDGE_AI_DIR   # developer-provided tree wins over remote
```

Without `remote` the directory IS the module source (vendored: copied into
the framework cache's `_pio/modules/` on every build, `pin.yml` excluded).
With `remote` it is a stub: the pinned revision is cloned into the cache on
first use (`override_env` checked first), and the module's own `fixes/`
directory (v2 convention) is applied to the cloned tree right after it
lands.

Registered modules are appended to **ZEPHYR_EXTRA_MODULES** — Zephyr's
official injection channel (`zephyr_module.cmake` reads the environment
variable), which reaches sysbuild child images (mcuboot) as well. Adding a
module = dropping a directory here; removing one = deleting it. No builder
change either way.

## Tooling layout

- `builder/frameworks/zephyr/main.py`      — orchestrator: boards copy, env prep, module provisioning, fixes, engine SConscript
- `builder/frameworks/zephyr/modules.py`   — module provisioner (pin.yml gates, vendored refresh, pinned clones)
- `builder/frameworks/zephyr/fixes.py`     — fixes walker (framework + board level, baseline gating)
- `builder/frameworks/zephyr/patch.py`     — executor A: applies one `.patch` (idempotent, new-block-first)
- `builder/frameworks/zephyr/override.py`  — executor B: copies one override (baseline verification)

The executors are stateless pure functions: they only know "source file +
root + target path"; they read no manifest and know nothing about boards or
versions, so they are independently unit-testable (tests/test_zephyr_*.py).
Consistency is enforced offline by `scripts/ci/verify_zephyr_routing.py`
(board -> variant-derived name -> family board dir chain closed; baseline
<-> fix two-way correspondence for both levels), wired into
`.github/workflows/check-board-manifests.yml`.
