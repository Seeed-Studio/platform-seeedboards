/* LSM6DS3TR-C adapter for the XIAO nRF54LM20B gesture collector. */
#include "imu.h"

#include <errno.h>
#include <zephyr/device.h>
#include <zephyr/drivers/regulator.h>
#include <zephyr/drivers/sensor.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(imu, CONFIG_LOG_DEFAULT_LEVEL);

static const struct device *const power_en_dev = DEVICE_DT_GET(DT_NODELABEL(power_en));
static const struct device *const imu_vdd_dev = DEVICE_DT_GET(DT_NODELABEL(imu_vdd));
static const struct device *const imu_dev = DEVICE_DT_GET(DT_ALIAS(imu0));
static generic_cb_t ready_cb;
static bool initialized;

static void sample_timer_handler(struct k_timer *timer)
{
	ARG_UNUSED(timer);
	if (ready_cb != NULL) {
		ready_cb();
	}
}
K_TIMER_DEFINE(sample_timer, sample_timer_handler, NULL);

status_t imu_init(const imu_config_t *config, generic_cb_t data_ready_cb)
{
	struct sensor_value accel_fs, gyro_fs, frequency;
	int ret;

	if (config == NULL || config->data_rate_hz == 0) {
		return STATUS_INVALID_PARAM;
	}
	if (!device_is_ready(power_en_dev) || !device_is_ready(imu_vdd_dev)) {
		LOG_ERR("IMU power regulators are not ready");
		return STATUS_HARDWARE_ERROR;
	}
	ret = regulator_enable(power_en_dev);
	if (ret < 0 && ret != -EALREADY) return STATUS_HARDWARE_ERROR;
	ret = regulator_enable(imu_vdd_dev);
	if (ret < 0 && ret != -EALREADY) return STATUS_HARDWARE_ERROR;
	k_sleep(K_MSEC(20));
	if (!device_is_ready(imu_dev)) {
		ret = device_init(imu_dev);
		if (ret < 0 && ret != -EALREADY) return STATUS_HARDWARE_ERROR;
	}
	if (!device_is_ready(imu_dev)) return STATUS_HARDWARE_ERROR;

	sensor_g_to_ms2(config->accel_fs_g, &accel_fs);
	sensor_degrees_to_rad(config->gyro_fs_dps, &gyro_fs);
	frequency.val1 = config->data_rate_hz == 100 ? 104 : config->data_rate_hz;
	frequency.val2 = 0;
	ret = sensor_attr_set(imu_dev, SENSOR_CHAN_ACCEL_XYZ, SENSOR_ATTR_FULL_SCALE, &accel_fs);
	if (ret != 0) return STATUS_HARDWARE_ERROR;
	ret = sensor_attr_set(imu_dev, SENSOR_CHAN_ACCEL_XYZ, SENSOR_ATTR_SAMPLING_FREQUENCY, &frequency);
	if (ret != 0) return STATUS_HARDWARE_ERROR;
	ret = sensor_attr_set(imu_dev, SENSOR_CHAN_GYRO_XYZ, SENSOR_ATTR_FULL_SCALE, &gyro_fs);
	if (ret != 0) return STATUS_HARDWARE_ERROR;
	ret = sensor_attr_set(imu_dev, SENSOR_CHAN_GYRO_XYZ, SENSOR_ATTR_SAMPLING_FREQUENCY, &frequency);
	if (ret != 0) return STATUS_HARDWARE_ERROR;

	ready_cb = data_ready_cb;
	initialized = true;
	k_timer_start(&sample_timer, K_MSEC(10), K_MSEC(10));
	return STATUS_SUCCESS;
}

status_t imu_read(imu_data_t *data)
{
	struct sensor_value accel[IMU_NUM_AXES], gyro[IMU_NUM_AXES];
	if (data == NULL || !initialized) return STATUS_INVALID_PARAM;
	if (sensor_sample_fetch(imu_dev) != 0 ||
	    sensor_channel_get(imu_dev, SENSOR_CHAN_ACCEL_XYZ, accel) != 0 ||
	    sensor_channel_get(imu_dev, SENSOR_CHAN_GYRO_XYZ, gyro) != 0) {
		return STATUS_HARDWARE_ERROR;
	}
	for (int i = 0; i < IMU_NUM_AXES; ++i) {
		data->accel[i].phys = (float)sensor_value_to_double(&accel[i]);
		data->accel[i].raw = (int16_t)(data->accel[i].phys * 1000.0f);
		data->gyro[i].phys = (float)sensor_value_to_double(&gyro[i]);
		data->gyro[i].raw = (int16_t)(data->gyro[i].phys * 1000.0f);
	}
	return STATUS_SUCCESS;
}
