/*
 * Copyright (c) 2026 Seeed Technology Co., Ltd.
 * SPDX-License-Identifier: Apache-2.0
 *
 * I2C speed test for XIAO STM32C5 with DHT20.
 * The test configures I2C1 from low speed upward, triggers DHT20
 * measurements, validates CRC, and reports the fastest stable mode.
 */

#include <errno.h>
#include <stdint.h>

#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/i2c.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/printk.h>
#include <zephyr/sys/util.h>

LOG_MODULE_REGISTER(i2c_speed_dht20, LOG_LEVEL_INF);

#define I2C_NODE DT_NODELABEL(i2c1)

#define DHT20_ADDR                 0x38
#define DHT20_ADDR_STM32_HAL       (DHT20_ADDR << 1)
#define DHT20_READ_ADDR_BYTE       (DHT20_ADDR_STM32_HAL | 0x01)

#define DHT20_CMD_STATUS           0x71
#define DHT20_CMD_INIT             0xBE
#define DHT20_CMD_TRIGGER          0xAC
#define DHT20_CMD_ARG0             0x33
#define DHT20_CMD_ARG1             0x00
#define DHT20_CMD_INIT_ARG0        0x08
#define DHT20_CMD_INIT_ARG1        0x00

#define DHT20_STATUS_BUSY          BIT(7)
#define DHT20_STATUS_CALIBRATED    BIT(3)

#define DHT20_FRAME_LENGTH         7
#define DHT20_CRC_POLY             0x31
#define DHT20_CRC_INIT             0xFF

#define NUM_ITERATIONS             20
#define WARMUP_ITERATIONS          2
#define QUICK_CHECK_ITERATIONS     3

struct i2c_speed_config {
	uint32_t speed_const;
	const char *name;
	uint32_t freq_hz;
};

struct dht20_sample {
	uint32_t humidity_raw;
	uint32_t temperature_raw;
	uint32_t humidity_milli_percent;
	int32_t temperature_milli_c;
	uint8_t status;
	uint8_t raw[DHT20_FRAME_LENGTH];
};

static const struct i2c_speed_config test_speeds[] = {
	{ I2C_SPEED_STANDARD,  "100 kHz (Standard)",  100000 },
	{ I2C_SPEED_FAST,      "400 kHz (Fast)",      400000 },
	{ I2C_SPEED_FAST_PLUS, "1 MHz (Fast Plus)",   1000000 },
	{ I2C_SPEED_HIGH,      "3.4 MHz (High)",      3400000 },
};

static const struct device *i2c_dev;

