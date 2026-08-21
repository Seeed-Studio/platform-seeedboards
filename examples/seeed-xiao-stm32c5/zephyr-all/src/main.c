/*
 * Copyright (c) 2026 Seeed Technology Co., Ltd.
 * SPDX-License-Identifier: Apache-2.0
 *
 * Minimal USB CDC + blink + ADC bring-up sample for XIAO STM32C5.
 * USB output follows the zephyr-usb-cdc-echo-1m pattern and is not the
 * Zephyr console, so LED blink is independent of USB CDC state.
 */

#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#include <zephyr/device.h>
#include <zephyr/drivers/adc.h>
#include <zephyr/drivers/can.h>
#include <zephyr/drivers/flash.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/i2c.h>
#include <zephyr/drivers/pwm.h>
#include <zephyr/drivers/spi.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/byteorder.h>
#include <zephyr/sys/ring_buffer.h>
#include <zephyr/sys/util.h>

#define LED0_NODE DT_ALIAS(led0)
#define BAT_EN_NODE DT_ALIAS(baten)
#define PWM_A4_NODE DT_ALIAS(pwm_a4)
#define HEATER_NODE DT_ALIAS(imu_heater)
#define IMU_NODE DT_ALIAS(imu0)
#define EXT_FLASH_NODE DT_NODELABEL(ext_flash)
#define CAN_PHY_NODE DT_NODELABEL(can_phy0)
#define CANBUS_NODE DT_CHOSEN(zephyr_canbus)

#if !DT_NODE_EXISTS(DT_PATH(zephyr_user)) || \
	!DT_NODE_HAS_PROP(DT_PATH(zephyr_user), io_channels)
#error "No ADC io-channels specified"
#endif

#define DT_SPEC_AND_COMMA_FOR_INPUTS(node_id, prop, idx) \
	COND_CODE_1(DT_PHA_HAS_CELL_AT_IDX(node_id, prop, idx, input), \
		    (ADC_DT_SPEC_GET_BY_IDX(node_id, idx),), ())

#define ADC_AVG_SAMPLES 8
#define BATTERY_ADC_CHANNEL 4
#define BATTERY_ADC_RESOLUTION 12
#define BATTERY_ADC_VREF_MV 3300
#define BATTERY_AVG_SAMPLES 16
#define BATTERY_DIVIDER_NUM 2
#define BATTERY_DIVIDER_DEN 1
#define BATTERY_ENABLE_SETTLE_MS 5
#define LED_PERIOD_MS 500
#define PRINT_PERIOD_MS 5000
#define A4_PWM_DUTY_PERCENT 50U
#define IMU_TARGET_TEMPERATURE_MC 40000
#define IMU_CONTROL_INTERVAL_MS 500
#define IMU_DUTY_MIN_PERMILLE 0
#define IMU_DUTY_MAX_PERMILLE 600
#define IMU_DUTY_STEP_PERMILLE 50
#define IMU_FILTER_SHIFT 2
#define IMU_KP_PER_MILLE_PER_C 25
#define IMU_KI_PER_MILLE_PER_C_S 2
#define IMU_INTEGRAL_LIMIT_MC_S 180000
#define FLASH_TEST_OFFSET 0x00100000
#define FLASH_TEST_LEN 256
#define TX_RING_BUF_SIZE 4096
#define PRINT_BUF_SIZE 512
#define LSM6DSL_REG_WHO_AM_I 0x0f
#define LSM6DSL_REG_INT1_CTRL 0x0d
#define LSM6DSL_REG_CTRL1_XL 0x10
#define LSM6DSL_REG_CTRL2_G 0x11
#define LSM6DSL_REG_CTRL3_C 0x12
#define LSM6DSL_REG_OUT_TEMP_L 0x20
#define LSM6DSL_REG_OUTX_L_G 0x22
#define LSM6DSL_REG_OUTX_L_XL 0x28
#define LSM6DSL_WHO_AM_I_EXPECTED 0x6a
#define LSM6DSL_CTRL1_XL_ODR_MASK 0xf0
#define LSM6DSL_CTRL1_XL_ODR_12_5HZ 0x10
#define LSM6DSL_CTRL2_G_ODR_MASK 0xf0
#define LSM6DSL_CTRL2_G_ODR_12_5HZ 0x10
#define LSM6DSL_CTRL3_C_BDU BIT(6)
#define LSM6DSL_CTRL3_C_IF_INC BIT(2)
#define LSM6DSL_INT1_DRDY_XL BIT(0)
#ifndef CAN_TEST_NODE
#define CAN_TEST_NODE 1
#endif

#if CAN_TEST_NODE == 1
#define CAN_NODE_NAME "A"
#define CAN_PEER_NODE 2U
#define CAN_TX_ID 0x701U
#define CAN_RX_ID 0x702U
#elif CAN_TEST_NODE == 2
#define CAN_NODE_NAME "B"
#define CAN_PEER_NODE 1U
#define CAN_TX_ID 0x702U
#define CAN_RX_ID 0x701U
#else
#error "CAN_TEST_NODE must be 1 (node A) or 2 (node B)"
#endif

#define CAN_NOMINAL_BITRATE 1000000U
#define CAN_DATA_BITRATE 8000000U
#define CAN_TEST_MAGIC 0xc5080701U
#define CAN_TEST_PAYLOAD_LEN 16U
#define CAN_TEST_INTERVAL_MS 500U
#define CAN_TEST_SEND_TIMEOUT_MS 100U

static const struct device *const cdc_dev =
	DEVICE_DT_GET_ONE(zephyr_cdc_acm_uart);
static const struct device *const can_dev = DEVICE_DT_GET(CANBUS_NODE);
static const struct gpio_dt_spec led = GPIO_DT_SPEC_GET(LED0_NODE, gpios);
static const struct gpio_dt_spec bat_en = GPIO_DT_SPEC_GET(BAT_EN_NODE, gpios);
static const struct gpio_dt_spec can_standby =
	GPIO_DT_SPEC_GET(CAN_PHY_NODE, standby_gpios);
static const struct gpio_dt_spec imu_int = GPIO_DT_SPEC_GET(IMU_NODE,
							    irq_gpios);
static const struct pwm_dt_spec pwm_a4 = PWM_DT_SPEC_GET(PWM_A4_NODE);
static const struct pwm_dt_spec heater_pwm = PWM_DT_SPEC_GET(HEATER_NODE);
static const struct i2c_dt_spec imu_i2c = I2C_DT_SPEC_GET(IMU_NODE);
static const struct device *const battery_adc_dev =
	DEVICE_DT_GET(DT_NODELABEL(adc1));
static const struct adc_channel_cfg battery_adc_cfg = {
	.gain = ADC_GAIN_1,
	.reference = ADC_REF_INTERNAL,
	.acquisition_time = ADC_ACQ_TIME(ADC_ACQ_TIME_TICKS, 289),
	.channel_id = BATTERY_ADC_CHANNEL,
};
static const struct device *const ext_flash = DEVICE_DT_GET(EXT_FLASH_NODE);

