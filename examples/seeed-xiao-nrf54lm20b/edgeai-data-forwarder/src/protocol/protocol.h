/*
 * Copyright (c) 2026 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

#ifndef DATA_FORWARDER_PROTOCOL_H_
#define DATA_FORWARDER_PROTOCOL_H_

/**
 * @file
 * @defgroup data_fwd_protocol Data Forwarder Protocol
 * @ingroup sample_data_fwd
 * @{
 */

#include "protocol_types.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Transport callbacks used to send framed protocol messages.
 */
struct proto_transport {
	/** Send a buffer to the peer. Called from the protocol workqueue. */
	int (*send)(const uint8_t *buf, size_t len, void *ctx);
	/** Opaque context passed to @c send. */
	void *ctx;
	/**
	 * When false, payloads are COBS-encoded before @c send is called.
	 * Set true when the transport already delimits messages (for example BLE GATT).
	 */
	bool has_message_boundaries;
};

/**
 * @brief Session metadata included in periodic session-info messages.
 */
struct proto_session_config {
	/** Sampling rate in Hz. */
	uint16_t rate_hz;
	/** Number of data channels in each sample. */
	uint8_t channels;
	/** Application-defined sensor type identifier. */
	uint8_t sensor_type;
	/** Array of null-terminated channel name strings (up to 5 characters each). */
	const char *const *channel_names;
	/** Human-readable device name (up to 31 characters). */
	const char *device_name;
};

/**
 * @brief Initialize the data forwarder protocol layer.
 *
 * Stores @p transport, starts the internal workqueue on first call, and resets
 * session and sample state.
 *
 * @param transport Transport callbacks. Must not be @c NULL and must provide @c send.
 *
 * @retval 0 Success.
 * @retval -EINVAL @p transport or @p transport->send is @c NULL.
 */
int proto_init(const struct proto_transport *transport);

/**
 * @brief Start a new streaming session.
 *
 * Copies @p cfg, assigns a random session ID, and begins sending session-info messages.
 *
 * @param cfg Session configuration.
 *
 * @retval 0 Success.
 * @retval -EINVAL @p cfg is @c NULL or any field is invalid.
 * @retval -ENOMEM @c cfg->channels exceeds @c CONFIG_DATA_FWD_PROTO_MAX_CHANNELS.
 */
int proto_start_session(const struct proto_session_config *cfg);

/**
 * @brief Stop the current session.
 *
 * Stops session-info resends, clears the sample ring buffer, and drains pending protocol work.
 *
 * @retval 0 Success.
 */
int proto_stop_session(void);

/**
 * @brief Get the ID of the current or most recently started session.
 *
 * @return Session ID (random 32-bit value assigned at session start).
 */
uint32_t proto_get_session_id(void);

/**
 * @brief Enqueue sensor samples for transmission.
 *
 * Samples are encoded and sent asynchronously on the protocol workqueue.
 * If the ring buffer is full, the oldest sample is dropped and the drop
 * counter in session-info messages is incremented.
 *
 * @param values  Channel values (length @p count).
 * @param count   Number of values; must not exceed @c CONFIG_DATA_FWD_PROTO_MAX_CHANNELS.
 *
 * @retval 0 Success.
 * @retval -EACCES No session is active.
 * @retval -EINVAL @p values is @c NULL or @p count is zero or too large.
 * @retval -EFAULT Internal buffer was corrupted. @p values are dropped.
 */
int proto_send_samples(const proto_value_t *values, uint8_t count);

#ifdef __cplusplus
}
#endif

/**
 * @}
 */

#endif /* DATA_FORWARDER_PROTOCOL_H_ */

