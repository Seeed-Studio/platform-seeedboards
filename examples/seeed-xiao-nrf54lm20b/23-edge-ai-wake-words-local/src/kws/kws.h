/*
 * Copyright (c) 2026 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

/**
 * @defgroup kws Keyword spotting model functions
 * @{
 * @ingroup ww_kws
 */

#ifndef __KEYWORD_SPOTTING_H__
#define __KEYWORD_SPOTTING_H__

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

/**
 * @brief Prediction from keyword spotting model.
 */
struct kws_prediction {
	/** Prediction valid flag. */
	bool valid;
	/** Predicted class. */
	uint16_t class;
	/** Predicted class name. */
	const char *name;
	/** Average probability of multiple predictions. */
	float avg_probability;
};

/**
 * @brief Initialize keyword spotting model.
 *
 * @return Operation status, 0 for success.
 */
int kws_init(void);

/**
 * @brief Process audio data by keyword spotting model.
 *
 * @param audio_buffer Buffer of audio samples from @c dmic_read. Function takes ownership of
 * pointer.
 * @param num_samples Number of audio samples.
 * @param[out] prediction Result of keyword spotting.

 * @retval 0 Operation successful.
 * @retval -EPERM Operation failed on nRF Edge AI Lib level.
 * @retval -EBUSY Model needs more data.
 */
int kws_process(uint8_t *const audio_buffer, const uint16_t num_samples,
		struct kws_prediction *const prediction);

/**
 * @brief Reset keyword spotting model state.
 */
void kws_reset(void);

#ifdef __cplusplus
}
#endif /* __cplusplus */

#endif /* __KEYWORD_SPOTTING_H__ */

/**
 * @}
 */
