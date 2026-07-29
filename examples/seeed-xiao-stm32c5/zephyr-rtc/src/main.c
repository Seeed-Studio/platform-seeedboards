/*
 * Copyright (c) 2026 Seeed Technology Co., Ltd.
 * SPDX-License-Identifier: Apache-2.0
 *
 * RTC demo: sets RTC time, then reads it every second.
 * Adapted from Zephyr samples/drivers/rtc.
 */

#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/rtc.h>
#include <zephyr/sys/printk.h>

const struct device *const rtc = DEVICE_DT_GET(DT_ALIAS(rtc));

int main(void)
{
	if (!device_is_ready(rtc)) {
		printk("RTC device not ready\n");
		return 0;
	}

	struct rtc_time tm_set = {
		.tm_year = 2026 - 1900,
		.tm_mon  = 5,       /* June (0-based) */
		.tm_mday = 16,
		.tm_hour = 12,
		.tm_min  = 0,
		.tm_sec  = 0,
	};

	int ret = rtc_set_time(rtc, &tm_set);
	if (ret < 0) {
		printk("Cannot set time: %d\n", ret);
		return 0;
	}

	printk("RTC set to 2026-06-16 12:00:00\n");

	while (1) {
		struct rtc_time tm_get = {0};

		ret = rtc_get_time(rtc, &tm_get);
		if (ret < 0) {
			printk("Cannot read time: %d\n", ret);
		} else {
			printk("%04d-%02d-%02d %02d:%02d:%02d\n",
			       tm_get.tm_year + 1900,
			       tm_get.tm_mon + 1,
			       tm_get.tm_mday,
			       tm_get.tm_hour,
			       tm_get.tm_min,
			       tm_get.tm_sec);
		}
		k_msleep(1000);
	}

	return 0;
}