static void print_wiring_info(void)
{
	printk("\nWiring:\n");
	printk("  DHT20 SCL -> XIAO D5 / PB6 / I2C1_SCL\n");
	printk("  DHT20 SDA -> XIAO D4 / PB7 / I2C1_SDA\n");
	printk("  DHT20 VCC -> XIAO 3V3\n");
	printk("  DHT20 GND -> XIAO GND\n");
	printk("  Sensor model: DHT20\n");
	printk("  I2C 7-bit address / driver ID: 0x%02X\n", DHT20_ADDR);
	printk("  STM32 HAL address: 0x%02X, read address byte: 0x%02X\n",
	       DHT20_ADDR_STM32_HAL, DHT20_READ_ADDR_BYTE);
	printk("  Start at low speed; short wires and pull-ups help at high speed.\n");
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

static uint8_t dht20_crc8(const uint8_t *data, size_t len)
{
	uint8_t crc = DHT20_CRC_INIT;

	for (size_t i = 0; i < len; i++) {
		crc ^= data[i];
		for (int bit = 0; bit < 8; bit++) {
			if ((crc & 0x80) != 0U) {
				crc = (uint8_t)((crc << 1) ^ DHT20_CRC_POLY);
			} else {
				crc <<= 1;
			}
		}
	}

	return crc;
}

static int dht20_read_status(uint8_t *status)
{
	uint8_t cmd = DHT20_CMD_STATUS;
	int ret;

	ret = i2c_write_read(i2c_dev, DHT20_ADDR, &cmd, sizeof(cmd),
			     status, sizeof(*status));
	if (ret == 0) {
		return 0;
	}

	return i2c_read(i2c_dev, status, sizeof(*status), DHT20_ADDR);
}

static int dht20_detect(void)
{
	uint8_t status;
	int ret;

	ret = dht20_read_status(&status);
	if (ret != 0) {
		printk("DHT20 not found at 0x%02X (ret=%d)\n",
		       DHT20_ADDR, ret);
		return ret;
	}

	printk("DHT20 found at 0x%02X, status=0x%02X",
	       DHT20_ADDR, status);
	printk(" [busy=%u calibrated=%u]\n",
	       (status & DHT20_STATUS_BUSY) ? 1U : 0U,
	       (status & DHT20_STATUS_CALIBRATED) ? 1U : 0U);
	return 0;
}

static int dht20_init(void)
{
	uint8_t status;
	uint8_t init_cmd[] = {
		DHT20_CMD_INIT,
		DHT20_CMD_INIT_ARG0,
		DHT20_CMD_INIT_ARG1,
	};
	int ret;

	k_msleep(100);

	ret = dht20_read_status(&status);
	if (ret != 0) {
		printk("Initial status read failed (ret=%d)\n", ret);
		return ret;
	}

	if ((status & DHT20_STATUS_CALIBRATED) != 0U) {
		printk("DHT20 already calibrated (status=0x%02X)\n", status);
		return 0;
	}

	printk("DHT20 not calibrated yet (status=0x%02X), sending init command\n",
	       status);

	ret = i2c_write(i2c_dev, init_cmd, sizeof(init_cmd), DHT20_ADDR);
	if (ret != 0) {
		printk("DHT20 init command failed (ret=%d)\n", ret);
		return ret;
	}

	k_msleep(10);

	ret = dht20_read_status(&status);
	if (ret != 0) {
		printk("Post-init status read failed (ret=%d)\n", ret);
		return ret;
	}

	printk("DHT20 post-init status=0x%02X [calibrated=%u]\n",
	       status, (status & DHT20_STATUS_CALIBRATED) ? 1U : 0U);
	return 0;
}

static int dht20_read_sample(struct dht20_sample *sample)
{
	uint8_t trigger[] = {
		DHT20_CMD_TRIGGER,
		DHT20_CMD_ARG0,
		DHT20_CMD_ARG1,
	};
	uint8_t calc_crc;
	int ret;

	ret = i2c_write(i2c_dev, trigger, sizeof(trigger), DHT20_ADDR);
	if (ret != 0) {
		return ret;
	}

	k_msleep(80);

	ret = i2c_read(i2c_dev, sample->raw, sizeof(sample->raw), DHT20_ADDR);
	if (ret != 0) {
		return ret;
	}

	sample->status = sample->raw[0];
	if ((sample->status & DHT20_STATUS_BUSY) != 0U) {
		return -EBUSY;
	}

	calc_crc = dht20_crc8(sample->raw, DHT20_FRAME_LENGTH - 1U);
	if (calc_crc != sample->raw[DHT20_FRAME_LENGTH - 1U]) {
		printk("CRC mismatch: got 0x%02X expected 0x%02X\n",
		       sample->raw[DHT20_FRAME_LENGTH - 1U], calc_crc);
		return -EBADMSG;
	}

	sample->humidity_raw = ((uint32_t)sample->raw[1] << 12) |
			       ((uint32_t)sample->raw[2] << 4) |
			       ((uint32_t)sample->raw[3] >> 4);
	sample->temperature_raw = (((uint32_t)sample->raw[3] & 0x0FU) << 16) |
				  ((uint32_t)sample->raw[4] << 8) |
				  (uint32_t)sample->raw[5];

	sample->humidity_milli_percent =
		(uint32_t)(((uint64_t)sample->humidity_raw * 100000ULL) /
			   1048576ULL);
	sample->temperature_milli_c =
		(int32_t)(((int64_t)sample->temperature_raw * 200000LL) /
			  1048576LL) - 50000;

	return 0;
}

static void print_milli_unsigned(uint32_t value_milli, const char *unit)
{
	printk("%u.%03u %s", value_milli / 1000U, value_milli % 1000U, unit);
}

static void print_milli_signed(int32_t value_milli, const char *unit)
{
	uint32_t magnitude;

	if (value_milli < 0) {
		printk("-");
		magnitude = (uint32_t)(-value_milli);
	} else {
		magnitude = (uint32_t)value_milli;
	}

	printk("%u.%03u %s", magnitude / 1000U, magnitude % 1000U, unit);
}

static bool quick_speed_check(const struct i2c_speed_config *speed_cfg)
{
	struct dht20_sample sample;
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
		ret = dht20_read_sample(&sample);
		if (ret == 0) {
			success++;
		} else {
			failures++;
		}
		k_msleep(5);
	}

	if (failures == 0) {
		printk("OK (%d/%d successful)\n",
		       success, QUICK_CHECK_ITERATIONS);
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
	struct dht20_sample sample = { 0 };
	uint32_t success_count = 0;
	uint32_t fail_count = 0;
	uint64_t start_time;
	uint64_t total_time_us;
	uint32_t wire_bytes;
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

	ret = dht20_detect();
	if (ret != 0) {
		printk("DHT20 not responsive at %s - SKIPPED (ret=%d)\n",
		       speed_cfg->name, ret);
		return;
	}

	for (int i = 0; i < WARMUP_ITERATIONS; i++) {
		(void)dht20_read_sample(&sample);
		k_msleep(5);
	}

	start_time = k_ticks_to_us_floor64(k_uptime_ticks());

	for (int i = 0; i < NUM_ITERATIONS; i++) {
		ret = dht20_read_sample(&sample);
		if (ret == 0) {
			success_count++;
		} else {
			fail_count++;
			LOG_WRN("Read failed at iteration %d: %d", i, ret);
		}
		k_msleep(5);
	}

	total_time_us = k_ticks_to_us_floor64(k_uptime_ticks()) - start_time;
	wire_bytes = success_count * (sizeof(uint8_t) * 3U +
				      DHT20_FRAME_LENGTH);

	printk("\n--- Test Results ---\n");
	printk("  Speed Setting:       %s\n", speed_cfg->name);
	printk("  Iterations:          %d\n", NUM_ITERATIONS);
	printk("  Successful:          %u\n", success_count);
	printk("  Failed:              %u\n", fail_count);
	printk("  Total Time:          %llu us\n", total_time_us);

	if (success_count > 0U && total_time_us > 0U) {
		uint64_t avg_us = total_time_us / success_count;
		uint64_t throughput = (uint64_t)wire_bytes * 1000000ULL /
				      total_time_us;
		uint64_t effective_bitrate = throughput * 9ULL;

		printk("  Avg per Measurement: %llu us\n", avg_us);
		printk("  Wire Payload Bytes:  %u bytes\n", wire_bytes);
		printk("  Effective Payload:   %llu bytes/s\n", throughput);
		printk("  Effective Bit Rate:  %llu kbps (%llu bps)\n",
		       effective_bitrate / 1000ULL, effective_bitrate);
	} else {
		printk("  Avg per Measurement: n/a\n");
		printk("  Effective Payload:   n/a\n");
	}

	printk("  Status:              %s\n",
	       fail_count == 0U ? "STABLE" : "*** UNSTABLE ***");

	if (success_count > 0U) {
		printk("\nLast DHT20 sample:\n");
		printk("  Status Byte:         0x%02X\n", sample.status);
		printk("  Humidity Raw:        %u\n", sample.humidity_raw);
		printk("  Temperature Raw:     %u\n", sample.temperature_raw);
		printk("  Humidity:            ");
		print_milli_unsigned(sample.humidity_milli_percent, "%RH");
		printk("\n");
		printk("  Temperature:         ");
		print_milli_signed(sample.temperature_milli_c, "C");
		printk("\n");
		printk("  Raw Frame:           ");
		for (size_t i = 0; i < DHT20_FRAME_LENGTH; i++) {
			printk("%02X ", sample.raw[i]);
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
	printk("  Target: DHT20 Temperature & Humidity @ 0x38\n");
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

	ret = configure_speed(&test_speeds[0]);
	if (ret != 0) {
		printk("Error: cannot configure initial 100 kHz I2C speed (ret=%d)\n",
		       ret);
		return 0;
	}

	printk("\nChecking sensor at low speed first...\n");
	ret = dht20_detect();
	if (ret != 0) {
		printk("Error: DHT20 not found.\n");
		printk("Check wiring: D5/PB6=SCL, D4/PB7=SDA, 3V3, GND.\n");
		return 0;
	}

	ret = dht20_init();
	if (ret != 0) {
		printk("Warning: DHT20 initialization failed (ret=%d); continuing with measurement test.\n",
		       ret);
	} else {
		printk("DHT20 initialization complete\n");
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
	printk("  - DHT20 driver/model: DHT20, fixed 7-bit I2C address 0x38.\n");
	printk("  - Typical DHT20 buses use 100 kHz or 400 kHz; higher modes may fail.\n");
	printk("  - Measurement timing includes the DHT20 conversion delay.\n");

	return 0;
}
