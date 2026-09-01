/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * XIAO STM32C5 — DM-J4310-2EC V1.1 (Damiao) speed-mode CAN driver.
 *
 * Single-file example that drives the motor over FDCAN2 (classic CAN 2.0B
 * @ 1 Mbps) using the Damiao speed-mode protocol, and prints live feedback
 * on the USB CDC ACM virtual COM port.
 *
 * Wiring (differential bus only — do NOT wire MCU CAN_TX/CAN_RX logic pins
 * straight to the motor):
 *   XIAO CANH -> motor CANH
 *   XIAO CANL -> motor CANL
 *   XIAO GND  -> motor GND (24V-)
 *   24V+      -> motor VCC
 *   (120 Ohm termination at each end of the bus)
 *
 * Protocol (Damiao speed mode, motor ID = 0x007):
 *   Speed command : ID 0x200 + motor_id (0x207), D[0..3] = v_des float32 LE rad/s, DLC=4
 *   Control cmd   : ID 0x200 + motor_id (0x207), D[0..6] = 0xFF, D[7] = cmd, DLC=8
 *                    cmd: 0xFC = enable, 0xFD = disable, 0xFB = clear error
 *   Parameter r/w : ID 0x7FF, D[0..1] = motor_id (LE), D[2] = op, D[3] = reg, ...
 *                    op: 0x33 = read, 0x55 = write
 *   Feedback      : standard frame, D[0] = motor_id | (fault<<4), D[1..7] =
 *                    position / velocity / torque / temperatures (see decoder)
 */

#include <stdint.h>
#include <string.h>

#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/can.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

/* ---------------------------------------------------------------------- */
/*  Motor / bus configuration                                             */
/* ---------------------------------------------------------------------- */

/** Motor CAN ID (set by DIP switch / label on the motor). */
#define DM_MOTOR_ID       0x007U

/**
 * Master (host) CAN ID. Stored in the motor as a parameter; the motor uses it
 * to address parameter/feedback responses back to this host. It does not
 * appear in the speed-mode command frame IDs.
 */
#define DM_MASTER_ID      0x017U

#define DM_CAN_BITRATE    1000000U

/** Damiao speed-mode command base. Command/control ID = 0x200 + motor_id. */
#define DM_SPEED_OFFSET   0x200U
#define DM_CONTROL_ID     (DM_SPEED_OFFSET + DM_MOTOR_ID)  /* 0x207 */
#define DM_PARAM_ID       0x7FFU

/* Control commands (sent in D[7] of an 8-byte control frame). */
#define DM_CMD_ENABLE        0xFCU
#define DM_CMD_DISABLE       0xFDU
#define DM_CMD_CLEAR_ERROR   0xFBU

/* Parameter read/write opcodes and registers. */
#define DM_PARAM_READ        0x33U
#define DM_PARAM_WRITE       0x55U
#define DM_REG_CTRL_MODE     0x0AU
#define DM_CTRL_MODE_SPEED   3U

/* Feedback velocity scaling upper bound (rad/s). Default VMAX for this motor. */
#define DM_VMAX_RAD_S       30.0f

/* ---------------------------------------------------------------------- */
/*  Timing                                                               */
/* ---------------------------------------------------------------------- */

#define CONTROL_PERIOD_MS    20U    /* velocity command period (50 Hz)   */
#define GEAR_PERIOD_MS       5000U  /* auto gear advance period          */
#define FEEDBACK_PRINT_MS    500U   /* feedback print period             */

/* ---------------------------------------------------------------------- */
/*  Static state                                                         */
/* ---------------------------------------------------------------------- */

static const struct device *const can_dev = DEVICE_DT_GET(DT_CHOSEN(zephyr_canbus));
static struct gpio_dt_spec led = GPIO_DT_SPEC_GET_OR(DT_ALIAS(led0), gpios, {0});

CAN_MSGQ_DEFINE(rx_msgq, 16);

struct speed_gear {
	uint8_t gear;
	float speed_rad_s;
	const char *label;
};

/* Demo speed profile. Adjust to taste; see the README for a fixed-speed note. */
static const struct speed_gear gears[] = {
	{0U,  0.0f, "stop"},
	{1U,  3.0f, "low"},
	{2U,  6.0f, "medium"},
	{3U, 10.0f, "high"},
};

static const uint8_t gear_sequence[] = {0U, 1U, 2U, 3U, 2U, 1U};
static uint8_t seq_pos;

/* ---------------------------------------------------------------------- */
/*  CAN helpers                                                          */
/* ---------------------------------------------------------------------- */

static void tx_callback(const struct device *dev, int error, void *user_data)
{
	ARG_UNUSED(dev);
	ARG_UNUSED(user_data);

	if (error != 0) {
		printk("CAN TX error: %d\n", error);
	}
}

static int dm_send_cmd(uint8_t cmd)
{
	struct can_frame frame = {
		.id = DM_CONTROL_ID,
		.dlc = 8,
		.data = {0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, cmd},
	};

	return can_send(can_dev, &frame, K_NO_WAIT, tx_callback, NULL);
}

static int dm_write_u32_param(uint8_t reg, uint32_t value)
{
	struct can_frame frame = {
		.id = DM_PARAM_ID,
		.dlc = 8,
		.data = {
			DM_MOTOR_ID & 0xffU,
			(DM_MOTOR_ID >> 8) & 0xffU,
			DM_PARAM_WRITE,
			reg,
			value & 0xffU,
			(value >> 8) & 0xffU,
			(value >> 16) & 0xffU,
			(value >> 24) & 0xffU,
		},
	};

	return can_send(can_dev, &frame, K_NO_WAIT, tx_callback, NULL);
}

