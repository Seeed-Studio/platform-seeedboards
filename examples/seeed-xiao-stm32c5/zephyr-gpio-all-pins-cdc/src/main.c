/*
 * Copyright (c) 2026 Seeed Technology Co., Ltd.
 * SPDX-License-Identifier: Apache-2.0
 *
 * XIAO STM32C5 GPIO command test over USB CDC ACM.
 */

#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/ring_buffer.h>

#define GPIO_D0_NODE  DT_ALIAS(gpio_d0)
#define GPIO_D1_NODE  DT_ALIAS(gpio_d1)
#define GPIO_D2_NODE  DT_ALIAS(gpio_d2)
#define GPIO_D3_NODE  DT_ALIAS(gpio_d3)
#define GPIO_D4_NODE  DT_ALIAS(gpio_d4)
#define GPIO_D5_NODE  DT_ALIAS(gpio_d5)
#define GPIO_D6_NODE  DT_ALIAS(gpio_d6)
#define GPIO_D7_NODE  DT_ALIAS(gpio_d7)
#define GPIO_D8_NODE  DT_ALIAS(gpio_d8)
#define GPIO_D9_NODE  DT_ALIAS(gpio_d9)
#define GPIO_D10_NODE DT_ALIAS(gpio_d10)
#define GPIO_D11_NODE DT_ALIAS(gpio_d11)
#define GPIO_D12_NODE DT_ALIAS(gpio_d12)
#define GPIO_D13_NODE DT_ALIAS(gpio_d13)
#define GPIO_D14_NODE DT_ALIAS(gpio_d14)
#define GPIO_D15_NODE DT_ALIAS(gpio_d15)
#define GPIO_SWDIO_NODE DT_ALIAS(gpio_swdio)
#define GPIO_SWCLK_NODE DT_ALIAS(gpio_swclk)
#define GPIO_BOOT0_NODE DT_ALIAS(gpio_boot0)

#define CDC_NODE DT_COMPAT_GET_ANY_STATUS_OKAY(zephyr_cdc_acm_uart)

#define PIN_COUNT 19
#define CAN_STB_PIN_INDEX 15
#define COMMAND_BUFFER_SIZE 96
#define UART_RX_QUEUE_SIZE 256
#define UART_TX_RING_BUF_SIZE 8192
#define COMMAND_IDLE_COMMIT_MS 1000
#define HEARTBEAT_INTERVAL_MS 5000
#define DEFAULT_WALK_DELAY_MS 500

BUILD_ASSERT(DT_NODE_HAS_STATUS(GPIO_D0_NODE, okay), "gpio-d0 alias missing");
BUILD_ASSERT(DT_NODE_HAS_STATUS(GPIO_D1_NODE, okay), "gpio-d1 alias missing");
BUILD_ASSERT(DT_NODE_HAS_STATUS(GPIO_D2_NODE, okay), "gpio-d2 alias missing");
BUILD_ASSERT(DT_NODE_HAS_STATUS(GPIO_D3_NODE, okay), "gpio-d3 alias missing");
BUILD_ASSERT(DT_NODE_HAS_STATUS(GPIO_D4_NODE, okay), "gpio-d4 alias missing");
BUILD_ASSERT(DT_NODE_HAS_STATUS(GPIO_D5_NODE, okay), "gpio-d5 alias missing");
BUILD_ASSERT(DT_NODE_HAS_STATUS(GPIO_D6_NODE, okay), "gpio-d6 alias missing");
BUILD_ASSERT(DT_NODE_HAS_STATUS(GPIO_D7_NODE, okay), "gpio-d7 alias missing");
BUILD_ASSERT(DT_NODE_HAS_STATUS(GPIO_D8_NODE, okay), "gpio-d8 alias missing");
BUILD_ASSERT(DT_NODE_HAS_STATUS(GPIO_D9_NODE, okay), "gpio-d9 alias missing");
BUILD_ASSERT(DT_NODE_HAS_STATUS(GPIO_D10_NODE, okay), "gpio-d10 alias missing");
BUILD_ASSERT(DT_NODE_HAS_STATUS(GPIO_D11_NODE, okay), "gpio-d11 alias missing");
BUILD_ASSERT(DT_NODE_HAS_STATUS(GPIO_D12_NODE, okay), "gpio-d12 alias missing");
BUILD_ASSERT(DT_NODE_HAS_STATUS(GPIO_D13_NODE, okay), "gpio-d13 alias missing");
BUILD_ASSERT(DT_NODE_HAS_STATUS(GPIO_D14_NODE, okay), "gpio-d14 alias missing");
BUILD_ASSERT(DT_NODE_HAS_STATUS(GPIO_D15_NODE, okay), "gpio-d15 alias missing");
BUILD_ASSERT(DT_NODE_HAS_STATUS(GPIO_SWDIO_NODE, okay), "gpio-swdio alias missing");
BUILD_ASSERT(DT_NODE_HAS_STATUS(GPIO_SWCLK_NODE, okay), "gpio-swclk alias missing");
BUILD_ASSERT(DT_NODE_HAS_STATUS(GPIO_BOOT0_NODE, okay), "gpio-boot0 alias missing");
BUILD_ASSERT(DT_NODE_HAS_STATUS(CDC_NODE, okay), "USB CDC ACM UART missing");

