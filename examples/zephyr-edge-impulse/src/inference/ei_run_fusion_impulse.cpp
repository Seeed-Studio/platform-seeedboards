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

#include "model-parameters/model_metadata.h"
#if defined(EI_CLASSIFIER_SENSOR) && ((EI_CLASSIFIER_SENSOR == EI_CLASSIFIER_SENSOR_FUSION) || (EI_CLASSIFIER_SENSOR == EI_CLASSIFIER_SENSOR_ACCELEROMETER))
#include "edge-impulse-sdk/classifier/ei_run_classifier.h"
#include "edge-impulse-sdk/dsp/numpy.hpp"
#include "firmware-sdk/ei_fusion.h"
#include "ei_device_nordic.h"
#include <zephyr/kernel.h>
#include "cJSON.h"
#include <zephyr/logging/log.h>
LOG_MODULE_REGISTER(run_impulse);

typedef enum {
    INFERENCE_STOPPED,
    INFERENCE_WAITING,
    INFERENCE_SAMPLING,
    INFERENCE_DATA_READY
} inference_state_t;

static int print_results;
static uint16_t samples_per_inference;
static inference_state_t state = INFERENCE_STOPPED;
static bool continuous_mode = false;
static bool debug_mode = false;
static bool is_fusion = false;
static float samples_circ_buff[EI_CLASSIFIER_DSP_INPUT_FRAME_SIZE];
static int samples_wr_index = 0;
static EiDeviceNRF *dev = static_cast<EiDeviceNRF*>(EiDeviceInfo::get_device());

static inline inference_state_t set_thread_state(inference_state_t new_state)
{
    if(state != INFERENCE_STOPPED) {
        state = new_state;
    }

    return state;
}

/**
 * @brief Called for each single sample
 *
 */
bool samples_callback(const void *raw_sample, uint32_t raw_sample_size)
{
    if(state != INFERENCE_SAMPLING) {
        // stop collecting samples if we are not in SAMPLING state
        return true;
    }

    float *sample = (float *)raw_sample;

    for(int i = 0; i < (int)(raw_sample_size / sizeof(float)); i++) {
        samples_circ_buff[samples_wr_index++] = sample[i];
        if(samples_wr_index > EI_CLASSIFIER_DSP_INPUT_FRAME_SIZE) {
            /* start from beginning of the circular buffer */
            samples_wr_index = 0;
        }
        if(samples_wr_index >= samples_per_inference) {
            // we don't care about current state, it will be handled in the thread or next call of samples_callback
            set_thread_state(INFERENCE_DATA_READY);
            return true;
        }
    }

    return false;
}

static void process_results(ei_impulse_result_t* result)
{
    char *string = NULL;

    if(dev->get_serial_channel() == UART) {
        display_results(&ei_default_impulse, result);
    }
    else {
        cJSON *response = cJSON_CreateObject();
        cJSON *results = NULL;

        cJSON_AddStringToObject(response, "type", "inference-results");

        results = cJSON_AddArrayToObject(response, "classification");

        for (size_t ix = 0; ix < EI_CLASSIFIER_LABEL_COUNT; ix++) {
            cJSON *res = cJSON_CreateObject();
            cJSON_AddStringToObject(res, "label", result->classification[ix].label);
            cJSON_AddNumberToObject(res, "value", result->classification[ix].value);
            cJSON_AddItemToArray(results, res);
        }
#if EI_CLASSIFIER_HAS_ANOMALY == 1
        cJSON_AddNumberToObject(response, "anomaly", result->anomaly);
#endif

        string = cJSON_PrintUnformatted(response);
        if (string == NULL) {
            LOG_ERR("Failed to print monitor.\n");
        }

        cJSON_Delete(response);

        //ble_nus_send_data((uint8_t*)string, strlen((const char *)string));

        // cJSON_FreeString(string);
        k_free(string);
    }
}

