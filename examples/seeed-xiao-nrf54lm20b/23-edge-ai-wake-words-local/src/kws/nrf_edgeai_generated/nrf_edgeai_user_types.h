/*
* Copyright (c) 2026 Nordic Semiconductor ASA
* SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
*/

#ifndef _NRF_EDGEAI_USER_TYPES_H_
#define _NRF_EDGEAI_USER_TYPES_H_

#include <nrf_edgeai/nrf_edgeai_ctypes.h>

#ifdef   __cplusplus
extern "C"
{
#endif

typedef int16_t    nrf_user_input_t;
typedef int32_t    nrf_user_feature_t;
typedef flt32_t    nrf_user_output_t;
typedef uint8_t   nrf_user_coeff_t;
typedef int8_t    nrf_user_weight_t;
typedef nrf_user_coeff_t nrf_user_neuron_t;


#ifdef   __cplusplus
}
#endif

#endif /* _NRF_EDGEAI_USER_TYPES_H_ */
