/*
 * Copyright (c) 2026 Seeed Technology Co., Ltd.
 * SPDX-License-Identifier: Apache-2.0
 *
 * Continuous DHT20 read sample for XIAO STM32C5.
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

LOG_MODULE_REGISTER(i2c_dht20_read, LOG_LEVEL_INF);

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

#define SAMPLE_PERIOD_MS           1000
#define MEASUREMENT_DELAY_MS       80

struct dht20_sample {
	uint32_t humidity_raw;
	uint32_t temperature_raw;
	uint32_t humidity_milli_percent;
	int32_t temperature_milli_c;
	uint8_t status;
	uint8_t raw[DHT20_FRAME_LENGTH];
};

static const struct device *i2c_dev;

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
		printk("DHT20 status read failed at 0x%02X (ret=%d)\n",
		       DHT20_ADDR, ret);
		return ret;
	}

	printk("DHT20 status=0x%02X [busy=%u calibrated=%u]\n",
	       status,
	       (status & DHT20_STATUS_BUSY) ? 1U : 0U,
	       (status & DHT20_STATUS_CALIBRATED) ? 1U : 0U);

	if ((status & DHT20_STATUS_CALIBRATED) != 0U) {
		return 0;
	}

	ret = i2c_write(i2c_dev, init_cmd, sizeof(init_cmd), DHT20_ADDR);
	if (ret != 0) {
		printk("DHT20 init command failed (ret=%d)\n", ret);
		return ret;
	}

	k_msleep(10);

	ret = dht20_read_status(&status);
	if (ret != 0) {
		printk("DHT20 post-init status read failed (ret=%d)\n", ret);
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

	k_msleep(MEASUREMENT_DELAY_MS);

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

static void print_milli_unsigned(uint32_t value_milli)
{
	printk("%u.%03u", value_milli / 1000U, value_milli % 1000U);
}

static void print_milli_signed(int32_t value_milli)
{
	uint32_t magnitude;

	if (value_milli < 0) {
		printk("-");
		magnitude = (uint32_t)(-value_milli);
	} else {
		magnitude = (uint32_t)value_milli;
	}

	printk("%u.%03u", magnitude / 1000U, magnitude % 1000U);
}

static void print_raw_frame(const uint8_t *data, size_t len)
{
	for (size_t i = 0; i < len; i++) {
		printk("%02X", data[i]);
		if (i + 1U < len) {
			printk(" ");
		}
	}
}

static void print_sample(uint32_t seq, const struct dht20_sample *sample)
{
	printk("[%u] temperature=", seq);
	print_milli_signed(sample->temperature_milli_c);
	printk(" C, humidity=");
	print_milli_unsigned(sample->humidity_milli_percent);
	printk(" %%RH, status=0x%02X, raw=", sample->status);
	print_raw_frame(sample->raw, DHT20_FRAME_LENGTH);
	printk("\n");
}

int main(void)
{
	struct dht20_sample sample;
	uint32_t seq = 0;
	int ret;

	printk("\n");
	printk("============================================\n");
	printk("  XIAO STM32C5 DHT20 Continuous Read\n");
	printk("  Model: DHT20, I2C 7-bit address: 0x%02X\n", DHT20_ADDR);
	printk("  STM32 HAL address: 0x%02X, read byte: 0x%02X\n",
	       DHT20_ADDR_STM32_HAL, DHT20_READ_ADDR_BYTE);
	printk("  Bus: I2C1 on XIAO D5(SCL) / D4(SDA), 400 kHz\n");
	printk("============================================\n");

	i2c_dev = DEVICE_DT_GET(I2C_NODE);
	if (!device_is_ready(i2c_dev)) {
		printk("Error: I2C device not ready\n");
		return 0;
	}

	printk("I2C device: %s\n", i2c_dev->name);

	ret = i2c_configure(i2c_dev,
			    I2C_MODE_CONTROLLER |
			    I2C_SPEED_SET(I2C_SPEED_FAST));
	if (ret != 0) {
		printk("Error: cannot configure I2C speed (ret=%d)\n", ret);
		return 0;
	}

	ret = dht20_init();
	if (ret != 0) {
		printk("Error: DHT20 init failed. Check D5/PB6=SCL, D4/PB7=SDA, 3V3, GND.\n");
		return 0;
	}

	printk("Reading DHT20 once per second...\n");

	while (true) {
		ret = dht20_read_sample(&sample);
		if (ret == 0) {
			print_sample(seq, &sample);
		} else {
			printk("[%u] DHT20 read failed (ret=%d)\n", seq, ret);
		}

		seq++;
		k_msleep(SAMPLE_PERIOD_MS);
	}

	return 0;
}
