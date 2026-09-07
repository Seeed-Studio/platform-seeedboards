/* SPDX-License-Identifier: LicenseRef-Nordic-5-Clause */

#include <zephyr/logging/log.h>

#include "protocol/protocol.h"
#include "sensor/data_fwd_sensor.h"
#include "transport/transport.h"

LOG_MODULE_REGISTER(data_forwarder);

int main(void)
{
	struct proto_transport transport;
	const struct proto_session_config session = {
		.rate_hz = data_fwd_sensor_frequency(),
		.channels = data_fwd_sensor_channel_count(),
		.sensor_type = data_fwd_sensor_type_id(),
		.channel_names = data_fwd_sensor_channel_names(),
		.device_name = "XIAO nRF54LM20B",
	};
	int err = transport_init(&transport);
	if (err) {
		LOG_ERR("Transport init failed (err %d)", err);
		return err;
	}
	err = proto_init(&transport);
	if (err) {
		LOG_ERR("Protocol init failed (err %d)", err);
		return err;
	}
	err = data_fwd_sensor_init();
	if (err) {
		LOG_ERR("Sensor init failed (err %d)", err);
		return err;
	}
	err = proto_start_session(&session);
	if (err) {
		LOG_ERR("Failed to start session (err %d)", err);
		return err;
	}
	LOG_INF("Data forwarder started (sid %u)", proto_get_session_id());

	while (1) {
		proto_value_t values[CONFIG_DATA_FWD_PROTO_MAX_CHANNELS];
		size_t count;
		err = data_fwd_sensor_fetch(values, ARRAY_SIZE(values), &count);
		if (err) {
			LOG_WRN("Sample fetch failed (err %d)", err);
			continue;
		}
		err = proto_send_samples(values, count);
		if (err) {
			LOG_WRN("Sample send failed (err %d)", err);
		}
	}
}
