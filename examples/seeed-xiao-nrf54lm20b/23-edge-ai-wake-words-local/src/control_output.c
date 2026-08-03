/*
 * Copyright (c) 2026 Nordic Semiconductor ASA
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 *
 * Local-only control output for the XIAO Edge AI wakeword/KWS sample.
 *
 * The upstream sample reported wakeword/keyword state over BLE Nordic UART
 * Service and a separate async UART. For the local-detection build (no
 * Bluetooth), we just log the state to the console (USB CDC), keeping the same
 * control_output API so main.c is unchanged.
 */

#include <stddef.h>

#include <zephyr/logging/log.h>

#include "control_output.h"

LOG_MODULE_REGISTER(control_output);

int control_output_init(void)
{
	return 0;
}

void print_control_output(const struct control_message message)
{
	switch (message.type) {
	case CONTROL_MESSAGE_WAITING_WW:
		LOG_INF("Waiting for wakeword");
		break;
	case CONTROL_MESSAGE_WW_DETECTED:
		LOG_INF("Wakeword detected");
		break;
	case CONTROL_MESSAGE_WAITING_KW:
		LOG_INF("Waiting for keywords");
		break;
	case CONTROL_MESSAGE_KW_SPOTTED:
		LOG_INF("Keyword spotted: %s", message.name ? message.name : "?");
		break;
	case CONTROL_MESSAGE_TIMEOUT_KWS:
		LOG_INF("Keyword spotting window timeout");
		break;
	default:
		break;
	}
}
