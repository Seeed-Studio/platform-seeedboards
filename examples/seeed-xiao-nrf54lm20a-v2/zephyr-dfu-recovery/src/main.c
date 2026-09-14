/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * XIAO nRF54LM20A V2 USB DFU recovery tour.
 *
 * The V2 board ships the same three-image recovery scheme as the XIAO
 * nRF54LM20B: an MCUboot firmware-updater bootloader plus a USB MCUmgr
 * loader image in slot1. Applications are signed (Ed25519, PURE TLV) and
 * updated over USB -- an app can never brick the board.
 *
 * This demo prints a banner describing the three DFU entry paths, blinks
 * the blue LED as a heartbeat, and logs a counter so the USB CDC ACM
 * console (the app CDC enumerates as 0x2886:0x8068) stays observable.
 *
 * DFU entry paths (all end in the slot1 loader, 0x2886:0x0068):
 *   1. Automatic  -- `pio run -t upload` touches the app CDC at 1200 bps;
 *                    the xiao_dfu_reset module (on by default) records the
 *                    boot-mode in retained GPREGRET and cold-reboots into
 *                    the loader, then the upload continues.
 *   2. Manual     -- hold BTN (the back-pad button, P0.09) while pressing
 *                    RESET; MCUboot detects the GPIO entrance and chains
 *                    the loader.
 *   3. Empty slot -- with no valid application in slot0, MCUboot chains
 *                    the loader by itself (NO_APPLICATION mode), so a
 *                    crashed or erased app is always recoverable.
 */

#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>
#include <zephyr/drivers/gpio.h>

/* Blue LED heartbeat (aliases: led0=blue, led1=red, led2=green) */
#define LED_NODE DT_ALIAS(led0)
#if !DT_NODE_HAS_STATUS(LED_NODE, okay) || !DT_NODE_HAS_PROP(LED_NODE, gpios)
#error "Unsupported board: led0 (blue) alias is not defined"
#endif

static const struct gpio_dt_spec led = GPIO_DT_SPEC_GET(LED_NODE, gpios);

static void print_banner(void)
{
	printk("\n");
	printk("==============================================\n");
	printk(" XIAO nRF54LM20A V2 - USB DFU recovery demo\n");
	printk("==============================================\n");
	printk(" App CDC : USB serial, VID:PID 2886:8068\n");
	printk(" Loader  : DFU mode,     VID:PID 2886:0068\n");
	printk(" Firmware update paths:\n");
	printk("  1. pio run -t upload  (1200-bps touch, automatic)\n");
	printk("  2. Hold BTN (P0.09) + press RESET\n");
	printk("  3. No valid app in slot0 -> loader starts by itself\n");
	printk("==============================================\n");
}

int main(void)
{
	if (!gpio_is_ready_dt(&led)) {
		printk("blue LED not ready\n");
		return 0;
	}

	gpio_pin_configure_dt(&led, GPIO_OUTPUT_INACTIVE);

	print_banner();

	unsigned int n = 0;
	while (1) {
		gpio_pin_toggle_dt(&led);
		if ((n % 5) == 0) {
			printk("running for %u s - `pio run -t upload` to update "
			       "over USB DFU\n", n / 2);
		}
		n++;
		k_msleep(500);
	}

	return 0;
}
