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

#include "ei_at_handlers.h"
#include "ei_device_nordic.h"
#include "ei_base64_encode.h"
#include "inference/ei_run_impulse.h"
#include "edge-impulse-sdk/porting/ei_classifier_porting.h"
#include "firmware-sdk/at-server/ei_at_command_set.h"
#include "firmware-sdk/at-server/ei_at_server.h"
#include "firmware-sdk/ei_device_info_lib.h"
#include "firmware-sdk/ei_fusion.h"
#include "firmware-sdk/at_base64_lib.h"
#include "firmware-sdk/ei_device_lib.h"
#include "firmware-sdk/ei_device_interface.h"
#include <zephyr/logging/log.h>
#include <zephyr/kernel.h>
#include <string>

LOG_MODULE_REGISTER(at_handlers, LOG_LEVEL_DBG);

using namespace std;

static EiDeviceNRF *dev;

#define TRANSFER_BUF_LEN 32

inline bool check_args_num(const int &required, const int &received)
{
    if(received < required) {
        ei_printf("Too few arguments! Required: %d\n", required);
        return false;
    }

    return true;
}

bool at_get_device_id(void)
{
    ei_printf("%s\n", dev->get_device_id().c_str());

    return true;
}

bool at_set_device_id(const char **argv, const int argc)
{
    if(argc < 1) {
        ei_printf("Missing argument!\n");
        return true;
    }

    dev->set_device_id(argv[0]);

    ei_printf("OK\n");

    return true;
}

bool at_get_upload_host(void)
{
    ei_printf("%s\n", dev->get_upload_host().c_str());

    return true;
}

bool at_set_upload_host(const char **argv, const int argc)
{
    if(argc < 1) {
        ei_printf("Missing argument!\n");
        return true;
    }

    dev->set_upload_host(argv[0]);

    ei_printf("OK\n");

    return true;
}

bool at_get_upload_settings(void)
{
    ei_printf("Api Key:   %s\n", dev->get_upload_api_key().c_str());
    ei_printf("Host:      %s\n", dev->get_upload_host().c_str());
    ei_printf("Path:      %s\n", dev->get_upload_path().c_str());

    return true;
}

bool at_set_upload_settings(const char **argv, const int argc)
{
    if(argc < 2) {
        ei_printf("Missing argument! Required: " AT_UPLOADSETTINGS_ARGS "\n");
        return true;
    }

    //TODO: can we set these values to ""?
    dev->set_upload_api_key(argv[0]);
    dev->set_upload_path(argv[1]);

    ei_printf("OK\n");

    return true;
}

bool at_get_mgmt_url(void)
{
    ei_printf("%s\n", dev->get_management_url().c_str());

    return true;
}

bool at_set_mgmt_url(const char **argv, const int argc)
{
    if(argc < 1) {
        ei_printf("Missing argument!\n");
        return true;
    }

    dev->set_management_url(argv[0]);

    ei_printf("OK\n");

    return true;
}

bool at_get_sample_settings(void)
{
    ei_printf("Label:     %s\n", dev->get_sample_label().c_str());
    ei_printf("Interval:  %.2f ms.\n", (double)dev->get_sample_interval_ms());
    ei_printf("Length:    %u ms.\n", dev->get_sample_length_ms());
    ei_printf("HMAC key:  %s\n", dev->get_sample_hmac_key().c_str());

    return true;
}

bool at_set_sample_settings(const char **argv, const int argc)
{
    if(argc < 3) {
        ei_printf("Missing argument! Required: " AT_SAMPLESETTINGS_ARGS "\n");
        return true;
    }

    dev->set_sample_label(argv[0]);

    //TODO: sanity check and/or exception handling
    string interval_ms_str(argv[1]);
    dev->set_sample_interval_ms(stof(interval_ms_str));

    //TODO: sanity check and/or exception handling
    string sample_length_str(argv[2]);
    dev->set_sample_length_ms(stoi(sample_length_str));

    if(argc >= 4) {
        dev->set_sample_hmac_key(argv[3]);
    }

    ei_printf("OK\n");

    return true;
}

