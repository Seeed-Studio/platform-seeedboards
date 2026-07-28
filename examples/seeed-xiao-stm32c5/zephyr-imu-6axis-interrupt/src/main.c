/*
 * Copyright (c) 2026 Seeed Technology Co., Ltd.
 * SPDX-License-Identifier: Apache-2.0
 *
 * XIAO STM32C5 onboard LSM6DS3TR-C 6-axis data-ready interrupt test.
 */

#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/i2c.h>
#include <zephyr/drivers/sensor.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/printk.h>

#define IMU_NODE DT_ALIAS(imu0)

#define LSM6DSL_REG_WHO_AM_I 0x0f
#define LSM6DSL_EXPECTED_WHO_AM_I 0x6a
#define IMU_ODR_HZ 104
#define IMU_PRINT_DECIMALS 6
#define IMU_INTERRUPT_TIMEOUT_MS 1000

BUILD_ASSERT(DT_NODE_HAS_STATUS(IMU_NODE, okay),
	     "imu0 alias is not defined or not okay");

static const struct device *const imu = DEVICE_DT_GET(IMU_NODE);
static const struct i2c_dt_spec imu_i2c = I2C_DT_SPEC_GET(IMU_NODE);

static K_SEM_DEFINE(imu_drdy_sem, 0, 1);
static atomic_t imu_irq_count;

static int32_t abs_i32(int32_t value)
{
	return value < 0 ? -value : value;
}

static void print_sensor_value(const struct sensor_value *value)
{
	int32_t val1 = value->val1;
	int32_t val2 = value->val2;
	bool negative = (val1 < 0) || (val2 < 0);

	if (negative) {
		printk("-");
	}

	printk("%d.%0*d", abs_i32(val1), IMU_PRINT_DECIMALS, abs_i32(val2));
}

static int read_who_am_i(uint8_t *who_am_i)
{
	return i2c_reg_read_byte_dt(&imu_i2c, LSM6DSL_REG_WHO_AM_I, who_am_i);
}

static int configure_imu(void)
{
	struct sensor_value odr = {
		.val1 = IMU_ODR_HZ,
		.val2 = 0,
	};
	struct sensor_value accel_fs;
	struct sensor_value gyro_fs;
	int ret;

	sensor_g_to_ms2(4, &accel_fs);
	sensor_degrees_to_rad(500, &gyro_fs);

	ret = sensor_attr_set(imu, SENSOR_CHAN_ACCEL_XYZ,
			      SENSOR_ATTR_FULL_SCALE, &accel_fs);
	if (ret < 0) {
		printk("Failed to set accel full scale (+/-4g): %d\n", ret);
		return ret;
	}

	ret = sensor_attr_set(imu, SENSOR_CHAN_GYRO_XYZ,
			      SENSOR_ATTR_FULL_SCALE, &gyro_fs);
	if (ret < 0) {
		printk("Failed to set gyro full scale (+/-500 dps): %d\n", ret);
		return ret;
	}

	ret = sensor_attr_set(imu, SENSOR_CHAN_ACCEL_XYZ,
			      SENSOR_ATTR_SAMPLING_FREQUENCY, &odr);
	if (ret < 0) {
		printk("Failed to set accel ODR (%d Hz): %d\n", IMU_ODR_HZ, ret);
		return ret;
	}

	ret = sensor_attr_set(imu, SENSOR_CHAN_GYRO_XYZ,
			      SENSOR_ATTR_SAMPLING_FREQUENCY, &odr);
	if (ret < 0) {
		printk("Failed to set gyro ODR (%d Hz): %d\n", IMU_ODR_HZ, ret);
		return ret;
	}

	return 0;
}

static void imu_trigger_handler(const struct device *dev,
				const struct sensor_trigger *trigger)
{
	ARG_UNUSED(dev);
	ARG_UNUSED(trigger);

	atomic_inc(&imu_irq_count);
	k_sem_give(&imu_drdy_sem);
}

