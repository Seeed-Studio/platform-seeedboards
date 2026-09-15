# Zephyr local content (boards, modules, fixes)

This directory carries everything Zephyr needs beyond the stock
`framework-zephyr-*` package: board definitions, bundled west modules, and
per-board fixes for upstream gaps. Applied before the build by
`builder/frameworks/zephyr.py` + `builder/frameworks/zephyr_fixes.py`.

## Layout

```
zephyr/
├── boards/arm/<board>/          # board definition (upstream-style: board.yml,
│   │                            # dts/dtsi, Kconfig, board.cmake, defconfig)
│   └── fixes/                   # this board's fixes for the framework package
│       ├── fixes.baseline       # "<target> <sha256>" of the pristine upstream
│       │                        # file each fix was cut against
│       ├── <target-path>        # full-file override (provenance in header)
│       └── <target-path>.patch  # unified-diff patch (idempotent)
├── modules/<name>/              # bundled west modules (copied per build)
├── overrides/<board>/           # (removed -- superseded by fixes/)
└── patches/<board>/             # (removed -- superseded by fixes/)
```

A fix file's location inside `fixes/` IS its target path inside the
framework package -- the directory is the registration. There is no
registry file. Every fix file carries a header comment with the upstream
link, the validated Zephyr version, and its exit condition.

## Workflows

**Add a fix**: pick the mechanism (small focused change -> `.patch`; whole
file backport -> override), drop the file at `fixes/<framework-path>`[`.patch`]
under the board dir, and add a `fixes.baseline` line with the pristine
target's sha256 (compute from a fresh extraction of the pinned tarball).
No builder code changes.

**Remove a fix** (upstreamed / no longer needed): delete the file and its
baseline line. The first build after removal confirms the upstream tree is
sufficient.

**Zephyr framework upgrade**: the new tarball's files will not match
`fixes.baseline` -- overrides warn loudly and patch hunks fail with
baseline-drift context on the first build. Re-evaluate each fix: upstreamed
-> delete; still needed -> refresh the file against the new tree and update
its baseline sha.

**Consistency** is enforced offline by `scripts/ci/verify_zephyr_routing.py`
(board -> package -> boards/arm chain closed; baseline <-> fix file
two-way correspondence), wired into `.github/workflows/ci-verify.yml`.
