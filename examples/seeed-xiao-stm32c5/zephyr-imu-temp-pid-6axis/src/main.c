/*
 * Copyright (c) 2026 Seeed Technology Co., Ltd.
 * SPDX-License-Identifier: Apache-2.0
 *
 * XIAO STM32C5 onboard LSM6DS3TR-C temperature PID + 6-axis interrupt test.
 */

#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/i2c.h>
#include <zephyr/drivers/pwm.h>
#include <zephyr/drivers/sensor.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/printk.h>
#include <zephyr/sys/util.h>

#define IMU_NODE DT_ALIAS(imu0)
#define HEATER_NODE DT_ALIAS(imu_heater)

#define LSM6DSL_REG_WHO_AM_I 0x0f
#define LSM6DSL_REG_CTRL1_XL 0x10
#define LSM6DSL_REG_OUT_TEMP_L 0x20
#define LSM6DSL_EXPECTED_WHO_AM_I 0x6a

#define TARGET_TEMPERATURE_MC 40000
#define CONTROL_INTERVAL_MS 500
#define PID_LOG_INTERVAL_MS 1000
#define IMU_DATA_LOG_INTERVAL_MS 1000
#define IRQ_LOG_INTERVAL_MS 1000
#define LOOP_WAIT_MS 50

#define DUTY_MIN_PERMILLE 0
#define DUTY_MAX_PERMILLE 600
#define DUTY_STEP_PERMILLE 50
#define FILTER_SHIFT 2

#define KP_PER_MILLE_PER_C 25
#define KI_PER_MILLE_PER_C_S 2
#define INTEGRAL_LIMIT_MC_S 180000

#define IMU_ODR_HZ 104
#define IMU_PRINT_DECIMALS 6

BUILD_ASSERT(DT_NODE_HAS_STATUS(IMU_NODE, okay),
	     "imu0 alias is not defined or not okay");
BUILD_ASSERT(DT_NODE_HAS_STATUS(HEATER_NODE, okay),
	     "imu-heater alias is not defined or not okay");

static const struct device *const imu = DEVICE_DT_GET(IMU_NODE);
static const struct i2c_dt_spec imu_i2c = I2C_DT_SPEC_GET(IMU_NODE);
static const struct pwm_dt_spec heater = PWM_DT_SPEC_GET(HEATER_NODE);

static K_SEM_DEFINE(imu_drdy_sem, 0, 1);
static atomic_t imu_irq_count;

struct pid_state {
	int32_t integral_mc_s;
	int32_t filtered_temperature_mc;
	uint32_t previous_duty_permille;
	bool filter_ready;
};

static bool time_reached(uint32_t now_ms, uint32_t deadline_ms)
{
	return (int32_t)(now_ms - deadline_ms) >= 0;
}

static int32_t abs_i32(int32_t value)
{
	return value < 0 ? -value : value;
}

