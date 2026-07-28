/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * XIAO STM32C5 watchdog sample.
 */

#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/watchdog.h>
#include <zephyr/kernel.h>

#define WDT_NODE DT_ALIAS(watchdog0)
#define FEED_COUNT 5
#define FEED_INTERVAL_MS 100
#define WDT_TIMEOUT_MS 1000

int main(void)
{
	const struct device *const wdt = DEVICE_DT_GET(WDT_NODE);
	struct wdt_timeout_cfg wdt_config = {
		.flags = WDT_FLAG_RESET_SOC,
		.window.min = 0,
		.window.max = WDT_TIMEOUT_MS,
	};
	int channel_id;
	int ret;

	printk("XIAO STM32C5 watchdog sample\n");

	if (!device_is_ready(wdt)) {
		printk("Watchdog device %s is not ready\n", wdt->name);
		return 0;
	}

	channel_id = wdt_install_timeout(wdt, &wdt_config);
	if (channel_id < 0) {
		printk("Watchdog timeout install failed: %d\n", channel_id);
		return 0;
	}

	ret = wdt_setup(wdt, WDT_OPT_PAUSE_HALTED_BY_DBG);
	if (ret < 0) {
		printk("Watchdog setup failed: %d\n", ret);
		return 0;
	}

	printk("Feeding watchdog %d times\n", FEED_COUNT);
	for (int i = 0; i < FEED_COUNT; i++) {
		printk("Feeding watchdog...\n");
		wdt_feed(wdt, channel_id);
		k_msleep(FEED_INTERVAL_MS);
	}

	printk("Waiting for watchdog reset...\n");
	while (true) {
		k_yield();
	}
}
