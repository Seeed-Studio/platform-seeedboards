/* SPDX-License-Identifier: LicenseRef-Nordic-5-Clause */

#include "transport.h"

#include <zephyr/device.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(transport, CONFIG_LOG_DEFAULT_LEVEL);

static const struct device *uart_dev = DEVICE_DT_GET(DT_CHOSEN(ncs_data_forwarder_uart));
static int uart_send_cb(const uint8_t *buf, size_t len, void *ctx)
{
	ARG_UNUSED(ctx);
	if ((buf == NULL) || (len == 0U)) {
		return -EINVAL;
	}
	for (size_t i = 0; i < len; ++i) {
		uart_poll_out(uart_dev, buf[i]);
	}
	return 0;
}

int transport_init(struct proto_transport *out_transport)
{
	if (out_transport == NULL) {
		return -EINVAL;
	}

	if (!device_is_ready(uart_dev)) {
		return -ENODEV;
	}

	out_transport->send = uart_send_cb;
	out_transport->ctx = NULL;
	out_transport->has_message_boundaries = false;

	LOG_INF("USB CDC ACM Data Forwarder transport ready");
	return 0;
}

