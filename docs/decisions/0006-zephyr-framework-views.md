# ADR-0006: Per-build Zephyr framework views

## Context

ADR-0003 applies board fixes by copying overrides into, and patching, the
installed `framework-zephyr-*` package. That worked, but it makes the global
PlatformIO package cache a mutable, shared build directory:

- `seeed-xiao-stm32c5` and `seeed-xiao-nrf54lm20a{,b}` all use
  `framework-zephyr-nrf54lm20`; a fix applied for one board stays in the
  cache for the next board and for any other project on the machine;
- `fixes.baseline` is supposed to describe pristine upstream content, but a
  second build sees the first build's overrides;
- concurrent builds (or a killed build) can race or leave a half-patched
  package.

The package is also large (about 4.4 GB including west dependencies), so a
naive per-build `copytree` is not acceptable.

## Decision

1. The installed package stays read-only. Before a Zephyr build,
   `builder/board_build/zephyr/zephyr_view.py` creates a **framework view**
   under `$PROJECT_CORE_DIR/zephyr-views/<package>-<board>-<key>` and the
   build uses that directory as `FRAMEWORK_DIR`.
2. The view is a hardlink copy (`os.link`, falling back to `copy2`) of the
   package. Hardlinks share file data, so a 4.4 GB package costs metadata,
   not 4.4 GB per board; west dependencies already present in the package
   are reused.
3. The key is a digest of the package version, the board directory
   (`zephyr/boards/arm/<board>`), `zephyr/modules`, the platform's
   `builder/board_build/zephyr` code and the board name. Any input change
   creates a new view; a matching view is reused.
4. Every repository write into a view is atomic
   (`tempfile` + `os.replace`) so a hardlinked source file is never
   truncated in place: Zephyr fixes, board copies, `.west/config`, the
   framework build-script patches and the DFU module provisioning all go
   through `zephyr_view.atomic_write_text` / `atomic_copy`.
5. The upstream `platformio-build.py` hardcodes
   `FRAMEWORK_DIR = platform.get_package_dir(...)`; the view patches that
   line to derive the directory from `__file__`, so CMake, signing and
   module discovery all use the view.
6. `PIO_ZEPHYR_VIEW=0` is an explicit escape hatch for debugging. It
   restores the old in-place behavior and must not be used in CI.
7. Views are never deleted automatically during a build. They are cache:
   remove `$PROJECT_CORE_DIR/zephyr-views` to reclaim directory metadata
   (the package data is shared by hardlinks).

## Consequences

- Board/project builds no longer contaminate each other or the registry
  package; `fixes.baseline` can be compared against pristine content on
  every build.
- A first build pays a hardlink walk; subsequent builds with the same key
  reuse the view. Filesystems without hardlinks fall back to copying (with
  the expected cost).
- The upstream build script is patched in the view, not in the package, so
  a package update cannot silently lose the patch.
- ADR-0003's fixes mechanism is unchanged in content and semantics; only
  the target of the writes changes.

## Validation

- `tests/test_zephyr_view.py` proves a view write does not touch the
  source, key changes create a new view, and atomic writes preserve the
  original inode/content.
- T0 gates (`verify_zephyr_routing`, `verify_platform`) plus the Zephyr
  matrix; hardware upload remains T3 and is never claimed without a device.

## Related files

- `docs/decisions/0003-fixes-mechanism.md`
- `builder/board_build/zephyr/zephyr_view.py`
- `builder/board_build/zephyr/zephyr_framework.py`
- `builder/board_build/zephyr/zephyr_fixes.py`