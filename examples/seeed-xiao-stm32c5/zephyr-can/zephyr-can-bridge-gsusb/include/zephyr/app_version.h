/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * Static fallback for zephyr/app_version.h. Under the PlatformIO Zephyr build
 * the app_version.h generation step (framework CMakeLists.txt guard
 * `if(EXISTS ${APPLICATION_SOURCE_DIR}/VERSION)`) does not fire, so provide
 * the APP_VERSION_* macros statically from the CANnectivity VERSION (1.4.0).
 * Mirrors the macro names from Zephyr's version.h.in (VERSION_TYPE=APP). If
 * Zephyr's generation is later fixed, the generated header (same content) is
 * found first and this is a harmless shadow.
 */
#ifndef _APP_VERSION_H_
#define _APP_VERSION_H_

#define APPVERSION                   0x01040000U
#define APP_VERSION_NUMBER           0x010400U
#define APP_VERSION_MAJOR            1
#define APP_VERSION_MINOR            4
#define APP_PATCHLEVEL               0
#define APP_TWEAK                    0
#define APP_EXTRAVERSION             ""
#define APP_VERSION_STRING           "1.4.0"
#define APP_VERSION_EXTENDED_STRING  "1.4.0+0"
#define APP_VERSION_TWEAK_STRING     "1.4.0+0"

#endif /* _APP_VERSION_H_ */
