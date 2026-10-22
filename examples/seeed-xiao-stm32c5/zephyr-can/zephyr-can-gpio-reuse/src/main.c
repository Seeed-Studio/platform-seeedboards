/*
 * Copyright (c) 2026 Seeed Technology Co., Ltd.
 * SPDX-License-Identifier: Apache-2.0
 *
 * XIAO STM32C5 FDCAN2 pin GPIO reuse command test.
 */

#include <string.h>

#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>
#include <zephyr/sys/sys_io.h>

#define TP7_NODE DT_ALIAS(tp7_gpio)
#define TP8_NODE DT_ALIAS(tp8_gpio)
#define CAN_STB_NODE DT_ALIAS(can_stb_gpio)
#define UART_NODE DT_CHOSEN(zephyr_shell_uart)

#define GPIOB_BASE_ADDR 0x42020400UL
#define GPIO_MODER_OFFSET 0x00UL
#define GPIO_IDR_OFFSET 0x10UL
#define GPIO_ODR_OFFSET 0x14UL

#define PB5_PIN 5U
#define PB13_PIN 13U
#define PB14_PIN 14U
#define SETTLE_MS 20
#define COMMAND_BUFFER_SIZE 64
#define UART_RX_QUEUE_SIZE 256
#define IDLE_STATUS_INTERVAL_MS 5000
#define COMMAND_IDLE_COMMIT_MS 1000

BUILD_ASSERT(DT_NODE_HAS_STATUS(TP7_NODE, okay), "tp7-gpio alias missing");
BUILD_ASSERT(DT_NODE_HAS_STATUS(TP8_NODE, okay), "tp8-gpio alias missing");
BUILD_ASSERT(DT_NODE_HAS_STATUS(CAN_STB_NODE, okay), "can-stb-gpio alias missing");
BUILD_ASSERT(DT_NODE_HAS_STATUS(UART_NODE, okay), "zephyr,shell-uart chosen node missing");

static const struct gpio_dt_spec tp7_pb5 = GPIO_DT_SPEC_GET(TP7_NODE, gpios);
static const struct gpio_dt_spec tp8_pb13 = GPIO_DT_SPEC_GET(TP8_NODE, gpios);
static const struct gpio_dt_spec can_stb_pb14 = GPIO_DT_SPEC_GET(CAN_STB_NODE, gpios);
static const struct device *const command_uart = DEVICE_DT_GET(UART_NODE);
K_MSGQ_DEFINE(uart_rx_msgq, sizeof(uint8_t), UART_RX_QUEUE_SIZE, 4);

static int pb5_state;
static int pb13_state;
static uint32_t rx_drop_count;

static int configure_output(const struct gpio_dt_spec *spec, int value,
			    const char *name)
{
	int ret;

	if (!gpio_is_ready_dt(spec)) {
		printk("ERROR: %s GPIO controller is not ready\n", name);
		return -ENODEV;
	}

	ret = gpio_pin_configure_dt(spec, value ? GPIO_OUTPUT_ACTIVE :
				   GPIO_OUTPUT_INACTIVE);
	if (ret != 0) {
		printk("ERROR: configure %s failed: %d\n", name, ret);
		return ret;
	}

	return 0;
}

static int set_pin(const struct gpio_dt_spec *spec, int value,
		   const char *name)
{
	int ret = gpio_pin_set_dt(spec, value);

	if (ret != 0) {
		printk("ERROR: set %s=%d failed: %d\n", name, value, ret);
	}

	return ret;
}

static int force_standby_high(void)
{
	return set_pin(&can_stb_pb14, 1, "CAN_STB/PB14");
}

static uint32_t gpiob_reg(uint32_t offset)
{
	return sys_read32(GPIOB_BASE_ADDR + offset);
}

static uint32_t pin_bit(uint32_t value, uint32_t pin)
{
	return (value & BIT(pin)) ? 1U : 0U;
}

static void print_status_compact(const char *prefix)
{
	int pb5_read = gpio_pin_get_dt(&tp7_pb5);
	int pb13_read = gpio_pin_get_dt(&tp8_pb13);
	int stb_read = gpio_pin_get_dt(&can_stb_pb14);

	printk("%s PB5=%d(read %d) PB13=%d(read %d) PB14/STB=HIGH(read %d)\n",
	       prefix, pb5_state, pb5_read, pb13_state, pb13_read, stb_read);
}