static const struct adc_dt_spec adc_channels[] = {
	DT_FOREACH_PROP_ELEM(DT_PATH(zephyr_user), io_channels,
			     DT_SPEC_AND_COMMA_FOR_INPUTS)
};

static const char *const adc_labels[] = {
	"A0/D0",
	"A1/D1",
	"A2/D2",
	"A3/D3",
};

static uint8_t tx_ring_buffer[TX_RING_BUF_SIZE];
static char cdc_print_buffer[PRINT_BUF_SIZE];
static struct ring_buf tx_ringbuf;
static uint32_t tx_bytes;
static uint32_t rx_bytes;
static uint32_t drop_bytes;
static uint32_t led_toggle_count;
static bool led_ready;
static bool adc_ready;
static bool pwm_ready;
static bool heater_pwm_ready;
static bool battery_ready;
static bool flash_ready;
static bool can_phy_ready;
static bool can_controller_ready;
static bool i2c_feature_ready;
static bool spi_feature_ready;
static int can_standby_ret;
static int can_mode_ret;
static int can_bitrate_ret;
static int can_data_bitrate_ret;
static int can_start_ret;
static int can_state_ret;
static enum can_state can_last_state = CAN_STATE_STOPPED;
static struct can_bus_err_cnt can_last_err;
static int can_core_clock_ret;
static uint32_t can_core_clock_hz;
static int can_rx_filter_ret;
static atomic_t can_tx_ok;
static atomic_t can_tx_fail;
static atomic_t can_rx_total;
static atomic_t can_rx_valid;
static atomic_t can_rx_invalid;
static atomic_t can_rx_seq_gap;
static uint32_t can_tx_seq;
static uint32_t can_rx_last_seq;
static bool can_rx_have_seq;
static uint32_t heater_pwm_duty_permille;
static int heater_pwm_ret;
static int imu_init_ret;
static uint8_t imu_init_ctrl1_xl;
static struct flash_pages_info flash_page;
static uint8_t flash_write_buf[FLASH_TEST_LEN];
static uint8_t flash_read_buf[FLASH_TEST_LEN];
static uint8_t flash_jedec_id[3];
static int flash_jedec_ret;

struct flash_cycle_result {
	uint32_t cycle;
	int erase_ret;
	int write_ret;
	int read_ret;
	int verify_ret;
	size_t mismatch_offset;
	uint8_t expected;
	uint8_t actual;
};

struct imu_temp_result {
	bool bus_ready;
	int ret;
	uint8_t who_am_i;
	uint8_t ctrl1_xl;
	int16_t raw_temperature;
	int32_t temperature_mc;
};

struct imu_pid_state {
	int32_t integral_mc_s;
	int32_t filtered_temperature_mc;
	uint32_t previous_duty_permille;
	bool filter_ready;
};

struct imu_pid_report {
	struct imu_temp_result temperature;
	int32_t filtered_temperature_mc;
	int32_t error_mc;
	int32_t integral_mc_s;
	uint32_t duty_permille;
	uint32_t sample_count;
	int control_ret;
};

struct imu_axis_raw {
	int16_t x;
	int16_t y;
	int16_t z;
};

struct imu_data_status {
	bool ready;
	int init_ret;
	int last_read_ret;
	uint32_t irq_count;
	uint32_t work_count;
	uint32_t skipped_count;
	struct imu_axis_raw accel;
	struct imu_axis_raw gyro;
	uint8_t int1_ctrl;
	uint8_t ctrl1_xl;
	uint8_t ctrl2_g;
	uint8_t ctrl3_c;
};

static struct k_thread led_thread_data;
static struct k_thread can_test_thread_data;
static struct imu_pid_state imu_pid;
static struct imu_pid_report imu_pid_status;
static struct imu_data_status imu_data;
static struct gpio_callback imu_int_cb;
static struct k_work imu_data_work;
static atomic_t imu_irq_count;
static atomic_t imu_skipped_count;
static atomic_t imu_work_pending;
K_THREAD_STACK_DEFINE(led_stack, 512);
K_THREAD_STACK_DEFINE(can_test_stack, 1536);
K_MUTEX_DEFINE(imu_i2c_lock);

static void imu_data_work_handler(struct k_work *work);
static void imu_int_handler(const struct device *dev,
			    struct gpio_callback *cb, uint32_t pins);

static uint32_t cdc_tx_put(const uint8_t *buf, uint32_t len)
{
	uint32_t key;
	uint32_t stored;

	key = irq_lock();
	stored = ring_buf_put(&tx_ringbuf, buf, len);
	if (stored < len) {
		drop_bytes += len - stored;
	}
	irq_unlock(key);

	if (stored > 0U) {
		uart_irq_tx_enable(cdc_dev);
	}

	return stored;
}

static void cdc_printf(const char *fmt, ...)
{
	va_list args;
	int len;

	va_start(args, fmt);
	len = vsnprintf(cdc_print_buffer, sizeof(cdc_print_buffer), fmt, args);
	va_end(args);

	if (len < 0) {
		return;
	}

	if (len >= (int)sizeof(cdc_print_buffer)) {
		len = sizeof(cdc_print_buffer) - 1;
	}

	(void)cdc_tx_put((const uint8_t *)cdc_print_buffer, (uint32_t)len);
}

static void serial_cb(const struct device *dev, void *user_data)
{
	uint8_t buf[64];
	int len;

	ARG_UNUSED(user_data);

	while (uart_irq_update(dev) && uart_irq_is_pending(dev)) {
		if (uart_irq_rx_ready(dev)) {
			len = uart_fifo_read(dev, buf, sizeof(buf));
			if (len > 0) {
				rx_bytes += len;
			}
		}

		if (uart_irq_tx_ready(dev)) {
			len = ring_buf_get(&tx_ringbuf, buf, sizeof(buf));
			if (len == 0) {
				uart_irq_tx_disable(dev);
				continue;
			}

			len = uart_fifo_fill(dev, buf, len);
			if (len > 0) {
				tx_bytes += len;
			}
		}
	}
}

static bool cdc_get_line_state(uint32_t *dtr, uint32_t *baudrate)
{
	if (!device_is_ready(cdc_dev)) {
		return false;
	}

	(void)uart_line_ctrl_get(cdc_dev, UART_LINE_CTRL_DTR, dtr);
	(void)uart_line_ctrl_get(cdc_dev, UART_LINE_CTRL_BAUD_RATE, baudrate);

	return true;
}

static int read_adc_average(const struct adc_dt_spec *adc, uint16_t *raw_avg,
			    int32_t *mv)
{
	uint16_t raw;
	uint32_t raw_sum = 0;
	struct adc_sequence sequence = {
		.buffer = &raw,
		.buffer_size = sizeof(raw),
	};
	int ret;

	ret = adc_sequence_init_dt(adc, &sequence);
	if (ret < 0) {
		return ret;
	}

	ret = adc_read(adc->dev, &sequence);
	if (ret < 0) {
		return ret;
	}

	for (int i = 0; i < ADC_AVG_SAMPLES; i++) {
		ret = adc_read(adc->dev, &sequence);
		if (ret < 0) {
			return ret;
		}

		raw_sum += raw;
	}

	*raw_avg = raw_sum / ADC_AVG_SAMPLES;
	*mv = *raw_avg;
	return adc_raw_to_millivolts_dt(adc, mv);
}

