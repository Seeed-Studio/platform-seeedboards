/*
 * Copyright (c) 2026 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

#include "protocol.h"

#include <stdbool.h>
#include <string.h>

#include <zephyr/data/cobs.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/net_buf.h>
#include <zephyr/random/random.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/crc.h>
#include <zephyr/sys/ring_buffer.h>

#include "data_forwarder_encode.h"


LOG_MODULE_REGISTER(protocol);

#define PROTO_WORKQUEUE_STACK_SIZE 1024
#define PROTO_WORKQUEUE_PRIORITY   1

#define PROTO_DEVICE_NAME_MAX_LEN  31
#define PROTO_CHANNEL_NAME_MAX_LEN 5

#define PROTO_MAX_CBOR_SESSION_SIZE                                                                \
	(1 + (4 + 5) + (3 + 3) + (3 + 2) +                                                         \
	 (5 + 2 + CONFIG_DATA_FWD_PROTO_MAX_CHANNELS * (2 + PROTO_CHANNEL_NAME_MAX_LEN)) +         \
	 (3 + 2) + (3 + 5) + (5 + 2 + PROTO_DEVICE_NAME_MAX_LEN))
#define PROTO_MAX_CBOR_SENSOR_SIZE                                                                 \
	(1 + (4 + 5) + (3 + 5) + (4 + 2 + CONFIG_DATA_FWD_PROTO_MAX_CHANNELS * 5))
#define PROTO_MAX_CBOR_SIZE                                                                        \
	(1 + (2 + 3) + (2 + MAX(PROTO_MAX_CBOR_SESSION_SIZE, PROTO_MAX_CBOR_SENSOR_SIZE)))

#define PROTO_LENGTH_SIZE	  sizeof(uint16_t)
#define PROTO_CRC_SIZE		  sizeof(uint16_t)
#define PROTO_MAX_RAW_FRAME_SIZE  (PROTO_LENGTH_SIZE + PROTO_MAX_CBOR_SIZE + PROTO_CRC_SIZE)
#define PROTO_MAX_COBS_FRAME_SIZE (PROTO_MAX_RAW_FRAME_SIZE + (PROTO_MAX_RAW_FRAME_SIZE / 254) + 2)

#define PROTO_MAX_ASCII_LINE_SIZE (CONFIG_DATA_FWD_PROTO_MAX_CHANNELS * 15)

struct proto_sample {
	uint32_t seq;
	uint32_t timestamp_ms;
	uint8_t count;
	proto_value_t values[CONFIG_DATA_FWD_PROTO_MAX_CHANNELS];
};

static struct proto_transport transport_cfg;
static struct proto_session_config session_cfg;
static char session_device_name[PROTO_DEVICE_NAME_MAX_LEN + 1];
static char session_channel_names[CONFIG_DATA_FWD_PROTO_MAX_CHANNELS]
				 [PROTO_CHANNEL_NAME_MAX_LEN + 1];

static bool session_started;
static uint32_t session_start_ms;
static uint32_t session_id;

static uint32_t seq_num;
static atomic_t producer_drops;

RING_BUF_DECLARE(proto_rb, CONFIG_DATA_FWD_PROTO_RING_BUF_SIZE);
static K_MUTEX_DEFINE(proto_rb_lock);

NET_BUF_POOL_DEFINE(proto_frame_pool, 2, PROTO_MAX_COBS_FRAME_SIZE, 0, NULL);

static void proto_meta_timer_handler(struct k_timer *timer);
static K_TIMER_DEFINE(proto_meta_timer, proto_meta_timer_handler, NULL);

static struct k_work_q proto_work_q;
static K_THREAD_STACK_DEFINE(proto_workq_stack, PROTO_WORKQUEUE_STACK_SIZE);

static void proto_meta_work_handler(struct k_work *work);
static K_WORK_DEFINE(proto_meta_work, proto_meta_work_handler);

static void proto_data_work_handler(struct k_work *work);
static K_WORK_DEFINE(proto_data_work, proto_data_work_handler);

static uint32_t proto_rb_queued_samples(void)
{
	return ring_buf_size_get(&proto_rb) / sizeof(struct proto_sample);
}

static bool proto_rb_pop_sample(struct proto_sample *sample, bool *more)
{
	k_mutex_lock(&proto_rb_lock, K_FOREVER);

	const uint32_t got = ring_buf_get(&proto_rb, (uint8_t *)sample, sizeof(*sample));

	if (got == 0) {
		k_mutex_unlock(&proto_rb_lock);
		return false;
	}

	if (got != sizeof(*sample)) {
		const uint32_t queued = proto_rb_queued_samples();

		ring_buf_reset(&proto_rb);
		k_mutex_unlock(&proto_rb_lock);

		atomic_add(&producer_drops, (atomic_val_t)queued + 1);
		LOG_ERR("Ring buffer corrupted, dropped %u queued samples", queued + 1);

		return false;
	}

	*more = !ring_buf_is_empty(&proto_rb);
	k_mutex_unlock(&proto_rb_lock);

	return true;
}

static int proto_encode_session(uint8_t *buf, size_t buf_len, size_t *out_len)
{
	struct envelope env = {0};
	struct zcbor_string dev_name = {
		.value = (const uint8_t *)session_device_name,
		.len = strlen(session_device_name),
	};

	env.envelope_t_choice = envelope_t_si_tstr_c;
	env.envelope_d_choice = envelope_d_session_info_m_c;
	env.envelope_d_session_info_m.session_info_sid = session_id;
	env.envelope_d_session_info_m.session_info_hz = session_cfg.rate_hz;
	env.envelope_d_session_info_m.session_info_ch = session_cfg.channels;
	env.envelope_d_session_info_m.session_info_ch_n_tstr0_5_count = session_cfg.channels;

	for (size_t i = 0; i < session_cfg.channels; i++) {
		struct zcbor_string channel_name = {
			.value = (const uint8_t *)session_channel_names[i],
			.len = strlen(session_channel_names[i]),
		};
		env.envelope_d_session_info_m.session_info_ch_n_tstr0_5[i] = channel_name;
	}

	env.envelope_d_session_info_m.session_info_st = session_cfg.sensor_type;
	env.envelope_d_session_info_m.session_info_dr = (uint32_t)atomic_get(&producer_drops);
	env.envelope_d_session_info_m.session_info_name = dev_name;

	return cbor_encode_envelope(buf, buf_len, &env, out_len);
}

static int proto_encode_sample(const struct proto_sample *sample, uint8_t *buf, size_t buf_len,
			       size_t *out_len)
{
	struct envelope env = {0};

	env.envelope_t_choice = envelope_t_sd_tstr_c;
	env.envelope_d_choice = envelope_d_sensor_data_m_c;
	env.envelope_d_sensor_data_m.sensor_data_seq = sample->seq;
	env.envelope_d_sensor_data_m.sensor_data_ts = sample->timestamp_ms;

	if (IS_ENABLED(CONFIG_DATA_FWD_PROTO_INT32_VALUES)) {
		env.envelope_d_sensor_data_m.sensor_data_val_choice = val_int_l_c;
		env.envelope_d_sensor_data_m.val_int_l_int_count = sample->count;

		for (size_t i = 0; i < sample->count; i++) {
			env.envelope_d_sensor_data_m.val_int_l_int[i] = (int32_t)sample->values[i];
		}
	} else {
		env.envelope_d_sensor_data_m.sensor_data_val_choice = val_float32_l_c;
		env.envelope_d_sensor_data_m.val_float32_l_float32_count = sample->count;

		for (size_t i = 0; i < sample->count; i++) {
			env.envelope_d_sensor_data_m.val_float32_l_float32[i] =
				(float)sample->values[i];
		}
	} /* IS_ENABLED(CONFIG_DATA_FWD_PROTO_INT32_VALUES) */

	return cbor_encode_envelope(buf, buf_len, &env, out_len);
}