static int configure_imu_interrupt(void)
{
	struct sensor_trigger trigger = {
		.type = SENSOR_TRIG_DATA_READY,
		.chan = SENSOR_CHAN_ACCEL_XYZ,
	};
	int ret = sensor_trigger_set(imu, &trigger, imu_trigger_handler);

	if (ret < 0) {
		printk("Failed to configure IMU data-ready interrupt: %d\n", ret);
		return ret;
	}

	printk("IMU data-ready interrupt configured on PC13 / INT1\n");
	return 0;
}

static int read_and_print_imu_sample(int32_t irq_count)
{
	struct sensor_value accel[3];
	struct sensor_value gyro[3];
	int ret;

	ret = sensor_sample_fetch(imu);
	if (ret < 0) {
		printk("[IMU] sample fetch failed: %d\n", ret);
		return ret;
	}

	ret = sensor_channel_get(imu, SENSOR_CHAN_ACCEL_XYZ, accel);
	if (ret < 0) {
		printk("[IMU] accel read failed: %d\n", ret);
		return ret;
	}

	ret = sensor_channel_get(imu, SENSOR_CHAN_GYRO_XYZ, gyro);
	if (ret < 0) {
		printk("[IMU] gyro read failed: %d\n", ret);
		return ret;
	}

	printk("[IMU] irq=%d accel(m/s^2) x=", irq_count);
	print_sensor_value(&accel[0]);
	printk(" y=");
	print_sensor_value(&accel[1]);
	printk(" z=");
	print_sensor_value(&accel[2]);
	printk(" gyro(rad/s) x=");
	print_sensor_value(&gyro[0]);
	printk(" y=");
	print_sensor_value(&gyro[1]);
	printk(" z=");
	print_sensor_value(&gyro[2]);
	printk("\n");

	return 0;
}

int main(void)
{
	uint8_t who_am_i;
	int ret;

	printk("\n");
	printk("============================================\n");
	printk("  IMU 6-Axis Interrupt Test for XIAO STM32C5\n");
	printk("============================================\n");
	printk("USB flashing:\n");
	printk("  Connect USB, enter UF2 bootloader, copy firmware.uf2 to the UF2 drive.\n");
	printk("Hardware mapping:\n");
	printk("  IMU          -> LSM6DS3TR-C\n");
	printk("  I2C          -> I2C2, address 0x6A\n");
	printk("  SCL/SDA      -> PB3 / PB4\n");
	printk("  INT1         -> PC13, active-high data-ready interrupt\n");
	printk("  External wiring required: none\n");
	printk("Runtime setup:\n");
	printk("  Accel        -> +/-4g, %d Hz\n", IMU_ODR_HZ);
	printk("  Gyro         -> +/-500 dps, %d Hz\n", IMU_ODR_HZ);

	if (!device_is_ready(imu)) {
		printk("IMU device %s is not ready\n", imu->name);
		return 0;
	}

	if (!i2c_is_ready_dt(&imu_i2c)) {
		printk("IMU I2C bus %s is not ready\n", imu_i2c.bus->name);
		return 0;
	}

	ret = read_who_am_i(&who_am_i);
	if (ret < 0) {
		printk("Failed to read IMU WHO_AM_I: %d\n", ret);
		return 0;
	}

	printk("IMU device: %s\n", imu->name);
	printk("IMU I2C bus: %s\n", imu_i2c.bus->name);
	printk("IMU WHO_AM_I=0x%02x", who_am_i);
	if (who_am_i == LSM6DSL_EXPECTED_WHO_AM_I) {
		printk(" OK\n");
	} else {
		printk(" unexpected, expected 0x%02x\n", LSM6DSL_EXPECTED_WHO_AM_I);
	}

	ret = configure_imu();
	if (ret < 0) {
		return 0;
	}

	ret = configure_imu_interrupt();
	if (ret < 0) {
		printk("Continuing with polling reads so six-axis data can still be checked.\n");
	}

	printk("\nMove or rotate the board; irq counter should increase continuously.\n");

	while (true) {
		ret = k_sem_take(&imu_drdy_sem,
				 K_MSEC(IMU_INTERRUPT_TIMEOUT_MS));
		if (ret < 0) {
			printk("[IMU] no data-ready interrupt in %d ms; polling once\n",
			       IMU_INTERRUPT_TIMEOUT_MS);
		}

		read_and_print_imu_sample(atomic_get(&imu_irq_count));
	}

	return 0;
}
