/*
 * Copyright (c) 2026 Seeed Technology Co., Ltd.
 * SPDX-License-Identifier: Apache-2.0
 *
 * XIAO STM32C5 low-power IMU wake-up sample.
 */

#include <errno.h>
#include <stdbool.h>
#include <stdint.h>

#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/i2c.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

#include <stm32_ll_rcc.h>

#define IMU_NODE DT_ALIAS(imu0)
#define CAN_PHY_NODE DT_NODELABEL(can_phy0)
#define FLASH_CS_GPIO_NODE DT_NODELABEL(gpiob)

#define FLASH_CS_PIN 10U
#define STATUS_INTERVAL_MS 500

#define LSM6DSL_REG_WHO_AM_I 0x0f
#define LSM6DSL_REG_WAKE_UP_SRC 0x1b
#define LSM6DSL_REG_CTRL1_XL 0x10
#define LSM6DSL_REG_CTRL2_G 0x11
#define LSM6DSL_REG_CTRL3_C 0x12
#define LSM6DSL_REG_CTRL6_C 0x15
#define LSM6DSL_REG_TAP_CFG 0x58
#define LSM6DSL_REG_WAKE_UP_THS 0x5b
#define LSM6DSL_REG_WAKE_UP_DUR 0x5c
#define LSM6DSL_REG_MD1_CFG 0x5e
#define LSM6DSL_REG_MD2_CFG 0x5f
#define LSM6DSL_EXPECTED_WHO_AM_I 0x6a

#define LSM6DSL_CTRL3_C_BDU_IF_INC 0x44
#define LSM6DSL_CTRL6_C_XL_LOW_POWER 0x10
#define LSM6DSL_CTRL1_XL_12HZ5_2G 0x10
#define LSM6DSL_CTRL2_G_POWER_DOWN 0x00
#define LSM6DSL_TAP_CFG_INTERRUPTS_ENABLE 0x80
#define LSM6DSL_WAKE_UP_THS_154MG 0x02
#define LSM6DSL_WAKE_UP_DUR_NONE 0x00
#define LSM6DSL_MD1_CFG_INT1_WU 0x20

BUILD_ASSERT(DT_NODE_HAS_STATUS(IMU_NODE, okay),
	     "imu0 alias is not defined or not okay");
BUILD_ASSERT(DT_NODE_HAS_STATUS(CAN_PHY_NODE, okay),
	     "can_phy0 node is not defined or not okay");
BUILD_ASSERT(DT_NODE_HAS_PROP(IMU_NODE, irq_gpios),
	     "imu0 irq-gpios is required for wake-up output");

static const struct i2c_dt_spec imu_i2c = I2C_DT_SPEC_GET(IMU_NODE);
static const struct gpio_dt_spec imu_int1 =
	GPIO_DT_SPEC_GET(IMU_NODE, irq_gpios);
static const struct gpio_dt_spec can_standby =
	GPIO_DT_SPEC_GET(CAN_PHY_NODE, standby_gpios);
static const struct device *const flash_cs_gpio =
	DEVICE_DT_GET(FLASH_CS_GPIO_NODE);

static struct gpio_callback imu_int1_cb;
static volatile uint32_t imu_int1_count;

static int write_imu_reg(uint8_t reg, uint8_t value)
{
	return i2c_reg_write_byte_dt(&imu_i2c, reg, value);
}

static int read_imu_reg(uint8_t reg, uint8_t *value)
{
	return i2c_reg_read_byte_dt(&imu_i2c, reg, value);
}

static void imu_int1_callback(const struct device *dev,
			      struct gpio_callback *cb,
			      uint32_t pins)
{
	ARG_UNUSED(dev);
	ARG_UNUSED(cb);

	if ((pins & BIT(imu_int1.pin)) != 0U) {
		imu_int1_count++;
	}
}

static void print_imu_registers(const char *prefix)
{
	uint8_t who_am_i = 0;
	uint8_t ctrl1_xl = 0;
	uint8_t ctrl2_g = 0;
	uint8_t wake_ths = 0;
	uint8_t md1_cfg = 0;
	int ret;

	ret = read_imu_reg(LSM6DSL_REG_WHO_AM_I, &who_am_i);
	if (ret < 0) {
		printk("%s WHO_AM_I read failed: %d\n", prefix, ret);
		return;
	}

	(void)read_imu_reg(LSM6DSL_REG_CTRL1_XL, &ctrl1_xl);
	(void)read_imu_reg(LSM6DSL_REG_CTRL2_G, &ctrl2_g);
	(void)read_imu_reg(LSM6DSL_REG_WAKE_UP_THS, &wake_ths);
	(void)read_imu_reg(LSM6DSL_REG_MD1_CFG, &md1_cfg);

	printk("%s WHO_AM_I=0x%02x%s CTRL1_XL=0x%02x CTRL2_G=0x%02x WAKE_THS=0x%02x MD1_CFG=0x%02x\n",
	       prefix,
	       who_am_i,
	       who_am_i == LSM6DSL_EXPECTED_WHO_AM_I ? "" : " (unexpected)",
	       ctrl1_xl,
	       ctrl2_g,
	       wake_ths,
	       md1_cfg);
}