static int read_battery_average(uint16_t *raw_avg, int32_t *adc_mv,
				int32_t *battery_mv)
{
	uint16_t raw;
	uint32_t raw_sum = 0;
	struct adc_sequence sequence = {
		.channels = BIT(BATTERY_ADC_CHANNEL),
		.buffer = &raw,
		.buffer_size = sizeof(raw),
		.resolution = BATTERY_ADC_RESOLUTION,
	};
	int ret;

	ret = gpio_pin_set_dt(&bat_en, 1);
	if (ret < 0) {
		return ret;
	}

	k_msleep(BATTERY_ENABLE_SETTLE_MS);

	ret = adc_read(battery_adc_dev, &sequence);
	if (ret < 0) {
		(void)gpio_pin_set_dt(&bat_en, 0);
		return ret;
	}

	for (int i = 0; i < BATTERY_AVG_SAMPLES; i++) {
		ret = adc_read(battery_adc_dev, &sequence);
		if (ret < 0) {
			(void)gpio_pin_set_dt(&bat_en, 0);
			return ret;
		}

		raw_sum += raw;
	}

	(void)gpio_pin_set_dt(&bat_en, 0);

	*raw_avg = raw_sum / BATTERY_AVG_SAMPLES;
	*adc_mv = *raw_avg;
	ret = adc_raw_to_millivolts(BATTERY_ADC_VREF_MV, ADC_GAIN_1,
				    BATTERY_ADC_RESOLUTION, adc_mv);
	if (ret < 0) {
		return ret;
	}

	*battery_mv = (*adc_mv * BATTERY_DIVIDER_NUM) / BATTERY_DIVIDER_DEN;
	return 0;
}

static int init_imu_temperature(void)
{
	uint8_t who_am_i;
	uint8_t ctrl1_xl;
	uint8_t ctrl2_g;
	uint8_t ctrl3_c;
	int ret;

	imu_init_ret = -ENODEV;
	imu_init_ctrl1_xl = 0;

	if (!i2c_is_ready_dt(&imu_i2c)) {
		return imu_init_ret;
	}

	k_mutex_lock(&imu_i2c_lock, K_FOREVER);

	ret = i2c_reg_read_byte_dt(&imu_i2c, LSM6DSL_REG_WHO_AM_I, &who_am_i);
	if (ret < 0) {
		imu_init_ret = ret;
		goto out;
	}

	if (who_am_i != LSM6DSL_WHO_AM_I_EXPECTED) {
		imu_init_ret = -EIO;
		ret = imu_init_ret;
		goto out;
	}

	ret = i2c_reg_read_byte_dt(&imu_i2c, LSM6DSL_REG_CTRL1_XL, &ctrl1_xl);
	if (ret < 0) {
		imu_init_ret = ret;
		goto out;
	}

	if ((ctrl1_xl & LSM6DSL_CTRL1_XL_ODR_MASK) == 0U) {
		ctrl1_xl = (ctrl1_xl & ~LSM6DSL_CTRL1_XL_ODR_MASK) |
			   LSM6DSL_CTRL1_XL_ODR_12_5HZ;
		ret = i2c_reg_write_byte_dt(&imu_i2c, LSM6DSL_REG_CTRL1_XL,
					    ctrl1_xl);
		if (ret < 0) {
			imu_init_ret = ret;
			goto out;
		}
	}

	ret = i2c_reg_read_byte_dt(&imu_i2c, LSM6DSL_REG_CTRL2_G, &ctrl2_g);
	if (ret < 0) {
		imu_init_ret = ret;
		goto out;
	}

	if ((ctrl2_g & LSM6DSL_CTRL2_G_ODR_MASK) == 0U) {
		ctrl2_g = (ctrl2_g & ~LSM6DSL_CTRL2_G_ODR_MASK) |
			  LSM6DSL_CTRL2_G_ODR_12_5HZ;
		ret = i2c_reg_write_byte_dt(&imu_i2c, LSM6DSL_REG_CTRL2_G,
					    ctrl2_g);
		if (ret < 0) {
			imu_init_ret = ret;
			goto out;
		}
	}

	ret = i2c_reg_read_byte_dt(&imu_i2c, LSM6DSL_REG_CTRL3_C, &ctrl3_c);
	if (ret < 0) {
		imu_init_ret = ret;
		goto out;
	}

	ctrl3_c |= LSM6DSL_CTRL3_C_BDU | LSM6DSL_CTRL3_C_IF_INC;
	ret = i2c_reg_write_byte_dt(&imu_i2c, LSM6DSL_REG_CTRL3_C, ctrl3_c);
	if (ret < 0) {
		imu_init_ret = ret;
		goto out;
	}

	ret = i2c_reg_read_byte_dt(&imu_i2c, LSM6DSL_REG_CTRL1_XL,
				   &imu_init_ctrl1_xl);
	if (ret < 0) {
		imu_init_ret = ret;
		goto out;
	}

	imu_init_ret = 0;
	ret = 0;

out:
	k_mutex_unlock(&imu_i2c_lock);
	return ret;
}

static void read_imu_temperature(struct imu_temp_result *result)
{
	uint8_t temp_l;
	uint8_t temp_h;
	int ret;

	memset(result, 0, sizeof(*result));
	result->ret = -ENODEV;

	result->bus_ready = i2c_is_ready_dt(&imu_i2c);
	if (!result->bus_ready) {
		return;
	}

	k_mutex_lock(&imu_i2c_lock, K_FOREVER);

	ret = i2c_reg_read_byte_dt(&imu_i2c, LSM6DSL_REG_WHO_AM_I,
				   &result->who_am_i);
	if (ret < 0) {
		result->ret = ret;
		goto out;
	}

	ret = i2c_reg_read_byte_dt(&imu_i2c, LSM6DSL_REG_CTRL1_XL,
				   &result->ctrl1_xl);
	if (ret < 0) {
		result->ret = ret;
		goto out;
	}

	ret = i2c_reg_read_byte_dt(&imu_i2c, LSM6DSL_REG_OUT_TEMP_L, &temp_l);
	if (ret < 0) {
		result->ret = ret;
		goto out;
	}

	ret = i2c_reg_read_byte_dt(&imu_i2c, LSM6DSL_REG_OUT_TEMP_L + 1,
				   &temp_h);
	if (ret < 0) {
		result->ret = ret;
		goto out;
	}

	result->raw_temperature =
		(int16_t)((uint16_t)temp_l | ((uint16_t)temp_h << 8));
	result->temperature_mc =
		25000 + (((int32_t)result->raw_temperature * 1000) / 256);
	result->ret = 0;

out:
	k_mutex_unlock(&imu_i2c_lock);
}