static int proto_encode_ascii(const struct proto_sample *sample, char *line, const size_t line_size)
{
	size_t off = 0;
	size_t remain = line_size;
	int n;

	if (sample == NULL) {
		return -EINVAL;
	}

	for (size_t i = 0; i < sample->count; i++) {
		if (IS_ENABLED(CONFIG_DATA_FWD_PROTO_INT32_VALUES)) {
			n = snprintk(line + off, remain, "%s%d", i == 0 ? "" : ",",
				     (int32_t)sample->values[i]);
		} else {
			n = snprintk(line + off, remain, "%s%f", i == 0 ? "" : ",",
				     (double)sample->values[i]);
		}

		if ((n < 0) || (n >= remain)) {
			return -EMSGSIZE;
		}

		off += n;
		remain -= n;
	}

	n = snprintk(line + off, remain, "\r\n");
	if ((n < 0) || (n >= remain)) {
		return -EMSGSIZE;
	}
	off += n;

	return (int)off;
}

static int proto_send_ascii(const struct proto_sample *sample)
{
	char line[PROTO_MAX_ASCII_LINE_SIZE];
	const int len = proto_encode_ascii(sample, line, sizeof(line));

	if (len < 0) {
		atomic_inc(&producer_drops);
		return len;
	}

	return transport_cfg.send(line, len, transport_cfg.ctx);
}

