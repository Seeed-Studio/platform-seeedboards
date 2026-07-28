/*
 * Copyright (c) 2026 Seeed Technology Co., Ltd.
 * SPDX-License-Identifier: Apache-2.0
 *
 * I2C speed test for XIAO STM32C5 with BME280/BMP280.
 * The test configures I2C1 through several speed modes, reads the sensor data
 * registers repeatedly, and reports the fastest stable mode.
 */

#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/i2c.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/printk.h>
#include <zephyr/sys/util.h>

LOG_MODULE_REGISTER(i2c_speed_bme280, LOG_LEVEL_INF);

#define I2C_NODE DT_NODELABEL(i2c1)

#define BME280_ADDR_PRIMARY        0x76
#define BME280_ADDR_SECONDARY      0x77

#define BME280_REG_ID              0xD0
#define BME280_REG_RESET           0xE0
#define BME280_REG_CTRL_HUM        0xF2
#define BME280_REG_STATUS          0xF3
#define BME280_REG_CTRL_MEAS       0xF4
#define BME280_REG_CONFIG          0xF5
#define BME280_REG_DATA            0xF7

#define BME280_CHIP_ID             0x60
#define BMP280_CHIP_ID             0x58

#define NUM_ITERATIONS             100
#define WARMUP_ITERATIONS          10
#define QUICK_CHECK_ITERATIONS     10
#define BME280_DATA_LENGTH         8
#define BMP280_DATA_LENGTH         6
#define MAX_DATA_LENGTH            BME280_DATA_LENGTH

struct i2c_speed_config {
	uint32_t speed_const;
	const char *name;
	uint32_t freq_hz;
};

static const struct i2c_speed_config test_speeds[] = {
	{ I2C_SPEED_STANDARD,  "100 kHz (Standard)",  100000 },
	{ I2C_SPEED_FAST,      "400 kHz (Fast)",      400000 },
	{ I2C_SPEED_FAST_PLUS, "1 MHz (Fast Plus)",   1000000 },
	{ I2C_SPEED_HIGH,      "3.4 MHz (High)",      3400000 },
};

static const struct device *i2c_dev;
static uint8_t sensor_addr;
static uint8_t sensor_chip_id;
static size_t sensor_data_len;

static void print_wiring_info(void)
{
	printk("\nWiring:\n");
	printk("  BME280/BMP280 SCL -> XIAO D5 / PB6 / I2C1_SCL\n");
	printk("  BME280/BMP280 SDA -> XIAO D4 / PB7 / I2C1_SDA\n");
	printk("  BME280/BMP280 VCC -> XIAO 3V3\n");
	printk("  BME280/BMP280 GND -> XIAO GND\n");
	printk("  Sensor address: 0x%02X or 0x%02X\n",
	       BME280_ADDR_PRIMARY, BME280_ADDR_SECONDARY);
	printk("  Use short wires and suitable pull-ups for high-speed I2C.\n");
}

static const char *speed_name_from_config(uint32_t config)
{
	switch (I2C_SPEED_GET(config)) {
	case I2C_SPEED_STANDARD:
		return "100 kHz (Standard)";
	case I2C_SPEED_FAST:
		return "400 kHz (Fast)";
	case I2C_SPEED_FAST_PLUS:
		return "1 MHz (Fast Plus)";
	case I2C_SPEED_HIGH:
		return "3.4 MHz (High)";
	case I2C_SPEED_ULTRA:
		return "5 MHz (Ultra Fast)";
	case I2C_SPEED_DT:
		return "Devicetree";
	default:
		return "Unknown";
	}
}

static int configure_speed(const struct i2c_speed_config *speed_cfg)
{
	return i2c_configure(i2c_dev,
			     I2C_MODE_CONTROLLER |
			     I2C_SPEED_SET(speed_cfg->speed_const));
}

static int sensor_read_chip_id(uint8_t addr, uint8_t *chip_id)
{
	return i2c_reg_read_byte(i2c_dev, addr, BME280_REG_ID, chip_id);
}

static int sensor_check(uint8_t addr)
{
	uint8_t chip_id;
	int ret = sensor_read_chip_id(addr, &chip_id);

	if (ret != 0) {
		return ret;
	}

	if (chip_id != BME280_CHIP_ID && chip_id != BMP280_CHIP_ID) {
		printk("Unexpected chip ID at 0x%02X: 0x%02X\n", addr, chip_id);
		return -ENODEV;
	}

	sensor_addr = addr;
	sensor_chip_id = chip_id;
	sensor_data_len = chip_id == BME280_CHIP_ID ? BME280_DATA_LENGTH :
						 BMP280_DATA_LENGTH;
	printk("Sensor found at 0x%02X, chip ID 0x%02X (%s)\n",
	       sensor_addr, sensor_chip_id,
	       sensor_chip_id == BME280_CHIP_ID ? "BME280" : "BMP280");
	printk("Sensor data read length: %u bytes\n", (uint32_t)sensor_data_len);
	return 0;
}