static struct imu_axis_raw imu_unpack_axis(const uint8_t *buf)
{
	return (struct imu_axis_raw) {
		.x = (int16_t)((uint16_t)buf[0] | ((uint16_t)buf[1] << 8)),
		.y = (int16_t)((uint16_t)buf[2] | ((uint16_t)buf[3] << 8)),
		.z = (int16_t)((uint16_t)buf[4] | ((uint16_t)buf[5] << 8)),
	};
}

static int read_imu_axes(struct imu_axis_raw *accel, struct imu_axis_raw *gyro)
{
	uint8_t buf[6];
	int ret;

	k_mutex_lock(&imu_i2c_lock, K_FOREVER);

	ret = i2c_burst_read_dt(&imu_i2c, LSM6DSL_REG_OUTX_L_G, buf,
				sizeof(buf));
	if (ret < 0) {
		goto out;
	}
	*gyro = imu_unpack_axis(buf);

	ret = i2c_burst_read_dt(&imu_i2c, LSM6DSL_REG_OUTX_L_XL, buf,
				sizeof(buf));
	if (ret < 0) {
		goto out;
	}
	*accel = imu_unpack_axis(buf);

out:
	k_mutex_unlock(&imu_i2c_lock);
	return ret;
}

static void imu_data_work_handler(struct k_work *work)
{
	struct imu_axis_raw accel;
	struct imu_axis_raw gyro;
	int ret;

	ARG_UNUSED(work);

	ret = read_imu_axes(&accel, &gyro);
	imu_data.last_read_ret = ret;
	imu_data.irq_count = (uint32_t)atomic_get(&imu_irq_count);
	imu_data.skipped_count = (uint32_t)atomic_get(&imu_skipped_count);

	if (ret == 0) {
		imu_data.accel = accel;
		imu_data.gyro = gyro;
		imu_data.work_count++;
	}

	atomic_set(&imu_work_pending, 0);
}

static void imu_int_handler(const struct device *dev,
			    struct gpio_callback *cb, uint32_t pins)
{
	ARG_UNUSED(dev);
	ARG_UNUSED(cb);
	ARG_UNUSED(pins);

	atomic_inc(&imu_irq_count);
	if (atomic_cas(&imu_work_pending, 0, 1)) {
		(void)k_work_submit(&imu_data_work);
	} else {
		atomic_inc(&imu_skipped_count);
	}
}

static int init_imu_data_interrupt(void)
{
	int ret;

	memset(&imu_data, 0, sizeof(imu_data));
	imu_data.init_ret = -ENODEV;
	atomic_set(&imu_irq_count, 0);
	atomic_set(&imu_skipped_count, 0);
	atomic_set(&imu_work_pending, 0);

	if (!gpio_is_ready_dt(&imu_int) || !i2c_is_ready_dt(&imu_i2c)) {
		return imu_data.init_ret;
	}

	ret = gpio_pin_configure_dt(&imu_int, GPIO_INPUT);
	if (ret < 0) {
		imu_data.init_ret = ret;
		return ret;
	}

	k_mutex_lock(&imu_i2c_lock, K_FOREVER);

	ret = i2c_reg_write_byte_dt(&imu_i2c, LSM6DSL_REG_INT1_CTRL,
				    LSM6DSL_INT1_DRDY_XL);
	if (ret < 0) {
		imu_data.init_ret = ret;
		goto unlock;
	}

	(void)i2c_reg_read_byte_dt(&imu_i2c, LSM6DSL_REG_INT1_CTRL,
				   &imu_data.int1_ctrl);
	(void)i2c_reg_read_byte_dt(&imu_i2c, LSM6DSL_REG_CTRL1_XL,
				   &imu_data.ctrl1_xl);
	(void)i2c_reg_read_byte_dt(&imu_i2c, LSM6DSL_REG_CTRL2_G,
				   &imu_data.ctrl2_g);
	(void)i2c_reg_read_byte_dt(&imu_i2c, LSM6DSL_REG_CTRL3_C,
				   &imu_data.ctrl3_c);

unlock:
	k_mutex_unlock(&imu_i2c_lock);
	if (ret < 0) {
		return ret;
	}

	ret = read_imu_axes(&imu_data.accel, &imu_data.gyro);
	imu_data.last_read_ret = ret;
	if (ret < 0) {
		imu_data.init_ret = ret;
		return ret;
	}

	k_work_init(&imu_data_work, imu_data_work_handler);
	gpio_init_callback(&imu_int_cb, imu_int_handler, BIT(imu_int.pin));

	ret = gpio_add_callback(imu_int.port, &imu_int_cb);
	if (ret < 0) {
		imu_data.init_ret = ret;
		return ret;
	}

	ret = gpio_pin_interrupt_configure_dt(&imu_int, GPIO_INT_EDGE_TO_ACTIVE);
	if (ret < 0) {
		imu_data.init_ret = ret;
		return ret;
	}

	imu_data.ready = true;
	imu_data.init_ret = 0;
	return 0;
}

static bool init_led(void)
{
	int ret;

	if (!gpio_is_ready_dt(&led)) {
		return false;
	}

	ret = gpio_pin_configure_dt(&led, GPIO_OUTPUT_INACTIVE);
	return ret == 0;
}

static bool init_can_transceiver(void)
{
	if (!gpio_is_ready_dt(&can_standby)) {
		can_standby_ret = -ENODEV;
		return false;
	}

	can_standby_ret = gpio_pin_configure_dt(&can_standby,
						GPIO_OUTPUT_INACTIVE);
	return can_standby_ret == 0;
}

static const char *can_state_name(enum can_state state)
{
	switch (state) {
	case CAN_STATE_ERROR_ACTIVE:
		return "error-active";
	case CAN_STATE_ERROR_WARNING:
		return "error-warning";
	case CAN_STATE_ERROR_PASSIVE:
		return "error-passive";
	case CAN_STATE_BUS_OFF:
		return "bus-off";
	case CAN_STATE_STOPPED:
		return "stopped";
	default:
		return "unknown";
	}
}

static void update_can_state(void)
{
	can_state_ret = can_get_state(can_dev, &can_last_state, &can_last_err);
}

static void can_rx_callback(const struct device *dev, struct can_frame *frame,
			    void *user_data)
{
	uint8_t payload_len = can_dlc_to_bytes(frame->dlc);
	uint32_t seq;

	ARG_UNUSED(dev);
	ARG_UNUSED(user_data);

	atomic_inc(&can_rx_total);
	if (frame->id != CAN_RX_ID ||
	    (frame->flags & (CAN_FRAME_FDF | CAN_FRAME_BRS)) !=
		(CAN_FRAME_FDF | CAN_FRAME_BRS) ||
	    payload_len != CAN_TEST_PAYLOAD_LEN ||
	    sys_get_le32(&frame->data[0]) != CAN_TEST_MAGIC ||
	    frame->data[4] != CAN_PEER_NODE || frame->data[5] != 1U) {
		atomic_inc(&can_rx_invalid);
		return;
	}

	seq = sys_get_le32(&frame->data[8]);
	if (can_rx_have_seq && seq != can_rx_last_seq + 1U) {
		atomic_add(&can_rx_seq_gap,
			   seq > can_rx_last_seq ? seq - can_rx_last_seq - 1U : 1U);
	}
	can_rx_last_seq = seq;
	can_rx_have_seq = true;

	if (frame->data[12] != (uint8_t)(0xa5U ^ seq) ||
	    frame->data[13] != (uint8_t)(0x5aU ^ (seq >> 8)) ||
	    frame->data[14] != (uint8_t)(0x3cU ^ (seq >> 16)) ||
	    frame->data[15] != (uint8_t)(0xc3U ^ (seq >> 24))) {
		atomic_inc(&can_rx_invalid);
		return;
	}

	atomic_inc(&can_rx_valid);
}