static void print_status_detail(const char *prefix)
{
	uint32_t moder = gpiob_reg(GPIO_MODER_OFFSET);
	uint32_t odr = gpiob_reg(GPIO_ODR_OFFSET);
	uint32_t idr = gpiob_reg(GPIO_IDR_OFFSET);

	print_status_compact(prefix);
	printk("%s GPIOB MODER=%08x ODR=%08x IDR=%08x | "
	       "ODR PB5/PB13/PB14=%u/%u/%u IDR PB5/PB13/PB14=%u/%u/%u\n",
	       prefix, moder, odr, idr,
	       pin_bit(odr, PB5_PIN), pin_bit(odr, PB13_PIN),
	       pin_bit(odr, PB14_PIN),
	       pin_bit(idr, PB5_PIN), pin_bit(idr, PB13_PIN),
	       pin_bit(idr, PB14_PIN));
}

static int apply_gpio_state(const char *reason)
{
	int ret;

	ret = force_standby_high();
	if (ret != 0) {
		return ret;
	}

	ret = set_pin(&tp7_pb5, pb5_state, "TP7/PB5");
	if (ret != 0) {
		return ret;
	}

	ret = set_pin(&tp8_pb13, pb13_state, "TP8/PB13");
	if (ret != 0) {
		return ret;
	}

	k_msleep(SETTLE_MS);
	print_status_detail(reason);
	return 0;
}

static void print_help(void)
{
	printk("\n");
	printk("============================================================\n");
	printk("  XIAO STM32C5 FDCAN2 Reuse GPIO Command Test\n");
	printk("============================================================\n");
	printk("Purpose:\n");
	printk("  Use a multimeter to verify TP7/PB5 and TP8/PB13 level changes.\n");
	printk("  PB14/CAN_STB is configured as GPIO output HIGH at startup and\n");
	printk("  forced HIGH after every command to keep the CAN transceiver in standby.\n");
	printk("\nHardware mapping:\n");
	printk("  TP7  -> PB5  / FDCAN2_RX -> GPIO output controlled by command\n");
	printk("  TP8  -> PB13 / FDCAN2_TX -> GPIO output controlled by command\n");
	printk("  STB  -> PB14 / CAN_STB   -> fixed GPIO HIGH, transceiver standby\n");
	printk("\nCommand format:\n");
	printk("  ASCII text, 115200 8N1. End command with Enter (CR/LF).\n");
	printk("  If the tool sends no CR/LF, a complete command is accepted after 1 s idle.\n");
	printk("  UART RX uses interrupt FIFO, same path as zephyr-uart-max-rate.\n");
	printk("  help              Print this command list\n");
	printk("  status            Print PB5/PB13/PB14 readback and GPIOB registers\n");
	printk("  pb5 0             Drive TP7/PB5 LOW\n");
	printk("  pb5 1             Drive TP7/PB5 HIGH\n");
	printk("  pb13 0            Drive TP8/PB13 LOW\n");
	printk("  pb13 1            Drive TP8/PB13 HIGH\n");
	printk("  set 0 0           Drive PB5 LOW,  PB13 LOW\n");
	printk("  set 1 0           Drive PB5 HIGH, PB13 LOW\n");
	printk("  set 0 1           Drive PB5 LOW,  PB13 HIGH\n");
	printk("  set 1 1           Drive PB5 HIGH, PB13 HIGH\n");
	printk("  toggle pb5        Toggle TP7/PB5 only\n");
	printk("  toggle pb13       Toggle TP8/PB13 only\n");
	printk("  toggle both       Toggle PB5 and PB13 together\n");
	printk("\nMeasurement tips:\n");
	printk("  Meter black probe -> GND. Red probe -> TP7/PB5 or TP8/PB13.\n");
	printk("  Expected LOW is near 0 V. Expected HIGH is near 3.3 V.\n");
	printk("============================================================\n");
}

