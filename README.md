# Seeed Xiao Series: development platform for [PlatformIO](http://platformio.org)

[![Build Status](https://travis-ci.org/platformio/platform-atmelsam.svg?branch=develop)](https://travis-ci.org/platformio/platform-atmelsam)
[![Build status](https://ci.appveyor.com/api/projects/status/dj1c3b2d6fyxkoxq/branch/develop?svg=true)](https://ci.appveyor.com/project/ivankravets/platform-atmelsam/branch/develop)

The [Seeed Studio XIAO Series](https://wiki.seeedstudio.com/SeeedStudio_XIAO_Series_Introduction/) is a collection of thumb-sized, powerful microcontroller units (MCUs) tailor-made for space-conscious projects requiring high performance and wireless connectivity.

* [Home](http://platformio.org/platforms/seeedxiao) (home page in PlatformIO Platform Registry)
* [Documentation](http://docs.platformio.org/page/platforms/seeedxiao.html) (advanced usage, packages, boards, frameworks, etc.)

## Usage

1. [Install PlatformIO](http://platformio.org)
2. Create PlatformIO project and configure a platform option in [platformio.ini](http://docs.platformio.org/page/projectconf.html) file:

### Stable version

```ini
[env:stable]
platform = Seeed Studio
board = ...
framework = arduino
...
```

### Development version

```ini
[env:development]
platform = https://github.com/Seeed-Studio/platform-seeedboards.git
board = ...
framework = arduino
...
```

## Configuration

Please navigate to [documentation](http://docs.platformio.org/page/platforms/seeedxiao.html).

## Factory Reset for XIAO nRF54L15

For XIAO nRF54L15 boards, a factory reset script is provided to recover the board from a bad state (e.g., when it's can not upload due to the internal NVM write protection). This script will perform a mass erase of the flash and program a factory firmware.

### Location

The scripts are located in the `scripts/factory_reset/` directory.

### Usage

The script will automatically create and manage a local Python virtual environment to install the necessary tools, so it can be run out-of-the-box.

*   **For Windows:**
    Navigate to the `scripts/factory_reset` directory and run:
    ```shell
    .\factory_reset.bat
    ```

*   **For Linux and macOS:**
    Navigate to the `scripts/factory_reset` directory and run:
    ```shell
    bash factory_reset.sh
    ```