static void can_prepare_test_frame(struct can_frame *frame, uint32_t seq)
{
	frame->id = CAN_TX_ID;
	frame->flags = CAN_FRAME_FDF | CAN_FRAME_BRS;
	frame->dlc = can_bytes_to_dlc(CAN_TEST_PAYLOAD_LEN);
	sys_put_le32(CAN_TEST_MAGIC, &frame->data[0]);
	frame->data[4] = CAN_TEST_NODE;
	frame->data[5] = 1U;
	frame->data[6] = 0U;
	frame->data[7] = 0U;
	sys_put_le32(seq, &frame->data[8]);
	frame->data[12] = (uint8_t)(0xa5U ^ seq);
	frame->data[13] = (uint8_t)(0x5aU ^ (seq >> 8));
	frame->data[14] = (uint8_t)(0x3cU ^ (seq >> 16));
	frame->data[15] = (uint8_t)(0xc3U ^ (seq >> 24));
}

static bool init_can_controller(void)
{
	const struct can_filter peer_filter = {
		.flags = 0,
		.id = CAN_RX_ID,
		.mask = 0x7ffU,
	};

	memset(&can_last_err, 0, sizeof(can_last_err));
	can_mode_ret = -ENODEV;
	can_bitrate_ret = -ENODEV;
	can_data_bitrate_ret = -ENODEV;
	can_start_ret = -ENODEV;
	can_state_ret = -ENODEV;
	can_core_clock_ret = -ENODEV;
	can_core_clock_hz = 0U;
	can_rx_filter_ret = -ENODEV;
	atomic_set(&can_tx_ok, 0);
	atomic_set(&can_tx_fail, 0);
	atomic_set(&can_rx_total, 0);
	atomic_set(&can_rx_valid, 0);
	atomic_set(&can_rx_invalid, 0);
	atomic_set(&can_rx_seq_gap, 0);
	can_tx_seq = 0U;
	can_rx_last_seq = 0U;
	can_rx_have_seq = false;

	if (!device_is_ready(can_dev)) {
		return false;
	}

	can_core_clock_ret = can_get_core_clock(can_dev, &can_core_clock_hz);
	can_rx_filter_ret = can_add_rx_filter(can_dev, can_rx_callback, NULL,
					      &peer_filter);
	if (can_rx_filter_ret < 0) {
		return false;
	}

	can_mode_ret = can_set_mode(can_dev, CAN_MODE_FD);
	if (can_mode_ret != 0) {
		update_can_state();
		return false;
	}

	can_bitrate_ret = can_set_bitrate(can_dev, CAN_NOMINAL_BITRATE);
	if (can_bitrate_ret != 0) {
		update_can_state();
		return false;
	}

	can_data_bitrate_ret = can_set_bitrate_data(can_dev, CAN_DATA_BITRATE);
	if (can_data_bitrate_ret != 0) {
		update_can_state();
		return false;
	}

	can_start_ret = can_start(can_dev);
	if (can_start_ret == -EALREADY) {
		can_start_ret = 0;
	}

	update_can_state();
	return can_start_ret == 0;
}

static bool init_a4_pwm(void)
{
	uint32_t pulse_ns = (pwm_a4.period * A4_PWM_DUTY_PERCENT) / 100U;
	int ret;

	if (!pwm_is_ready_dt(&pwm_a4)) {
		return false;
	}

	ret = pwm_set_dt(&pwm_a4, pwm_a4.period, pulse_ns);
	return ret == 0;
}

static int set_heater_pwm_duty(uint32_t duty_permille)
{
	uint32_t pulse_ns = (heater_pwm.period * duty_permille) / 1000U;
	int ret;

	if (!heater_pwm_ready) {
		heater_pwm_ret = -ENODEV;
		return -ENODEV;
	}

	ret = pwm_set_dt(&heater_pwm, heater_pwm.period, pulse_ns);
	heater_pwm_duty_permille = duty_permille;
	heater_pwm_ret = ret;
	return ret;
}

static bool init_heater_pwm(void)
{
	if (!pwm_is_ready_dt(&heater_pwm)) {
		heater_pwm_ret = -ENODEV;
		return false;
	}

	heater_pwm_ready = true;
	return set_heater_pwm_duty(IMU_DUTY_MIN_PERMILLE) == 0;
}

static uint32_t apply_imu_duty_slew_limit(struct imu_pid_state *pid,
					  uint32_t duty_permille)
{
	uint32_t previous = pid->previous_duty_permille;

	if (duty_permille > previous + IMU_DUTY_STEP_PERMILLE) {
		duty_permille = previous + IMU_DUTY_STEP_PERMILLE;
	} else if (previous > duty_permille + IMU_DUTY_STEP_PERMILLE) {
		duty_permille = previous - IMU_DUTY_STEP_PERMILLE;
	}

	pid->previous_duty_permille = duty_permille;
	return duty_permille;
}

static uint32_t update_imu_pi(struct imu_pid_state *pid, int32_t temperature_mc,
			      int32_t *filtered_temperature_mc,
			      int32_t *error_mc)
{
	int32_t p_term;
	int32_t i_term;
	int32_t output_permille;

	if (!pid->filter_ready) {
		pid->filtered_temperature_mc = temperature_mc;
		pid->filter_ready = true;
	} else {
		pid->filtered_temperature_mc +=
			(temperature_mc - pid->filtered_temperature_mc) >>
			IMU_FILTER_SHIFT;
	}

	*filtered_temperature_mc = pid->filtered_temperature_mc;
	*error_mc = IMU_TARGET_TEMPERATURE_MC - pid->filtered_temperature_mc;

	pid->integral_mc_s += (*error_mc * IMU_CONTROL_INTERVAL_MS) / 1000;
	pid->integral_mc_s = CLAMP(pid->integral_mc_s,
				   -IMU_INTEGRAL_LIMIT_MC_S,
				   IMU_INTEGRAL_LIMIT_MC_S);

	p_term = (IMU_KP_PER_MILLE_PER_C * *error_mc) / 1000;
	i_term = (IMU_KI_PER_MILLE_PER_C_S * pid->integral_mc_s) / 1000;
	output_permille = CLAMP(p_term + i_term, IMU_DUTY_MIN_PERMILLE,
				IMU_DUTY_MAX_PERMILLE);

	return apply_imu_duty_slew_limit(pid, (uint32_t)output_permille);
}

