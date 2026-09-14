/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * XIAO nRF54LM20A V2 blink + USB CDC ACM log.
 *
 * Toggles the green LED (led2) and prints a line to the USB CDC ACM console
 * on each toggle. The V2 board's default zephyr,console is &cdc_acm_uart
 * (nRF54 native USB CDC ACM -- V2 replaced the V1 SAMD11 USB-UART bridge
 * with the nRF54 USB peripheral), so printk() goes straight out over USB
 * with no extra wiring.
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

	printk("XIAO nRF54LM20A V2 blink + USB CDC ACM console ready\n");

	unsigned int n = 0;
	while (1) {
		gpio_pin_toggle_dt(&led);
		printk("toggle %u\n", n++);
		k_msleep(500);
	}

	return 0;
}
