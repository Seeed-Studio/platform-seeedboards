/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * XIAO STM32C5 Damiao DM-J4340P-2EC V1.1 24V speed-mode sample.
 */

#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/can.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>

#define CANBUS_NODE DT_CHOSEN(zephyr_canbus)

#ifndef DAMIAO_MOTOR_ID
#define DAMIAO_MOTOR_ID 1U
#endif

#define DAMIAO_SPEED_MODE_OFFSET 0x200U
#define DAMIAO_PARAM_FRAME_ID 0x7FFU
#define DAMIAO_CONTROL_FRAME_ID (DAMIAO_SPEED_MODE_OFFSET + DAMIAO_MOTOR_ID)
#define DAMIAO_CMD_ENABLE 0xFCU
#define DAMIAO_CMD_DISABLE 0xFDU
#define DAMIAO_CMD_CLEAR_ERROR 0xFBU
#define DAMIAO_PARAM_READ 0x33U
#define DAMIAO_PARAM_WRITE 0x55U
#define DAMIAO_REG_ACC 0x04U
#define DAMIAO_REG_DEC 0x05U
#define DAMIAO_REG_MAX_SPD 0x06U
#define DAMIAO_REG_CTRL_MODE 0x0AU
#define DAMIAO_REG_VMAX 0x16U
#define DAMIAO_REG_KP_ASR 0x19U
#define DAMIAO_REG_KI_ASR 0x1AU
#define DAMIAO_REG_DETA 0x1FU
#define DAMIAO_REG_VBUS 0x3CU
#define DAMIAO_CTRL_MODE_SPEED 3U

#define CONTROL_PERIOD_MS 20
#define GEAR_PERIOD_MS 5000
#define FEEDBACK_PRINT_PERIOD_MS 500

static const struct device *const can_dev = DEVICE_DT_GET(CANBUS_NODE);
static struct gpio_dt_spec led = GPIO_DT_SPEC_GET_OR(DT_ALIAS(led0), gpios, {0});
static float feedback_vmax_rad_s = 30.0f;

CAN_MSGQ_DEFINE(rx_msgq, 16);

struct speed_gear {
	uint8_t gear;
	float speed_rad_s;
	const char *label;
};

static const struct speed_gear gears[] = {
	{0U, 0.0f, "stop"},
	{1U, 3.0f, "low"},
	{2U, 6.0f, "medium"},
};

static const uint8_t gear_sequence[] = {0U, 1U, 2U, 1U};
static uint8_t sequence_pos;

static void tx_callback(const struct device *dev, int error, void *user_data)
{
	ARG_UNUSED(dev);
	ARG_UNUSED(user_data);

	if (error != 0) {
		printf("CAN TX error: %d\n", error);
	}
}

static int damiao_send_cmd(uint8_t cmd)
{
	struct can_frame frame = {
		.id = DAMIAO_CONTROL_FRAME_ID,
		.dlc = 8,
		.data = {0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, cmd},
	};

	return can_send(can_dev, &frame, K_NO_WAIT, tx_callback, NULL);
}

static int damiao_read_param(uint8_t reg)
{
	struct can_frame frame = {
		.id = DAMIAO_PARAM_FRAME_ID,
		.dlc = 4,
		.data = {
			DAMIAO_MOTOR_ID & 0xffU,
			(DAMIAO_MOTOR_ID >> 8) & 0xffU,
			DAMIAO_PARAM_READ,
			reg,
		},
	};

	return can_send(can_dev, &frame, K_NO_WAIT, tx_callback, NULL);
}

static int damiao_write_u32_param(uint8_t reg, uint32_t value)
{
	struct can_frame frame = {
		.id = DAMIAO_PARAM_FRAME_ID,
		.dlc = 8,
		.data = {
			DAMIAO_MOTOR_ID & 0xffU,
			(DAMIAO_MOTOR_ID >> 8) & 0xffU,
			DAMIAO_PARAM_WRITE,
			reg,
			value & 0xffU,
			(value >> 8) & 0xffU,
			(value >> 16) & 0xffU,
			(value >> 24) & 0xffU,
		},
	};

	return can_send(can_dev, &frame, K_NO_WAIT, tx_callback, NULL);
}

static int damiao_send_speed(float speed_rad_s)
{
	struct can_frame frame = {
		.id = DAMIAO_CONTROL_FRAME_ID,
		.dlc = 4,
	};

	memcpy(&frame.data[0], &speed_rad_s, sizeof(speed_rad_s));
	return can_send(can_dev, &frame, K_NO_WAIT, tx_callback, NULL);
}