static void print_mc(const char *label, int32_t value_mc)
{
	int32_t abs_value = abs_i32(value_mc);

	printk("%s%s%d.%03d C",
	       label,
	       value_mc < 0 ? "-" : "",
	       abs_value / 1000,
	       abs_value % 1000);
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

static int read_who_am_i(uint8_t *who_am_i)
{
	return i2c_reg_read_byte_dt(&imu_i2c, LSM6DSL_REG_WHO_AM_I, who_am_i);
}

static int read_imu_temperature_mc(int32_t *temperature_mc)
{
	struct sensor_value temperature;
	int ret;

	ret = sensor_sample_fetch_chan(imu, SENSOR_CHAN_DIE_TEMP);
	if (ret < 0) {
		return ret;
	}

	ret = sensor_channel_get(imu, SENSOR_CHAN_DIE_TEMP, &temperature);
	if (ret < 0) {
		return ret;
	}

	*temperature_mc = (temperature.val1 * 1000) + (temperature.val2 / 1000);
	return 0;
}

static int read_raw_temperature(int16_t *raw_temperature)
{
	uint8_t temp_l;
	uint8_t temp_h;
	int ret;

	ret = i2c_reg_read_byte_dt(&imu_i2c, LSM6DSL_REG_OUT_TEMP_L, &temp_l);
	if (ret < 0) {
		return ret;
	}

	ret = i2c_reg_read_byte_dt(&imu_i2c, LSM6DSL_REG_OUT_TEMP_L + 1, &temp_h);
	if (ret < 0) {
		return ret;
	}

	*raw_temperature = (int16_t)((uint16_t)temp_l | ((uint16_t)temp_h << 8));
	return 0;
}

static void print_imu_debug_registers(void)
{
	uint8_t who_am_i;
	uint8_t ctrl1_xl;
	int ret;

	ret = read_who_am_i(&who_am_i);
	if (ret < 0) {
		printk("Failed to read WHO_AM_I: %d\n", ret);
		return;
	}

	ret = i2c_reg_read_byte_dt(&imu_i2c, LSM6DSL_REG_CTRL1_XL, &ctrl1_xl);
	if (ret < 0) {
		printk("Failed to read CTRL1_XL: %d\n", ret);
		return;
	}

	printk("IMU WHO_AM_I=0x%02x", who_am_i);
	if (who_am_i == LSM6DSL_EXPECTED_WHO_AM_I) {
		printk(" OK");
	} else {
		printk(" unexpected, expected 0x%02x", LSM6DSL_EXPECTED_WHO_AM_I);
	}
	printk(" CTRL1_XL=0x%02x\n", ctrl1_xl);
}

static int set_heater_duty(uint32_t duty_permille)
{
	uint32_t pulse = (heater.period * duty_permille) / 1000U;

	return pwm_set_dt(&heater, heater.period, pulse);
}

static uint32_t apply_duty_slew_limit(struct pid_state *pid,
				      uint32_t duty_permille)
{
	uint32_t previous = pid->previous_duty_permille;

	if (duty_permille > previous + DUTY_STEP_PERMILLE) {
		duty_permille = previous + DUTY_STEP_PERMILLE;
	} else if (previous > duty_permille + DUTY_STEP_PERMILLE) {
		duty_permille = previous - DUTY_STEP_PERMILLE;
	}

	pid->previous_duty_permille = duty_permille;
	return duty_permille;
}

static uint32_t pi_update(struct pid_state *pid, int32_t temperature_mc,
			  int32_t *filtered_temperature_mc, int32_t *error_mc)
{
	int32_t p_term;
	int32_t i_term;
	int32_t output_permille;

	if (!pid->filter_ready) {
		pid->filtered_temperature_mc = temperature_mc;
		pid->filter_ready = true;
	} else {
		pid->filtered_temperature_mc +=
			(temperature_mc - pid->filtered_temperature_mc) >> FILTER_SHIFT;
	}

	*filtered_temperature_mc = pid->filtered_temperature_mc;
	*error_mc = TARGET_TEMPERATURE_MC - pid->filtered_temperature_mc;

	pid->integral_mc_s += (*error_mc * CONTROL_INTERVAL_MS) / 1000;
	pid->integral_mc_s = CLAMP(pid->integral_mc_s,
				   -INTEGRAL_LIMIT_MC_S,
				   INTEGRAL_LIMIT_MC_S);

	p_term = (KP_PER_MILLE_PER_C * *error_mc) / 1000;
	i_term = (KI_PER_MILLE_PER_C_S * pid->integral_mc_s) / 1000;

	output_permille = p_term + i_term;
	output_permille = CLAMP(output_permille,
				DUTY_MIN_PERMILLE,
				DUTY_MAX_PERMILLE);

	return apply_duty_slew_limit(pid, output_permille);
}

static int run_pid_control_step(struct pid_state *pid, bool print_log)
{
	int32_t temperature_mc;
	int32_t filtered_temperature_mc;
	int32_t error_mc;
	int16_t raw_temperature;
	uint32_t duty_permille;
	int ret;

	ret = read_imu_temperature_mc(&temperature_mc);
	if (ret < 0) {
		(void)set_heater_duty(0);
		printk("[PID] failed to read IMU temperature: %d; heater off\n", ret);
		return ret;
	}

	ret = read_raw_temperature(&raw_temperature);
	if (ret < 0) {
		raw_temperature = 0;
		if (print_log) {
			printk("[PID] failed to read raw IMU temperature: %d\n", ret);
		}
	}

	duty_permille = pi_update(pid, temperature_mc,
				  &filtered_temperature_mc, &error_mc);

	ret = set_heater_duty(duty_permille);
	if (ret < 0) {
		printk("[PID] failed to set heater PWM: %d\n", ret);
		return ret;
	}

	if (print_log) {
		printk("[PID] ");
		print_mc("temp=", temperature_mc);
		printk(" ");
		print_mc("filtered=", filtered_temperature_mc);
		printk(" ");
		print_mc("target=", TARGET_TEMPERATURE_MC);
		printk(" ");
		print_mc("error=", error_mc);
		printk(" raw=%d duty=%u.%u%%\n",
		       raw_temperature, duty_permille / 10, duty_permille % 10);
	}

	return 0;
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
	struct pid_state pid = { 0 };
	uint32_t now_ms = k_uptime_get_32();
	uint32_t next_control_ms = now_ms;
	uint32_t next_pid_log_ms = now_ms;
	uint32_t next_imu_log_ms = now_ms;
	uint32_t next_irq_log_ms = now_ms + IRQ_LOG_INTERVAL_MS;
	uint32_t last_irq_seen_ms = now_ms;
	int32_t last_irq_log_count = 0;
	bool sample_pending = true;
	bool irq_enabled = false;
	int ret;

	printk("\n");
	printk("====================================================\n");
	printk("  IMU Temp PID + 6-Axis Test for XIAO STM32C5\n");
	printk("====================================================\n");
	printk("Hardware mapping:\n");
	printk("  IMU          -> LSM6DS3TR-C, I2C address 0x6A\n");
	printk("  I2C          -> I2C2 on PB3(SCL) / PB4(SDA)\n");
	printk("  INT1         -> PC13, active-high data-ready interrupt\n");
	printk("  Heater PWM   -> PA8 / TIM1_CH1, period %u ns\n", heater.period);
	printk("Runtime setup:\n");
	printk("  PID target   -> %d.%03d C, control interval %d ms\n",
	       TARGET_TEMPERATURE_MC / 1000,
	       TARGET_TEMPERATURE_MC % 1000,
	       CONTROL_INTERVAL_MS);
	printk("  Accel        -> +/-4g, %d Hz\n", IMU_ODR_HZ);
	printk("  Gyro         -> +/-500 dps, %d Hz\n", IMU_ODR_HZ);
	printk("  Log rate     -> PID/IMU/IRQ about once per second\n");
	printk("  External wiring required: none\n");

	if (!device_is_ready(imu)) {
		printk("IMU device %s is not ready\n", imu->name);
		return 0;
	}

	if (!i2c_is_ready_dt(&imu_i2c)) {
		printk("IMU I2C bus %s is not ready\n", imu_i2c.bus->name);
		return 0;
	}

	if (!pwm_is_ready_dt(&heater)) {
		printk("Heater PWM device is not ready\n");
		return 0;
	}

	printk("IMU device: %s\n", imu->name);
	printk("IMU I2C bus: %s\n", imu_i2c.bus->name);
	print_imu_debug_registers();

	ret = set_heater_duty(0);
	if (ret < 0) {
		printk("Failed to disable heater PWM: %d\n", ret);
		return 0;
	}

	ret = configure_imu();
	if (ret < 0) {
		(void)set_heater_duty(0);
		return 0;
	}

	ret = configure_imu_interrupt();
	if (ret == 0) {
		irq_enabled = true;
	} else {
		printk("Continuing with 1 Hz polling reads so six-axis data can still be checked.\n");
	}

	printk("\nRunning. Move or rotate the board; irq total/delta should increase.\n");

	while (true) {
		ret = k_sem_take(&imu_drdy_sem, K_MSEC(LOOP_WAIT_MS));
		now_ms = k_uptime_get_32();

		if (ret == 0) {
			sample_pending = true;
			last_irq_seen_ms = now_ms;
		}

		if (time_reached(now_ms, next_control_ms)) {
			bool print_pid = time_reached(now_ms, next_pid_log_ms);

			ret = run_pid_control_step(&pid, print_pid);
			if (ret < 0 && !print_pid) {
				next_pid_log_ms = now_ms + PID_LOG_INTERVAL_MS;
			}

			next_control_ms = now_ms + CONTROL_INTERVAL_MS;
			if (print_pid) {
				next_pid_log_ms = now_ms + PID_LOG_INTERVAL_MS;
			}
		}

		if (irq_enabled && time_reached(now_ms, next_irq_log_ms)) {
			int32_t irq_count = atomic_get(&imu_irq_count);
			int32_t irq_delta = irq_count - last_irq_log_count;
			uint32_t irq_age_ms = now_ms - last_irq_seen_ms;

			printk("[IRQ] data-ready total=%d delta=%d/%dms last=%u ms ago\n",
			       irq_count, irq_delta, IRQ_LOG_INTERVAL_MS, irq_age_ms);

			last_irq_log_count = irq_count;
			next_irq_log_ms = now_ms + IRQ_LOG_INTERVAL_MS;

			if (irq_delta == 0) {
				sample_pending = true;
			}
		}

		if (!irq_enabled && time_reached(now_ms, next_imu_log_ms)) {
			sample_pending = true;
		}

		if (sample_pending && time_reached(now_ms, next_imu_log_ms)) {
			(void)read_and_print_imu_sample(atomic_get(&imu_irq_count));
			sample_pending = false;
			next_imu_log_ms = now_ms + IMU_DATA_LOG_INTERVAL_MS;
		}
	}

	return 0;
}
