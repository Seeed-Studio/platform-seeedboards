/* SPDX-License-Identifier: LicenseRef-Nordic-5-Clause */

#ifndef XIAO_DATA_FWD_SENSOR_H_
#define XIAO_DATA_FWD_SENSOR_H_

#include <stddef.h>
#include <stdint.h>

#include <zephyr/drivers/sensor.h>

#include "../protocol/protocol_types.h"

int data_fwd_sensor_init(void);
int data_fwd_sensor_fetch(proto_value_t *values, size_t values_size, size_t *count);
uint8_t data_fwd_sensor_channel_count(void);
const char *const *data_fwd_sensor_channel_names(void);
uint8_t data_fwd_sensor_type_id(void);
uint16_t data_fwd_sensor_frequency(void);

#endif
