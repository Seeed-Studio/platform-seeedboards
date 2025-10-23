/*
 * Copyright (c) 2024 EdgeImpulse Inc.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an "AS
 * IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
 * express or implied. See the License for the specific language
 * governing permissions and limitations under the License.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#ifndef EI_INERTIAL_SENSOR_H
#define EI_INERTIAL_SENSOR_H

/* Include ----------------------------------------------------------------- */
#include "firmware-sdk/ei_fusion.h"
#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/sensor.h>

/** Number of axis used and sample data format */
#define ACCEL_AXIS_SAMPLED            3

/* Function prototypes ----------------------------------------------------- */
bool ei_inertial_init(void);
float *ei_fusion_acc_read_data(int n_samples);

static const ei_device_fusion_sensor_t accelerometer_sensor = {
    // name of sensor module to be displayed in fusion list
    "Accelerometer",
    // number of sensor module axis
    ACCEL_AXIS_SAMPLED,
    // sampling frequencies
    { 20.0f, 62.5f, 100.0f },
    // axis name and units payload (must be same order as read in)
    { {"accX", "m/s2"}, {"accY", "m/s2"}, {"accZ", "m/s2"} },
    // reference to read data function
    &ei_fusion_acc_read_data,
    0
};

#endif /* EI_INERTIAL_SENSOR_H */