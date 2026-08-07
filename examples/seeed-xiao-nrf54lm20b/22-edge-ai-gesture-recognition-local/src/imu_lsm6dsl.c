/*
 * LSM6DS3TR-C adapter for the official nRF Edge AI gesture-recognition app.
 *
 * The official nRF54LM20 DK uses a Bosch BMI270.  XIAO exposes its onboard
 * ST LSM6DS3TR-C as the imu0 devicetree alias.  Both drivers report Zephyr
 * standard SI units, so the model input scaling remains unchanged.
 */

#include "sensor/imu/imu.h"

#include <errno.h>
#include <zephyr/device.h>
#include <zephyr/drivers/regulator.h>
#include <zephyr/drivers/sensor.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

LOG_MODULE_DECLARE(main);

static const struct device *const power_en_dev =
	DEVICE_DT_GET(DT_NODELABEL(power_en));
static const struct device *const imu_vdd_dev =
	DEVICE_DT_GET(DT_NODELABEL(imu_vdd));

static struct {
	bool initialized;
	generic_cb_t data_ready_cb;
	const struct device *dev;
} imu_ctx = {
	.initialized = false,
	.data_ready_cb = NULL,
	.dev = DEVICE_DT_GET(DT_ALIAS(imu0)),
};

static void data_read_timer_handler(struct k_timer *timer)
{
	ARG_UNUSED(timer);

	if (imu_ctx.data_ready_cb != NULL) {
		imu_ctx.data_ready_cb();
	}
}

K_TIMER_DEFINE(data_ready_timer, data_read_timer_handler, NULL);

static int enable_imu_power_and_init(void)
{
	int ret;

	if (!device_is_ready(power_en_dev)) {
		LOG_ERR("IMU power_en regulator is not ready");
		return -ENODEV;
	}
	if (!device_is_ready(imu_vdd_dev)) {
		LOG_ERR("IMU LDO1 regulator is not ready");
		return -ENODEV;
	}

	ret = regulator_enable(power_en_dev);
	if (ret < 0 && ret != -EALREADY) {
		LOG_ERR("Failed to enable IMU power_en: %d", ret);
		return ret;
	}
	ret = regulator_enable(imu_vdd_dev);
	if (ret < 0 && ret != -EALREADY) {
		LOG_ERR("Failed to enable IMU LDO1: %d", ret);
		return ret;
	}

	/* LDO output and the IMU need to settle before the first I2C access. */
	k_sleep(K_MSEC(20));

	if (!device_is_ready(imu_ctx.dev)) {
		ret = device_init(imu_ctx.dev);
		if (ret < 0 && ret != -EALREADY) {
			LOG_ERR("Failed to probe IMU %s: %d", imu_ctx.dev->name, ret);
			return ret;
		}
	}

	if (!device_is_ready(imu_ctx.dev)) {
		LOG_ERR("IMU %s is not ready after probe", imu_ctx.dev->name);
		return -ENODEV;
	}

	return 0;
}

status_t imu_init(const imu_config_t *p_config, generic_cb_t data_ready_cb)
{
	struct sensor_value accel_fs;
	struct sensor_value gyro_fs;
	struct sensor_value sampling_freq;
	uint32_t period_ms;
	int ret;

	NULL_CHECK(p_config);
	VERIFY_VALID_ARG(p_config->data_rate_hz > 0);
	sampling_freq.val1 = p_config->data_rate_hz;
	sampling_freq.val2 = 0;
	/*
	 * LSM6DS3TR-C supports 12.5/26/52/104/... Hz, but the Edge AI model
	 * consumes a 100 Hz input stream.  Run the sensor at its nearest supported
	 * ODR while retaining the model's 10 ms sampling timer below.
	 */
	if (sampling_freq.val1 == 100) {
		sampling_freq.val1 = 104;
		LOG_INF("Using 104 Hz IMU ODR for the 100 Hz model input stream");
	}

	ret = enable_imu_power_and_init();
	HW_RETURN_IF(ret != 0, STATUS_HARDWARE_ERROR);

	/* LSM6DSL follows Zephyr's SI-unit API: m/s^2 and rad/s. */
	sensor_g_to_ms2(p_config->accel_fs_g, &accel_fs);
	sensor_degrees_to_rad(p_config->gyro_fs_dps, &gyro_fs);

	ret = sensor_attr_set(imu_ctx.dev, SENSOR_CHAN_ACCEL_XYZ,
			      SENSOR_ATTR_FULL_SCALE, &accel_fs);
	if (ret != 0) {
		LOG_ERR("Failed to set accelerometer full scale: %d", ret);
		return STATUS_HARDWARE_ERROR;
	}
	ret = sensor_attr_set(imu_ctx.dev, SENSOR_CHAN_ACCEL_XYZ,
			      SENSOR_ATTR_SAMPLING_FREQUENCY, &sampling_freq);
	if (ret != 0) {
		LOG_ERR("Failed to set accelerometer ODR: %d", ret);
		return STATUS_HARDWARE_ERROR;
	}
	ret = sensor_attr_set(imu_ctx.dev, SENSOR_CHAN_GYRO_XYZ,
			      SENSOR_ATTR_FULL_SCALE, &gyro_fs);
	if (ret != 0) {
		LOG_ERR("Failed to set gyroscope full scale: %d", ret);
		return STATUS_HARDWARE_ERROR;
	}
	ret = sensor_attr_set(imu_ctx.dev, SENSOR_CHAN_GYRO_XYZ,
			      SENSOR_ATTR_SAMPLING_FREQUENCY, &sampling_freq);
	if (ret != 0) {
		LOG_ERR("Failed to set gyroscope ODR: %d", ret);
		return STATUS_HARDWARE_ERROR;
	}

	imu_ctx.data_ready_cb = data_ready_cb;
	period_ms = MAX(1U, 1000U / (uint32_t)p_config->data_rate_hz);
	k_timer_start(&data_ready_timer, K_MSEC(period_ms), K_MSEC(period_ms));
	imu_ctx.initialized = true;

	return STATUS_SUCCESS;
}

status_t imu_read(imu_data_t *const p_data)
{
	struct sensor_value acc[IMU_NUM_AXES];
	struct sensor_value gyr[IMU_NUM_AXES];
	int ret;

	NULL_CHECK(p_data);
	HW_RETURN_IF(!imu_ctx.initialized, STATUS_HARDWARE_ERROR);

	ret = sensor_sample_fetch(imu_ctx.dev);
	HW_RETURN_IF(ret != 0, STATUS_HARDWARE_ERROR);
	ret = sensor_channel_get(imu_ctx.dev, SENSOR_CHAN_ACCEL_XYZ, acc);
	HW_RETURN_IF(ret != 0, STATUS_HARDWARE_ERROR);
	ret = sensor_channel_get(imu_ctx.dev, SENSOR_CHAN_GYRO_XYZ, gyr);
	HW_RETURN_IF(ret != 0, STATUS_HARDWARE_ERROR);

	for (int i = 0; i < IMU_NUM_AXES; i++) {
		p_data->accel[i].phys = (float)sensor_value_to_double(&acc[i]);
		p_data->accel[i].raw = (int16_t)(p_data->accel[i].phys * 1000.0f);
		p_data->gyro[i].phys = (float)sensor_value_to_double(&gyr[i]);
		p_data->gyro[i].raw = (int16_t)(p_data->gyro[i].phys * 1000.0f);
	}

	return STATUS_SUCCESS;
}
