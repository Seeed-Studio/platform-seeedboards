/*
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 *
 * Data Forwarder sensor wrapper for the XIAO nRF54LM20B onboard
 * LSM6DS3TR-C. The device is exposed by Zephyr as the LSM6DSL-compatible
 * driver. Values are exported as signed 32-bit micro-units, which is the
 * official Data Forwarder integer protocol representation:
 *   acceleration: micro m/s^2
 *   angular velocity: micro rad/s
 */

#include <errno.h>
#include <limits.h>

#include <zephyr/device.h>
#include <zephyr/drivers/regulator.h>
#include <zephyr/drivers/sensor.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

#include "data_fwd_sensor.h"

LOG_MODULE_REGISTER(sensor);

#define SENSOR_CHANNEL_COUNT 6
#define SENSOR_TYPE_VALUE    1
#define FREQUENCY_HZ         100

static const char *const channel_names[SENSOR_CHANNEL_COUNT] = {
	"ax", "ay", "az", "gx", "gy", "gz"
};

static const struct device *const imu = DEVICE_DT_GET(DT_ALIAS(imu0));
static const struct device *const power_en = DEVICE_DT_GET(DT_NODELABEL(power_en));
static const struct device *const imu_vdd = DEVICE_DT_GET(DT_NODELABEL(imu_vdd));

static K_SEM_DEFINE(fetch_sem, 0, 1);
static void fetch_timer_handler(struct k_timer *timer)
{
	ARG_UNUSED(timer);
	k_sem_give(&fetch_sem);
}
K_TIMER_DEFINE(fetch_timer, fetch_timer_handler, NULL);

static proto_value_t to_micro(const struct sensor_value *value)
{
	int64_t micro = (int64_t)value->val1 * 1000000LL + value->val2;
	if (micro > INT32_MAX) {
		return INT32_MAX;
	}
	if (micro < INT32_MIN) {
		return INT32_MIN;
	}
	return (proto_value_t)micro;
}

int data_fwd_sensor_init(void)
{
	struct sensor_value accel_fs;
	struct sensor_value gyro_fs;
	struct sensor_value odr = { .val1 = 104, .val2 = 0 };
	int err;

	/* Zephyr sensor attributes use SI units (m/s^2 and rad/s), not g/dps. */
	sensor_g_to_ms2(4, &accel_fs);
	sensor_degrees_to_rad(1000, &gyro_fs);

	if (!device_is_ready(power_en) || !device_is_ready(imu_vdd)) {
		return -ENODEV;
	}
	err = regulator_enable(power_en);
	if (err < 0 && err != -EALREADY) {
		return err;
	}
	err = regulator_enable(imu_vdd);
	if (err < 0 && err != -EALREADY) {
		return err;
	}
	k_sleep(K_MSEC(20));

	if (!device_is_ready(imu)) {
		err = device_init(imu);
		if (err < 0 && err != -EALREADY) {
			return err;
		}
	}
	if (!device_is_ready(imu)) {
		return -ENODEV;
	}

	err = sensor_attr_set(imu, SENSOR_CHAN_ACCEL_XYZ, SENSOR_ATTR_FULL_SCALE, &accel_fs);
	if (err) return err;
	err = sensor_attr_set(imu, SENSOR_CHAN_ACCEL_XYZ, SENSOR_ATTR_SAMPLING_FREQUENCY, &odr);
	if (err) return err;
	err = sensor_attr_set(imu, SENSOR_CHAN_GYRO_XYZ, SENSOR_ATTR_FULL_SCALE, &gyro_fs);
	if (err) return err;
	err = sensor_attr_set(imu, SENSOR_CHAN_GYRO_XYZ, SENSOR_ATTR_SAMPLING_FREQUENCY, &odr);
	if (err) return err;

	k_timer_start(&fetch_timer, K_NO_WAIT, K_MSEC(10));
	return 0;
}

int data_fwd_sensor_fetch(proto_value_t *values, const size_t values_size, size_t *count)
{
	struct sensor_value accel[3];
	struct sensor_value gyro[3];
	int err;

	if (!values || !count || values_size < SENSOR_CHANNEL_COUNT) {
		return -EINVAL;
	}
	k_sem_take(&fetch_sem, K_FOREVER);
	err = sensor_sample_fetch(imu);
	if (err) return err;
	err = sensor_channel_get(imu, SENSOR_CHAN_ACCEL_XYZ, accel);
	if (err) return err;
	err = sensor_channel_get(imu, SENSOR_CHAN_GYRO_XYZ, gyro);
	if (err) return err;
	for (size_t i = 0; i < 3; ++i) {
		values[i] = to_micro(&accel[i]);
		values[i + 3] = to_micro(&gyro[i]);
	}
	*count = SENSOR_CHANNEL_COUNT;
	return 0;
}

uint8_t data_fwd_sensor_channel_count(void)
{
	return SENSOR_CHANNEL_COUNT;
}

const char *const *data_fwd_sensor_channel_names(void)
{
	return channel_names;
}

uint8_t data_fwd_sensor_type_id(void)
{
	return SENSOR_TYPE_VALUE;
}

uint16_t data_fwd_sensor_frequency(void)
{
	return FREQUENCY_HZ;
}
