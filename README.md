# Seeed Xiao Series: development platform for [PlatformIO](http://platformio.org)

[![Build Status](https://travis-ci.org/platformio/platform-atmelsam.svg?branch=develop)](https://travis-ci.org/platformio/platform-atmelsam)
[![Build status](https://ci.appveyor.com/api/projects/status/dj1c3b2d6fyxkoxq/branch/develop?svg=true)](https://ci.appveyor.com/project/ivankravets/platform-atmelsam/branch/develop)

The [Seeed Studio XIAO Series](https://wiki.seeedstudio.com/SeeedStudio_XIAO_Series_Introduction/) is a collection of thumb-sized, powerful microcontroller units (MCUs) tailor-made for space-conscious projects requiring high performance and wireless connectivity.

* [Home](http://platformio.org/platforms/seeedxiao) (home page in PlatformIO Platform Registry)
* [Documentation](http://docs.platformio.org/page/platforms/seeedxiao.html) (advanced usage, packages, boards, frameworks, etc.)

# Usage

1. [Install PlatformIO](http://platformio.org)
2. Create PlatformIO project and configure a platform option in [platformio.ini](http://docs.platformio.org/page/projectconf.html) file:

## Stable version

```ini
[env:stable]
platform = Seeed Studio
board = ...
framework = arduino
...
```

## Development version

```ini
[env:development]
platform = https://github.com/Seeed-Studio/platform-seeedboards.git
board = ...
framework = arduino
...
```

# Configuration

Please navigate to [documentation](http://docs.platformio.org/page/platforms/seeedxiao.html).