static void run_imu_pid_step(void)
{
	struct imu_temp_result temperature;
	uint32_t duty_permille;

	read_imu_temperature(&temperature);
	imu_pid_status.temperature = temperature;

	if (temperature.ret < 0 ||
	    temperature.who_am_i != LSM6DSL_WHO_AM_I_EXPECTED) {
		imu_pid.previous_duty_permille = 0;
		imu_pid_status.control_ret = temperature.ret < 0 ?
					     temperature.ret : -EIO;
		imu_pid_status.duty_permille = 0;
		(void)set_heater_pwm_duty(0);
		return;
	}

	duty_permille = update_imu_pi(&imu_pid, temperature.temperature_mc,
				      &imu_pid_status.filtered_temperature_mc,
				      &imu_pid_status.error_mc);

	imu_pid_status.control_ret = set_heater_pwm_duty(duty_permille);
	if (imu_pid_status.control_ret < 0) {
		duty_permille = 0;
	}

	imu_pid_status.integral_mc_s = imu_pid.integral_mc_s;
	imu_pid_status.duty_permille = duty_permille;
	imu_pid_status.sample_count++;
}

static bool init_adc(void)
{
	BUILD_ASSERT(ARRAY_SIZE(adc_channels) == ARRAY_SIZE(adc_labels),
		     "ADC channel count must match A0-A3 labels");

	for (size_t i = 0; i < ARRAY_SIZE(adc_channels); i++) {
		int ret;

		if (!device_is_ready(adc_channels[i].dev)) {
			return false;
		}

		ret = adc_channel_setup_dt(&adc_channels[i]);
		if (ret < 0) {
			return false;
		}
	}

	return true;
}

static bool init_battery(void)
{
	int ret;

	if (!device_is_ready(battery_adc_dev)) {
		return false;
	}

	if (!gpio_is_ready_dt(&bat_en)) {
		return false;
	}

	ret = gpio_pin_configure_dt(&bat_en, GPIO_OUTPUT_INACTIVE);
	if (ret < 0) {
		return false;
	}

	ret = adc_channel_setup(battery_adc_dev, &battery_adc_cfg);
	return ret == 0;
}

static bool init_flash(void)
{
	int ret;

	if (!device_is_ready(ext_flash)) {
		return false;
	}

	flash_jedec_ret = flash_read_jedec_id(ext_flash, flash_jedec_id);

	ret = flash_get_page_info_by_offs(ext_flash, FLASH_TEST_OFFSET,
					  &flash_page);
	return ret == 0;
}

static void run_flash_cycle(uint32_t cycle, struct flash_cycle_result *result)
{
	memset(result, 0, sizeof(*result));
	result->cycle = cycle;

	for (size_t i = 0; i < sizeof(flash_write_buf); i++) {
		flash_write_buf[i] = (uint8_t)(0xa5 ^ i ^ cycle);
		flash_read_buf[i] = 0;
	}

	result->erase_ret = flash_erase(ext_flash, flash_page.start_offset,
					flash_page.size);
	if (result->erase_ret != 0) {
		return;
	}

	result->write_ret = flash_write(ext_flash, FLASH_TEST_OFFSET,
					flash_write_buf,
					sizeof(flash_write_buf));
	if (result->write_ret != 0) {
		return;
	}

	result->read_ret = flash_read(ext_flash, FLASH_TEST_OFFSET,
				      flash_read_buf, sizeof(flash_read_buf));
	if (result->read_ret != 0) {
		return;
	}

	result->verify_ret = memcmp(flash_write_buf, flash_read_buf,
				    sizeof(flash_write_buf));
	if (result->verify_ret == 0) {
		return;
	}

	for (size_t i = 0; i < sizeof(flash_write_buf); i++) {
		if (flash_write_buf[i] != flash_read_buf[i]) {
			result->mismatch_offset = i;
			result->expected = flash_write_buf[i];
			result->actual = flash_read_buf[i];
			return;
		}
	}
}

static bool init_cdc(void)
{
	if (!device_is_ready(cdc_dev)) {
		return false;
	}

	ring_buf_init(&tx_ringbuf, sizeof(tx_ring_buffer), tx_ring_buffer);
	(void)uart_line_ctrl_set(cdc_dev, UART_LINE_CTRL_DCD, 1);
	(void)uart_line_ctrl_set(cdc_dev, UART_LINE_CTRL_DSR, 1);

	uart_irq_callback_user_data_set(cdc_dev, serial_cb, NULL);
	uart_irq_rx_enable(cdc_dev);

	return true;
}

static void led_thread(void *p1, void *p2, void *p3)
{
	ARG_UNUSED(p1);
	ARG_UNUSED(p2);
	ARG_UNUSED(p3);

	while (true) {
		if (led_ready) {
			(void)gpio_pin_toggle_dt(&led);
			led_toggle_count++;
		}

		k_msleep(LED_PERIOD_MS);
	}
}

static void can_test_thread(void *p1, void *p2, void *p3)
{
	ARG_UNUSED(p1);
	ARG_UNUSED(p2);
	ARG_UNUSED(p3);

	while (true) {
		struct can_frame frame = { 0 };
		int ret;

		can_prepare_test_frame(&frame, can_tx_seq++);
		ret = can_send(can_dev, &frame,
			       K_MSEC(CAN_TEST_SEND_TIMEOUT_MS), NULL, NULL);
		if (ret == 0) {
			atomic_inc(&can_tx_ok);
		} else {
			atomic_inc(&can_tx_fail);
		}

		k_msleep(CAN_TEST_INTERVAL_MS);
	}
}

/* Return a percentage in basis points, i.e. 1234 means 12.34%. */
static uint32_t can_loss_rate_bp(uint32_t lost, uint32_t total)
{
	if (total == 0U) {
		return 0U;
	}

	return (uint32_t)(((uint64_t)lost * 10000U) / total);
}

