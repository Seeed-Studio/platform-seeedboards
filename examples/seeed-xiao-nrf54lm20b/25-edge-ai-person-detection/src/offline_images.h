/* SPDX-License-Identifier: LicenseRef-Nordic-5-Clause */

#ifndef OFFLINE_IMAGES_H_
#define OFFLINE_IMAGES_H_

#include <stddef.h>
#include <stdint.h>

#define OFFLINE_IMAGE_WIDTH 128
#define OFFLINE_IMAGE_HEIGHT 128
#define OFFLINE_IMAGE_RGB565_BYTES (OFFLINE_IMAGE_WIDTH * OFFLINE_IMAGE_HEIGHT * 2)

struct offline_image {
	const char *name;
	const char *expected;
	const uint8_t *rgb565_be;
};

extern const struct offline_image offline_images[];
extern const size_t offline_images_count;

#endif /* OFFLINE_IMAGES_H_ */
