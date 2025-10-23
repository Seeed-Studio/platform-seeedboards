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

/* Include ----------------------------------------------------------------- */
#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/sensor.h>
#include "ei_inertial_sensor.h"
#include "ei_device_nordic.h"
#include "edge-impulse-sdk/porting/ei_classifier_porting.h"
#include <cstdint>

#include <zephyr/logging/log.h>
LOG_MODULE_REGISTER(acc_sensor);

/* Constant defines -------------------------------------------------------- */
#define CONVERT_G_TO_MS2    9.80665f

const struct device *iis2dlpc;

static void iis2dlpc_config(const struct device *iis2dlpc)
{
    struct sensor_value odr_attr, fs_attr;

    /* set IIS2DLPC accel/gyro sampling frequency to 1600 Hz */
    odr_attr.val1 = 1600;
    odr_attr.val2 = 0;

    if (sensor_attr_set(iis2dlpc, SENSOR_CHAN_ACCEL_XYZ,
                SENSOR_ATTR_SAMPLING_FREQUENCY, &odr_attr) < 0) {
        LOG_ERR("Cannot set sampling frequency for IIS2DLPC accel");
        return;
    }

    sensor_g_to_ms2(2, &fs_attr);

    if (sensor_attr_set(iis2dlpc, SENSOR_CHAN_ACCEL_XYZ,
                SENSOR_ATTR_FULL_SCALE, &fs_attr) < 0) {
        LOG_ERR("Cannot set sampling frequency for IIS2DLPC gyro");
        return;
    }
}

/**
 * @brief      Setup I2C config and accelerometer convert value
 *
 * @return     false if communinication error occured
 */
bool ei_inertial_init(void)
{
    iis2dlpc = DEVICE_DT_GET_ONE(st_iis2dlpc);
    if (!device_is_ready(iis2dlpc))
    {
        LOG_ERR("%s: device not ready.", iis2dlpc->name);
        return false;
    }

    iis2dlpc_config(iis2dlpc);

    if(ei_add_sensor_to_fusion_list(accelerometer_sensor) == false) {
        LOG_ERR("ERR: failed to register accelerometer sensor!");
        return false;
    }

    return true;
}

/**
 * @brief
 *
 * @return float* pointer to internal array with accel data
 */
float *ei_fusion_acc_read_data(int n_samples)
{
    struct sensor_value accel2[ACCEL_AXIS_SAMPLED];
    static float acceleration_g[ACCEL_AXIS_SAMPLED];

    memset(acceleration_g, 0, ACCEL_AXIS_SAMPLED * sizeof(float));

    if (sensor_sample_fetch(iis2dlpc) < 0) {
        LOG_ERR("IIS2DLPC Sensor sample update error");
    }
    else {
        sensor_channel_get(iis2dlpc, SENSOR_CHAN_ACCEL_XYZ, accel2);
        acceleration_g[0] = sensor_value_to_double(&accel2[0]);
        acceleration_g[1] = sensor_value_to_double(&accel2[1]);
        acceleration_g[2] = sensor_value_to_double(&accel2[2]);
    }

    return acceleration_g;
}