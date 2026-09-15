# Zephyr local content (boards, modules, fixes)

This directory carries everything Zephyr needs beyond the stock
`framework-zephyr-*` package: board definitions, bundled west modules, and
per-board fixes for upstream gaps. Applied before the build by
`builder/frameworks/zephyr.py` + `builder/frameworks/zephyr_fixes.py`.

## Layout

```
zephyr/
├── <family>/                          # per-family standalone board root
│   └── boards/seeed/<board>/          # board definition (upstream-style:
│       │                              #   board.yml, dts/dtsi, Kconfig,
│       │                              #   board.cmake, defconfig)
│       └── fixes/                     # this board's fixes for the framework
│           ├── fixes.baseline         #   "<target> <sha256>" of the pristine
│           │                          #   upstream file each fix was cut against
│           ├── <target-path>          #   full-file override (provenance in header)
│           └── <target-path>.patch    #   unified-diff patch (idempotent)
└── modules/<name>/                    # bundled west modules (copied per build)
```

A fix file's location inside `fixes/` IS its target path inside the
framework package -- the directory is the registration. There is no
registry file. Every fix file carries a header comment with the upstream
link, the validated Zephyr version, and its exit condition.

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

## Which mechanism to use?

| Scenario | Mechanism |
|---|---|
| Upstream file exists, change is focused (a few hunks) | `<target>.patch` (unified diff) |
| Upstream file missing, or the change spans the whole file (whole-file backport of new SoC support) | `<target>` (full-file override) |

## Workflows

**Add a fix**: pick the mechanism (small focused change -> `.patch`; whole
file backport -> override), drop the file at `fixes/<framework-path>`[`.patch`]
under the board's directory, and add a `fixes.baseline` line with the
pristine target's sha256 (compute from a fresh extraction of the pinned
tarball). No builder code changes.

**Remove a fix** (upstreamed / no longer needed): delete the file and its
baseline line. The first build after removal confirms the upstream tree is
sufficient.

**Zephyr framework upgrade**: the new tarball's files will not match
`fixes.baseline` -- overrides warn loudly and patch hunks fail with
baseline-drift context on the first build. Re-evaluate each fix: upstreamed
-> delete; still needed -> refresh the file against the new tree and update
its baseline sha.

**Consistency** is enforced offline by `scripts/ci/verify_zephyr_routing.py`
(board -> package -> `<family>/boards/seeed/` chain closed; baseline <->
fix file two-way correspondence), wired into
`.github/workflows/ci-verify.yml`.

> **Package sharing note**: `seeed-xiao-stm32c5` declares
> `framework-zephyr-nrf54lm20` directly — it uses the **exact same** Zephyr
> 4.4.0 tarball as nrf54lm20 (identical content), so no separate
> `framework-zephyr-stm32c5` package is shipped; even if one were shipped,
> PlatformIO would URL-dedupe an identically-versioned package into the
> nrf54lm20 directory, leaving only a misleading name behind. STM32C5
> board-level differences (pinctrl via the hal_stm32 west module;
> udc/xspi/adc fixes) are injected per board from the board's `fixes/`
> directory.

## Module layout

- `builder/frameworks/zephyr_fixes.py`    — fixes applier: walks the board's fixes/ directory (baseline gating + dispatch)
- `builder/frameworks/zephyr_patch.py`    — executor A: applies one `.patch` to the framework package (idempotent)
- `builder/frameworks/zephyr_override.py` — executor B: copies one override into the framework package (with baseline verification)

The executors are stateless pure functions: they only know "source file +
framework root + target path"; they read no manifest and know nothing about
boards or versions, so they are independently unit-testable.
