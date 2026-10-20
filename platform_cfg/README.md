# platform_cfg/

Per-family package and debug-tool configuration, one `FamilyConfig`
subclass per architecture family.

`platform.py` resolves a board's family from the `build.family` key in its
board manifest (`SeeedstudioPlatform.get_board_family()`), then looks the
family up in the `FAMILY_CONFIGS` registry (`platform_cfg/__init__.py`)
and calls the three hook methods on a fresh config instance. The instance
carries the platform (`self.platform`), so subclasses read packages and
board configs through `self.platform.packages` / `self.board_config(...)`
or the shared base helpers.

## Families

| Family         | Class            | Board manifest `build.family` |
| -------------- | ---------------- | ----------------------------- |
| `esp`          | `EspConfig`      | all ESP32 boards              |
| `nrf`          | `NrfConfig`      | nRF52 / nRF54 boards          |
| `rpi`          | `RpiConfig`      | RP2040 / RP2350 boards        |
| `renesas`      | `RenesasConfig`  | RA4M1                         |
| `samd`         | `SamdConfig`     | SAMD21                        |
| `siliconlab`   | `SiliconlabConfig` | MG24                        |
| `stm32`        | `Stm32Config`    | STM32                         |

## The three hooks (every subclass defines all of them)

| Hook | Called from | Purpose |
| ---- | ----------- | ------- |
| `configure_default_packages(variables, targets)` | `SeeedstudioPlatform.configure_default_packages` | The tool-selection layer: flips `optional` / `version` flags and deletes entries in `self.platform.packages` so only the tools this build actually needs are installed. Inputs: the board manifest (`build.mcu`, `build.bsp.name`, ...), the selected frameworks (`variables["pioframework"]`), the upload protocol, and the active targets (e.g. `bootloader` / `erase` pull in `tool-nrfjprog`). |
| `add_default_debug_tools(board)` | `SeeedstudioPlatform._add_dynamic_options` | Registers the board's default debug tools (probe protocols, server options). |
| `configure_debug_session(debug_config)` | `SeeedstudioPlatform.configure_debug_session` | Adjusts the debug session configuration (GDB server / client options). |

The base class (`base.py`) raises `NotImplementedError` for any hook a
subclass forgets to override; an unknown `build.family` value raises
`ValueError` listing the valid families at dispatch time.

## Shared helpers (`base.FamilyConfig`)

- `mark_required(*names)` — flip `optional = False` for packages present
  on the platform menu
- `pin_version(package, version)` / `drop_package(package)`
- `board_config(board)` — delegate to the platform
- `prune_jlink(variables)` — drop `tool-jlink` unless the build variables
  or the board manifest ask for it (shared by stm32 / nrf / rpi)

## Division of responsibility

Keep this layer thin and put data where it belongs:

- **Board-intrinsic, static facts** belong in the board manifest
  (`boards/*.json`): `build.mcu`, `build.bsp.name`, `build.zephyr.package`,
  `build.family`, `upload.cdc.*`, ... — anything a board can declare once
  and forever.
- **Session-dependent rules** belong here: the chosen framework, the
  active targets, `upload_protocol`, user variables. A static manifest
  cannot express "only when ...".
- **The package menu and default flags** live in `platform.json`
  (`packages` section). These classes only pick from that menu; they do
  not declare packages.

## Conventions

- `self.platform.packages` is shared across families in one process:
  only touch what your family needs and never delete another family's
  packages (`tests/test_cross_family_isolation.py`).
- A new architecture family needs (1) `build.family` in the new board
  manifests, and (2) a new `<family>_cfg.py` subclass plus one
  `FAMILY_CONFIGS` entry in `platform_cfg/__init__.py` — a missing
  registry entry fails loudly with the list of valid families.
