# platform_cfg/

Per-architecture package and debug-tool configuration.

`platform.py` resolves a board's architecture family from its board id,
then dynamically imports the matching `<arch>_cfg.py` from this directory
and calls the three hook functions below **by naming convention**
(`import_module` + `getattr`). Each hook receives the `SeeedstudioPlatform`
instance as `self`, so every file here behaves like an extension of the
platform class.

## Architecture detection (in `platform.py`)

| Architecture   | Selected when                                    |
| -------------- | ------------------------------------------------ |
| `esp`          | `"esp32"` appears in the board id                |
| `nrf`          | `"nrf"` appears in the board id                  |
| `samd`         | `"samd"` appears in the board id                 |
| `siliconlab`   | `"mg24"` appears in the board id                 |
| `stm32`        | `"stm32"` appears in the board id                |
| `renesas`      | board id is `seeed-xiao-ra4m1`                   |
| `rpi`          | board id is `seeed-xiao-rp2040` / `rp2350`       |

## The three hooks (every `<arch>_cfg.py` defines all of them)

| Hook | Called from | Purpose |
| ---- | ----------- | ------- |
| `configure_<arch>_default_packages(self, variables, targets)` | `SeeedstudioPlatform.configure_default_packages` | The tool-selection layer: flips `optional` / `version` flags and deletes entries in `self.packages` so only the tools this build actually needs are installed. Inputs: the board manifest (`build.mcu`, `build.bsp.name`, ...), the selected frameworks (`variables["pioframework"]`), the upload protocol, and the active targets (e.g. `bootloader` / `erase` pull in `tool-nrfjprog`). |
| `_add_<arch>_default_debug_tools(self, board)` | `SeeedstudioPlatform._add_dynamic_options` | Registers the board's default debug tools (probe protocols, server options). |
| `configure_<arch>_debug_session(self, debug_config)` | `SeeedstudioPlatform.configure_debug_session` | Adjusts the debug session configuration (GDB server / client options). |

## Division of responsibility

Keep this layer thin and put data where it belongs:

- **Board-intrinsic, static facts** belong in the board manifest
  (`boards/*.json`): `build.mcu`, `build.bsp.name`, `build.zephyr.package`,
  `upload.cdc.*`, ... — anything a board can declare once and forever.
- **Session-dependent rules** belong here: the chosen framework, the
  active targets, `upload_protocol`, user variables. A static manifest
  cannot express "only when ...".
- **The package menu and default flags** live in `platform.json`
  (`packages` section). These files only pick from that menu; they do
  not declare packages.

## Conventions

- Names are load-bearing: `platform.py` resolves both the module and the
  functions by string. Renaming a file or hook here breaks dispatch at
  runtime.
- A new architecture family needs (1) a detection rule in `platform.py`
  at both dispatch sites, and (2) a new `<arch>_cfg.py` with all three
  hooks.
- A missing hook currently fails softly (dispatch prints an error and
  continues). Do not rely on that — define all three.
