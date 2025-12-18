#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/sensor.h>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(zephyr_imu, LOG_LEVEL_INF);

static inline float out_ev(struct sensor_value *val)
{
	return (val->val1 + (float)val->val2 / 1000000);
}

static void fetch_and_display(const struct device *dev)
{
	struct sensor_value x, y, z;
	static int trig_cnt;

	trig_cnt++;

	/* lsm6dsl accel */
	sensor_sample_fetch_chan(dev, SENSOR_CHAN_ACCEL_XYZ);
	sensor_channel_get(dev, SENSOR_CHAN_ACCEL_X, &x);
	sensor_channel_get(dev, SENSOR_CHAN_ACCEL_Y, &y);
	sensor_channel_get(dev, SENSOR_CHAN_ACCEL_Z, &z);

	LOG_INF("accel x:%f m/s^2 y:%f m/s^2 z:%f m/s^2",
			(double)out_ev(&x), (double)out_ev(&y), (double)out_ev(&z));

	/* lsm6dsl gyro */
	sensor_sample_fetch_chan(dev, SENSOR_CHAN_GYRO_XYZ);
	sensor_channel_get(dev, SENSOR_CHAN_GYRO_X, &x);
	sensor_channel_get(dev, SENSOR_CHAN_GYRO_Y, &y);
	sensor_channel_get(dev, SENSOR_CHAN_GYRO_Z, &z);

	LOG_INF("gyro x:%f rad/s y:%f rad/s z:%f rad/s",
			(double)out_ev(&x), (double)out_ev(&y), (double)out_ev(&z));

	LOG_INF("trig_cnt:%d", trig_cnt);
}

static int set_sampling_freq(const struct device *dev)
{
	int ret = 0;
	struct sensor_value odr_attr;

	/* set accel/gyro sampling frequency to 12.5 Hz */
	odr_attr.val1 = 12.5;
	odr_attr.val2 = 0;

	ret = sensor_attr_set(dev, SENSOR_CHAN_ACCEL_XYZ,
			SENSOR_ATTR_SAMPLING_FREQUENCY, &odr_attr);
	if (ret != 0) {
		LOG_ERR("Cannot set sampling frequency for accelerometer.");
		return ret;
	}

	ret = sensor_attr_set(dev, SENSOR_CHAN_GYRO_XYZ,
			SENSOR_ATTR_SAMPLING_FREQUENCY, &odr_attr);
	if (ret != 0) {
		LOG_ERR("Cannot set sampling frequency for gyro.");
		return ret;
	}

	return 0;
}

#ifdef CONFIG_LSM6DSL_TRIGGER
static void trigger_handler(const struct device *dev,
			    const struct sensor_trigger *trig)
{
	fetch_and_display(dev);
}

static void test_trigger_mode(const struct device *dev)
{
	struct sensor_trigger trig;

	if (set_sampling_freq(dev) != 0) {
		return;
	}

	trig.type = SENSOR_TRIG_DATA_READY;
	trig.chan = SENSOR_CHAN_ACCEL_XYZ;

	if (sensor_trigger_set(dev, &trig, trigger_handler) != 0) {
		LOG_ERR("Could not set sensor type and channel");
		return;
	}
}

#else
static void test_polling_mode(const struct device *dev)
{
	if (set_sampling_freq(dev) != 0) {
		return;
	}

	while (1) {
		fetch_and_display(dev);
		k_sleep(K_MSEC(1000));
	}
}
#endif

int main(void)
{
	const struct device *const dev = DEVICE_DT_GET(DT_ALIAS(imu0));

	if (!device_is_ready(dev)) {
		LOG_ERR("%s: device not ready.", dev->name);
		return 0;
	}

#ifdef CONFIG_LSM6DSL_TRIGGER
	LOG_INF("Testing LSM6DSL sensor in trigger mode.");
	test_trigger_mode(dev);
#else
	LOG_INF("Testing LSM6DSL sensor in polling mode.");
	test_polling_mode(dev);
#endif
	return 0;
}
