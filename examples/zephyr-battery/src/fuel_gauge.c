/*
 * Copyright (c) 2023 Nordic Semiconductor ASA
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 *
 * Simplified fuel gauge implementation without nrf_fuel_gauge library.
 * Reads and reports raw battery sensor values (voltage, current, temperature,
 * charge status) from the NPM1300 charger.
 */

#ifdef CONFIG_BOARD_XIAO_NRF54LM20A

#include <stdlib.h>

#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/sensor.h>
#include <zephyr/drivers/sensor/npm13xx_charger.h>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(fuel_gauge, LOG_LEVEL_INF);

/* nPM13xx CHARGER.BCHGCHARGESTATUS register bitmasks */
#define NPM13XX_CHG_STATUS_COMPLETE_MASK BIT(1)
#define NPM13XX_CHG_STATUS_TRICKLE_MASK  BIT(2)
#define NPM13XX_CHG_STATUS_CC_MASK       BIT(3)
#define NPM13XX_CHG_STATUS_CV_MASK       BIT(4)

static int read_sensors(const struct device *charger, float *voltage, float *current,
			float *temp, int32_t *chg_status)
{
	struct sensor_value value;
	int ret;

	ret = sensor_sample_fetch(charger);
	if (ret < 0) {
		return ret;
	}

	sensor_channel_get(charger, SENSOR_CHAN_GAUGE_VOLTAGE, &value);
	*voltage = (float)value.val1 + ((float)value.val2 / 1000000);

	sensor_channel_get(charger, SENSOR_CHAN_GAUGE_TEMP, &value);
	*temp = (float)value.val1 + ((float)value.val2 / 1000000);

	sensor_channel_get(charger, SENSOR_CHAN_GAUGE_AVG_CURRENT, &value);
	*current = (float)value.val1 + ((float)value.val2 / 1000000);

	sensor_channel_get(charger, SENSOR_CHAN_NPM13XX_CHARGER_STATUS, &value);
	*chg_status = value.val1;

	return 0;
}

static const char *charge_status_str(int32_t chg_status)
{
	if (chg_status & NPM13XX_CHG_STATUS_COMPLETE_MASK) {
		return "Complete";
	} else if (chg_status & NPM13XX_CHG_STATUS_TRICKLE_MASK) {
		return "Trickle";
	} else if (chg_status & NPM13XX_CHG_STATUS_CC_MASK) {
		return "CC";
	} else if (chg_status & NPM13XX_CHG_STATUS_CV_MASK) {
		return "CV";
	}
	return "Idle";
}

int fuel_gauge_init(const struct device *charger)
{
	float voltage, current, temp;
	int32_t chg_status;
	int ret;

	ret = read_sensors(charger, &voltage, &current, &temp, &chg_status);
	if (ret < 0) {
		LOG_ERR("Could not read initial sensor values: %d", ret);
		return ret;
	}

	LOG_INF("Init: V=%.3f I=%.3f mA T=%.2f C Status=%s",
		(double)voltage, (double)(current * 1000.0f), (double)temp,
		charge_status_str(chg_status));

	return 0;
}

int fuel_gauge_update(const struct device *charger)
{
	float voltage, current, temp;
	int32_t chg_status;
	struct sensor_value vbus_val;
	bool vbus_connected;
	int ret;

	ret = read_sensors(charger, &voltage, &current, &temp, &chg_status);
	if (ret < 0) {
		LOG_ERR("Could not read from charger device: %d", ret);
		return ret;
	}

	/* Read VBUS status directly from charger sensor channel */
	sensor_channel_get(charger, SENSOR_CHAN_NPM13XX_CHARGER_VBUS_STATUS, &vbus_val);
	vbus_connected = vbus_val.val1 != 0;

	LOG_INF("V:%.3f I:%.3f mA T:%.2f C VBUS:%s Status:%s %s",
		(double)voltage, (double)(current * 1000.0f), (double)temp,
		vbus_connected ? "connected" : "disconnected",
		charge_status_str(chg_status),
		(chg_status & NPM13XX_CHG_STATUS_COMPLETE_MASK) ?
			"[FULL]" : "[Charging]");

	return 0;
}

#endif /* CONFIG_BOARD_XIAO_NRF54LM20A */