void ei_inference_thread(void* param1, void* param2, void* param3)
{
    while(1) {
        switch(state) {
            case INFERENCE_STOPPED:
                // nothing to do
                ei_sleep(5);
                continue;
            case INFERENCE_WAITING:
                ei_sleep(2000);
                if(set_thread_state(INFERENCE_SAMPLING) == INFERENCE_STOPPED) {
                    // if someone stopped inference during delay, go to thread loop iteration
                    continue;
                }
                // start sampling now, don't collect samples during waiting period
#if MULTI_FREQ_ENABLED == 1
                if (is_fusion) {
                    ei_multi_fusion_sample_start(&samples_callback, EI_CLASSIFIER_INTERVAL_MS);
                }
                else {
                    ei_fusion_sample_start(&samples_callback, EI_CLASSIFIER_INTERVAL_MS);
                }
#else
                ei_fusion_sample_start(&samples_callback, EI_CLASSIFIER_INTERVAL_MS);
#endif
                dev->set_state(eiStateSampling);
                continue;
            case INFERENCE_SAMPLING:
                // wait for data to be collected through callback
                ei_sleep(1);
                continue;
            case INFERENCE_DATA_READY:
                dev->set_state(eiStateIdle);
                // nothing to do, just continue to inference provcessing below
                break;
            default:
                break;
        }

        signal_t signal;

        // shift circular buffer, so the newest data will be the first
        // if samples_wr_index is 0, then roll is immediately returning
        numpy::roll(samples_circ_buff, EI_CLASSIFIER_DSP_INPUT_FRAME_SIZE, (-samples_wr_index));
        /* reset wr index, the oldest data will be overwritten */
        samples_wr_index = 0;

        // Create a data structure to represent this window of data
        int err = numpy::signal_from_buffer(samples_circ_buff, EI_CLASSIFIER_DSP_INPUT_FRAME_SIZE, &signal);
        if (err != 0) {
            ei_printf("ERR: signal_from_buffer failed (%d)\n", err);
        }

        // run the impulse: DSP, neural network and the Anomaly algorithm
        ei_impulse_result_t result = { 0 };
        EI_IMPULSE_ERROR ei_error;
        if(continuous_mode == true) {
            ei_error = run_classifier_continuous(&signal, &result, debug_mode);
        }
        else {
            ei_error = run_classifier(&signal, &result, debug_mode);
        }

        if (ei_error != EI_IMPULSE_OK) {
            ei_printf("Failed to run impulse (%d)", ei_error);
            set_thread_state(INFERENCE_STOPPED);
            continue;
        }

        if(continuous_mode == true) {
            if(++print_results >= (EI_CLASSIFIER_SLICES_PER_MODEL_WINDOW >> 1)) {
                process_results(&result);
                print_results = 0;
            }
        }
        else {
            process_results(&result);
        }

        if(continuous_mode == true) {
            set_thread_state(INFERENCE_SAMPLING);
        }
        else {
            ei_printf("Starting inferencing in 2 seconds...\n");
            set_thread_state(INFERENCE_WAITING);
        }
    }
}

void ei_start_impulse(bool continuous, bool debug, bool use_max_uart_speed)
{
    const char *axis_name = EI_CLASSIFIER_FUSION_AXES_STRING;
    if (!ei_connect_fusion_list(axis_name, AXIS_FORMAT)) {
        ei_printf("ERR: Failed to find sensor '%s' in the sensor list\n", axis_name);
        return;
    }

    continuous_mode = continuous;
    debug_mode = debug;
#if MULTI_FREQ_ENABLED == 1
    is_fusion = ei_is_fusion();
#endif

    // summary of inferencing settings (from model_metadata.h)
    ei_printf("Inferencing settings:\n");
    ei_printf("\tInterval: %.04fms.\n", (double)EI_CLASSIFIER_INTERVAL_MS);
    ei_printf("\tFrame size: %d\n", EI_CLASSIFIER_DSP_INPUT_FRAME_SIZE);
    ei_printf("\tSample length: %.02f ms.\n", (double)(EI_CLASSIFIER_RAW_SAMPLE_COUNT * EI_CLASSIFIER_INTERVAL_MS));
    ei_printf("\tNo. of classes: %d\n", sizeof(ei_classifier_inferencing_categories) /
                                            sizeof(ei_classifier_inferencing_categories[0]));
    ei_printf("Starting inferencing, press 'b' to break\n");

    dev->set_sample_length_ms(EI_CLASSIFIER_RAW_SAMPLE_COUNT * EI_CLASSIFIER_INTERVAL_MS);
    dev->set_sample_interval_ms(EI_CLASSIFIER_INTERVAL_MS);

    if (continuous == true) {
        samples_per_inference = EI_CLASSIFIER_SLICE_SIZE * EI_CLASSIFIER_RAW_SAMPLES_PER_FRAME;
        // In order to have meaningful classification results, continuous inference has to run over
        // the complete model window. So the first iterations will print out garbage.
        // We now use a fixed length moving average filter of half the slices per model window and
        // only print when we run the complete maf buffer to prevent printing the same classification multiple times.
        print_results = -(EI_CLASSIFIER_SLICES_PER_MODEL_WINDOW);
        run_classifier_init();
        state = INFERENCE_SAMPLING;
    }
    else {
        samples_per_inference = EI_CLASSIFIER_RAW_SAMPLE_COUNT * EI_CLASSIFIER_RAW_SAMPLES_PER_FRAME;
        // it's time to prepare for sampling
        ei_printf("Starting inferencing in 2 seconds...\n");
        state = INFERENCE_WAITING;
    }
}

void ei_stop_impulse(void)
{
    if(state != INFERENCE_STOPPED) {
        set_thread_state(INFERENCE_STOPPED);
        ei_printf("Inferencing stopped by user\r\n");
        dev->set_state(eiStateFinished);
        /* reset samples buffer */
        samples_wr_index = 0;
        run_classifier_deinit();
    }
}

bool is_inference_running(void)
{
    return (state != INFERENCE_STOPPED);
}

K_THREAD_DEFINE(inference_thread_id, CONFIG_EI_INFERENCE_THREAD_STACK,
                ei_inference_thread, NULL, NULL, NULL,
                CONFIG_EI_INFERENCE_THREAD_PRIO, 0, 0);

#endif /* defined(EI_CLASSIFIER_SENSOR) && EI_CLASSIFIER_SENSOR == EI_CLASSIFIER_SENSOR_FUSION */