static void print_status(uint32_t loop_count, uint32_t dtr, uint32_t baudrate,
			 const struct flash_cycle_result *flash_result)
{
	cdc_printf("\r\n");
	cdc_printf("========== XIAO STM32C5 BRING-UP | tick %u ==========\r\n",
		   loop_count);

	cdc_printf("[USB]\r\n");
	cdc_printf("  CDC ACM     : ready, dtr=%u, baud=%u\r\n", dtr, baudrate);
	cdc_printf("  Counters    : tx=%u bytes, rx=%u bytes, drop=%u bytes\r\n",
		   tx_bytes, rx_bytes, drop_bytes);

	if (device_is_ready(can_dev)) {
		update_can_state();
	}

	cdc_printf("[BUS ENABLE]\r\n");
	cdc_printf("  Config      : I2C=%s, SPI=%s, CAN=%s, CAN_FD=%s\r\n",
		   IS_ENABLED(CONFIG_I2C) ? "y" : "n",
		   IS_ENABLED(CONFIG_SPI) ? "y" : "n",
		   IS_ENABLED(CONFIG_CAN) ? "y" : "n",
		   IS_ENABLED(CONFIG_CAN_FD_MODE) ? "y" : "n");
	cdc_printf("  I2C         : I2C2/IMU bus %s\r\n",
		   i2c_feature_ready ? "ready" : "not-ready");
	cdc_printf("  SPI         : XSPI1/flash device %s, external flash %s\r\n",
		   spi_feature_ready ? "ready" : "not-ready",
		   flash_ready ? "ready" : "not-ready");
	if (device_is_ready(can_dev)) {
		cdc_printf("  CAN         : FDCAN2 ready, controller=%s, mode=FD, nominal=%u, data=%u\r\n",
			   can_controller_ready ? "started" : "not-started",
			   CAN_NOMINAL_BITRATE, CAN_DATA_BITRATE);
		cdc_printf("  CAN status  : mode=%d, bitrate=%d, data_bitrate=%d, start=%d, state=%s(%d), rxerr=%u, txerr=%u\r\n",
			   can_mode_ret, can_bitrate_ret, can_data_bitrate_ret,
			   can_start_ret, can_state_name(can_last_state),
			   can_state_ret, can_last_err.rx_err_cnt,
			   can_last_err.tx_err_cnt);
		cdc_printf("  CAN clock   : get=%d, frequency=%u Hz\r\n",
			   can_core_clock_ret, can_core_clock_hz);
		{
			uint32_t tx_ok = (uint32_t)atomic_get(&can_tx_ok);
			uint32_t tx_fail = (uint32_t)atomic_get(&can_tx_fail);
			uint32_t tx_total = tx_ok + tx_fail;
			uint32_t tx_loss_rate = can_loss_rate_bp(tx_fail, tx_total);
			uint32_t rx_total = (uint32_t)atomic_get(&can_rx_total);
			uint32_t rx_valid = (uint32_t)atomic_get(&can_rx_valid);
			uint32_t rx_invalid = (uint32_t)atomic_get(&can_rx_invalid);
			uint32_t rx_lost = (uint32_t)atomic_get(&can_rx_seq_gap);
			uint32_t rx_expected = rx_valid + rx_lost;
			uint32_t rx_loss_rate = can_loss_rate_bp(rx_lost, rx_expected);

			cdc_printf("  CAN test    : node=%s tx=0x%03x rx=0x%03x, 1M/8M FD+BRS, filter=%d\r\n",
				   CAN_NODE_NAME, CAN_TX_ID, CAN_RX_ID,
				   can_rx_filter_ret);
			cdc_printf("  TX packets  : total=%u, success=%u, failed=%u, lost=%u, loss_rate=%u.%02u%%\r\n",
				   tx_total, tx_ok, tx_fail, tx_fail,
				   tx_loss_rate / 100U, tx_loss_rate % 100U);
			cdc_printf("  RX packets  : total=%u, valid=%u, invalid=%u, lost=%u, loss_rate=%u.%02u%%\r\n",
				   rx_total, rx_valid, rx_invalid, rx_lost,
				   rx_loss_rate / 100U, rx_loss_rate % 100U);
		}
	} else {
		cdc_printf("  CAN         : FDCAN2 not-ready, start=%d\r\n",
			   can_start_ret);
	}

	cdc_printf("[LED]\r\n");
	cdc_printf("  User LED    : %s, blink=%u ms, toggles=%u\r\n",
		   led_ready ? "ready" : "not-ready", LED_PERIOD_MS,
		   led_toggle_count);

	cdc_printf("[ADC A0-A3]\r\n");

	if (adc_ready) {
		for (size_t i = 0; i < ARRAY_SIZE(adc_channels); i++) {
			uint16_t raw;
			int32_t mv;
			int ret = read_adc_average(&adc_channels[i], &raw, &mv);

			if (ret < 0) {
				cdc_printf("  %-8s : read failed (%d)\r\n",
					   adc_labels[i], ret);
			} else {
				cdc_printf("  %-8s : raw=%4u, voltage=%4d mV\r\n",
					   adc_labels[i], raw, mv);
			}
		}
	} else {
		cdc_printf("  Status      : not-ready\r\n");
	}

	cdc_printf("[PWM]\r\n");
	if (pwm_ready) {
		cdc_printf("  A4/D4/PB7   : TIM4_CH2, period=%u ns, duty=%u%%\r\n",
			   pwm_a4.period, A4_PWM_DUTY_PERCENT);
	} else {
		cdc_printf("  A4/D4/PB7   : not-ready\r\n");
	}

	cdc_printf("[HEATER PWM]\r\n");
	if (heater_pwm_ready) {
		cdc_printf("  PA8/TIM1_CH1: period=%u ns, duty=%u.%u%%, set_ret=%d\r\n",
			   heater_pwm.period, heater_pwm_duty_permille / 10,
			   heater_pwm_duty_permille % 10,
			   heater_pwm_ret);
		cdc_printf("  Control     : PI temperature compensation, interval=%u ms\r\n",
			   IMU_CONTROL_INTERVAL_MS);
	} else {
		cdc_printf("  PA8/TIM1_CH1: not-ready, set_ret=%d\r\n",
			   heater_pwm_ret);
	}

	cdc_printf("[CAN PHY]\r\n");
	if (can_phy_ready) {
		cdc_printf("  CAN_STB/PB14: LOW, transceiver=enabled, set_ret=%d\r\n",
			   can_standby_ret);
	} else {
		cdc_printf("  CAN_STB/PB14: not-ready, set_ret=%d\r\n",
			   can_standby_ret);
	}

	cdc_printf("[IMU TEMP]\r\n");
	{
		struct imu_temp_result *imu_temp = &imu_pid_status.temperature;

		if (imu_temp->ret < 0) {
			cdc_printf("  I2C         : %s, read failed (%d)\r\n",
				   imu_temp->bus_ready ? "ready" : "not-ready",
				   imu_temp->ret);
		} else {
			int32_t temp_abs = imu_temp->temperature_mc < 0 ?
					   -imu_temp->temperature_mc :
					   imu_temp->temperature_mc;
			int32_t filtered_abs =
				imu_pid_status.filtered_temperature_mc < 0 ?
				-imu_pid_status.filtered_temperature_mc :
				imu_pid_status.filtered_temperature_mc;
			int32_t error_abs = imu_pid_status.error_mc < 0 ?
					    -imu_pid_status.error_mc :
					    imu_pid_status.error_mc;

			cdc_printf("  I2C         : ready, polled register read\r\n");
			cdc_printf("  Init        : ret=%d, CTRL1_XL=0x%02x\r\n",
				   imu_init_ret, imu_init_ctrl1_xl);
			cdc_printf("  Registers   : WHO_AM_I=0x%02x (expect 0x%02x), CTRL1_XL=0x%02x\r\n",
				   imu_temp->who_am_i,
				   LSM6DSL_WHO_AM_I_EXPECTED,
				   imu_temp->ctrl1_xl);
			cdc_printf("  Temperature : raw=%d LSB, %s%d.%03d C\r\n",
				   imu_temp->raw_temperature,
				   imu_temp->temperature_mc < 0 ? "-" : "",
				   temp_abs / 1000, temp_abs % 1000);
			cdc_printf("  Filtered    : %s%d.%03d C, target=%d.%03d C\r\n",
				   imu_pid_status.filtered_temperature_mc < 0 ?
				   "-" : "", filtered_abs / 1000,
				   filtered_abs % 1000,
				   IMU_TARGET_TEMPERATURE_MC / 1000,
				   IMU_TARGET_TEMPERATURE_MC % 1000);
			cdc_printf("  Error       : %s%d.%03d C, samples=%u\r\n",
				   imu_pid_status.error_mc < 0 ? "-" : "",
				   error_abs / 1000, error_abs % 1000,
				   imu_pid_status.sample_count);
			cdc_printf("  PI          : kp=%u, ki=%u, integral=%d mC*s, control_ret=%d\r\n",
				   IMU_KP_PER_MILLE_PER_C,
				   IMU_KI_PER_MILLE_PER_C_S,
				   imu_pid_status.integral_mc_s,
				   imu_pid_status.control_ret);
		}
	}

	cdc_printf("[IMU DATA IRQ]\r\n");
	if (imu_data.ready) {
		imu_data.irq_count = (uint32_t)atomic_get(&imu_irq_count);
		imu_data.skipped_count = (uint32_t)atomic_get(&imu_skipped_count);
		cdc_printf("  INT1/PC13   : ready, irq=%u, work=%u, skip=%u, read_ret=%d\r\n",
			   imu_data.irq_count, imu_data.work_count,
			   imu_data.skipped_count, imu_data.last_read_ret);
		cdc_printf("  Registers   : INT1_CTRL=0x%02x, CTRL1_XL=0x%02x, CTRL2_G=0x%02x, CTRL3_C=0x%02x\r\n",
			   imu_data.int1_ctrl, imu_data.ctrl1_xl,
			   imu_data.ctrl2_g, imu_data.ctrl3_c);
		cdc_printf("  Accel raw   : x=%6d, y=%6d, z=%6d\r\n",
			   imu_data.accel.x, imu_data.accel.y,
			   imu_data.accel.z);
		cdc_printf("  Gyro raw    : x=%6d, y=%6d, z=%6d\r\n",
			   imu_data.gyro.x, imu_data.gyro.y, imu_data.gyro.z);
	} else {
		cdc_printf("  INT1/PC13   : not-ready, init_ret=%d, read_ret=%d\r\n",
			   imu_data.init_ret, imu_data.last_read_ret);
	}

	cdc_printf("[BAT]\r\n");
	if (battery_ready) {
		uint16_t raw;
		int32_t adc_mv;
		int32_t battery_mv;
		int ret = read_battery_average(&raw, &adc_mv, &battery_mv);

		if (ret < 0) {
			cdc_printf("  Battery     : read failed (%d)\r\n", ret);
		} else {
		cdc_printf("  Sense path  : BAT_EN/PA15 + BAT_Reading/PA4 ADC1_IN4\r\n");
			cdc_printf("  Reading     : raw=%4u, adc=%4d mV, battery=%4d mV (%d.%03d V)\r\n",
				   raw, adc_mv, battery_mv, battery_mv / 1000,
				   battery_mv % 1000);
		}
	} else {
		cdc_printf("  Battery     : not-ready\r\n");
	}

	cdc_printf("[FLASH]\r\n");
	if (flash_ready && flash_result != NULL) {
		cdc_printf("  Device      : %s\r\n", ext_flash->name);
		if (flash_jedec_ret == 0) {
			cdc_printf("  JEDEC ID    : %02x %02x %02x\r\n",
				   flash_jedec_id[0], flash_jedec_id[1],
				   flash_jedec_id[2]);
		} else {
			cdc_printf("  JEDEC ID    : read failed (%d)\r\n",
				   flash_jedec_ret);
		}
		cdc_printf("  Region      : offset=0x%08x, len=%u, erase_page=0x%08lx/%zu\r\n",
			   FLASH_TEST_OFFSET, FLASH_TEST_LEN,
			   (unsigned long)flash_page.start_offset,
			   flash_page.size);
		cdc_printf("  Cycle       : %u\r\n", flash_result->cycle);

		if (flash_result->erase_ret != 0) {
			cdc_printf("  Result      : erase failed (%d)\r\n",
				   flash_result->erase_ret);
		} else if (flash_result->write_ret != 0) {
			cdc_printf("  Result      : erase=OK, write failed (%d)\r\n",
				   flash_result->write_ret);
		} else if (flash_result->read_ret != 0) {
			cdc_printf("  Result      : erase=OK, write=OK, read failed (%d)\r\n",
				   flash_result->read_ret);
		} else if (flash_result->verify_ret != 0) {
			cdc_printf("  Result      : erase=OK, write=OK, read=OK, verify failed at +0x%zx (0x%02x != 0x%02x)\r\n",
				   flash_result->mismatch_offset,
				   flash_result->expected, flash_result->actual);
		} else {
			cdc_printf("  Result      : erase=OK, write=OK, read=OK, verify=OK\r\n");
		}
	} else {
		cdc_printf("  External    : not-ready\r\n");
	}

	cdc_printf("======================================================\r\n");
}