bool at_clear_config(void)
{
    dev->clear_config();
    dev->init_device_id();
#ifdef CONFIG_WIFI_NRF700X
    if(cmd_wifi_connected()) {
        ei_ws_client_stop();
        cmd_wifi_disconnect();
    }
#endif
    return true;
}

bool at_unlink_file(const char **argv, const int argc)
{
    ei_printf("\n");

    return true;
}

bool at_read_buffer(const char **argv, const int argc)
{
    if(argc < 2) {
        ei_printf("Missing argument! Required: " AT_READBUFFER_ARGS "\n");
        return true;
    }

    size_t start = (size_t)atoi(argv[0]);
    size_t length = (size_t)atoi(argv[1]);

    dev->set_state(eiStateUploading);

    bool use_max_baudrate = false;
    if (argc >= 3 && argv[2][0] == 'y') {
       use_max_baudrate = true;
    }

    if (use_max_baudrate) {
        ei_printf("OK\r\n");
        ei_sleep(100);
        dev->set_max_data_output_baudrate();
        ei_sleep(100);
    }

    bool success = read_encode_send(start, length);

    if (use_max_baudrate) {
        ei_printf("\r\nOK\r\n");
        ei_sleep(100);
        dev->set_default_data_output_baudrate();
        ei_sleep(100);
    }

    if (!success) {
        ei_printf("ERR: Failed to read from buffer\n");
        dev->set_state(eiStateIdle);
    }
    else {
        ei_printf("\n");
        dev->set_state(eiStateFinished);
    }

    return true;
}

bool at_sample_start(const char **argv, const int argc)
{
    EiDeviceNRF *dev = static_cast<EiDeviceNRF*>(EiDeviceInfo::get_device());
    dev->set_serial_channel(UART);
    if(argc < 1) {
        ei_printf("Missing sensor name!\n");
        return true;
    }

    const ei_device_sensor_t *sensor_list;
    size_t sensor_list_size;

    dev->get_sensor_list((const ei_device_sensor_t **)&sensor_list, &sensor_list_size);

    for (size_t ix = 0; ix < sensor_list_size; ix++) {
        if (strcmp(sensor_list[ix].name, argv[0]) == 0) {
            if (!sensor_list[ix].start_sampling_cb()) {
                ei_printf("ERR: Failed to start sampling\n");
                dev->set_state(eiStateIdle);
            }
            else {
                dev->set_state(eiStateFinished);
            }
            return true;
        }
    }

    if (ei_connect_fusion_list(argv[0], SENSOR_FORMAT)) {
        if (!ei_fusion_setup_data_sampling()) {
            ei_printf("ERR: Failed to start sensor fusion sampling\n");
            dev->set_state(eiStateIdle);
        }
        else {
            dev->set_state(eiStateFinished);
        }
    }
    else {
        ei_printf("ERR: Failed to find sensor '%s' in the sensor list\n", argv[0]);
    }

    return true;
}

bool at_run_impulse(void)
{
    EiDeviceNRF *dev = static_cast<EiDeviceNRF*>(EiDeviceInfo::get_device());
    dev->set_serial_channel(UART);
    ei_start_impulse(false, false);

    return false;
}

bool at_run_impulse_cont(void)
{
    EiDeviceNRF *dev = static_cast<EiDeviceNRF*>(EiDeviceInfo::get_device());
    dev->set_serial_channel(UART);
    ei_start_impulse(true, false);

    return false;
}

bool at_run_impulse_static_data(const char **argv, const int argc)
{
    EiDeviceNRF *dev = static_cast<EiDeviceNRF*>(EiDeviceInfo::get_device());
    dev->set_serial_channel(UART);
    if (check_args_num(2, argc) == false) {
        return false;
    }

    bool debug = (argv[0][0] == 'y');
    size_t length = (size_t)atoi(argv[1]);

    bool res = run_impulse_static_data(debug, length, TRANSFER_BUF_LEN);

    return res;
}

bool at_stop_impulse(void)
{
    EiDeviceNRF *dev = static_cast<EiDeviceNRF*>(EiDeviceInfo::get_device());
    dev->set_serial_channel(UART);
    ei_stop_impulse();

    return true;
}

