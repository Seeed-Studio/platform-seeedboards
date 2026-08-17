/*
 * Copyright (c) 2026 Seeed Technology Co., Ltd.
 * SPDX-License-Identifier: Apache-2.0
 */

#include <errno.h>

#include <zephyr/device.h>
#include <zephyr/drivers/sensor.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/util.h>

#define BMP280_NODE DT_NODELABEL(bmp280)

static void print_sensor_value(const char *name, const struct sensor_value *value,
			       const char *unit)
{
	int32_t fraction = value->val2 < 0 ? -value->val2 : value->val2;

	if (value->val1 == 0 && value->val2 < 0) {
		printk("%s: -0.%06d %s\n", name, fraction, unit);
		return;
	}

	printk("%s: %d.%06d %s\n", name, value->val1, fraction, unit);
}

int main(void)
{
	const struct device *const bmp280 = DEVICE_DT_GET(BMP280_NODE);
	struct sensor_value temperature;
	struct sensor_value pressure;
	int ret;

	printk("BMP280 SPI sample for XIAO STM32C5\n");
	printk("Bus: SPI3 D8/PE2=SCK, D9/PB0=MISO, D10/PB15=MOSI, D3/PA3=CS\n");

	if (!device_is_ready(bmp280)) {
		printk("BMP280 device is not ready; check the SPI wiring.\n");
		return 0;
	}

	while (true) {
		ret = sensor_sample_fetch(bmp280);
		if (ret != 0) {
			printk("sensor_sample_fetch() failed: %d\n", ret);
			k_sleep(K_SECONDS(1));
			continue;
		}

		ret = sensor_channel_get(bmp280, SENSOR_CHAN_AMBIENT_TEMP,
					 &temperature);
		if (ret == 0) {
			ret = sensor_channel_get(bmp280, SENSOR_CHAN_PRESS, &pressure);
		}
		if (ret != 0) {
			printk("sensor_channel_get() failed: %d\n", ret);
			k_sleep(K_SECONDS(1));
			continue;
		}

		print_sensor_value("Temperature", &temperature, "C");
		print_sensor_value("Pressure", &pressure, "kPa");
		k_sleep(K_SECONDS(1));
	}
}