static const struct device *const cdc_dev = DEVICE_DT_GET(CDC_NODE);

static const struct gpio_dt_spec pins[PIN_COUNT] = {
	GPIO_DT_SPEC_GET(GPIO_D0_NODE, gpios),
	GPIO_DT_SPEC_GET(GPIO_D1_NODE, gpios),
	GPIO_DT_SPEC_GET(GPIO_D2_NODE, gpios),
	GPIO_DT_SPEC_GET(GPIO_D3_NODE, gpios),
	GPIO_DT_SPEC_GET(GPIO_D4_NODE, gpios),
	GPIO_DT_SPEC_GET(GPIO_D5_NODE, gpios),
	GPIO_DT_SPEC_GET(GPIO_D6_NODE, gpios),
	GPIO_DT_SPEC_GET(GPIO_D7_NODE, gpios),
	GPIO_DT_SPEC_GET(GPIO_D8_NODE, gpios),
	GPIO_DT_SPEC_GET(GPIO_D9_NODE, gpios),
	GPIO_DT_SPEC_GET(GPIO_D10_NODE, gpios),
	GPIO_DT_SPEC_GET(GPIO_D11_NODE, gpios),
	GPIO_DT_SPEC_GET(GPIO_D12_NODE, gpios),
	GPIO_DT_SPEC_GET(GPIO_D13_NODE, gpios),
	GPIO_DT_SPEC_GET(GPIO_D14_NODE, gpios),
	GPIO_DT_SPEC_GET(GPIO_D15_NODE, gpios),
	GPIO_DT_SPEC_GET(GPIO_SWDIO_NODE, gpios),
	GPIO_DT_SPEC_GET(GPIO_SWCLK_NODE, gpios),
	GPIO_DT_SPEC_GET(GPIO_BOOT0_NODE, gpios),
};

static const char *const pin_names[PIN_COUNT] = {
	"D0", "D1", "D2", "D3", "D4", "D5", "D6", "D7",
	"D8", "D9", "D10", "D11", "D12", "D13", "D14", "D15",
	"SWDIO", "SWCLK", "BOOT0",
};

static const char *const pin_mcu_names[PIN_COUNT] = {
	"PA0", "PA1", "PA2", "PA3", "PB7", "PB6", "PA9", "PA10",
	"PA15", "PB0", "PB15", "PB8", "PB9", "PB5", "PB13", "PB14",
	"PA13", "PA14", "PH2",
};