int main(void)
{
	uint32_t report_count = 0;
	uint32_t control_tick = 0;
	uint32_t flash_cycle = 0;
	bool cdc_ready;

	led_ready = init_led();
	(void)k_thread_create(&led_thread_data, led_stack,
			      K_THREAD_STACK_SIZEOF(led_stack),
			      led_thread, NULL, NULL, NULL,
			      7, 0, K_NO_WAIT);

	adc_ready = init_adc();
	pwm_ready = init_a4_pwm();
	heater_pwm_ready = init_heater_pwm();
	i2c_feature_ready = i2c_is_ready_dt(&imu_i2c);
	spi_feature_ready = device_is_ready(ext_flash);
	can_phy_ready = init_can_transceiver();
	can_controller_ready = init_can_controller();
	if (can_controller_ready) {
		(void)k_thread_create(&can_test_thread_data, can_test_stack,
				      K_THREAD_STACK_SIZEOF(can_test_stack),
				      can_test_thread, NULL, NULL, NULL,
				      6, 0, K_NO_WAIT);
	}
	battery_ready = init_battery();
	flash_ready = init_flash();
	cdc_ready = init_cdc();
	(void)init_imu_temperature();
	(void)init_imu_data_interrupt();

	while (true) {
		run_imu_pid_step();

		if ((control_tick %
		     (PRINT_PERIOD_MS / IMU_CONTROL_INTERVAL_MS)) == 0U) {
			uint32_t dtr = 0U;
			uint32_t baudrate = 0U;
			struct flash_cycle_result flash_result;
			const struct flash_cycle_result *flash_report = NULL;

			if (flash_ready) {
				run_flash_cycle(flash_cycle, &flash_result);
				flash_report = &flash_result;
				flash_cycle++;
			}

			if (cdc_ready && cdc_get_line_state(&dtr, &baudrate)) {
				print_status(report_count, dtr, baudrate,
					     flash_report);
			}

			report_count++;
		}

		control_tick++;
		k_msleep(IMU_CONTROL_INTERVAL_MS);
	}

	return 0;
}