#ifdef CONFIG_WIFI_NRF700X
bool at_scan_wifi(void)
{
    cmd_wifi_scan();
    cmd_wifi_scan_done();

    return true;
}

bool at_set_wifi(const char **argv, const int argc)
{
    LOG_DBG("set WiFi\n");

    char *endptr;
    int idx = 1;
    static const char* password = NULL;
    unsigned int security = 0;

    if (argc < 1) {
        return -EINVAL;
    }

    /* PSK (optional) */
    if (idx < argc) {
        password = argv[idx];
        idx++;

        if (idx < argc) {
            security = strtol(argv[idx], &endptr, 10);
        }
    } else {
        password = NULL;
        security = 0;
    }

    cmd_wifi_connect(argv[0], password, security);
    //waithing to connect to wifi
    if(cmd_wifi_connecting() < 0) {
        ei_printf("ERR: Failed to connect to WiFi\n");
        return false;
    }
    //waitinhg to connect to dhcp
    if(cmd_dhcp_configured() < 0) {
        ei_printf("ERR: Failed to configure DHCP\n");
        return false;
    }
    ei_ws_client_start(dev, nullptr);
    ei_sleep(100);
    ei_printf("OK\n");

    return true;
}

bool at_get_wifi(void)
{
    char ssid[128] = { 0 };
    char password[128] = { 0 };
    int security = 0;

    dev->get_wifi_config(ssid, password, &security);

    ei_printf("Present:   1\n");
    ei_printf("SSID:      %s\n", ssid);
    ei_printf("Password:  %s\n", password);
    ei_printf("Security:  %d\n", security);
    ei_printf("MAC:       %s\n", dev->get_mac_address().c_str());
    ei_printf("Connected: %d\n", cmd_wifi_connected());

    return true;
}
#endif

bool at_get_config(void)
{
    const ei_device_sensor_t *sensor_list;
    size_t sensor_list_size;

    dev->get_sensor_list((const ei_device_sensor_t **)&sensor_list, &sensor_list_size);

    ei_printf("===== Device info =====\n");
    ei_printf("ID:         %s\n", dev->get_device_id().c_str());
    ei_printf("Type:       %s\n", dev->get_device_type().c_str());
    ei_printf("AT Version: " AT_COMMAND_VERSION "\n");
    ei_printf("Data Transfer Baudrate: %u\n", dev->get_data_output_baudrate());
    ei_printf("\n");
    ei_printf("===== Sensors ======\n");
    for (size_t ix = 0; ix < sensor_list_size; ix++) {
        ei_printf("Name: %s, Max sample length: %hus, Frequencies: [", sensor_list[ix].name, sensor_list[ix].max_sample_length_s);
        for (size_t fx = 0; fx < EI_MAX_FREQUENCIES; fx++) {
            if (sensor_list[ix].frequencies[fx] != 0.0f) {
                if (fx != 0) {
                    ei_printf(", ");
                }
                ei_printf("%.2fHz", (double)sensor_list[ix].frequencies[fx]);
            }
        }
        ei_printf("]\n");
    }
    ei_built_sensor_fusion_list();
    ei_printf("\n");
    ei_printf("===== WIFI =====\n");
#ifdef CONFIG_WIFI_NRF700X
    at_get_wifi();
#else
    ei_printf("Present:   %d\n", false);
    ei_printf("SSID:      %s\n", "");
    ei_printf("Password:  %s\n", "");
    ei_printf("Security:  %d\n", false);
    ei_printf("MAC:       %s\n", dev->get_mac_address().c_str());
    ei_printf("Connected: %d\n", false);
#endif
    ei_printf("\n");
    ei_printf("===== Sampling parameters =====\n");
    ei_printf("Label:     %s\n", dev->get_sample_label().c_str());
    ei_printf("Interval:  %.2f ms.\n", (double)dev->get_sample_interval_ms());
    ei_printf("Length:    %u ms.\n", dev->get_sample_length_ms());
    ei_printf("HMAC key:  %s\n", dev->get_sample_hmac_key().c_str());
    ei_printf("\n");
    ei_printf("===== Upload settings =====\n");
    ei_printf("Api Key:   %s\n", dev->get_upload_api_key().c_str());
    ei_printf("Host:      %s\n", dev->get_upload_host().c_str());
    ei_printf("Path:      %s\n", dev->get_upload_path().c_str());
    ei_printf("\n");
    ei_printf("===== Remote management =====\n");
    ei_printf("URL:        %s\n", dev->get_management_url().c_str());
#ifdef CONFIG_WIFI_NRF700X
    bool connected = ei_ws_get_connection_status();
#else
    bool connected = false;
#endif
    ei_printf("Connected: %d\n", connected);
    ei_printf("Last error: \n");
    ei_printf("\n");

    return true;
}