static const char *const pin_notes[PIN_COUNT] = {
	"ADC1_IN0",
	"ADC1_IN1",
	"ADC1_IN2",
	"ADC1_IN3",
	"I2C1_SDA",
	"I2C1_SCL",
	"USART1_TX",
	"USART1_RX",
	"GPIO",
	"GPIO",
	"GPIO",
	"FDCAN1_RX",
	"FDCAN1_TX",
	"FDCAN2_RX",
	"FDCAN2_TX",
	"CAN_STB",
	"SWDIO debug pad, GPIO test disables SWD while app runs",
	"SWCLK debug pad, GPIO test disables SWD while app runs",
	"BOOT0 pad, affects boot mode if held HIGH during reset",
};

K_MSGQ_DEFINE(cdc_rx_msgq, sizeof(uint8_t), UART_RX_QUEUE_SIZE, 4);

static uint8_t tx_ring_buffer[UART_TX_RING_BUF_SIZE];
static struct ring_buf tx_ringbuf;
static int pin_state[PIN_COUNT];
static uint32_t cmd_count;
static uint32_t rx_bytes;
static uint32_t rx_drop_count;
static uint32_t tx_bytes;
static uint32_t tx_drop_count;

static uint32_t cdc_tx_put(const uint8_t *buf, uint32_t len)
{
	uint32_t key;
	uint32_t stored;

	key = irq_lock();
	stored = ring_buf_put(&tx_ringbuf, buf, len);
	if (stored < len) {
		tx_drop_count += len - stored;
	}
	irq_unlock(key);

	if (stored > 0U) {
		uart_irq_tx_enable(cdc_dev);
	}

	return stored;
}

static void cdc_puts(const char *s)
{
	(void)cdc_tx_put((const uint8_t *)s, strlen(s));
}

static void cdc_printf(const char *fmt, ...)
{
	char buf[192];
	va_list args;
	int len;

	va_start(args, fmt);
	len = vsnprintf(buf, sizeof(buf), fmt, args);
	va_end(args);

	if (len < 0) {
		return;
	}

	if (len >= (int)sizeof(buf)) {
		len = sizeof(buf) - 1;
	}

	(void)cdc_tx_put((const uint8_t *)buf, (uint32_t)len);
}

static void str_to_lower(char *text)
{
	while (*text != '\0') {
		if (*text >= 'A' && *text <= 'Z') {
			*text = *text - 'A' + 'a';
		}
		text++;
	}
}

static int parse_pin(const char *text)
{
	char *endptr;
	long value;

	if (strcmp(text, "swdio") == 0 || strcmp(text, "pa13") == 0) {
		return 16;
	}

	if (strcmp(text, "swclk") == 0 || strcmp(text, "pa14") == 0) {
		return 17;
	}

	if (strcmp(text, "boot0") == 0 || strcmp(text, "boot") == 0 ||
	    strcmp(text, "ph2") == 0) {
		return 18;
	}

	if (text[0] == 'd') {
		text++;
	}

	if (*text == '\0') {
		return -EINVAL;
	}

	value = strtol(text, &endptr, 10);
	if (*endptr != '\0' || value < 0 || value >= PIN_COUNT) {
		return -EINVAL;
	}

	return (int)value;
}

static int parse_level(const char *text, int *level)
{
	if (strcmp(text, "0") == 0 || strcmp(text, "low") == 0 ||
	    strcmp(text, "l") == 0) {
		*level = 0;
		return 0;
	}

	if (strcmp(text, "1") == 0 || strcmp(text, "high") == 0 ||
	    strcmp(text, "h") == 0) {
		*level = 1;
		return 0;
	}

	return -EINVAL;
}

static int set_pin_state(int pin, int value)
{
	int ret;

	if (pin < 0 || pin >= PIN_COUNT) {
		return -EINVAL;
	}

	ret = gpio_pin_set_dt(&pins[pin], value);
	if (ret != 0) {
		cdc_printf("ERROR: set %s/%s=%d failed: %d\r\n",
			   pin_names[pin], pin_mcu_names[pin], value, ret);
		return ret;
	}

	pin_state[pin] = value;
	return 0;
}

