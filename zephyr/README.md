# Zephyr framework local fixes (patches & overrides)

This directory carries local fixes applied on top of PlatformIO's
`framework-zephyr` package so that Seeed XIAO boards work on the current
Zephyr version. All fixes are **centrally registered** in `fixes.yml`;
`builder/frameworks/zephyr_fixes.py` reads it before the build and applies
the registered fixes to the framework package of the board being built.

## Directory layout

```
zephyr/
├── <family>/         # per-family board root: zephyr/<family>/boards/seeed/<board>/
│   └── boards/seeed/ #   (e.g. nrf/, stm32/); discovered by the builder via
│                     #   glob(zephyr/*/boards/*), no builder change per family
├── patches/          # patches (unified diff)
│   └── <board>/      #   one level per board
│       └── 0001-*.patch
├── overrides/        # overrides (whole files)
│   └── <board>/      #   one level per board; relative path below = target path inside the framework package
│       └── drivers/...
├── fixes.yml         # fix registry (single source of truth)
└── README.md         # this file
```

Each `zephyr/<family>` is a standalone Zephyr board root. `zephyr/nrf` is the
root the wiki tells nRF Connect users to add under **Board Roots**, so it may
only contain boards whose SoC and drivers exist unpatched in the target SDK —
a board referencing a SoC missing from the SDK (e.g. `xiao_stm32c5`'s
`stm32c5a3xx` in NCS) breaks the extension's SoC cache for every board.
Boards that depend on `fixes.yml` fixes belong in their own family root
(`zephyr/stm32`); they reach the framework package only through the builder's
copy step, never through a board-root scan.

`<board>` = the Zephyr board name (the directory name under
`zephyr/<family>/boards/seeed/<same name>/`, equal to the `board.yml` `board.name`),
derived by `platform.get_zephyr_board_name()` from the board manifest's `build.zephyr.variant`: the first component
of `board[@revision]/soc/...` (before any `/` and `@`); a board revision
(e.g. `xiao_nrf54lm20a@2.0.0/...`) collapses to its shared board directory
`xiao_nrf54lm20a`.

## Which mechanism to use?

| Scenario | Mechanism |
|---|---|
| Modifying a file that **exists** upstream, change is focused (a few hunks) | `patch` |
| Upstream file **missing**, or the change spans the whole file (whole-file backport of new SoC support) | `override` |

- `patch`: unified diff; small and reviewable; idempotent (skipped if already applied).
- `override`: whole-file replacement at the target path; the optional `baseline_sha` guards against silent regressions after a framework upgrade.

## fixes.yml format

See the comment block at the top of `fixes.yml`. Each fix entry carries
`id/type/path/target/applies_to` plus optional `upstream/baseline_sha/reason`.
Sections keyed by `boards[<board.name>]` provide **board/package isolation**;
`applies_to` provides **version gating**. The two gates together ensure that
one board's fixes never touch another board's framework package, and that
entries auto-expire after a Zephyr upgrade, forcing re-evaluation.

## Adding a new fix

1. Pick the mechanism: small change → put a `.patch` file under
   `patches/<board>/`; whole file → put the file under
   `overrides/<board>/<relative path inside the framework package>/`
   (the path is the target).
2. Add a `fixes` entry under the `boards[<board>]` section in `fixes.yml`
   (create the section if missing) with `path/target/applies_to/reason`;
   for overrides, filling in `baseline_sha` is recommended.
3. **No builder code changes needed.**

## Adding a new board

No Python code changes are needed — board-level data lives in
`boards/<board-id>.json`:

1. Declare `build.zephyr.variant` in `boards/<board-id>.json` (in
   `board[@revision]/soc/...` form, e.g.
   `xiao_nrf54lm20a@2.0.0/nrf54lm20a/cpuapp`). The first component of the
   variant (before `/` and `@`) is the board.name — the key of this
   directory's fixes mechanism. All boards build against the single
   `framework-zephyr` package pinned in `platform.json`; there is no
   per-board package field.
2. Create `zephyr/patches/<board.name>/` and `zephyr/overrides/<board.name>/`
   (only if the board has fixes).
3. Add a `boards[<board.name>]` section in `fixes.yml`.

`scripts/ci/verify_board_manifests.py` validates in CI that the variant
field is present (a missing declaration fails the check instead of silently
producing a board with no fixes key) and cross-checks that every `fixes.yml`
key matches a manifest-derived board name.

> **Single package note**: every Zephyr board — including
> `seeed-xiao-stm32c5` — builds against the same pinned `framework-zephyr`
> tarball from `platform.json`; Zephyr version bumps are platform-level
> decisions, not per-board ones. Board-level differences (pinctrl via the
> hal_stm32 west module; udc/xspi/adc overrides) are injected per board via
> `fixes.yml`.

## Adapting to a new Zephyr version (framework package upgrade)

After an upgrade, entries whose `applies_to` does not include the new version
are skipped automatically (version gating). Re-evaluate each entry:
- patch landed upstream → delete the entry;
- still applies → add the new version value to `applies_to`;
- needs a redo → add a new entry pointing at the new file.

Overrides need their `baseline_sha` recomputed (the upstream target file has
changed).

## baseline_sha (override regression guard)

An override replaces a whole file, so a framework package upgrade can
silently clobber the new upstream version. `baseline_sha` records the
sha256 the upstream target file should have at apply time; it is verified
before applying, and a mismatch prints a warning (it does not block the
build):

```bash
# Compute after the framework package is extracted (it is downloaded on
# first build):
sha256sum <framework_dir>/<target>
```

Fill the value into the fix's `baseline_sha` field. Optional; omit it to
overwrite without verification.

## Module layout

- `builder/frameworks/zephyr_fixes.py`    — dispatcher: reads `fixes.yml` + board/version gating + dispatch
- `builder/frameworks/zephyr_patch.py`    — executor A: applies one `.patch` to the framework package (idempotent)
- `builder/frameworks/zephyr_override.py` — executor B: copies one override into the framework package (with baseline verification)

The executors are stateless pure functions: they only know "source file +
framework root + target path"; they read no manifest and know nothing about
boards or versions, so they are independently unit-testable.