static void print_current_gear(void)
{
	const struct speed_gear *gear = &gears[gear_sequence[sequence_pos]];

	printf("Gear %u (%s): %.2f rad/s\n", gear->gear, gear->label, (double)gear->speed_rad_s);
}

static void advance_gear(void)
{
	sequence_pos = (sequence_pos + 1U) % ARRAY_SIZE(gear_sequence);
	print_current_gear();
}

static bool handle_param_response(const struct can_frame *frame)
{
	if (frame->dlc < 8U || frame->data[0] != (DAMIAO_MOTOR_ID & 0xffU) ||
	    frame->data[1] != ((DAMIAO_MOTOR_ID >> 8) & 0xffU)) {
		return false;
	}

	if (frame->data[2] == DAMIAO_PARAM_READ || frame->data[2] == DAMIAO_PARAM_WRITE) {
		uint32_t value_u32 = (uint32_t)frame->data[4] | ((uint32_t)frame->data[5] << 8) |
				     ((uint32_t)frame->data[6] << 16) |
				     ((uint32_t)frame->data[7] << 24);
		float value_float;

		memcpy(&value_float, &value_u32, sizeof(value_float));

		if (frame->data[3] == DAMIAO_REG_CTRL_MODE) {
			printf("PARAM CTRL_MODE %s: %u\n",
			       frame->data[2] == DAMIAO_PARAM_READ ? "read" : "write", value_u32);
		} else if (frame->data[3] == DAMIAO_REG_ACC) {
			printf("PARAM ACC %s: %.2f rad/s^2\n",
			       frame->data[2] == DAMIAO_PARAM_READ ? "read" : "write",
			       (double)value_float);
		} else if (frame->data[3] == DAMIAO_REG_DEC) {
			printf("PARAM DEC %s: %.2f rad/s^2\n",
			       frame->data[2] == DAMIAO_PARAM_READ ? "read" : "write",
			       (double)value_float);
		} else if (frame->data[3] == DAMIAO_REG_MAX_SPD) {
			printf("PARAM MAX_SPD %s: %.2f rad/s\n",
			       frame->data[2] == DAMIAO_PARAM_READ ? "read" : "write",
			       (double)value_float);
		} else if (frame->data[3] == DAMIAO_REG_VMAX) {
			printf("PARAM VMAX %s: %.2f rad/s\n",
			       frame->data[2] == DAMIAO_PARAM_READ ? "read" : "write",
			       (double)value_float);
			if (value_float > 0.0f && value_float < 1000.0f) {
				feedback_vmax_rad_s = value_float;
			}
		} else if (frame->data[3] == DAMIAO_REG_VBUS) {
			printf("PARAM VBus %s: %.2f V\n",
			       frame->data[2] == DAMIAO_PARAM_READ ? "read" : "write",
			       (double)value_float);
		} else if (frame->data[3] == DAMIAO_REG_KP_ASR) {
			printf("PARAM KP_ASR %s: %.3f\n",
			       frame->data[2] == DAMIAO_PARAM_READ ? "read" : "write",
			       (double)value_float);
		} else if (frame->data[3] == DAMIAO_REG_KI_ASR) {
			printf("PARAM KI_ASR %s: %.3f\n",
			       frame->data[2] == DAMIAO_PARAM_READ ? "read" : "write",
			       (double)value_float);
		} else if (frame->data[3] == DAMIAO_REG_DETA) {
			printf("PARAM Deta %s: %.3f\n",
			       frame->data[2] == DAMIAO_PARAM_READ ? "read" : "write",
			       (double)value_float);
		} else {
			printf("PARAM reg=0x%02x cmd=0x%02x value_u32=%u value_float=%.3f\n",
			       frame->data[3], frame->data[2], value_u32, (double)value_float);
		}

		return true;
	}

	return false;
}