ATServer *ei_at_init(void)
{
    ATServer *at;
    dev = static_cast<EiDeviceNRF*>(EiDeviceInfo::get_device());

    at = ATServer::get_instance();

    at->register_command(AT_DEVICEID, AT_DEVICEID_HELP_TEXT, nullptr, at_get_device_id, at_set_device_id, AT_DEVICEID_ARGS);
    at->register_command(AT_UPLOADHOST, AT_UPLOADHOST_HELP_TEXT, nullptr, at_get_upload_host, at_set_upload_host, AT_UPLOADHOST_ARGS);
    at->register_command(AT_UPLOADSETTINGS, AT_UPLOADSETTINGS_HELP_TEXT, nullptr, at_get_upload_settings, at_set_upload_settings, AT_UPLOADSETTINGS_ARGS);
    at->register_command(AT_MGMTSETTINGS, AT_MGMTSETTINGS_HELP_TEXT, nullptr, at_get_mgmt_url, at_set_mgmt_url, AT_MGMTSETTINGS_ARGS);
    at->register_command(AT_SAMPLESETTINGS, AT_SAMPLESETTINGS_HELP_TEXT, nullptr, at_get_sample_settings, at_set_sample_settings, AT_SAMPLESETTINGS_ARGS);
    at->register_command(AT_CLEARCONFIG, AT_CLEARCONFIG_HELP_TEXT, at_clear_config, nullptr, nullptr, nullptr);
    at->register_command(AT_UNLINKFILE, AT_UNLINKFILE_HELP_TEXT, nullptr, nullptr, at_unlink_file, AT_UNLINKFILE_ARGS);
    at->register_command(AT_READBUFFER, AT_READBUFFER_HELP_TEXT, nullptr, nullptr, at_read_buffer, AT_READBUFFER_ARGS);
    at->register_command(AT_SAMPLESTART, AT_SAMPLESTART_HELP_TEXT, nullptr, nullptr, at_sample_start, AT_SAMPLESTART_ARGS);
    at->register_command(AT_CONFIG, AT_CONFIG_HELP_TEXT, nullptr, at_get_config, nullptr, nullptr);
    at->register_command(AT_RUNIMPULSE, AT_RUNIMPULSE_HELP_TEXT, at_run_impulse, nullptr, nullptr, nullptr);
    at->register_command(AT_RUNIMPULSECONT, AT_RUNIMPULSECONT_HELP_TEXT, at_run_impulse_cont, nullptr, nullptr, nullptr);
    at->register_command("STOPIMPULSE", "", at_stop_impulse, nullptr, nullptr, nullptr);
    at->register_command(AT_RUNIMPULSESTATIC, AT_RUNIMPULSESTATIC_HELP_TEXT, nullptr, nullptr, at_run_impulse_static_data, AT_RUNIMPULSESTATIC_ARGS);
#ifdef CONFIG_WIFI_NRF700X
    at->register_command(AT_WIFI, AT_WIFI_HELP_TEXT, nullptr, &at_get_wifi, &at_set_wifi, AT_WIFI_ARGS);
    at->register_command(AT_SCANWIFI, AT_SCANWIFI_HELP_TEXT, &at_scan_wifi, nullptr, nullptr, nullptr);
#endif

    return at;
}