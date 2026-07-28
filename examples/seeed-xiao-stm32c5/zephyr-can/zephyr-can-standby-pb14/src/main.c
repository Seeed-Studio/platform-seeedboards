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

int main(void)
{
	if (gpio_is_ready_dt(&can_standby)) {
		(void)gpio_pin_configure_dt(&can_standby, GPIO_OUTPUT_ACTIVE);
	}

	for (;;) {
		k_sleep(K_FOREVER);
	}

	return 0;
}
