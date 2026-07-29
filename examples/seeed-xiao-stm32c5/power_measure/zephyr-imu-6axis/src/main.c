/*
 * Copyright (c) 2026 Seeed Technology Co., Ltd.
 * SPDX-License-Identifier: Apache-2.0
 *
 * XIAO STM32C5 low-power IMU six-axis sample.
 *
 * Runtime state:
 * - LSM6DS3TR-C accel + gyro sampling over I2C2.
 * - External flash CS# PB10 driven high, so the flash is deselected/standby.
 * - CAN transceiver standby pin PB14 driven high.
 * - HSE disabled after boot if it is not the active system clock.
 */

#include <errno.h>
#include <stdbool.h>
#include <stdint.h>

#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/i2c.h>
#include <zephyr/drivers/sensor.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

#include <stm32_ll_rcc.h>

#define IMU_NODE DT_ALIAS(imu0)
#define CAN_PHY_NODE DT_NODELABEL(can_phy0)
#define FLASH_CS_GPIO_NODE DT_NODELABEL(gpiob)

#define FLASH_CS_PIN 10U
#define IMU_ODR_HZ 26
#define IMU_PRINT_DECIMALS 6
#define SAMPLE_INTERVAL_MS 1000

#define LSM6DSL_REG_WHO_AM_I 0x0f
#define LSM6DSL_REG_CTRL1_XL 0x10
#define LSM6DSL_REG_CTRL2_G 0x11
#define LSM6DSL_EXPECTED_WHO_AM_I 0x6a

BUILD_ASSERT(DT_NODE_HAS_STATUS(IMU_NODE, okay),
	     "imu0 alias is not defined or not okay");
BUILD_ASSERT(DT_NODE_HAS_STATUS(CAN_PHY_NODE, okay),
	     "can_phy0 node is not defined or not okay");

static const struct device *const imu = DEVICE_DT_GET(IMU_NODE);
static const struct i2c_dt_spec imu_i2c = I2C_DT_SPEC_GET(IMU_NODE);
static const struct gpio_dt_spec can_standby =
	GPIO_DT_SPEC_GET(CAN_PHY_NODE, standby_gpios);
static const struct device *const flash_cs_gpio =
	DEVICE_DT_GET(FLASH_CS_GPIO_NODE);

static int32_t abs_i32(int32_t value)
{
	return value < 0 ? -value : value;
}

static void print_sensor_value(const struct sensor_value *value)
{
	int32_t micro_value = (value->val1 * 1000000) + value->val2;
	int32_t abs_value = abs_i32(micro_value);

	printk("%s%d.%0*d",
	       micro_value < 0 ? "-" : "",
	       abs_value / 1000000,
	       IMU_PRINT_DECIMALS,
	       abs_value % 1000000);
}

static int read_imu_reg(uint8_t reg, uint8_t *value)
{
	return i2c_reg_read_byte_dt(&imu_i2c, reg, value);
}

static void print_imu_registers(const char *prefix)
{
	uint8_t who_am_i = 0;
	uint8_t ctrl1_xl = 0;
	uint8_t ctrl2_g = 0;
	int ret;

	ret = read_imu_reg(LSM6DSL_REG_WHO_AM_I, &who_am_i);
	if (ret < 0) {
		printk("%s WHO_AM_I read failed: %d\n", prefix, ret);
		return;
	}

	(void)read_imu_reg(LSM6DSL_REG_CTRL1_XL, &ctrl1_xl);
	(void)read_imu_reg(LSM6DSL_REG_CTRL2_G, &ctrl2_g);

	printk("%s WHO_AM_I=0x%02x%s CTRL1_XL=0x%02x CTRL2_G=0x%02x\n",
	       prefix,
	       who_am_i,
	       who_am_i == LSM6DSL_EXPECTED_WHO_AM_I ? "" : " (unexpected)",
	       ctrl1_xl,
	       ctrl2_g);
}

static int configure_board_standby_pins(void)
{
	int ret;

	if (!device_is_ready(flash_cs_gpio)) {
		printk("GPIOB is not ready; cannot drive flash CS# PB10 high\n");
		return -ENODEV;
	}

	ret = gpio_pin_configure(flash_cs_gpio, FLASH_CS_PIN, GPIO_OUTPUT_HIGH);
	if (ret < 0) {
		printk("Failed to drive flash CS# PB10 high: %d\n", ret);
		return ret;
	}

	if (!gpio_is_ready_dt(&can_standby)) {
		printk("CAN standby GPIO is not ready\n");
		return -ENODEV;
	}

	ret = gpio_pin_configure_dt(&can_standby, GPIO_OUTPUT_ACTIVE);
	if (ret < 0) {
		printk("Failed to drive CAN_STB active: %d\n", ret);
		return ret;
	}

	return 0;
}

static bool hse_ready(void)
{
#if defined(RCC_CR1_HSERDY)
	return LL_RCC_HSE_IsReady() != 0U;
#else
	return false;
#endif
}

static int disable_hse(void)
{
#if defined(RCC_CR1_HSEON)
#if defined(LL_RCC_SYS_CLKSOURCE_STATUS_HSE)
	if (LL_RCC_GetSysClkSource() == LL_RCC_SYS_CLKSOURCE_STATUS_HSE) {
		return -EBUSY;
	}
#endif

#if defined(RCC_CR1_PSISON)
	LL_RCC_PSIS_Disable();
#endif

	LL_RCC_HSE_Disable();
	for (uint32_t timeout = 100000U; timeout > 0U; timeout--) {
		if (!hse_ready()) {
			return 0;
		}
	}

	return -EBUSY;
#else
	return -ENOTSUP;
#endif
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

static int read_and_print_imu_sample(uint32_t sample_count)
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

	printk("[IMU %u] accel(m/s^2) x=", sample_count);
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
	uint32_t sample_count = 0;
	int ret;

	(void)configure_board_standby_pins();

	printk("\n");
	printk("XIAO STM32C5 low-power IMU six-axis sample\n");
	printk("State: flash CS# PB10 high, CAN_STB PB14 high, HSE off, IMU 6-axis %d Hz\n",
	       IMU_ODR_HZ);
	printk("IMU: LSM6DS3TR-C on I2C2 PB3/PB4, address 0x6a\n");
	printk("HSE before disable: %s\n", hse_ready() ? "ready/on" : "off/not-ready");

	ret = disable_hse();
	printk("HSE disable ret=%d, after: %s\n",
	       ret, hse_ready() ? "ready/on" : "off/not-ready");

	if (!device_is_ready(imu)) {
		printk("IMU device %s is not ready\n", imu->name);
		return 0;
	}

	if (!i2c_is_ready_dt(&imu_i2c)) {
		printk("IMU I2C bus %s is not ready\n", imu_i2c.bus->name);
		return 0;
	}

	printk("IMU device: %s\n", imu->name);
	printk("IMU I2C bus: %s\n", imu_i2c.bus->name);
	print_imu_registers("Before config");

	ret = configure_imu();
	if (ret < 0) {
		return 0;
	}

	print_imu_registers("After config ");

	while (true) {
		(void)read_and_print_imu_sample(++sample_count);
		k_sleep(K_MSEC(SAMPLE_INTERVAL_MS));
	}

	return 0;
}
