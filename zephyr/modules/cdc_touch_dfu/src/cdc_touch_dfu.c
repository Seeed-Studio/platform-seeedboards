/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * Generic XIAO 1200-bps USB CDC bootloader trigger (ride-along).
 *
 * Brings up no USB stack of its own: boards/samples own the USB device
 * context(s) (board.c or the sample, per-board VID/PID). This module walks
 * the existing usbd_context section and registers one message callback per
 * context; when the host sets CDC ACM line coding to 1200 baud it hands
 * over to the board's bootloader backend:
 *
 *  - nRF54LM20 (retention boot-mode API): bootmode_set(BOOTLOADER) +
 *    cold reboot into the MCUboot firmware loader.
 *  - boards describing a uf2_dbl_tap device node (STM32C5): write
 *    the TinyUF2 double-tap magic and NVIC-reset into the UF2 bootloader.
 *
 * Merged from the former xiao_dfu_reset (nRF54LM20A V2/B) and
 * uf2_dfu_reset (STM32C5) modules; the physical double-tap reset remains
 * the hardware fallback on every board.
 */

#include <zephyr/device.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>
#include <zephyr/usb/usbd.h>

#define DFU_TRIGGER_BAUDRATE 1200U

#if DT_NODE_EXISTS(DT_NODELABEL(uf2_dbl_tap))
/* Board describes a TinyUF2 double-tap register node (STM32C5): take that
 * as the backend of record even if the retention stack is also compiled
 * in (the module Kconfig selects it for the nRF54LM20 boards). Zephyr 4.4
 * generates no DT_CHOSEN_* for custom chosen keys, hence the nodelabel.
 */
#include <cmsis_core.h>
#define DFU_BACKEND_TINYUF2 1
#define DFU_DBL_TAP_ADDR DT_REG_ADDR(DT_NODELABEL(uf2_dbl_tap))
#define DFU_DBL_TAP_MAGIC 0xf01669efUL
#elif defined(CONFIG_RETENTION_BOOT_MODE) && defined(CONFIG_REBOOT)
#include <zephyr/retention/bootmode.h>
#include <zephyr/sys/reboot.h>
#define DFU_BACKEND_BOOTMODE 1
#else
#error "cdc_touch_dfu: board has neither a uf2_dbl_tap node nor retention boot-mode"
#endif

static struct k_work dfu_trigger_work;
static volatile unsigned int dfu_ctx_count;

static void dfu_trigger_fn(struct k_work *work)
{
	ARG_UNUSED(work);

#if DFU_BACKEND_BOOTMODE
	int rc = bootmode_set(BOOT_MODE_TYPE_BOOTLOADER);

	printk("[cdc_dfu] 1200-bps touch: bootmode_set=%d\n", rc);
	if (rc != 0) {
		printk("[cdc_dfu] DFU reboot cancelled: boot mode was not retained\n");
		return;
	}
	printk("[cdc_dfu] rebooting into DFU loader\n");
	k_msleep(CONFIG_CDC_TOUCH_DFU_BOOTLOADER_TIMEOUT_MS);
	sys_reboot(SYS_REBOOT_COLD);
#elif DFU_BACKEND_TINYUF2
	volatile uint32_t *dbl_tap = (volatile uint32_t *)DFU_DBL_TAP_ADDR;

	/* Arm the double-tap magic; TinyUF2 checks it on the next boot. The
	 * write is ordered before the reset via DSB; SRAM content survives
	 * NVIC_SystemReset() (only power-on reset clears it).
	 */
	printk("[cdc_dfu] 1200-bps touch: entering UF2 bootloader\n");
	*dbl_tap = DFU_DBL_TAP_MAGIC;
	__DSB();
	k_msleep(CONFIG_CDC_TOUCH_DFU_BOOTLOADER_TIMEOUT_MS);
	NVIC_SystemReset();
#endif
}

static void dfu_msg_cb(struct usbd_context *const ctx, const struct usbd_msg *msg)
{
	uint32_t baud = 0U;

	ARG_UNUSED(ctx);
	if (msg->type != USBD_MSG_CDC_ACM_LINE_CODING) {
		return;
	}

	if (uart_line_ctrl_get(msg->dev, UART_LINE_CTRL_BAUD_RATE, &baud) == 0) {
		printk("[cdc_dfu] CDC line coding: baud=%u\n", baud);
		if (baud == DFU_TRIGGER_BAUDRATE) {
			k_work_submit(&dfu_trigger_work);
		}
	}
}

static int cdc_touch_dfu_init(void)
{
	unsigned int count = 0U;

	k_work_init(&dfu_trigger_work, dfu_trigger_fn);

	STRUCT_SECTION_FOREACH(usbd_context, ctx) {
		if (usbd_msg_register_cb(ctx, dfu_msg_cb) == 0) {
			count++;
		}
	}

	/* Zero contexts means the board/sample never brought USB up; the
	 * trigger stays unarmed and the double-tap fallback still works.
	 */
	dfu_ctx_count = count;
	printk("[cdc_dfu] armed on %u USB context(s)\n", count);
	return 0;
}
/* APPLICATION level: the board's own USB bring-up (board.c, same level,
 * board.cmake/board.yml ordering puts board.c first) has already created
 * the usbd_context instances by the time we walk the section.
 */
SYS_INIT(cdc_touch_dfu_init, APPLICATION, CONFIG_APPLICATION_INIT_PRIORITY);
