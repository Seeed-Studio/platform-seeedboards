/*
 * Copyright (c) 2026 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

/**
 * @defgroup control_output Printing control output functions
 * @{
 * @ingroup ww_kws
 */

#ifndef __CONTROL_OUTPUT_H__
#define __CONTROL_OUTPUT_H__

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

/**
 * @brief Control message type.
 */
enum control_message_type {
	CONTROL_MESSAGE_WAITING_WW,
	CONTROL_MESSAGE_WW_DETECTED,

	CONTROL_MESSAGE_WAITING_KW,
	CONTROL_MESSAGE_KW_SPOTTED,
	CONTROL_MESSAGE_TIMEOUT_KWS,

	CONTROL_MESSAGE_COUNT
};

/**
 * @brief Control message.
 */
struct control_message {
	enum control_message_type type;
	uint16_t kw_class;
	const char *name;
};

/**
 * @brief Initialize control output backend.
 *
 * @return Operation status, 0 for success.
 */
int control_output_init(void);

/**
 * @brief Print the control messages to @c ncs_control_output_uart serial.
 *
 * @param message Control message to be printed.
 */
void print_control_output(const struct control_message message);

#ifdef __cplusplus
}
#endif /* __cplusplus */

#endif /* __CONTROL_OUTPUT_H__ */

/**
 * @}
 */