static int sensor_detect(void)
{
	int ret = sensor_check(BME280_ADDR_PRIMARY);

	if (ret == 0) {
		return 0;
	}

	return sensor_check(BME280_ADDR_SECONDARY);
}

static int sensor_init(void)
{
	uint8_t status;
	int ret;

	printk("Initializing %s...\n",
	       sensor_chip_id == BME280_CHIP_ID ? "BME280" : "BMP280");

	ret = i2c_reg_write_byte(i2c_dev, sensor_addr, BME280_REG_RESET, 0xB6);
	if (ret != 0) {
		printk("  Soft reset failed (reg 0x%02X, ret=%d)\n",
		       BME280_REG_RESET, ret);
		return ret;
	}

	k_msleep(50);

	for (int i = 0; i < 20; i++) {
		ret = i2c_reg_read_byte(i2c_dev, sensor_addr, BME280_REG_STATUS,
					&status);
		if (ret != 0) {
			printk("  Status read failed (reg 0x%02X, ret=%d)\n",
			       BME280_REG_STATUS, ret);
			return ret;
		}

		if ((status & BIT(0)) == 0U) {
			break;
		}

		k_msleep(5);
	}

	if (sensor_chip_id == BME280_CHIP_ID) {
		ret = i2c_reg_write_byte(i2c_dev, sensor_addr,
					 BME280_REG_CTRL_HUM, 0x01);
		if (ret != 0) {
			printk("  Humidity config failed (reg 0x%02X, ret=%d)\n",
			       BME280_REG_CTRL_HUM, ret);
			return ret;
		}
	}

	/* CONFIG is only latched while the sensor is in sleep mode. */
	ret = i2c_reg_write_byte(i2c_dev, sensor_addr, BME280_REG_CONFIG,
				 0x00);
	if (ret != 0) {
		printk("  Filter/standby config failed (reg 0x%02X, ret=%d)\n",
		       BME280_REG_CONFIG, ret);
		return ret;
	}

	ret = i2c_reg_write_byte(i2c_dev, sensor_addr, BME280_REG_CTRL_MEAS,
				 0x27);
	if (ret != 0) {
		printk("  Measurement config failed (reg 0x%02X, ret=%d)\n",
		       BME280_REG_CTRL_MEAS, ret);
		return ret;
	}

	return 0;
}

static int sensor_read_data(uint8_t *data, size_t len)
{
	uint8_t reg = BME280_REG_DATA;
	struct i2c_msg msgs[2] = {
		{
			.buf = &reg,
			.len = sizeof(reg),
			.flags = I2C_MSG_WRITE,
		},
		{
			.buf = data,
			.len = len,
			.flags = I2C_MSG_RESTART | I2C_MSG_READ | I2C_MSG_STOP,
		},
	};

	return i2c_transfer(i2c_dev, msgs, ARRAY_SIZE(msgs), sensor_addr);
}

static bool quick_speed_check(const struct i2c_speed_config *speed_cfg)
{
	uint8_t data[MAX_DATA_LENGTH];
	int success = 0;
	int failures = 0;
	int ret;

	printk("Trying %s... ", speed_cfg->name);

	ret = configure_speed(speed_cfg);
	if (ret != 0) {
		printk("NOT SUPPORTED (ret=%d)\n", ret);
		return false;
	}

	k_msleep(5);

	for (int i = 0; i < QUICK_CHECK_ITERATIONS; i++) {
		ret = sensor_read_data(data, sensor_data_len);
		if (ret == 0) {
			success++;
		} else {
			failures++;
		}
		k_msleep(1);
	}

	if (failures == 0) {
		printk("OK (%d/%d successful)\n", success, QUICK_CHECK_ITERATIONS);
		return true;
	}

	printk("UNSTABLE (%d failures)\n", failures);
	return false;
}

static int find_fastest_stable_speed(void)
{
	int fastest_stable_idx = -1;

	printk("\n");
	printk("========================================\n");
	printk("Finding Fastest Stable Speed\n");
	printk("========================================\n");

	for (int i = 0; i < ARRAY_SIZE(test_speeds); i++) {
		if (quick_speed_check(&test_speeds[i])) {
			fastest_stable_idx = i;
		}
	}

	printk("\n");
	if (fastest_stable_idx >= 0) {
		printk(">>> Fastest stable speed: %s <<<\n",
		       test_speeds[fastest_stable_idx].name);
	} else {
		printk(">>> No stable speed found! <<<\n");
	}

	return fastest_stable_idx;
}

