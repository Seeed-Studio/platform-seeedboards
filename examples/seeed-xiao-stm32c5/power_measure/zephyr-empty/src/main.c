/*
 * Copyright (c) 2026 Seeed Technology Co., Ltd.
 * SPDX-License-Identifier: Apache-2.0
 */

#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>

static const struct gpio_dt_spec can_standby =
	GPIO_DT_SPEC_GET(DT_NODELABEL(can_phy0), standby_gpios);
static const struct device *const flash_cs_gpio = DEVICE_DT_GET(DT_NODELABEL(gpiob));

#define FLASH_CS_PIN 10U

int main(void)
{
	if (device_is_ready(flash_cs_gpio)) {
		(void)gpio_pin_configure(flash_cs_gpio, FLASH_CS_PIN, GPIO_OUTPUT_HIGH);
	}

	if (gpio_is_ready_dt(&can_standby)) {
		(void)gpio_pin_configure_dt(&can_standby, GPIO_OUTPUT_INACTIVE);
	}

	for (;;) {
		k_sleep(K_FOREVER);
	}

	return 0;
}
