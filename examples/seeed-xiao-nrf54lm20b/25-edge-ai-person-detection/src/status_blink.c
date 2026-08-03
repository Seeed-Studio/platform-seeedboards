/* SPDX-License-Identifier: LicenseRef-Nordic-5-Clause */

#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>

/* XIAO nRF54LM20B RGB LED: green is P1.24 and electrically active low. */
#define STATUS_LED_PORT DT_NODELABEL(gpio1)
#define STATUS_LED_PIN  24

static void status_blink(void)
{
	const struct device *const gpio1 = DEVICE_DT_GET(STATUS_LED_PORT);

	if (!device_is_ready(gpio1)) {
		return;
	}

	(void)gpio_pin_configure(gpio1, STATUS_LED_PIN, GPIO_OUTPUT_HIGH);
	while (true) {
		(void)gpio_pin_set(gpio1, STATUS_LED_PIN, 0);
		k_msleep(100);
		(void)gpio_pin_set(gpio1, STATUS_LED_PIN, 1);
		k_msleep(900);
	}
}

K_THREAD_DEFINE(status_blink_thread, 512, status_blink, NULL, NULL, NULL, 7, 0, 0);