static void run_speed_test(const struct i2c_speed_config *speed_cfg)
{
	uint8_t data[MAX_DATA_LENGTH] = { 0 };
	uint32_t success_count = 0;
	uint32_t fail_count = 0;
	uint64_t start_time;
	uint64_t total_time_us;
	uint32_t payload_bytes;
	int ret;

	printk("\n");
	printk("========================================\n");
	printk("Testing: %s\n", speed_cfg->name);
	printk("========================================\n");

	ret = configure_speed(speed_cfg);
	if (ret != 0) {
		printk("Configuration FAILED (ret=%d) - SKIPPED\n", ret);
		return;
	}

	k_msleep(10);

	ret = sensor_check(sensor_addr);
	if (ret != 0) {
		printk("Sensor not responsive at %s - SKIPPED (ret=%d)\n",
		       speed_cfg->name, ret);
		return;
	}

	for (int i = 0; i < WARMUP_ITERATIONS; i++) {
		(void)sensor_read_data(data, sensor_data_len);
		k_msleep(1);
	}

	start_time = k_ticks_to_us_floor64(k_uptime_ticks());

	for (int i = 0; i < NUM_ITERATIONS; i++) {
		ret = sensor_read_data(data, sensor_data_len);
		if (ret == 0) {
			success_count++;
		} else {
			fail_count++;
			LOG_WRN("Read failed at iteration %d: %d", i, ret);
		}
	}

	total_time_us = k_ticks_to_us_floor64(k_uptime_ticks()) - start_time;
	payload_bytes = success_count * (sensor_data_len + 1U);

	printk("\n--- Test Results ---\n");
	printk("  Speed Setting:       %s\n", speed_cfg->name);
	printk("  Iterations:          %d\n", NUM_ITERATIONS);
	printk("  Successful:          %u\n", success_count);
	printk("  Failed:              %u\n", fail_count);
	printk("  Total Time:          %llu us\n", total_time_us);

	if (success_count > 0U && total_time_us > 0U) {
		uint64_t avg_us = total_time_us / success_count;
		uint64_t throughput = (uint64_t)payload_bytes * 1000000ULL /
				      total_time_us;
		uint64_t effective_bitrate = throughput * 9ULL;
		uint64_t theoretical_bytes = speed_cfg->freq_hz / 9ULL;
		uint32_t efficiency = (uint32_t)((throughput * 100ULL) /
						 theoretical_bytes);

		printk("  Avg per Transaction: %llu us\n", avg_us);
		printk("  Payload Bytes:       %u bytes\n", payload_bytes);
		printk("  Throughput:          %llu bytes/s\n", throughput);
		printk("  Effective Bit Rate:  %llu kbps (%llu bps)\n",
		       effective_bitrate / 1000ULL, effective_bitrate);
		printk("  Theoretical Max:     %llu bytes/s\n",
		       theoretical_bytes);
		printk("  Bus Efficiency:      %u%%\n", efficiency);
	} else {
		printk("  Avg per Transaction: n/a\n");
		printk("  Throughput:          n/a\n");
	}

	printk("  Status:              %s\n",
	       fail_count == 0U ? "STABLE" : "*** UNSTABLE ***");

	if (success_count > 0U) {
		printk("\nLast sensor data (raw hex): ");
		for (size_t i = 0; i < sensor_data_len; i++) {
			printk("%02X ", data[i]);
		}
		printk("\n");
	}
}

int main(void)
{
	uint32_t current_config;
	int fastest_idx;
	int ret;

	printk("\n");
	printk("============================================\n");
	printk("  I2C Speed Test for XIAO STM32C5\n");
	printk("  Target: BME280/BMP280 @ 0x76 or 0x77\n");
	printk("  Bus: I2C1 on XIAO D5(SCL) / D4(SDA)\n");
	printk("============================================\n");
	print_wiring_info();

	i2c_dev = DEVICE_DT_GET(I2C_NODE);
	if (!device_is_ready(i2c_dev)) {
		printk("Error: I2C device not ready\n");
		return 0;
	}

	printk("I2C device: %s\n", i2c_dev->name);

	ret = i2c_get_config(i2c_dev, &current_config);
	if (ret == 0) {
		printk("Default I2C speed from config: %s\n",
		       speed_name_from_config(current_config));
	}

	printk("\nChecking sensor...\n");
	ret = sensor_detect();
	if (ret != 0) {
		printk("Error: BME280/BMP280 not found.\n");
		printk("Check wiring: D5/PB6=SCL, D4/PB7=SDA, 3V3, GND.\n");
		return 0;
	}

	ret = sensor_init();
	if (ret != 0) {
		printk("Warning: sensor initialization failed (ret=%d); continuing with raw read speed test.\n",
		       ret);
	} else {
		printk("Sensor initialized successfully\n");
	}

	fastest_idx = find_fastest_stable_speed();

	for (int i = 0; i < ARRAY_SIZE(test_speeds); i++) {
		run_speed_test(&test_speeds[i]);
		k_msleep(100);
	}

	printk("\n");
	printk("============================================\n");
	printk("  I2C Speed Test Complete\n");
	printk("============================================\n");

	if (fastest_idx >= 0) {
		printk("Fastest stable speed: %s\n",
		       test_speeds[fastest_idx].name);
	} else {
		printk("Fastest stable speed: none\n");
	}

	printk("Notes:\n");
	printk("  - Unsupported modes are rejected by the I2C driver.\n");
	printk("  - Stable speed depends on pull-ups, wire length, and bus capacitance.\n");

	return 0;
}
