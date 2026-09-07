/*
 * Copyright (c) 2026 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

#ifndef DATA_FORWARDER_TRANSPORT_H_
#define DATA_FORWARDER_TRANSPORT_H_

#include "../protocol/protocol.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Initialize the selected transport and fill @p out_transport.
 *
 * The concrete backend is chosen at build time via @c CONFIG_DATA_FWD_TRANSPORT_*.
 *
 * @param[out] out_transport Populated with send callback and transport settings.
 *
 * @retval 0 Success.
 * @retval -EINVAL @p out_transport is @c NULL.
 * @retval -errno Negative error code on failure.
 */
int transport_init(struct proto_transport *out_transport);

#ifdef __cplusplus
}
#endif

#endif /* DATA_FORWARDER_TRANSPORT_H_ */

