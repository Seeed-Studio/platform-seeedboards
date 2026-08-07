/* 2026-05-05T13:20:38.840464 */

/*
* Copyright (c) 2026 Nordic Semiconductor ASA
* SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
*/

#ifndef _NRF_EDGEAI_USER_MODEL_WAKEWORD_H_
#define _NRF_EDGEAI_USER_MODEL_WAKEWORD_H_

#include <nrf_edgeai/rt/nrf_edgeai_types.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Get pointer to the Nordic Edge AI Lab model instance (@ref nrf_edgeai_t).
 */
nrf_edgeai_t* nrf_edgeai_user_model_wakeword(void);
/**
 * @brief Get size FLASH/ROM size of the Nordic Edge AI Neuton model.
 *
 * @warning This function is only valid for Neuton models. You can check the model type
 *          by inspecting the model context type field: p_edgeai->model.type == NRF_EDGEAI_MODEL_NEUTON
 * @return Size in bytes of the Neuton model.
 */
uint32_t nrf_edgeai_user_model_neuton_size_wakeword(void);

/**
 * @brief Alias for the Nordic Edge AI Lab user model API name.
 */
#ifndef nrf_edgeai_user_model
#define nrf_edgeai_user_model nrf_edgeai_user_model_wakeword
#endif

/**
 * @brief Alias for the Nordic Edge AI Lab user model neuton size API name.
 */
#ifndef nrf_edgeai_user_model_neuton_size
#define nrf_edgeai_user_model_neuton_size nrf_edgeai_user_model_neuton_size_wakeword
#endif

#ifdef __cplusplus
}
#endif

#endif /* _NRF_EDGEAI_USER_MODEL_WAKEWORD_H_ */