static int parse_level(const char *text, int *level)
{
	if (strcmp(text, "0") == 0 || strcmp(text, "low") == 0) {
		*level = 0;
		return 0;
	}

	if (strcmp(text, "1") == 0 || strcmp(text, "high") == 0) {
		*level = 1;
		return 0;
	}

	return -EINVAL;
}

static int execute_command(char *line)
{
	char *argv[4];
	int argc = 0;
	char *token;
	int level;
	int ret;

	for (token = strtok(line, " \t"); token != NULL && argc < ARRAY_SIZE(argv);
	     token = strtok(NULL, " \t")) {
		argv[argc++] = token;
	}

	if (argc == 0) {
		return 0;
	}

	printk("RX command: ");
	for (int i = 0; i < argc; i++) {
		printk("%s%s", i == 0 ? "" : " ", argv[i]);
	}
	printk("\n");

	(void)force_standby_high();

	if (strcmp(argv[0], "help") == 0 || strcmp(argv[0], "?") == 0) {
		print_help();
		print_status_detail("[status]");
		printk("OK: help\n");
		return 0;
	}

	if (strcmp(argv[0], "status") == 0 || strcmp(argv[0], "read") == 0) {
		print_status_detail("[status]");
		printk("OK: status\n");
		return 0;
	}

	if (strcmp(argv[0], "pb5") == 0 && argc == 2) {
		if (parse_level(argv[1], &level) == 0) {
			pb5_state = level;
			ret = apply_gpio_state("[pb5]");
			printk("%s: pb5 %d\n", ret == 0 ? "OK" : "ERROR", level);
			return ret;
		} else {
			printk("ERROR: pb5 value must be 0/1 or low/high\n");
			return -EINVAL;
		}
	}

	if (strcmp(argv[0], "pb13") == 0 && argc == 2) {
		if (parse_level(argv[1], &level) == 0) {
			pb13_state = level;
			ret = apply_gpio_state("[pb13]");
			printk("%s: pb13 %d\n", ret == 0 ? "OK" : "ERROR", level);
			return ret;
		} else {
			printk("ERROR: pb13 value must be 0/1 or low/high\n");
			return -EINVAL;
		}
	}

	if (strcmp(argv[0], "set") == 0 && argc == 3) {
		int pb5_level;
		int pb13_level;

		if (parse_level(argv[1], &pb5_level) == 0 &&
		    parse_level(argv[2], &pb13_level) == 0) {
			pb5_state = pb5_level;
			pb13_state = pb13_level;
			ret = apply_gpio_state("[set]");
			printk("%s: set %d %d\n", ret == 0 ? "OK" : "ERROR",
			       pb5_level, pb13_level);
			return ret;
		} else {
			printk("ERROR: set values must be 0/1 or low/high\n");
			return -EINVAL;
		}
	}

	if (strcmp(argv[0], "toggle") == 0 && argc == 2) {
		if (strcmp(argv[1], "pb5") == 0) {
			pb5_state = !pb5_state;
			ret = apply_gpio_state("[toggle pb5]");
			printk("%s: toggle pb5\n", ret == 0 ? "OK" : "ERROR");
			return ret;
		}

		if (strcmp(argv[1], "pb13") == 0) {
			pb13_state = !pb13_state;
			ret = apply_gpio_state("[toggle pb13]");
			printk("%s: toggle pb13\n", ret == 0 ? "OK" : "ERROR");
			return ret;
		}

		if (strcmp(argv[1], "both") == 0) {
			pb5_state = !pb5_state;
			pb13_state = !pb13_state;
			ret = apply_gpio_state("[toggle both]");
			printk("%s: toggle both\n", ret == 0 ? "OK" : "ERROR");
			return ret;
		}
	}

	printk("ERROR: unknown command: %s\n", argv[0]);
	printk("Type 'help' to print command format.\n");
	return -EINVAL;
}

static void uart_rx_callback(const struct device *dev, void *user_data)
{
	uint8_t c;

	ARG_UNUSED(user_data);

	if (!uart_irq_update(dev) || !uart_irq_rx_ready(dev)) {
		return;
	}

	while (uart_fifo_read(dev, &c, 1) == 1) {
		if (k_msgq_put(&uart_rx_msgq, &c, K_NO_WAIT) != 0) {
			rx_drop_count++;
		}
	}
}