static int dm_send_speed(float speed_rad_s)
{
	struct can_frame frame = {
		.id = DM_CONTROL_ID,
		.dlc = 4,
	};

	memcpy(&frame.data[0], &speed_rad_s, sizeof(speed_rad_s));
	return can_send(can_dev, &frame, K_NO_WAIT, tx_callback, NULL);
}

/* ---------------------------------------------------------------------- */
/*  Feedback decoding                                                    */
/* ---------------------------------------------------------------------- */

static void handle_feedback(void)
{
	static int64_t last_print_time;
	struct can_frame frame;
	int64_t now = k_uptime_get();

	while (k_msgq_get(&rx_msgq, &frame, K_NO_WAIT) == 0) {
		/* Speed-mode feedback is a standard frame with DLC >= 8. */
		if ((frame.flags & CAN_FRAME_IDE) != 0U || frame.dlc < 8U) {
			continue;
		}

		uint8_t motor_id = frame.data[0] & 0x0fU;
		uint8_t fault    = frame.data[0] >> 4;
		uint16_t pos_raw   = ((uint16_t)frame.data[1] << 8) | frame.data[2];
		uint16_t vel_raw   = ((uint16_t)frame.data[3] << 4) | (frame.data[4] >> 4);
		uint16_t torque_raw = ((uint16_t)(frame.data[4] & 0x0fU) << 8) | frame.data[5];

		if (motor_id != (DM_MOTOR_ID & 0x0fU)) {
			continue;
		}

		if (now - last_print_time < FEEDBACK_PRINT_MS) {
			continue;
		}

		float vel_rad_s = (((float)vel_raw / 4095.0f) * 2.0f - 1.0f) * DM_VMAX_RAD_S;

		printk("FB id=0x%03x motor=%u err=0x%x pos=0x%04x vel=0x%03x %.2f rad/s "
		       "tq=0x%03x mos=%u rotor=%u\n",
		       frame.id, motor_id, fault, pos_raw, vel_raw, (double)vel_rad_s,
		       torque_raw, frame.data[6], frame.data[7]);
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

/* ---------------------------------------------------------------------- */
/*  Main                                                                 */
/* ---------------------------------------------------------------------- */

int main(void)
{
	int ret;

	printk("XIAO STM32C5 DM-J4310-2EC V1.1 speed-mode driver\n");
	printk("motor_id=0x%03x master_id=0x%03x bitrate=1 Mbps\n",
	       DM_MOTOR_ID, DM_MASTER_ID);

	if (!device_is_ready(can_dev)) {
		printk("CAN device %s not ready\n", can_dev->name);
		return 0;
	}

	if (led.port != NULL && gpio_is_ready_dt(&led)) {
		(void)gpio_pin_configure_dt(&led, GPIO_OUTPUT_INACTIVE);
	}

	/* 1. Configure + start the FDCAN2 controller. */
	ret = can_set_bitrate(can_dev, DM_CAN_BITRATE);
	if (ret != 0) {
		printk("Failed to set CAN bitrate: %d\n", ret);
		return 0;
	}

	/* Catch-all RX filter: accept every frame, decode in handle_feedback(). */
	const struct can_filter rx_all = { .id = 0, .mask = 0 };
	ret = can_add_rx_filter_msgq(can_dev, &rx_msgq, &rx_all);
	if (ret < 0) {
		printk("Failed to add CAN RX filter: %d\n", ret);
		return 0;
	}

	ret = can_start(can_dev);
	if (ret != 0) {
		printk("Failed to start CAN controller: %d\n", ret);
		return 0;
	}

	/* 2. Motor startup sequence: clear error -> select speed mode -> enable. */
	(void)dm_send_cmd(DM_CMD_CLEAR_ERROR);
	drain_rx_for(100);

	(void)dm_write_u32_param(DM_REG_CTRL_MODE, DM_CTRL_MODE_SPEED);
	drain_rx_for(100);

	(void)dm_send_cmd(DM_CMD_ENABLE);
	drain_rx_for(100);

	printk("Motor enabled (speed mode). Cycling speed gears every %u s.\n",
	       GEAR_PERIOD_MS / 1000U);

	int64_t next_gear_time = k_uptime_get() + GEAR_PERIOD_MS;

	while (true) {
		const struct speed_gear *gear = &gears[gear_sequence[seq_pos]];

		if (k_uptime_get() >= next_gear_time) {
			seq_pos = (seq_pos + 1U) % ARRAY_SIZE(gear_sequence);
			printk("Gear %u (%s): %.2f rad/s\n",
			       gears[gear_sequence[seq_pos]].gear,
			       gears[gear_sequence[seq_pos]].label,
			       (double)gears[gear_sequence[seq_pos]].speed_rad_s);
			next_gear_time += GEAR_PERIOD_MS;
		}

		(void)dm_send_speed(gear->speed_rad_s);
		handle_feedback();

		if (led.port != NULL) {
			(void)gpio_pin_set_dt(&led, gear->gear != 0U);
		}

		k_sleep(K_MSEC(CONTROL_PERIOD_MS));
	}
}
