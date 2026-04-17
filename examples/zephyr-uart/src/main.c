/*
 * UART21 Demo for XIAO nRF54LM20A (Polling Mode)
 *
 * This demo shows how to use UART21 for serial communication using polling mode.
 * - TX: P1.8
 * - RX: P1.9
 * - Baud rate: 1000000
 *
 * The demo will:
 * 1. Send a welcome message on startup
 * 2. Echo back any received characters
 * 3. Periodically send a heartbeat message
 */

#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/logging/log.h>
#include <stdio.h>
#include <string.h>

LOG_MODULE_REGISTER(uart21_demo, LOG_LEVEL_INF);

/* UART21 device */
static const struct device *uart21_dev = DEVICE_DT_GET(DT_NODELABEL(uart21));

#define RX_BUF_SIZE 128
#define TX_BUF_SIZE 256
#define HEARTBEAT_INTERVAL_MS 5000

static uint8_t rx_buf[RX_BUF_SIZE];
static size_t rx_buf_pos = 0;
static char tx_buf[TX_BUF_SIZE];

/* Send a string over UART21 using polling */
static void uart21_send_string(const char *str)
{
	while (*str) {
		uart_poll_out(uart21_dev, *str++);
	}
}

/* Receive a character from UART21 (non-blocking) */
static int uart21_recv_char(uint8_t *c)
{
	return uart_poll_in(uart21_dev, c);
}

static void handle_complete_line(void)
{
	rx_buf[rx_buf_pos] = '\0';

	if (rx_buf_pos > 0) {
		LOG_INF("Received: %s", rx_buf);
		uart21_send_string("\r\nYou sent: ");
		uart21_send_string((const char *)rx_buf);
	}

	uart21_send_string("\r\n");
	rx_buf_pos = 0;
	memset(rx_buf, 0, sizeof(rx_buf));
}

/* Process a received byte and maintain a simple line buffer */
static void process_rx_byte(uint8_t c)
{
	static bool last_was_cr;

	if (c == '\r' || c == '\n') {
		if (c == '\n' && last_was_cr) {
			last_was_cr = false;
			return;
		}

		uart21_send_string("\r\n");
		handle_complete_line();
		last_was_cr = (c == '\r');
		return;
	}

	last_was_cr = false;
	uart_poll_out(uart21_dev, c);

	if (rx_buf_pos < RX_BUF_SIZE - 1) {
		rx_buf[rx_buf_pos++] = c;
		return;
	}

	uart21_send_string("\r\n[Warning] Input too long, buffer cleared.\r\n");
	rx_buf_pos = 0;
	memset(rx_buf, 0, sizeof(rx_buf));
}

int main(void)
{
	uint8_t c;
	uint32_t heartbeat_count = 0;
	int64_t last_heartbeat = 0;

	LOG_INF("========================================");
	LOG_INF("  UART21 Demo for XIAO nRF54LM20A");
	LOG_INF("========================================");
	LOG_INF("");

	/* Check if UART21 device is ready */
	if (!device_is_ready(uart21_dev)) {
		LOG_ERR("UART21 device not ready!");
		return -1;
	}
	LOG_INF("UART21 device ready: %s", uart21_dev->name);

	/* Send welcome message */
	uart21_send_string("\r\n");
	uart21_send_string("========================================\r\n");
	uart21_send_string("  UART21 Demo for XIAO nRF54LM20A\r\n");
	uart21_send_string("========================================\r\n");
	uart21_send_string("\r\n");
	uart21_send_string("Pin Configuration:\r\n");
	uart21_send_string("  TX: P1.8\r\n");
	uart21_send_string("  RX: P1.9\r\n");
	uart21_send_string("  Baud Rate: 1000000\r\n");
	uart21_send_string("\r\n");
	uart21_send_string("Type something and press Enter to see it echoed.\r\n");
	uart21_send_string("\r\n");

	LOG_INF("UART21 demo started. Waiting for data...");
	LOG_INF("Connect UART terminal to P1.8(TX) and P1.9(RX)");

	last_heartbeat = k_uptime_get();

	/* Main loop */
	while (1) {
		/* Check for received data */
		if (uart21_recv_char(&c) == 0) {
			process_rx_byte(c);
		}

		/* Check for heartbeat */
		int64_t now = k_uptime_get();
		if (now - last_heartbeat >= HEARTBEAT_INTERVAL_MS) {
			last_heartbeat = now;
			heartbeat_count++;

			snprintf(tx_buf, sizeof(tx_buf),
				"\r\n[Heartbeat #%u] UART21 running...\r\n",
				heartbeat_count);
			uart21_send_string(tx_buf);

			LOG_INF("Heartbeat #%u sent", heartbeat_count);
		}

		/* Small delay to prevent busy loop */
		k_msleep(10);
	}

	return 0;
}
