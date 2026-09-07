/*
 * Copyright (c) 2026 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

#ifndef DATA_FORWARDER_PROTOCOL_TYPES_H_
#define DATA_FORWARDER_PROTOCOL_TYPES_H_

/**
 * @file
 * @addtogroup data_fwd_protocol
 * @{
 */

#include <stdint.h>

#if CONFIG_DATA_FWD_PROTO_INT32_VALUES
typedef int32_t proto_value_t;
#else
typedef float proto_value_t;
#endif

/**
 * @}
 */

#endif /* DATA_FORWARDER_PROTOCOL_TYPES_H_ */

