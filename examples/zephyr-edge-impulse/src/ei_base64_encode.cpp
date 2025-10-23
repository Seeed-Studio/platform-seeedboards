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
#include "edge-impulse-sdk/porting/ei_classifier_porting.h"
#include "firmware-sdk/ei_device_info_lib.h"
#include "firmware-sdk/ei_device_memory.h"
#include "firmware-sdk/at_base64_lib.h"
#include "ei_device_nordic.h"
#include <zephyr/logging/log.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/kernel.h>
#include <cmath>

LOG_MODULE_REGISTER(base64, LOG_LEVEL_DBG);

bool read_encode_send(size_t address, size_t length)
{
    EiDeviceInfo *dev = EiDeviceInfo::get_device();
    EiDeviceMemory *memory = dev->get_memory();
    // we are encoiding data into base64, so it needs to be divisible by 3
    const int buffer_size = 513;
    uint8_t* buffer = (uint8_t*)ei_malloc(buffer_size);
    if(buffer == nullptr) {
        LOG_ERR("Unable to allocate base64 encoder buffer");
        return false;
    }

    while (1) {
        LOG_DBG("Reading %d bytes from %d", length, address);
        size_t bytes_to_read = buffer_size;

        if (bytes_to_read > length) {
            bytes_to_read = length;
        }

        if (bytes_to_read == 0) {
            ei_free(buffer);
            return true;
        }

        if (memory->read_sample_data(buffer, address, bytes_to_read) != bytes_to_read) {
            ei_free(buffer);
            LOG_ERR("Failed to read samples memory");
            return false;
        }

        base64_encode((char *)buffer, bytes_to_read, ei_putchar);

        address += bytes_to_read;
        length -= bytes_to_read;
    }

    ei_free(buffer);
    return true;
}
