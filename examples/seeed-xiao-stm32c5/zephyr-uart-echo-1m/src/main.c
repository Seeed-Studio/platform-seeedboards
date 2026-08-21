/*
 * Copyright (c) 2026 Seeed Technology Co., Ltd.
 * SPDX-License-Identifier: Apache-2.0
 *
 * UART max rate demo for XIAO STM32C5.
 * USART1 on PA9/PA10 is fixed to 1,000,000 bps by devicetree overlay.
 * Any received byte is echoed back as-is.
 */

#include <zephyr/device.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

/* The echo path is deliberately the physical 1 Mbps USART1 on PA9/PA10.
 * Console output remains on the board's USB CDC ACM device.
 */
#define UART_DEVICE_NODE DT_NODELABEL(usart1)

static const struct device *const uart_dev = DEVICE_DT_GET(UART_DEVICE_NODE);

static void serial_cb(const struct device *dev, void *user_data)
{
	ARG_UNUSED(dev);
	ARG_UNUSED(user_data);

	uint8_t c;

	if (!uart_irq_update(uart_dev) || !uart_irq_rx_ready(uart_dev)) {
		return;
	}

	while (uart_fifo_read(uart_dev, &c, 1) == 1) {
		while (uart_fifo_fill(uart_dev, &c, 1) != 1) {
		}
	}
}

int main(void)
{
	if (!device_is_ready(uart_dev)) {
		printk("UART device not ready\n");
		return 0;
	}

	printk("UART echo ready at 1000000 bps on PA9/PA10\n");

	uart_irq_callback_user_data_set(uart_dev, serial_cb, NULL);
	uart_irq_rx_enable(uart_dev);

	while (1) {
		k_msleep(1000);
	}

	return 0;
}
