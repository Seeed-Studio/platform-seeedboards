/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * XIAO nRF54LM20B USB CDC 1200-bps DFU trigger.
 */

#include <zephyr/device.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/kernel.h>
#include <zephyr/retention/bootmode.h>
#include <zephyr/sys/printk.h>
#include <zephyr/sys/reboot.h>
#include <zephyr/usb/usbd.h>

#define DFU_TRIGGER_BAUDRATE 1200U

static struct k_work xiao_dfu_init_work;
static struct k_work xiao_dfu_debug_work;
static struct k_work xiao_dfu_trigger_work;
static volatile unsigned int xiao_dfu_ctx_count;
static volatile uint32_t xiao_dfu_last_type;
static volatile uint32_t xiao_dfu_last_baud;
static volatile int xiao_dfu_last_baud_rc;

static void xiao_dfu_init_fn(struct k_work *work)
{
	ARG_UNUSED(work);
	printk("[xiao_dfu] armed on %u USB context(s)\n", xiao_dfu_ctx_count);
}

static void xiao_dfu_debug_fn(struct k_work *work)
{
	ARG_UNUSED(work);
	printk("[xiao_dfu] CDC line coding: type=%u baud=%u rc=%d\n",
	       xiao_dfu_last_type, xiao_dfu_last_baud,
	       xiao_dfu_last_baud_rc);
}

static void xiao_dfu_trigger_fn(struct k_work *work)
{
	int rc;

	ARG_UNUSED(work);
	rc = bootmode_set(BOOT_MODE_TYPE_BOOTLOADER);
	printk("[xiao_dfu] 1200-bps touch: bootmode_set=%d\n", rc);
	if (rc != 0) {
		printk("[xiao_dfu] DFU reboot cancelled: boot mode was not retained\n");
		return;
	}

	printk("[xiao_dfu] rebooting into DFU loader\n");
	k_msleep(100);
	sys_reboot(SYS_REBOOT_COLD);
}

static void xiao_dfu_msg_cb(struct usbd_context *const ctx,
			    const struct usbd_msg *msg)
{
	uint32_t baud = 0U;
	int baud_rc = -ENOTSUP;

	ARG_UNUSED(ctx);
	if (msg->type != USBD_MSG_CDC_ACM_LINE_CODING) {
		return;
	}

	baud_rc = uart_line_ctrl_get(msg->dev, UART_LINE_CTRL_BAUD_RATE, &baud);
	xiao_dfu_last_type = (uint32_t)msg->type;
	xiao_dfu_last_baud = baud;
	xiao_dfu_last_baud_rc = baud_rc;
	k_work_submit(&xiao_dfu_debug_work);

	if (baud_rc == 0 && baud == DFU_TRIGGER_BAUDRATE) {
		k_work_submit(&xiao_dfu_trigger_work);
	}
}

static int xiao_dfu_init(void)
{
	unsigned int count = 0U;

	k_work_init(&xiao_dfu_init_work, xiao_dfu_init_fn);
	k_work_init(&xiao_dfu_debug_work, xiao_dfu_debug_fn);
	k_work_init(&xiao_dfu_trigger_work, xiao_dfu_trigger_fn);

	STRUCT_SECTION_FOREACH(usbd_context, ctx) {
		if (usbd_msg_register_cb(ctx, xiao_dfu_msg_cb) == 0) {
			count++;
		}
	}

	xiao_dfu_ctx_count = count;
	k_work_submit(&xiao_dfu_init_work);
	return 0;
}
SYS_INIT(xiao_dfu_init, APPLICATION, CONFIG_APPLICATION_INIT_PRIORITY);