static void handle_feedback(void)
{
	static int64_t last_print_time;
	struct can_frame frame;
	int64_t now = k_uptime_get();

	while (k_msgq_get(&rx_msgq, &frame, K_NO_WAIT) == 0) {
		if ((frame.flags & CAN_FRAME_IDE) != 0U || frame.dlc < 8U) {
			if ((frame.flags & CAN_FRAME_IDE) == 0U && frame.dlc >= 4U) {
				printf("RX can_id=0x%03x dlc=%u data=%02x %02x %02x %02x\n",
			       frame.id, frame.dlc, frame.data[0], frame.data[1],
			       frame.data[2], frame.data[3]);
			}
			continue;
		}

		if (handle_param_response(&frame)) {
			continue;
		}

		if (now - last_print_time < FEEDBACK_PRINT_PERIOD_MS) {
			continue;
		}

		uint8_t motor_id = frame.data[0] & 0x0fU;
		uint8_t err = frame.data[0] >> 4;
		uint16_t pos_raw = ((uint16_t)frame.data[1] << 8) | frame.data[2];
		uint16_t vel_raw = ((uint16_t)frame.data[3] << 4) | (frame.data[4] >> 4);
		uint16_t torque_raw = ((uint16_t)(frame.data[4] & 0x0fU) << 8) | frame.data[5];
		float vel_rad_s = (((float)vel_raw / 4095.0f) * 2.0f - 1.0f) * feedback_vmax_rad_s;

		printf("FB can_id=0x%03x motor=%u err=0x%x pos=0x%04x vel=0x%03x %.2f rad/s tq=0x%03x mos=%u rotor=%u\n",
		       frame.id, motor_id, err, pos_raw, vel_raw, (double)vel_rad_s, torque_raw,
		       frame.data[6], frame.data[7]);
		last_print_time = now;
	}
}

static void drain_rx_for(int32_t duration_ms)
{
	int64_t deadline = k_uptime_get() + duration_ms;

	do {
		handle_feedback();
		k_sleep(K_MSEC(5));
	} while (k_uptime_get() < deadline);
}

static void read_param_with_drain(uint8_t reg)
{
	(void)damiao_read_param(reg);
	drain_rx_for(80);
}

int main(void)
{
	const struct can_filter feedback_filter = {
		.id = 0,
		.mask = 0,
	};
	int ret;

	printf("XIAO STM32C5 Damiao DM-J4340P-2EC V1.1 24V speed sample\n");
	printf("Automatic speed sequence every 5 seconds: 0->3->6->3->0 rad/s\n");
	printf("Motor ID: %u, CAN bitrate: 1 Mbps\n", DAMIAO_MOTOR_ID);

	if (!device_is_ready(can_dev)) {
		printf("CAN device %s is not ready\n", can_dev->name);
		return 0;
	}

	if (led.port != NULL && gpio_is_ready_dt(&led)) {
		(void)gpio_pin_configure_dt(&led, GPIO_OUTPUT_INACTIVE);
	}

	ret = can_set_bitrate(can_dev, 1000000U);
	if (ret != 0) {
		printf("Failed to set CAN bitrate: %d\n", ret);
		return 0;
	}

	ret = can_add_rx_filter_msgq(can_dev, &rx_msgq, &feedback_filter);
	if (ret < 0) {
		printf("Failed to add CAN RX filter: %d\n", ret);
		return 0;
	}

	ret = can_start(can_dev);
	if (ret != 0) {
		printf("Failed to start CAN controller: %d\n", ret);
		return 0;
	}

	(void)damiao_send_cmd(DAMIAO_CMD_CLEAR_ERROR);
	drain_rx_for(100);
	(void)damiao_write_u32_param(DAMIAO_REG_CTRL_MODE, DAMIAO_CTRL_MODE_SPEED);
	drain_rx_for(100);
	read_param_with_drain(DAMIAO_REG_CTRL_MODE);
	read_param_with_drain(DAMIAO_REG_ACC);
	read_param_with_drain(DAMIAO_REG_DEC);
	read_param_with_drain(DAMIAO_REG_MAX_SPD);
	read_param_with_drain(DAMIAO_REG_VMAX);
	read_param_with_drain(DAMIAO_REG_KP_ASR);
	read_param_with_drain(DAMIAO_REG_KI_ASR);
	read_param_with_drain(DAMIAO_REG_DETA);
	read_param_with_drain(DAMIAO_REG_VBUS);
	(void)damiao_send_cmd(DAMIAO_CMD_ENABLE);
	drain_rx_for(100);
	print_current_gear();

	int64_t next_gear_time = k_uptime_get() + GEAR_PERIOD_MS;

	while (true) {
		const struct speed_gear *gear = &gears[gear_sequence[sequence_pos]];

		if (k_uptime_get() >= next_gear_time) {
			advance_gear();
			next_gear_time += GEAR_PERIOD_MS;
		}

		(void)damiao_send_speed(gear->speed_rad_s);
		handle_feedback();

		if (led.port != NULL) {
			(void)gpio_pin_set_dt(&led, gear->gear != 0U);
		}

		k_sleep(K_MSEC(CONTROL_PERIOD_MS));
	}
}