static void proto_add_framing(struct net_buf *buf)
{
	__ASSERT_NO_MSG(net_buf_headroom(buf) >= PROTO_LENGTH_SIZE);
	net_buf_push_le16(buf, buf->len);

	if (IS_ENABLED(CONFIG_DATA_FWD_PROTO_CRC)) {
		const uint16_t crc = crc16_ccitt(0xFFFF, buf->data + PROTO_LENGTH_SIZE,
						 buf->len - PROTO_LENGTH_SIZE);

		net_buf_add_le16(buf, crc);
	}
}

static int proto_cobs_wrap(struct net_buf **buf)
{
	int err;
	struct net_buf *input = *buf;
	struct net_buf *cobs_buf = net_buf_alloc(&proto_frame_pool, K_NO_WAIT);

	if (cobs_buf == NULL) {
		net_buf_unref(input);
		*buf = NULL;

		return -ENOMEM;
	}

	err = cobs_encode(input, cobs_buf, COBS_FLAG_TRAILING_DELIMITER);
	net_buf_unref(input);

	if (err) {
		net_buf_unref(cobs_buf);
		*buf = NULL;

		return err;
	}

	*buf = cobs_buf;

	return 0;
}

static int proto_transport_send_buf(struct net_buf *buf)
{
	const int err = transport_cfg.send(buf->data, buf->len, transport_cfg.ctx);

	net_buf_unref(buf);

	return err;
}

static int proto_encode_sample_cbor(const struct proto_sample *sample, struct net_buf **buf)
{
	int err;
	size_t cbor_len;

	*buf = net_buf_alloc(&proto_frame_pool, K_FOREVER);
	__ASSERT_NO_MSG(*buf);
	net_buf_reserve(*buf, PROTO_LENGTH_SIZE);

	uint8_t *cbor_buf = net_buf_add(*buf, PROTO_MAX_CBOR_SIZE);

	err = proto_encode_sample(sample, cbor_buf, PROTO_MAX_CBOR_SIZE, &cbor_len);
	if (err) {
		net_buf_unref(*buf);
		*buf = NULL;

		return err;
	}

	net_buf_remove_mem(*buf, PROTO_MAX_CBOR_SIZE - cbor_len);

	return 0;
}

static int proto_encode_session_cbor(struct net_buf **buf)
{
	int err;
	size_t cbor_len;

	*buf = net_buf_alloc(&proto_frame_pool, K_FOREVER);
	__ASSERT_NO_MSG(*buf);
	net_buf_reserve(*buf, PROTO_LENGTH_SIZE);

	uint8_t *cbor_buf = net_buf_add(*buf, PROTO_MAX_CBOR_SIZE);

	err = proto_encode_session(cbor_buf, PROTO_MAX_CBOR_SIZE, &cbor_len);
	if (err) {
		net_buf_unref(*buf);
		*buf = NULL;

		return err;
	}

	net_buf_remove_mem(*buf, PROTO_MAX_CBOR_SIZE - cbor_len);

	return 0;
}

static void proto_data_work_handler(struct k_work *work)
{
	ARG_UNUSED(work);

	int err;
	struct proto_sample sample;
	bool more_samples;

	if (!proto_rb_pop_sample(&sample, &more_samples)) {
		return;
	}

	if (more_samples) {
		k_work_submit_to_queue(&proto_work_q, &proto_data_work);
	}

	if (IS_ENABLED(CONFIG_DATA_FWD_PROTO_ASCII_MODE)) {
		err = proto_send_ascii(&sample);
		if (err) {
			LOG_WRN_RATELIMIT("Samples send failed: %d", err);
		}

		return;
	}

	struct net_buf *buf;

	err = proto_encode_sample_cbor(&sample, &buf);
	if (err) {
		atomic_inc(&producer_drops);
		LOG_WRN_RATELIMIT("Samples CBOR encode failed: %d", err);
		return;
	}

	proto_add_framing(buf);

	if (!transport_cfg.has_message_boundaries) {
		err = proto_cobs_wrap(&buf);
		if (err) {
			atomic_inc(&producer_drops);
			LOG_WRN_RATELIMIT("Samples COBS encode failed: %d", err);
			return;
		}
	}

	err = proto_transport_send_buf(buf);
	if (err) {
		LOG_WRN_RATELIMIT("Samples send failed: %d", err);
	}
}

static void proto_meta_work_handler(struct k_work *work)
{
	ARG_UNUSED(work);

	int err;
	struct net_buf *buf;

	if (!session_started) {
		return;
	}

	err = proto_encode_session_cbor(&buf);
	if (err) {
		LOG_WRN_RATELIMIT("Session CBOR encode failed: %d", err);
		return;
	}

	proto_add_framing(buf);

	if (!transport_cfg.has_message_boundaries) {
		err = proto_cobs_wrap(&buf);
		if (err) {
			LOG_WRN_RATELIMIT("Session COBS encode failed: %d", err);
			return;
		}
	}

	err = proto_transport_send_buf(buf);
	if (err) {
		LOG_WRN_RATELIMIT("Session send failed: %d", err);
	}
}

