/*
 * Generated using zcbor version 0.9.1
 * https://github.com/NordicSemiconductor/zcbor
 * Generated with a --default-max-qty of 6
 */

#ifndef DATA_FORWARDER_ENCODE_H__
#define DATA_FORWARDER_ENCODE_H__

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>
#include "data_forwarder_encode_types.h"

#ifdef __cplusplus
extern "C" {
#endif

#if DEFAULT_MAX_QTY != 6
#error "The type file was generated with a different default_max_qty than this file"
#endif


int cbor_encode_envelope(
		uint8_t *payload, size_t payload_len,
		const struct envelope *input,
		size_t *payload_len_out);


#ifdef __cplusplus
}
#endif

#endif /* DATA_FORWARDER_ENCODE_H__ */
