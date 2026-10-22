# Authoring: adding a board or a chip family

This is the practical checklist behind `AGENTS.md`, ADR-0001 (registry),
ADR-0002 (package slots), ADR-0003 (fixes) and ADR-0006 (framework views).
Read the relevant ADR before changing routing, packages, fixes or CI.

## Layer map

| Layer | Location | Rule |
| --- | --- | --- |
| Board facts | `boards/<board-id>.json` | data only; no behavior |
| Family behavior | `families/<family>.py` | one `ChipFamily` subclass |
| Family build scripts | `builder/board_build/<family>/` | family-owned SCons code |
| Package declarations | `platform.json` | one optional slot per name |
| Zephyr fixes | `zephyr/boards/arm/<board>/fixes/` | directory is the registry |
| Regression demos | `examples/<demo>/platformio.ini` | one env per board/framework |
| Gates | `scripts/ci/verify_*.py` | fail fast, name the file/rule |

## Add a board to an existing family

### 1. Manifest

Create `boards/<board-id>.json`. Minimum facts:

- `name`, `url`, `vendor`;
- `build.chip_family` — must be a registered `family_id`;
- `build.mcu`;
- `frameworks` — subset of `arduino`, `zephyr`, `espidf`;
- `upload.protocol` and a non-empty `upload.protocols` containing it;
- `debug` fields needed by the family's `inject_debug_tools`:
  `jlink_device`, `openocd_target`, `openocd_chipname`,
  `default_tools`, `onboard_tools`, as applicable.

Per-framework routing keys:

```jsonc
"build": {
  "chip_family": "nrf",
  "arduino": {"package": "framework-arduinoadafruitnrf52", "ldscript": "..."},
  "zephyr": {
    "package": "framework-zephyr-nrf54lm20",
    "board_name": "xiao_nrf54lm20a",
    "variant": "xiao_nrf54lm20a@2.0.0/nrf54lm20a/cpuapp",
    "masquerade": "nordicnrf52",
    "bootloader": {"header_len": "0x800", "...": "..."}
  }
}
```

Rules enforced by `verify_boards.py` / `verify_platform.py`:

- every `build.<framework>.package` is declared in `platform.json`;
- `build.zephyr.variant` derives the same name as `build.zephyr.board_name`;
- `nrfutil-mcumgr` requires `upload.cdc.app_vidpid` and
  `upload.cdc.loader_vidpids` (`UPPER:UPPER` hex);
- `extra_flags` lives under `build`, never at the manifest top level;
- `upload.protocol` must be listed in `upload.protocols`.

### 2. Demos

Add an `[env:<board-id>]` to every demo of each declared framework
(`examples/arduino-blink`, `examples/arduino-uart`, `examples/zephyr-blink`,
...). At minimum `verify_examples.py` requires one env per
board/framework pair; the convention is blink + uart for Arduino/Zephyr and
blink for ESP-IDF. Canonical demos currently live in `arduino-wifiscan`,
`arduino-usb-keyboard`, `arduino-rmt-blink`, `zephyr-ble`, `zephyr-adc`,
`zephyr-gpio`, `zephyr-button`, `zephyr-pwm`, `zephyr-battery`,
`zephyr-imu`, `zephyr-tapwake`, `zephyr-gps`, `zephyr-lowpower`,
`zephyr-npm1300-register-read`, `zephyr-rfsw`, `zephyr-ble-lbs`,
expansion-base RTC/OLED, both e-paper sizes, and the STM32C5 CAN GPIO-reuse
sample. Board-specific hardware samples may live at
`examples/<board-id>/<sample>/`; see `docs/example-parity.md`.

### 3. Snapshot and validation

Add the board id to `SUPPORTED_BOARD_IDS` in `scripts/ci/verify_boards.py`
(the failure message says so), then run:

```bash
pytest tests/ -q
python scripts/ci/verify_boards.py
python scripts/ci/verify_platform.py
python scripts/ci/verify_examples.py
python scripts/ci/build_examples.py --framework arduino --clean \
    --only-env <board-id>
```

The first build is a real compile; do not claim it from `compileall` alone.

## Add a family

### 1. Family module

Create `families/<family>.py`:

```python
from families.base import ChipFamily

class MyFamily(ChipFamily):
    family_ids = ("myfamily",)

    def required_packages(self, board, variables=None): ...
    def build_flags(self, board): ...
    def upload_protocol(self, board): ...
    def inject_debug_tools(self, board): ...
    def configure_debug_session(self, debug_config): ...
    def build_script(self, env, board): ...
```

Optional hooks: `arduino_script`, `zephyr_script`, `configure_env`,
`get_build_hooks`, `post_activate_packages`.

Add one import line to `families/__init__.py`. `platform.py` and
`builder/main.py` must stay untouched; `verify_core.py` enforces zero-string
routing.

### 2. Packages

Declare every package in `platform.json`, `optional: true` by default. The
family activates packages per board in `required_packages` and may narrow a
version with evidence in a comment (ADR-0002). Never delete packages from
`self.packages`; return only what this board needs.

If a package exists in two incompatible shapes, give it a distinct name
(ADR-0002), never a silent per-family override on a shared slot.

### 3. Builder directory and boards

- put family SCons code in `builder/board_build/<family>/`;
- `build_script` points at the family entry;
- `arduino_script` / `zephyr_script` point at the framework entry;
- add boards through the board checklist above.

### 4. Validate

```bash
pytest tests/ -q
python scripts/ci/verify_boards.py
python scripts/ci/verify_core.py
python scripts/ci/verify_zephyr_routing.py
python scripts/ci/verify_platform.py
python scripts/ci/build_examples.py --framework <framework> --clean
```

## Zephyr fixes and framework views

- Fix files live in `zephyr/boards/arm/<board>/fixes/`; the path inside
  `fixes/` is the target path in the framework package.
- `.patch` = unified diff; plain file = whole-file override with a
  provenance header.
- `fixes.baseline` = pristine upstream sha256 per target. Recompute from a
  **fresh extraction** of the pinned tarball, never from the installed
  package or a build view (ADR-0006).
- Builds use a per-build hardlink view under
  `$PLATFORMIO_CORE_DIR/zephyr-views`; the installed package is read-only.
- Inspect/prune cache:

```bash
python scripts/ci/clean_zephyr_views.py --dry-run
python scripts/ci/clean_zephyr_views.py --keep 3
```

Hardlink-capable filesystems make first builds fast; when hardlinks are
unavailable the build logs a warning and copies the package instead.

## Anti-patterns

- `if "esp32" in board.id` in `platform.py` or `builder/main.py` — use
  `build.chip_family` and the registry.
- deleting entries from `platform.packages` in a family — use
  `required_packages`.
- top-level `extra_flags` — PlatformIO reads `build.extra_flags`.
- editing the installed framework package or a view by hand — fixes belong
  in the board directory; views are disposable.
- committing generated `sdkconfig.*` — only `sdkconfig.defaults.*` is source.
- weakening a gate to make a board pass — fix the manifest/data or document
  the exception in an ADR.

## Where to look

- ADRs: `docs/decisions/`
- Skills: `.agents/skills/{add-board,add-family,validate,zephyr-fixes,sync-upstream}/`
- Gates: `scripts/ci/`
- CI: `.github/workflows/`