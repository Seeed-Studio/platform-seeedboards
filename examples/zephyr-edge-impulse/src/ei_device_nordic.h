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

#ifndef EI_DEVICE_NORDIC
#define EI_DEVICE_NORDIC

/* Include ----------------------------------------------------------------- */
#include "firmware-sdk/ei_device_info_lib.h"
#include "firmware-sdk/ei_device_memory.h"
#include <cstdint>

#define DEFAULT_BAUD 115200
/* 230400 bps seems to be the highest, the safest and most compatible speed
 * for UART. Tests shown that 460800 is not working on nRF5340DK, while 921600
 * is not working on nRF52840DK.
 * See: https://devzone.nordicsemi.com/f/nordic-q-a/76793/baudrate-on-vcom-on-nrf52840dk */
#define MAX_BAUD 115200

typedef enum {
    UART = 0,
    WIFI
} serial_channel_t;

class EiDeviceNRF : public EiDeviceInfo
{
private:
    std::string mac_address = "00:11:22:33:44:55:66";
    EiState state;
    static const int standalone_sensor_num = 1;
    ei_device_sensor_t standalone_sensor_list[standalone_sensor_num];
    serial_channel_t last_channel;

public:
    EiDeviceNRF(void);
    EiDeviceNRF(EiDeviceMemory* mem);
    ~EiDeviceNRF();

    std::string get_mac_address(void);

    void init_device_id(void);
    void clear_config(void);

    void set_state(EiState state) override;
    EiState get_state(void);

    void set_serial_channel(serial_channel_t chan);
    serial_channel_t get_serial_channel(void);
    void set_default_data_output_baudrate() override;
    void set_max_data_output_baudrate() override;

    bool start_sample_thread(void (*sample_read_cb)(void), float sample_interval_ms) override;
    bool stop_sample_thread(void) override;
    void (*sample_read_callback)(void);

    bool get_sensor_list(const ei_device_sensor_t **sensor_list, size_t *sensor_list_size) override;
    uint32_t get_data_output_baudrate(void) override;

    int set_wifi_config(const char *ssid, const char *password, const int security);
    int get_wifi_config(char *ssid, char *password, int *security);
#if MULTI_FREQ_ENABLED == 1
    bool start_multi_sample_thread(void (*sample_multi_read_cb)(uint8_t), float* multi_sample_interval_ms, uint8_t num_fusioned);
#endif
};

int uart_init(void);
char uart_getchar(void);

#endif /* EI_DEVICE_NORDIC */
