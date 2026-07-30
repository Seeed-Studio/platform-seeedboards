/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * XIAO nRF54LM20B blink + USB CDC ACM log.
 *
 * Toggles the green LED (led2) and prints a line to the USB CDC ACM console
 * on each toggle. The board's default zephyr,console is &cdc_acm_uart (USB
 * CDC ACM), so printk() goes straight out over USB — no extra wiring.
 */

#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>
#include <zephyr/drivers/gpio.h>

/* Green LED (aliases: led0=blue, led1=red, led2=green) */
#define LED_NODE DT_ALIAS(led2)
#if !DT_NODE_HAS_STATUS(LED_NODE, okay) || !DT_NODE_HAS_PROP(LED_NODE, gpios)
#error "Unsupported board: led2 (green) alias is not defined"
#endif

static const struct gpio_dt_spec led = GPIO_DT_SPEC_GET(LED_NODE, gpios);

int main(void)
{
	if (!gpio_is_ready_dt(&led)) {
		printk("green LED not ready\n");
		return 0;
	}

	gpio_pin_configure_dt(&led, GPIO_OUTPUT_INACTIVE);

	printk("XIAO nRF54LM20B blink + USB CDC ACM console ready\n");

	unsigned int n = 0;
	while (1) {
		gpio_pin_toggle_dt(&led);
		printk("toggle %u\n", n++);
		k_msleep(500);
	}

	return 0;
}