static int configure_board_lowpower_pins(void)
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

static int configure_imu_int1_gpio(void)
{
	int ret;

	if (!gpio_is_ready_dt(&imu_int1)) {
		printk("IMU INT1 GPIO is not ready\n");
		return -ENODEV;
	}

	ret = gpio_pin_configure_dt(&imu_int1, GPIO_INPUT);
	if (ret < 0) {
		return ret;
	}

	gpio_init_callback(&imu_int1_cb, imu_int1_callback, BIT(imu_int1.pin));
	ret = gpio_add_callback(imu_int1.port, &imu_int1_cb);
	if (ret < 0) {
		return ret;
	}

	return gpio_pin_interrupt_configure_dt(&imu_int1, GPIO_INT_EDGE_TO_ACTIVE);
}

static int configure_imu_wakeup(void)
{
	int ret;

	ret = write_imu_reg(LSM6DSL_REG_CTRL3_C, LSM6DSL_CTRL3_C_BDU_IF_INC);
	if (ret < 0) {
		return ret;
	}

	ret = write_imu_reg(LSM6DSL_REG_CTRL2_G, LSM6DSL_CTRL2_G_POWER_DOWN);
	if (ret < 0) {
		return ret;
	}

	ret = write_imu_reg(LSM6DSL_REG_CTRL6_C, LSM6DSL_CTRL6_C_XL_LOW_POWER);
	if (ret < 0) {
		return ret;
	}

	ret = write_imu_reg(LSM6DSL_REG_CTRL1_XL, LSM6DSL_CTRL1_XL_12HZ5_2G);
	if (ret < 0) {
		return ret;
	}

	ret = write_imu_reg(LSM6DSL_REG_WAKE_UP_THS, LSM6DSL_WAKE_UP_THS_154MG);
	if (ret < 0) {
		return ret;
	}

	ret = write_imu_reg(LSM6DSL_REG_WAKE_UP_DUR, LSM6DSL_WAKE_UP_DUR_NONE);
	if (ret < 0) {
		return ret;
	}

	ret = write_imu_reg(LSM6DSL_REG_TAP_CFG, LSM6DSL_TAP_CFG_INTERRUPTS_ENABLE);
	if (ret < 0) {
		return ret;
	}

	ret = write_imu_reg(LSM6DSL_REG_MD2_CFG, 0x00);
	if (ret < 0) {
		return ret;
	}

	return write_imu_reg(LSM6DSL_REG_MD1_CFG, LSM6DSL_MD1_CFG_INT1_WU);
}

int main(void)
{
	int ret;

	(void)configure_board_lowpower_pins();

	printk("\n");
	printk("XIAO STM32C5 IMU wake-up sample\n");
	printk("State: flash CS# high, CAN standby, HSE off, accel wake-up detection, gyro off\n");
	printk("IMU mode: accel 12.5 Hz low-power +/-2g, wake threshold ~154 mg on INT1/PC13\n");
	printk("HSE before disable: %s\n", hse_ready() ? "ready/on" : "off/not-ready");
	ret = disable_hse();
	printk("HSE disable ret=%d, after: %s\n",
	       ret, hse_ready() ? "ready/on" : "off/not-ready");

	if (!i2c_is_ready_dt(&imu_i2c)) {
		printk("IMU I2C bus %s is not ready\n", imu_i2c.bus->name);
		return 0;
	}

	print_imu_registers("Before config");

	ret = configure_imu_int1_gpio();
	if (ret < 0) {
		printk("Failed to configure IMU INT1 GPIO: %d\n", ret);
	}

	ret = configure_imu_wakeup();
	if (ret < 0) {
		printk("Failed to configure IMU wake-up mode: %d\n", ret);
		return 0;
	}

	print_imu_registers("After config ");

	while (true) {
		uint8_t wake_src = 0;
		int int_level = gpio_is_ready_dt(&imu_int1) ?
			gpio_pin_get_dt(&imu_int1) : -1;

		(void)read_imu_reg(LSM6DSL_REG_WAKE_UP_SRC, &wake_src);
		printk("[WAKE] int1_count=%u int1=%d WAKE_UP_SRC=0x%02x\n",
		       imu_int1_count, int_level, wake_src);
		k_sleep(K_MSEC(STATUS_INTERVAL_MS));
	}

	return 0;
}
