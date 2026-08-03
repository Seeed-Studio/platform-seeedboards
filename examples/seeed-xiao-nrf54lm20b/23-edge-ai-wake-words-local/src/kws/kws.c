#include <assert.h>  /* for static_assert in the generated Axon model header */
/*
 * Copyright (c) 2026 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

#include <stddef.h>
#include <stdint.h>

#include <zephyr/logging/log.h>
#include <nrf_edgeai/nrf_edgeai.h>
#include <nrf_edgeai/rt/nrf_edgeai_runtime_aux.h>

#include "../dmic.h"
#include "kws.h"
#include "nrf_edgeai_generated/nrf_edgeai_user_model.h"

LOG_MODULE_REGISTER(kws);

/* Equal to 150 ms of audio. */
#define SKIP_DETECTIONS_COUNT 5

/* Classes predicted by keyword spotting model. The need to stay in sync with used model.
 * It will be subject to change how this classes are defined.
 */
enum keyword_class {
	KEYWORD_DOWN,
	KEYWORD_GO,
	KEYWORD_LEFT,
	KEYWORD_NO,
	KEYWORD_OFF,
	KEYWORD_ON,
	KEYWORD_RIGHT,
	KEYWORD_SILENCE,
	KEYWORD_STOP,
	KEYWORD_UNKNOWN,
	KEYWORD_UP,
	KEYWORD_YES,
	KEYWORDS_COUNT
};

struct keyword_detection_ctx {
	const char *name;
	const float threshold;
	const uint8_t num_in_row;
};

static const struct keyword_detection_ctx keyword_detection_ctxs[] = {
	[KEYWORD_DOWN] = {.name = "Down", .threshold = 0.9f, .num_in_row = 22},
	[KEYWORD_GO] = {.name = "Go", .threshold = 0.9f, .num_in_row = 22},
	[KEYWORD_LEFT] = {.name = "Left", .threshold = 0.9f, .num_in_row = 22},
	[KEYWORD_NO] = {.name = "No", .threshold = 0.9f, .num_in_row = 22},
	[KEYWORD_OFF] = {.name = "Off", .threshold = 0.9f, .num_in_row = 22},
	[KEYWORD_ON] = {.name = "On", .threshold = 0.9f, .num_in_row = 22},
	[KEYWORD_RIGHT] = {.name = "Right", .threshold = 0.9f, .num_in_row = 22},
	[KEYWORD_SILENCE] = {.name = "Silence", .threshold = 0.9f, .num_in_row = 22},
	[KEYWORD_STOP] = {.name = "Stop", .threshold = 0.9f, .num_in_row = 22},
	[KEYWORD_UNKNOWN] = {.name = "Unknown", .threshold = 0.9f, .num_in_row = 22},
	[KEYWORD_UP] = {.name = "Up", .threshold = 0.9f, .num_in_row = 22},
	[KEYWORD_YES] = {.name = "Yes", .threshold = 0.9f, .num_in_row = 22},
};

BUILD_ASSERT(KEYWORDS_COUNT == ARRAY_SIZE(keyword_detection_ctxs),
	     "Mismatch between keyword_class and keyword_detection_ctxs size");

static nrf_edgeai_t *kws_model;

int kws_init(void)
{
	kws_model = nrf_edgeai_user_model_kws();
	__ASSERT_NO_MSG(kws_model);
	__ASSERT_NO_MSG(nrf_edgeai_model_outputs_num(kws_model) == KEYWORDS_COUNT);
	__ASSERT_NO_MSG(nrf_edgeai_input_window_size(kws_model) == DMIC_SAMPLES_IN_BLOCK);

	nrf_edgeai_err_t err = nrf_edgeai_init(kws_model);

	if (err) {
		LOG_ERR("Model initialization failed (err %d)", err);
		return -ENOENT;
	}

	return 0;
}

static void kws_postprocess(struct kws_prediction *const prediction)
{
	prediction->valid = false;

	const float alpha = CONFIG_KWS_EMA_ALPHA / 1000.0f;
	static enum keyword_class last_class;
	static int count;

	/* Exponential moving average of class probability. */
	static float probability_ema;

	const uint16_t predicted_class = kws_model->decoded_output.classif.predicted_class;

	__ASSERT_NO_MSG(predicted_class < KEYWORDS_COUNT);

	const flt32_t class_probability =
		kws_model->decoded_output.classif.probabilities.p_f32[predicted_class];
	const struct keyword_detection_ctx *class_ctx = &keyword_detection_ctxs[predicted_class];

	if (predicted_class == KEYWORD_SILENCE || predicted_class == KEYWORD_UNKNOWN) {
		LOG_DBG("class: %s, prob: %f", class_ctx->name, (double)class_probability);
		count = 0;
		probability_ema = 0.0f;
		return;
	}

	if (predicted_class != last_class) {
		last_class = predicted_class;
		count = 0;
		probability_ema = 0.0f;
	}

	count++;
	probability_ema = alpha * class_probability + (1 - alpha) * probability_ema;

	LOG_DBG("class: %s, count %d, prob: %f, ema %f", class_ctx->name, count,
		(double)class_probability, (double)probability_ema);

	if (count >= class_ctx->num_in_row && probability_ema >= class_ctx->threshold) {
		prediction->valid = true;
		prediction->class = predicted_class;
		prediction->avg_probability = probability_ema;
		prediction->name = class_ctx->name;

		/* Skip detections to reduce double spotting. */
		count = -SKIP_DETECTIONS_COUNT;
		probability_ema = 0.0f;
	}
}

int kws_process(uint8_t *const audio_buffer, const uint16_t num_samples,
		struct kws_prediction *const prediction)
{
	__ASSERT_NO_MSG(audio_buffer);
	__ASSERT_NO_MSG(num_samples == nrf_edgeai_input_window_size(kws_model));
	__ASSERT_NO_MSG(prediction);

	nrf_edgeai_err_t err;

	err = nrf_edgeai_feed_inputs(kws_model, audio_buffer, num_samples);
	free_dmic_buffer(audio_buffer);

	if (err == NRF_EDGEAI_ERR_INPROGRESS) {
		/* Skip inference, not enough data. */
		return -EBUSY;
	} else if (err) {
		LOG_ERR("Failed to feed inputs (err %d)", err);
		return -EPERM;
	}

	err = nrf_edgeai_run_inference(kws_model);
	if (err == NRF_EDGEAI_ERR_INPROGRESS) {
		/* Skip output extraction, not enough data. */
		return -EBUSY;
	} else if (err) {
		LOG_ERR("Failed to run inference (err %d)", err);
		return -EPERM;
	}

	kws_postprocess(prediction);

	return 0;
}

void kws_reset(void)
{
	nrf_edgeai_model_axon_init_persistent_vars(kws_model);
}