static int configure_all_pins(void)
{
	for (int i = 0; i < PIN_COUNT; i++) {
		int initial = (i == CAN_STB_PIN_INDEX) ? 1 : 0;
		int ret;

		if (!gpio_is_ready_dt(&pins[i])) {
			cdc_printf("ERROR: %s/%s GPIO controller is not ready\r\n",
				   pin_names[i], pin_mcu_names[i]);
			return -ENODEV;
		}

		ret = gpio_pin_configure_dt(&pins[i],
					    initial ? GPIO_OUTPUT_ACTIVE :
					    GPIO_OUTPUT_INACTIVE);
		if (ret != 0) {
			cdc_printf("ERROR: configure %s/%s failed: %d\r\n",
				   pin_names[i], pin_mcu_names[i], ret);
			return ret;
		}

		pin_state[i] = initial;
	}

	return 0;
}

static int set_all_pins(int value)
{
	for (int i = 0; i < PIN_COUNT; i++) {
		int ret = set_pin_state(i, value);

		if (ret != 0) {
			return ret;
		}
	}

	return 0;
}

static int set_safe_idle_state(void)
{
	for (int i = 0; i < PIN_COUNT; i++) {
		int value = (i == CAN_STB_PIN_INDEX) ? 1 : 0;
		int ret = set_pin_state(i, value);

		if (ret != 0) {
			return ret;
		}
	}

	return 0;
}

static int print_pin_line(int start, int end)
{
	for (int i = start; i <= end; i++) {
		int read = gpio_pin_get_dt(&pins[i]);

		if (read < 0) {
			cdc_printf("%s=%d(read ERR%d) ", pin_names[i],
				   pin_state[i], read);
		} else {
			cdc_printf("%s=%d(read %d) ", pin_names[i],
				   pin_state[i], read);
		}
	}
	cdc_puts("\r\n");
	return 0;
}

static void print_status(const char *prefix)
{
	cdc_printf("%s D0-D7:  ", prefix);
	(void)print_pin_line(0, 7);
	cdc_printf("%s D8-D15: ", prefix);
	(void)print_pin_line(8, 15);
	cdc_printf("%s EXT:    ", prefix);
	(void)print_pin_line(16, PIN_COUNT - 1);
}

static void print_map(void)
{
	cdc_puts("\r\nPin map:\r\n");
	for (int i = 0; i < PIN_COUNT; i++) {
		cdc_printf("  %s -> %s / %s\r\n",
			   pin_names[i], pin_mcu_names[i], pin_notes[i]);
	}
}