static void proto_meta_timer_handler(struct k_timer *timer)
{
	ARG_UNUSED(timer);

	k_work_submit_to_queue(&proto_work_q, &proto_meta_work);
}

int proto_init(const struct proto_transport *transport)
{
	static bool workqueue_started;

	if ((transport == NULL) || (transport->send == NULL)) {
		return -EINVAL;
	}

	if (!workqueue_started) {
		k_work_queue_start(&proto_work_q, proto_workq_stack,
				   K_THREAD_STACK_SIZEOF(proto_workq_stack),
				   PROTO_WORKQUEUE_PRIORITY, NULL);
		workqueue_started = true;
	}

	transport_cfg = *transport;
	seq_num = 0U;
	session_start_ms = 0U;
	session_id = 0U;
	session_started = false;
	atomic_set(&producer_drops, 0);

	ring_buf_reset(&proto_rb);

	return 0;
}

int proto_start_session(const struct proto_session_config *cfg)
{
	if ((cfg == NULL) || (cfg->device_name == NULL) || (cfg->channel_names == NULL) ||
	    (cfg->channels == 0U)) {
		return -EINVAL;
	}

	if (cfg->channels > CONFIG_DATA_FWD_PROTO_MAX_CHANNELS) {
		LOG_ERR("Increase CONFIG_DATA_FWD_PROTO_MAX_CHANNELS to accommodate %u channels",
			cfg->channels);
		return -ENOMEM;
	}

	session_cfg = *cfg;
	session_cfg.device_name = NULL;
	snprintk(session_device_name, sizeof(session_device_name), "%s", cfg->device_name);

	session_cfg.channel_names = NULL;
	for (size_t i = 0; i < cfg->channels; i++) {
		if (cfg->channel_names[i] == NULL) {
			session_channel_names[i][0] = '\0';
		} else {
			snprintk(session_channel_names[i], sizeof(session_channel_names[i]), "%s",
				 cfg->channel_names[i]);
		}
	}

	session_id = sys_rand32_get();
	session_start_ms = k_uptime_get_32();
	session_started = true;

	if (!IS_ENABLED(CONFIG_DATA_FWD_PROTO_ASCII_MODE)) {
		k_timer_start(&proto_meta_timer, K_NO_WAIT,
			      K_SECONDS(CONFIG_DATA_FWD_PROTO_META_RESEND_S));

		k_work_submit_to_queue(&proto_work_q, &proto_meta_work);
	}

	return 0;
}

int proto_stop_session(void)
{
	session_started = false;
	k_timer_stop(&proto_meta_timer);

	k_mutex_lock(&proto_rb_lock, K_FOREVER);
	ring_buf_reset(&proto_rb);
	k_mutex_unlock(&proto_rb_lock);

	k_work_queue_drain(&proto_work_q, false);

	return 0;
}

uint32_t proto_get_session_id(void)
{
	return session_id;
}

int proto_send_samples(const proto_value_t *values, uint8_t count)
{
	if (!session_started) {
		return -EACCES;
	}
	if ((values == NULL) || (count == 0U) || (count > CONFIG_DATA_FWD_PROTO_MAX_CHANNELS)) {
		return -EINVAL;
	}

	struct proto_sample sample = {
		.seq = seq_num++,
		.timestamp_ms = k_uptime_get_32() - session_start_ms,
		.count = count,
	};

	for (size_t i = 0; i < count; i++) {
		sample.values[i] = values[i];
	}

	k_mutex_lock(&proto_rb_lock, K_FOREVER);

	/* Make space for new entry if needed. */
	if (ring_buf_space_get(&proto_rb) < sizeof(sample)) {
		ring_buf_get(&proto_rb, NULL, sizeof(sample));

		atomic_inc(&producer_drops);
	}

	uint32_t put = ring_buf_put(&proto_rb, (uint8_t *)&sample, sizeof(sample));

	if (put != sizeof(sample)) {
		const uint32_t queued = proto_rb_queued_samples();

		ring_buf_reset(&proto_rb);
		k_mutex_unlock(&proto_rb_lock);

		atomic_add(&producer_drops, (atomic_val_t)queued + 1);
		LOG_ERR("Ring buffer corrupted, dropped %u queued samples", queued + 1);

		return -EFAULT;
	}
	k_mutex_unlock(&proto_rb_lock);

	k_work_submit_to_queue(&proto_work_q, &proto_data_work);

	return 0;
}

