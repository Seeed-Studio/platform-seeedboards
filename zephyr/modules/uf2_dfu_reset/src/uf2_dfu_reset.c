/*
 * Copyright (c) 2026 Seeed Technology Co., Ltd.
 * SPDX-License-Identifier: Apache-2.0
 *
 * TinyUF2 1200-bps bootloader auto-trigger for XIAO STM32C5.
 *
 * USB is driven by Zephyr's standard UDC + CDC ACM stack (the udc_stm32.c
 * driver is HAL2-patched for STM32C5 — carried under zephyr/overrides/).
 * This module brings up the USB device and CDC ACM class automatically at
 * boot (SYS_INIT, no application code needed) and registers a USBD message
 * callback. When the host opens the CDC ACM port at 1200 baud, the
 * SET_LINE_CODING (USBD_MSG_CDC_ACM_LINE_CODING) callback reads the DTE
 * rate and, on 1200, writes the TinyUF2 double-tap magic and resets into
 * the bootloader.
 */

#include "uf2_dfu_reset.h"

#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/usb/usbd.h>
#include <cmsis_core.h>
#include <zephyr/logging/log.h>
LOG_MODULE_REGISTER(uf2_dfu_reset, LOG_LEVEL_INF);

/* --- USB device context & descriptors (Seeed XIAO STM32C5) --- */
/* Seeed VID:PID 0x2886:0x00C5 — matches the TinyUF2 bootloader (board
 * hwids) so the host sees a consistent identity across app and bootloader.
 */
USBD_DEVICE_DEFINE(uf2_usbd,
		   DEVICE_DT_GET(DT_NODELABEL(zephyr_udc0)),
		   0x2886, 0x00C5);
USBD_DESC_LANG_DEFINE(uf2_lang);
USBD_DESC_MANUFACTURER_DEFINE(uf2_mfr, "Seeed Studio");
USBD_DESC_PRODUCT_DEFINE(uf2_product, "XIAO STM32C5");
USBD_DESC_CONFIG_DEFINE(uf2_fs_cfg_desc, "FS Configuration");

/* Self-powered, 100 mA (max-power is in 2 mA units). */
USBD_CONFIGURATION_DEFINE(uf2_fs_config,
			  USB_SCD_SELF_POWERED, 50, &uf2_fs_cfg_desc);

/* USBD message callback: detect the 1200-bps touch via CDC ACM line coding. */
static void uf2_msg_cb(struct usbd_context *const ctx, const struct usbd_msg *msg)
{
	if (msg->type == USBD_MSG_CDC_ACM_LINE_CODING) {
		uint32_t baud = 0U;

		if (uart_line_ctrl_get(msg->dev, UART_LINE_CTRL_BAUD_RATE, &baud) == 0 &&
		    baud == UF2_DFU_TRIGGER_BAUDRATE) {
			LOG_INF("1200 baud touch detected, entering UF2 bootloader");
			uf2_enter_bootloader();
		}
	}
}

/* Bring up USB + CDC ACM and arm the 1200-bps trigger. APPLICATION level so
 * the UDC driver (POST_KERNEL) is already initialised when we run.
 */
static int uf2_dfu_usb_init(void)
{
	int err;

	err = usbd_add_descriptor(&uf2_usbd, &uf2_lang);
	if (err) {
		return err;
	}
	err = usbd_add_descriptor(&uf2_usbd, &uf2_mfr);
	if (err) {
		return err;
	}
	err = usbd_add_descriptor(&uf2_usbd, &uf2_product);
	if (err) {
		return err;
	}

	err = usbd_add_configuration(&uf2_usbd, USBD_SPEED_FS, &uf2_fs_config);
	if (err) {
		return err;
	}

	/* Register every enabled class (here: CDC ACM only). */
	err = usbd_register_all_classes(&uf2_usbd, USBD_SPEED_FS, 1, NULL);
	if (err) {
		return err;
	}

	/* CDC ACM spans multiple interfaces → advertise via IAD code triple. */
	usbd_device_set_code_triple(&uf2_usbd, USBD_SPEED_FS,
				    USB_BCC_MISCELLANEOUS, 0x02, 0x01);

	err = usbd_msg_register_cb(&uf2_usbd, uf2_msg_cb);
	if (err) {
		return err;
	}

	err = usbd_init(&uf2_usbd);
	if (err) {
		return err;
	}

	err = usbd_enable(&uf2_usbd);
	if (err) {
		return err;
	}

	LOG_INF("USB CDC ACM up, 1200-bps UF2 trigger armed");

	return 0;
}
SYS_INIT(uf2_dfu_usb_init, APPLICATION, CONFIG_APPLICATION_INIT_PRIORITY);

void uf2_enter_bootloader(void)
{
	volatile uint32_t *dbl_tap = (volatile uint32_t *)UF2_DBL_TAP_REG_ADDR;

	/* Arm the double-tap magic; the bootloader checks this on next boot. */
	*dbl_tap = UF2_DBL_TAP_MAGIC;

	/* Ensure the write lands before the reset takes effect. */
	__DSB();

	/* Soft reset preserves SRAM, so the magic survives into the bootloader. */
	NVIC_SystemReset();
}