static void print_help(void)
{
	cdc_puts("\r\n");
	cdc_puts("============================================================\r\n");
	cdc_puts("  XIAO STM32C5 GPIO All Pins Test over USB CDC\r\n");
	cdc_puts("============================================================\r\n");
	cdc_puts("Purpose:\r\n");
	cdc_puts("  Verify XIAO D0-D15 plus SWDIO/SWCLK/BOOT0 pads can be driven independently.\r\n");
	cdc_puts("  USB CDC is the command/log port; PA11/PA12 stay as USB DM/DP.\r\n");
	cdc_puts("  CANH/CANL are CAN transceiver bus pins, not MCU GPIO; RESET/NRST is not GPIO.\r\n");
	cdc_puts("\r\nDefault state:\r\n");
	cdc_puts("  D0-D14, SWDIO, SWCLK, BOOT0 = LOW. D15/PB14/CAN_STB = HIGH.\r\n");
	cdc_puts("  Warning: driving SWDIO/SWCLK as GPIO disables SWD debug access while this app runs.\r\n");
	cdc_puts("  Warning: BOOT0 HIGH during reset can change boot mode.\r\n");
	cdc_puts("\r\nIO target range:\r\n");
	cdc_puts("  Header pins: D0-D15\r\n");
	cdc_puts("  Extra pads:  SWDIO/PA13, SWCLK/PA14, BOOT0/PH2\r\n");
	cdc_puts("  Numeric IDs: 0-18 map to D0-D15, SWDIO, SWCLK, BOOT0\r\n");
	cdc_puts("  Accepted pin names: d0..d15, 0..18, swdio/pa13, swclk/pa14, boot0/boot/ph2\r\n");
	cdc_puts("  Levels: 0/1, low/high, l/h\r\n");
	cdc_puts("\r\nCommand format:\r\n");
	cdc_puts("  <command> [pin] [level]\r\n");
	cdc_puts("  End command with Enter, CR/LF, or 1 s RX idle timeout.\r\n");
	cdc_puts("\r\nCommands:\r\n");
	cdc_puts("  help                 Print this help\r\n");
	cdc_puts("  map                  Print pin to MCU pad mapping\r\n");
	cdc_puts("  status               Print expected/readback level for all pins\r\n");
	cdc_puts("  set d0 1             Drive one pin HIGH\r\n");
	cdc_puts("  set d0 0             Drive one pin LOW\r\n");
	cdc_puts("  set swdio 1          Drive SWDIO/PA13 HIGH\r\n");
	cdc_puts("  set swclk 1          Drive SWCLK/PA14 HIGH\r\n");
	cdc_puts("  set boot0 1          Drive BOOT0/PH2 HIGH\r\n");
	cdc_puts("  toggle d0            Toggle one pin\r\n");
	cdc_puts("  solo d0              D0 HIGH, others LOW, D15 HIGH\r\n");
	cdc_puts("  solo d15 0           Drive only D15/CAN_STB LOW for measurement\r\n");
	cdc_puts("  all 0                Drive all tested GPIOs LOW\r\n");
	cdc_puts("  all 1                Drive all tested GPIOs HIGH\r\n");
	cdc_puts("  idle                 Restore safe idle state\r\n");
	cdc_puts("  walk 500             Step each pin with 500 ms delay\r\n");
	cdc_puts("\r\nMeasurement tips:\r\n");
	cdc_puts("  Meter black probe -> GND. Red probe -> target D/EXT pad.\r\n");
	cdc_puts("  Expected LOW is near 0 V. Expected HIGH is near 3.3 V.\r\n");
	cdc_puts("============================================================\r\n");
}

static int execute_walk(int delay_ms)
{
	if (delay_ms <= 0) {
		delay_ms = DEFAULT_WALK_DELAY_MS;
	}

	cdc_printf("OK: walk start, delay=%d ms\r\n", delay_ms);

	for (int i = 0; i < PIN_COUNT; i++) {
		int ret;

		ret = set_safe_idle_state();
		if (ret != 0) {
			return ret;
		}

		if (i == CAN_STB_PIN_INDEX) {
			cdc_puts("[walk] D15/PB14/CAN_STB -> LOW\r\n");
			ret = set_pin_state(i, 0);
		} else {
			cdc_printf("[walk] %s/%s -> HIGH\r\n",
				   pin_names[i], pin_mcu_names[i]);
			ret = set_pin_state(i, 1);
		}

		if (ret != 0) {
			return ret;
		}

		print_status("[walk]");
		k_msleep(delay_ms);
	}

	(void)set_safe_idle_state();
	cdc_puts("OK: walk complete, safe idle restored\r\n");
	print_status("[status]");
	return 0;
}

