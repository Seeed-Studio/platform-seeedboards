/* SPDX-License-Identifier: LicenseRef-Nordic-5-Clause */

#include "offline_images.h"
#include "postprocessing.h"

#include <assert.h>
#include <stdint.h>
#include <string.h>

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

#include <axon/nrf_axon_platform.h>
#include <drivers/axon/nrf_axon_driver.h>
#include <drivers/axon/nrf_axon_nn_infer.h>

#include "generated/nrf_axon_model_person_det_.h"

LOG_MODULE_REGISTER(main);

/* The official model consumes 160 x 128 planar RGB data.  A 128 x 128 source
 * image is centred horizontally and the remaining pixels are neutral grey.
 */
#define CAM_WIDTH  OFFLINE_IMAGE_WIDTH
#define CAM_HEIGHT OFFLINE_IMAGE_HEIGHT
#define MODEL_WIDTH 160
#define MODEL_HEIGHT 128
#define PAD_LEFT ((MODEL_WIDTH - CAM_WIDTH) / 2)
#define PAD_TOP ((MODEL_HEIGHT - CAM_HEIGHT) / 2)

#define LUT_SIZE_5_BITS 32
#define LUT_SIZE_6_BITS 64
#define MAX_BOXES_LOG 8

static int8_t input_buf[MODEL_WIDTH * MODEL_HEIGHT * 3];
static int8_t output_buf[NRF_AXON_MODEL_PERSON_DET_PACKED_OUTPUT_SIZE];
static int8_t lut_red_blue[LUT_SIZE_5_BITS];
static int8_t lut_green[LUT_SIZE_6_BITS];

static inline int8_t quantize(const float value, const nrf_axon_nn_compiled_model_input_s *in)
{
	const float scale = (float)in->quant_mult / (float)(1 << in->quant_round);
	const int32_t quantized = (int32_t)(value * scale) + in->quant_zp;

	/* Saturate to signed 8-bit (replaces the CMSIS __ssat intrinsic, which the
	 * XIAO main.c cannot rely on being declared under this toolchain). */
	int32_t sat = quantized;
	if (sat > 127) {
		sat = 127;
	} else if (sat < -128) {
		sat = -128;
	}
	return (int8_t)sat;
}

static void prefill_input_buf(const nrf_axon_nn_compiled_model_input_s *in)
{
	/* In the model's symmetric [-1, 1] input space, zero is neutral grey. */
	memset(input_buf, quantize(0.0f, in), sizeof(input_buf));
}

static void prefill_luts(const nrf_axon_nn_compiled_model_input_s *in)
{
	for (size_t i = 0; i < ARRAY_SIZE(lut_red_blue); i++) {
		const float normalized = (float)i / 32.0f;

		lut_red_blue[i] = quantize((normalized * 2.0f) - 1.0f, in);
	}

	for (size_t i = 0; i < ARRAY_SIZE(lut_green); i++) {
		const float normalized = (float)i / 64.0f;

		lut_green[i] = quantize((normalized * 2.0f) - 1.0f, in);
	}
}

static inline uint16_t extract_pixel(const uint8_t *data, size_t pixel)
{
	const size_t offset = pixel * 2;

	return (uint16_t)((uint16_t)data[offset] << 8 | data[offset + 1]);
}

static void convert_image_to_model_input(const uint8_t *rgb565_be)
{
	for (size_t pixel_idx = 0; pixel_idx < CAM_WIDTH * CAM_HEIGHT; pixel_idx++) {
		const size_t cam_row = pixel_idx / CAM_WIDTH;
		const size_t cam_col = pixel_idx % CAM_WIDTH;
		const size_t dst_offset = (PAD_TOP + cam_row) * MODEL_WIDTH + PAD_LEFT + cam_col;
		const uint16_t pixel = extract_pixel(rgb565_be, pixel_idx);
		const uint8_t r5 = (pixel >> 11) & 0x1f;
		const uint8_t g6 = (pixel >> 5) & 0x3f;
		const uint8_t b5 = pixel & 0x1f;

		input_buf[0 * MODEL_WIDTH * MODEL_HEIGHT + dst_offset] = lut_red_blue[r5];
		input_buf[1 * MODEL_WIDTH * MODEL_HEIGHT + dst_offset] = lut_green[g6];
		input_buf[2 * MODEL_WIDTH * MODEL_HEIGHT + dst_offset] = lut_red_blue[b5];
	}
}

static void log_bounding_boxes(const struct detection_box *boxes, size_t count)
{
	for (size_t i = 0; i < count; i++) {
		LOG_INF("Box %u: head %s, [%.1f, %.1f, %.1f, %.1f], confidence %.3f",
			(unsigned int)i, model_head_name(boxes[i].head_id), (double)boxes[i].x1,
			(double)boxes[i].y1, (double)boxes[i].x2, (double)boxes[i].y2,
			(double)boxes[i].score);
	}
}

static int infer_offline_image(const struct offline_image *image,
			       const nrf_axon_nn_compiled_model_s *model,
			       const nrf_axon_nn_compiled_model_input_s *model_input)
{
	struct detection_box boxes[MAX_BOXES_LOG];
	nrf_axon_result_e result;

	LOG_INF("--------------------------------------------------");
	LOG_INF("Offline image: %s (expected: %s)", image->name, image->expected);
	prefill_input_buf(model_input);
	convert_image_to_model_input(image->rgb565_be);

	result = nrf_axon_nn_model_infer_sync(model, input_buf, output_buf);
	if (result != NRF_AXON_RESULT_SUCCESS) {
		LOG_ERR("NPU inference failed (result %d)", result);
		return -1;
	}

	const size_t boxes_count = decode_output(model, output_buf, boxes, ARRAY_SIZE(boxes));

	LOG_INF("NPU inference completed: %u person candidate(s) after NMS",
		(unsigned int)boxes_count);
	if (boxes_count == 0U) {
		LOG_INF("No person detections above the configured confidence threshold");
	} else {
		log_bounding_boxes(boxes, boxes_count);
	}

	return 0;
}

int main(void)
{
	const nrf_axon_nn_compiled_model_s *model = &model_person_det;
	const nrf_axon_nn_compiled_model_input_s *model_input =
		nrf_axon_nn_model_1st_external_input(model);
	nrf_axon_result_e result;

	LOG_INF("Offline person detection start (official person_det model on Axon NPU)");
	LOG_INF("Input: embedded 128x128 RGB565 public-domain images; no camera required");

	result = nrf_axon_platform_init();
	if (result != NRF_AXON_RESULT_SUCCESS) {
		LOG_ERR("Axon platform init failed (result %d)", result);
		return -1;
	}

	result = nrf_axon_nn_model_validate(model);
	if (result != NRF_AXON_RESULT_SUCCESS) {
		LOG_ERR("Model validation failed (result %d)", result);
		return -1;
	}

	prefill_luts(model_input);
	decode_init(model);

	while (true) {
		for (size_t i = 0; i < offline_images_count; i++) {
			if (infer_offline_image(&offline_images[i], model, model_input) != 0) {
				return -1;
			}
			k_msleep(500);
		}

		LOG_INF("One positive/negative offline test pass complete; repeating in 5 seconds");
		k_sleep(K_SECONDS(5));
	}
}