static int setup_command_uart(void)
{
	int ret;

	if (!device_is_ready(command_uart)) {
		printk("ERROR: command UART device is not ready\n");
		return -ENODEV;
	}

	ret = uart_irq_callback_user_data_set(command_uart, uart_rx_callback, NULL);
	if (ret != 0) {
		printk("ERROR: set UART RX callback failed: %d\n", ret);
		return ret;
	}

	uart_irq_rx_enable(command_uart);
	return 0;
}

static void handle_received_byte(char *buffer, size_t *length,
				 uint32_t *last_rx_ms, uint8_t c)
{
	if (c == '\r' || c == '\n') {
		if (*length == 0) {
			return;
		}

		printk("\n");
		buffer[*length] = '\0';
		(void)execute_command(buffer);
		*length = 0;
		printk("cmd> ");
		return;
	}

	if (c == '\b' || c == 0x7f) {
		if (*length > 0) {
			(*length)--;
		}
		*last_rx_ms = k_uptime_get_32();
		return;
	}

	if (c < 0x20 || c > 0x7e) {
		return;
	}

	if (*length < COMMAND_BUFFER_SIZE - 1) {
		buffer[*length] = (char)c;
		(*length)++;
		*last_rx_ms = k_uptime_get_32();
	} else {
		printk("\nERROR: command too long\ncmd> ");
		*length = 0;
		*last_rx_ms = 0;
	}
}

static void process_command_uart(char *buffer, size_t *length,
				 uint32_t *last_rx_ms)
{
	uint8_t c;

	while (k_msgq_get(&uart_rx_msgq, &c, K_NO_WAIT) == 0) {
		handle_received_byte(buffer, length, last_rx_ms, c);
	}
}

static void execute_idle_command(char *buffer, size_t *length,
				 uint32_t last_rx_ms)
{
	uint32_t now_ms;

	if (*length == 0) {
		return;
	}

	now_ms = k_uptime_get_32();
	if ((int32_t)(now_ms - last_rx_ms) < COMMAND_IDLE_COMMIT_MS) {
		return;
	}

	printk("\n");
	buffer[*length] = '\0';
	(void)execute_command(buffer);
	*length = 0;
	printk("cmd> ");
}

int main(void)
{
	char command_buffer[COMMAND_BUFFER_SIZE];
	size_t command_length = 0;
	uint32_t next_idle_status_ms = k_uptime_get_32() + IDLE_STATUS_INTERVAL_MS;
	uint32_t last_rx_ms = 0;

	printk("\n");
	print_help();

	if (setup_command_uart() != 0) {
		return 0;
	}

	if (configure_output(&can_stb_pb14, 1, "CAN_STB/PB14") != 0 ||
	    configure_output(&tp7_pb5, 0, "TP7/PB5") != 0 ||
	    configure_output(&tp8_pb13, 0, "TP8/PB13") != 0) {
		printk("GPIO setup failed; test stopped.\n");
		return 0;
	}

	pb5_state = 0;
	pb13_state = 0;

	(void)apply_gpio_state("[initial]");
	printk("Ready. Type a command, then press Enter.\n");
	printk("Protocol: ASCII 115200 8N1, command end = CR/LF or 1 s RX idle timeout.\n");
	printk("cmd> ");

	while (true) {
		uint32_t now_ms;

		(void)force_standby_high();
		process_command_uart(command_buffer, &command_length, &last_rx_ms);
		execute_idle_command(command_buffer, &command_length, last_rx_ms);

		now_ms = k_uptime_get_32();
		if ((int32_t)(now_ms - next_idle_status_ms) >= 0) {
			print_status_compact("[heartbeat]");
			if (rx_drop_count != 0U) {
				printk("[uart] RX queue dropped %u byte(s)\n",
				       rx_drop_count);
				rx_drop_count = 0U;
			}
			next_idle_status_ms = now_ms + IDLE_STATUS_INTERVAL_MS;
			printk("cmd> ");
		}

		k_msleep(10);
	}

	return 0;
}