static int execute_command(char *line)
{
	char *argv[4];
	char *token;
	int argc = 0;
	int pin;
	int level;
	int ret;

	str_to_lower(line);

	for (token = strtok(line, " \t"); token != NULL && argc < ARRAY_SIZE(argv);
	     token = strtok(NULL, " \t")) {
		argv[argc++] = token;
	}

	if (argc == 0) {
		return 0;
	}

	cmd_count++;

	cdc_puts("\r\nRX command:");
	for (int i = 0; i < argc; i++) {
		cdc_printf(" %s", argv[i]);
	}
	cdc_puts("\r\n");

	if (strcmp(argv[0], "help") == 0 || strcmp(argv[0], "?") == 0) {
		print_help();
		cdc_puts("OK: help\r\n");
		return 0;
	}

	if (strcmp(argv[0], "map") == 0) {
		print_map();
		cdc_puts("OK: map\r\n");
		return 0;
	}

	if (strcmp(argv[0], "status") == 0 || strcmp(argv[0], "read") == 0) {
		print_status("[status]");
		cdc_puts("OK: status\r\n");
		return 0;
	}

	if (strcmp(argv[0], "idle") == 0) {
		ret = set_safe_idle_state();
		print_status("[idle]");
		cdc_printf("%s: idle\r\n", ret == 0 ? "OK" : "ERROR");
		return ret;
	}

	if (strcmp(argv[0], "set") == 0 && argc == 3) {
		pin = parse_pin(argv[1]);
		if (pin < 0 || parse_level(argv[2], &level) != 0) {
			cdc_puts("ERROR: usage: set d0 0|1\r\n");
			return -EINVAL;
		}

		ret = set_pin_state(pin, level);
		print_status("[set]");
		cdc_printf("%s: set %s %d\r\n", ret == 0 ? "OK" : "ERROR",
			   pin_names[pin], level);
		return ret;
	}

	if (strcmp(argv[0], "toggle") == 0 && argc == 2) {
		pin = parse_pin(argv[1]);
		if (pin < 0) {
			cdc_puts("ERROR: usage: toggle d0\r\n");
			return -EINVAL;
		}

		ret = set_pin_state(pin, !pin_state[pin]);
		print_status("[toggle]");
		cdc_printf("%s: toggle %s -> %d\r\n",
			   ret == 0 ? "OK" : "ERROR",
			   pin_names[pin], pin_state[pin]);
		return ret;
	}

	if (strcmp(argv[0], "solo") == 0 && (argc == 2 || argc == 3)) {
		pin = parse_pin(argv[1]);
		if (pin < 0) {
			cdc_puts("ERROR: usage: solo d0 [0|1]\r\n");
			return -EINVAL;
		}

		level = 1;
		if (argc == 3 && parse_level(argv[2], &level) != 0) {
			cdc_puts("ERROR: usage: solo d0 [0|1]\r\n");
			return -EINVAL;
		}

		ret = set_safe_idle_state();
		if (ret == 0) {
			ret = set_pin_state(pin, level);
		}
		print_status("[solo]");
		cdc_printf("%s: solo %s %d\r\n", ret == 0 ? "OK" : "ERROR",
			   pin_names[pin], level);
		return ret;
	}

	if (strcmp(argv[0], "all") == 0 && argc == 2) {
		if (parse_level(argv[1], &level) != 0) {
			cdc_puts("ERROR: usage: all 0|1\r\n");
			return -EINVAL;
		}

		ret = set_all_pins(level);
		print_status("[all]");
		cdc_printf("%s: all %d\r\n", ret == 0 ? "OK" : "ERROR", level);
		return ret;
	}

	if (strcmp(argv[0], "walk") == 0 && argc <= 2) {
		int delay_ms = DEFAULT_WALK_DELAY_MS;

		if (argc == 2) {
			delay_ms = atoi(argv[1]);
			if (delay_ms <= 0 || delay_ms > 10000) {
				cdc_puts("ERROR: walk delay must be 1..10000 ms\r\n");
				return -EINVAL;
			}
		}

		return execute_walk(delay_ms);
	}

	cdc_printf("ERROR: unknown command: %s\r\n", argv[0]);
	cdc_puts("Type 'help' to print command format.\r\n");
	return -EINVAL;
}

