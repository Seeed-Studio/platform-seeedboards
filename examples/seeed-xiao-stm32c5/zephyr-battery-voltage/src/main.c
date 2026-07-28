/*
 * Copyright (c) 2026 Seeed Technology Co., Ltd.
 * SPDX-License-Identifier: Apache-2.0
 *
 * Battery voltage ADC test for XIAO STM32C5.
 * Schematic: BAT_Reading/PA4 -> ADC1_IN4, BAT_EN/PE2 enables the divider,
 * and battery voltage = ADC sampling voltage * 2.0.
 */

#include <zephyr/device.h>
#include <zephyr/drivers/adc.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

#if !DT_NODE_EXISTS(DT_PATH(zephyr_user)) || \
	!DT_NODE_HAS_PROP(DT_PATH(zephyr_user), io_channels)
#error "No battery ADC io-channel specified"
#endif

#define BATTERY_ADC_NODE DT_PATH(zephyr_user)
#define BAT_EN_NODE      DT_ALIAS(baten)

#define ADC_AVG_SAMPLES         16
#define BATTERY_DIVIDER_NUM     2
#define BATTERY_DIVIDER_DEN     1
#define BATTERY_ENABLE_SETTLE_MS 5
#define SAMPLE_PERIOD_MS        1000

static const struct adc_dt_spec battery_adc =
	ADC_DT_SPEC_GET_BY_IDX(BATTERY_ADC_NODE, 0);
static const struct gpio_dt_spec bat_en =
	GPIO_DT_SPEC_GET(BAT_EN_NODE, gpios);

static int read_battery_adc(uint16_t *raw_avg, int32_t *adc_mv,
			    int32_t *battery_mv)
{
	uint16_t raw;
	uint32_t raw_sum = 0;
	struct adc_sequence sequence = {
		.buffer = &raw,
		.buffer_size = sizeof(raw),
	};
	int err = adc_sequence_init_dt(&battery_adc, &sequence);

	if (err) {
		return err;
	}

	/* Drop the first conversion after enabling the divider/input path. */
	err = adc_read(battery_adc.dev, &sequence);
	if (err) {
		return err;
	}

	for (int i = 0; i < ADC_AVG_SAMPLES; i++) {
		err = adc_read(battery_adc.dev, &sequence);
		if (err) {
			return err;
		}

		raw_sum += raw;
	}

	*raw_avg = raw_sum / ADC_AVG_SAMPLES;
	*adc_mv = *raw_avg;
	err = adc_raw_to_millivolts_dt(&battery_adc, adc_mv);
	if (err) {
		return err;
	}

	*battery_mv = (*adc_mv * BATTERY_DIVIDER_NUM) / BATTERY_DIVIDER_DEN;
	return 0;
}

int main(void)
{
	int err;

	printk("\n");
	printk("============================================\n");
	printk("  Battery Voltage ADC Test for XIAO STM32C5\n");
	printk("============================================\n");
	printk("Hardware mapping:\n");
	printk("  BAT_Reading/PA4 -> ADC1_IN4\n");
	printk("  BAT_EN/PE2      -> GPIO output active-high\n");
	printk("  Formula         -> battery_mV = adc_mV * %d / %d\n",
	       BATTERY_DIVIDER_NUM, BATTERY_DIVIDER_DEN);
	printk("  Samples         -> %d-sample average every %d ms\n",
	       ADC_AVG_SAMPLES, SAMPLE_PERIOD_MS);

	if (!device_is_ready(battery_adc.dev)) {
		printk("ADC controller %s not ready\n", battery_adc.dev->name);
		return 0;
	}

	if (!gpio_is_ready_dt(&bat_en)) {
		printk("BAT_EN GPIO device not ready\n");
		return 0;
	}

	err = gpio_pin_configure_dt(&bat_en, GPIO_OUTPUT_INACTIVE);
	if (err) {
		printk("BAT_EN configure failed: %d\n", err);
		return 0;
	}

	err = adc_channel_setup_dt(&battery_adc);
	if (err) {
		printk("Battery ADC channel setup failed: %d\n", err);
		return 0;
	}

	printk("Battery ADC ready: dev=%s channel=%d resolution=%d\n",
	       battery_adc.dev->name, battery_adc.channel_id,
	       battery_adc.resolution);

	while (1) {
		uint16_t raw;
		int32_t adc_mv;
		int32_t battery_mv;

		gpio_pin_set_dt(&bat_en, 1);
		k_msleep(BATTERY_ENABLE_SETTLE_MS);

		err = read_battery_adc(&raw, &adc_mv, &battery_mv);
		if (err) {
			printk("[BAT] read failed: %d\n", err);
		} else {
			printk("[BAT] raw=%u adc=%d mV battery=%d mV (%d.%03d V)\n",
			       raw, adc_mv, battery_mv,
			       battery_mv / 1000, battery_mv % 1000);
		}

		k_msleep(SAMPLE_PERIOD_MS);
	}

	return 0;
}
