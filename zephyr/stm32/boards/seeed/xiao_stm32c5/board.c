/*
 * Copyright (c) 2026 Seeed Technology Co., Ltd.
 * SPDX-License-Identifier: Apache-2.0
 *
 * XIAO STM32C5 board USB bring-up (new USB device stack / UDC).
 *
 * The STM32C5 USB DRD FS peripheral is driven by Zephyr's standard
 * udc_stm32.c driver; its STM32C5 HAL2 backport (upstream PR #105957,
 * post-4.4.0) is carried as a board fix under this board's fixes/
 * directory. This file owns the USB identity (Seeed VID:PID 0x2886:0x00C5,
 * matching the TinyUF2 bootloader and boards/seeed-xiao-stm32c5.json
 * hwids) and brings up the device + CDC ACM class automatically at boot,
 * so samples get their USB console with no application code. The 1200-bps
 * bootloader trigger itself is the cdc_touch_dfu module's job (it rides
 * along on the contexts created here); the hardware double-tap reset
 * stays as the fallback.
 */

#include <zephyr/usb/usbd.h>

#include <zephyr/logging/log.h>
LOG_MODULE_REGISTER(xiao_stm32c5_usb, CONFIG_LOG_DEFAULT_LEVEL);

#if defined(CONFIG_XIAO_STM32C5_USB_AUTOBRINGUP)
USBD_DEVICE_DEFINE(xiao_stm32c5_usbd,
		   DEVICE_DT_GET(DT_NODELABEL(zephyr_udc0)),
		   CONFIG_XIAO_STM32C5_USB_VID, CONFIG_XIAO_STM32C5_USB_PID);
USBD_DESC_LANG_DEFINE(xiao_stm32c5_lang);
USBD_DESC_MANUFACTURER_DEFINE(xiao_stm32c5_mfr, "Seeed Studio");
USBD_DESC_PRODUCT_DEFINE(xiao_stm32c5_product, "XIAO STM32C5");
USBD_DESC_CONFIG_DEFINE(xiao_stm32c5_fs_cfg_desc, "FS Configuration");

/* Self-powered, 100 mA (max-power is in 2 mA units). */
USBD_CONFIGURATION_DEFINE(xiao_stm32c5_fs_config,
			  USB_SCD_SELF_POWERED, 50,
			  &xiao_stm32c5_fs_cfg_desc);

static int xiao_stm32c5_usb_init(void)
{
	int err;

	err = usbd_add_descriptor(&xiao_stm32c5_usbd, &xiao_stm32c5_lang);
	if (err) {
		return err;
	}
	err = usbd_add_descriptor(&xiao_stm32c5_usbd, &xiao_stm32c5_mfr);
	if (err) {
		return err;
	}
	err = usbd_add_descriptor(&xiao_stm32c5_usbd, &xiao_stm32c5_product);
	if (err) {
		return err;
	}

	err = usbd_add_configuration(&xiao_stm32c5_usbd, USBD_SPEED_FS,
				     &xiao_stm32c5_fs_config);
	if (err) {
		return err;
	}

	/* Register every enabled class (typically: CDC ACM for console). */
	err = usbd_register_all_classes(&xiao_stm32c5_usbd, USBD_SPEED_FS, 1,
					NULL);
	if (err) {
		return err;
	}

	/* CDC ACM spans multiple interfaces -> advertise via IAD code triple. */
	usbd_device_set_code_triple(&xiao_stm32c5_usbd, USBD_SPEED_FS,
				    USB_BCC_MISCELLANEOUS, 0x02, 0x01);

	err = usbd_init(&xiao_stm32c5_usbd);
	if (err) {
		return err;
	}

	err = usbd_enable(&xiao_stm32c5_usbd);
	if (err) {
		return err;
	}

	LOG_INF("USB device up (Seeed VID:PID, CDC ACM console)");
	return 0;
}
/* APPLICATION level: the UDC driver (POST_KERNEL) is initialised first;
 * the cdc_touch_dfu trigger arms itself at the same level afterwards.
 * The whole block follows XIAO_STM32C5_USB_AUTOBRINGUP: compiled out when
 * a sample turns the USB stack off (power builds) AND when a sample owns
 * its full USB stack (gs_usb builds a second context on zephyr_udc0 --
 * a board context here would double-init the controller and swallow the
 * sample's classes).
 */
SYS_INIT(xiao_stm32c5_usb_init, APPLICATION,
	 CONFIG_APPLICATION_INIT_PRIORITY);
#endif /* CONFIG_XIAO_STM32C5_USB_AUTOBRINGUP */