static void cdc_irq_callback(const struct device *dev, void *user_data)
{
	uint8_t buf[64];
	int len;

	ARG_UNUSED(user_data);

	while (uart_irq_update(dev) && uart_irq_is_pending(dev)) {
		if (uart_irq_rx_ready(dev)) {
			len = uart_fifo_read(dev, buf, sizeof(buf));
			for (int i = 0; i < len; i++) {
				rx_bytes++;
				if (k_msgq_put(&cdc_rx_msgq, &buf[i],
					       K_NO_WAIT) != 0) {
					rx_drop_count++;
				}
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

static int setup_cdc(void)
{
	int ret;

	if (!device_is_ready(cdc_dev)) {
		return -ENODEV;
	}

	ring_buf_init(&tx_ringbuf, sizeof(tx_ring_buffer), tx_ring_buffer);

	(void)uart_line_ctrl_set(cdc_dev, UART_LINE_CTRL_DCD, 1);
	(void)uart_line_ctrl_set(cdc_dev, UART_LINE_CTRL_DSR, 1);

	ret = uart_irq_callback_user_data_set(cdc_dev, cdc_irq_callback, NULL);
	if (ret != 0) {
		return ret;
	}

	uart_irq_rx_enable(cdc_dev);
	return 0;
}

static void handle_received_byte(char *buffer, size_t *length,
				 uint32_t *last_rx_ms, uint8_t c)
{
	if (c == '\r' || c == '\n') {
		if (*length == 0) {
			return;
		}

		buffer[*length] = '\0';
		(void)execute_command(buffer);
		*length = 0;
		cdc_puts("cmd> ");
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
		cdc_puts("\r\nERROR: command too long\r\ncmd> ");
		*length = 0;
		*last_rx_ms = 0;
	}
}

static void process_cdc_rx(char *buffer, size_t *length, uint32_t *last_rx_ms)
{
	uint8_t c;

	while (k_msgq_get(&cdc_rx_msgq, &c, K_NO_WAIT) == 0) {
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

	buffer[*length] = '\0';
	(void)execute_command(buffer);
	*length = 0;
	cdc_puts("cmd> ");
}

static void print_heartbeat(uint32_t dtr, uint32_t baud)
{
	cdc_printf("[heartbeat] dtr=%u baud=%u cmd=%u rx=%u rx_drop=%u tx=%u tx_drop=%u\r\n",
		   dtr, baud, cmd_count, rx_bytes, rx_drop_count, tx_bytes,
		   tx_drop_count);
	cdc_puts("[heartbeat] Type 'help' for IO range and command format.\r\n");
	print_status("[heartbeat]");
	cdc_puts("cmd> ");
}

int main(void)
{
	char command_buffer[COMMAND_BUFFER_SIZE];
	size_t command_length = 0;
	uint32_t last_rx_ms = 0;
	uint32_t next_heartbeat_ms = k_uptime_get_32() + HEARTBEAT_INTERVAL_MS;
	uint32_t dtr = 0;
	uint32_t prev_dtr = 0;
	uint32_t baud = 0;
	bool gpio_ready = false;

	if (setup_cdc() != 0) {
		return 0;
	}

	print_help();
	print_map();

	if (configure_all_pins() == 0) {
		gpio_ready = true;
		cdc_puts("GPIO setup complete.\r\n");
	} else {
		cdc_puts("GPIO setup failed; commands may fail.\r\n");
	}

	print_status("[initial]");
	cdc_puts("Ready. Type a command, then press Enter.\r\n");
	cdc_puts("Protocol: USB CDC ACM ASCII, command end = CR/LF or 1 s RX idle timeout.\r\n");
	cdc_puts("cmd> ");

	while (true) {
		uint32_t now_ms;

		(void)uart_line_ctrl_get(cdc_dev, UART_LINE_CTRL_DTR, &dtr);
		(void)uart_line_ctrl_get(cdc_dev, UART_LINE_CTRL_BAUD_RATE, &baud);

		if (dtr != 0U && prev_dtr == 0U) {
			cdc_puts("\r\nUSB CDC port open. Type 'help' for command format.\r\n");
			print_status("[initial]");
			cdc_puts("cmd> ");
			next_heartbeat_ms = k_uptime_get_32() + HEARTBEAT_INTERVAL_MS;
		}

		prev_dtr = dtr;

		process_cdc_rx(command_buffer, &command_length, &last_rx_ms);
		execute_idle_command(command_buffer, &command_length, last_rx_ms);

		now_ms = k_uptime_get_32();
		if (gpio_ready && (int32_t)(now_ms - next_heartbeat_ms) >= 0) {
			print_heartbeat(dtr, baud);
			next_heartbeat_ms = now_ms + HEARTBEAT_INTERVAL_MS;
		}

		k_msleep(10);
	}

	return 0;
}
