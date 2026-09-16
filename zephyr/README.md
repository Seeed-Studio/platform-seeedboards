# Zephyr framework local fixes (patches & overrides)

This directory carries local fixes applied on top of PlatformIO's
`framework-zephyr` package so that Seeed XIAO boards work on the current
Zephyr version. All fixes are **centrally registered** in `fixes.yml`;
`builder/frameworks/zephyr_fixes.py` reads it before the build and applies
the registered fixes to the framework package of the board being built.

## Directory layout

```
zephyr/
├── boards/           # board definitions (zephyr/boards/arm/<board>/); outside this mechanism
├── patches/          # patches (unified diff)
│   └── <board>/      #   one level per board
│       └── 0001-*.patch
├── overrides/        # overrides (whole files)
│   └── <board>/      #   one level per board; relative path below = target path inside the framework package
│       └── drivers/...
├── fixes.yml         # fix registry (single source of truth)
└── README.md         # this file
```

`<board>` = Zephyr board name（即 `zephyr/boards/arm/<同名>/` 的目录名，等于
`board.yml` 的 `board.name`），由 `platform.get_zephyr_board_name()` 解析。

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

## 加新板子

1. `platform.py` 的 `ZEPHYR_PACKAGE_BY_BOARD` 与 `ZEPHYR_BOARD_NAME_BY_BOARD` 各加一行。
2. 新建 `zephyr/patches/<board.name>/` 与 `zephyr/overrides/<board.name>/`（有修复才建）。
3. `fixes.yml` 加 `boards[<board.name>]` 节。

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
