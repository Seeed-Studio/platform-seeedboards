/*
 * Copyright (c) 2026 Seeed Technology Co., Ltd.
 * SPDX-License-Identifier: Apache-2.0
 *
 * TinyUF2 bootloader auto-trigger for XIAO STM32C5.
 *
 * When the USB host opens the CDC ACM port at 1200 baud, this module
 * writes the TinyUF2 double-tap magic to the top of SRAM and resets.
 * The bootloader sees the magic on the next boot and enters DFU mode,
 * eliminating the need to manually double-tap the RESET button.
 *
 * USB is driven by Zephyr's standard UDC + CDC ACM stack (udc_stm32.c,
 * patched for the STM32C5 HAL2 API — see zephyr/overrides/). This module
 * only registers the line-coding (DTE-rate) callback that detects the
 * 1200-baud touch and arms the reset; it does not touch the USB hardware.
 *
 * Magic register: 0x2003FFFC (top of 256 KB SRAM minus 4 bytes).
 * Magic value:    0xf01669ef (DBL_TAP_MAGIC, 32-bit register size).
 */

#ifndef UF2_DFU_RESET_H_
#define UF2_DFU_RESET_H_

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/* --- TinyUF2 protocol constants (must match bootloader) --- */

/** Double-tap magic value that tells TinyUF2 to stay in DFU mode. */
#define UF2_DBL_TAP_MAGIC        0xf01669efUL

/** Quick-boot magic — skip the double-tap delay and boot the app. */
#define UF2_DBL_TAP_MAGIC_QUICK_BOOT 0xf02669efUL

/**
 * Address of the double-tap register in SRAM.
 * STM32C5A3 has 256 KB SRAM starting at 0x20000000.
 * The TinyUF2 linker reserves the last 4 bytes:
 *   _board_dfu_dbl_tap = ORIGIN(RAM) + LENGTH(RAM)
 *                      = 0x20000000 + (0x40000 - 4)
 *                      = 0x2003FFFC
 *
 * This address survives NVIC_SystemReset() because SRAM is not
 * re-initialised by a soft reset (only a power-on reset clears it).
 */
#define UF2_DBL_TAP_REG_ADDR     0x2003FFFCUL

/** Baud rate that triggers bootloader entry. */
#define UF2_DFU_TRIGGER_BAUDRATE 1200U

/**
 * @brief Enter TinyUF2 bootloader immediately.
 *
 * Writes DBL_TAP_MAGIC and performs NVIC_SystemReset().
 * The bootloader will see the magic and enter DFU mode.
 */
void uf2_enter_bootloader(void);

#ifdef __cplusplus
}
#endif

#endif /* UF2_DFU_RESET_H_ */
