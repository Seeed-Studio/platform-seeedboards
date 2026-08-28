/*
 * Generated using zcbor version 0.9.1
 * https://github.com/NordicSemiconductor/zcbor
 * Generated with a --default-max-qty of 6
 */

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>
#include "zcbor_encode.h"
#include "data_forwarder_encode.h"
#include "zcbor_print.h"

#if DEFAULT_MAX_QTY != 6
#error "The type file was generated with a different default_max_qty than this file"
#endif

#define log_result(state, result, func) do { \
	if (!result) { \
		zcbor_trace_file(state); \
		zcbor_log("%s error: %s\r\n", func, zcbor_error_str(zcbor_peek_error(state))); \
	} else { \
		zcbor_log("%s success\r\n", func); \
	} \
} while(0)

static bool encode_repeated_session_info_ch_n_tstr0_5(zcbor_state_t *state, const struct zcbor_string *input);
static bool encode_session_info(zcbor_state_t *state, const struct session_info *input);
static bool encode_repeated_val_int_l_int(zcbor_state_t *state, const int32_t *input);
static bool encode_sensor_data(zcbor_state_t *state, const struct sensor_data *input);
static bool encode_envelope(zcbor_state_t *state, const struct envelope *input);


static bool encode_repeated_session_info_ch_n_tstr0_5(
		zcbor_state_t *state, const struct zcbor_string *input)
{
	zcbor_log("%s\r\n", __func__);

	bool res = ((((((*input).len >= 0)
	&& ((*input).len <= 5)) || (zcbor_error(state, ZCBOR_ERR_WRONG_RANGE), false))
	&& (zcbor_tstr_encode(state, (&(*input))))));

	log_result(state, res, __func__);
	return res;
}

static bool encode_session_info(
		zcbor_state_t *state, const struct session_info *input)
{
	zcbor_log("%s\r\n", __func__);
	struct zcbor_string tmp_str;

	bool res = (((zcbor_map_start_encode(state, 7) && (((((zcbor_tstr_encode(state, ((tmp_str.value = (uint8_t *)"sid", tmp_str.len = sizeof("sid") - 1, &tmp_str)))))
	&& ((((*input).session_info_sid <= UINT32_MAX)) || (zcbor_error(state, ZCBOR_ERR_WRONG_RANGE), false))
	&& (zcbor_uint32_encode(state, (&(*input).session_info_sid))))
	&& (((zcbor_tstr_encode(state, ((tmp_str.value = (uint8_t *)"hz", tmp_str.len = sizeof("hz") - 1, &tmp_str)))))
	&& ((((*input).session_info_hz <= UINT16_MAX)) || (zcbor_error(state, ZCBOR_ERR_WRONG_RANGE), false))
	&& (zcbor_uint32_encode(state, (&(*input).session_info_hz))))
	&& (((zcbor_tstr_encode(state, ((tmp_str.value = (uint8_t *)"ch", tmp_str.len = sizeof("ch") - 1, &tmp_str)))))
	&& ((((*input).session_info_ch <= UINT8_MAX)) || (zcbor_error(state, ZCBOR_ERR_WRONG_RANGE), false))
	&& (zcbor_uint32_encode(state, (&(*input).session_info_ch))))
	&& (((zcbor_tstr_encode(state, ((tmp_str.value = (uint8_t *)"ch_n", tmp_str.len = sizeof("ch_n") - 1, &tmp_str)))))
	&& (zcbor_list_start_encode(state, 6) && ((zcbor_multi_encode_minmax(1, 6, &(*input).session_info_ch_n_tstr0_5_count, (zcbor_encoder_t *)encode_repeated_session_info_ch_n_tstr0_5, state, (*&(*input).session_info_ch_n_tstr0_5), sizeof(struct zcbor_string))) || (zcbor_list_map_end_force_encode(state), false)) && zcbor_list_end_encode(state, 6)))
	&& (((zcbor_tstr_encode(state, ((tmp_str.value = (uint8_t *)"st", tmp_str.len = sizeof("st") - 1, &tmp_str)))))
	&& ((((*input).session_info_st <= UINT8_MAX)) || (zcbor_error(state, ZCBOR_ERR_WRONG_RANGE), false))
	&& (zcbor_uint32_encode(state, (&(*input).session_info_st))))
	&& (((zcbor_tstr_encode(state, ((tmp_str.value = (uint8_t *)"dr", tmp_str.len = sizeof("dr") - 1, &tmp_str)))))
	&& ((((*input).session_info_dr <= UINT32_MAX)) || (zcbor_error(state, ZCBOR_ERR_WRONG_RANGE), false))
	&& (zcbor_uint32_encode(state, (&(*input).session_info_dr))))
	&& (((zcbor_tstr_encode(state, ((tmp_str.value = (uint8_t *)"name", tmp_str.len = sizeof("name") - 1, &tmp_str)))))
	&& ((((*input).session_info_name.len >= 0)
	&& ((*input).session_info_name.len <= 31)) || (zcbor_error(state, ZCBOR_ERR_WRONG_RANGE), false))
	&& (zcbor_tstr_encode(state, (&(*input).session_info_name))))) || (zcbor_list_map_end_force_encode(state), false)) && zcbor_map_end_encode(state, 7))));

	log_result(state, res, __func__);
	return res;
}

static bool encode_repeated_val_int_l_int(
		zcbor_state_t *state, const int32_t *input)
{
	zcbor_log("%s\r\n", __func__);

	bool res = ((((((*input) >= INT32_MIN)
	&& ((*input) <= INT32_MAX)) || (zcbor_error(state, ZCBOR_ERR_WRONG_RANGE), false))
	&& (zcbor_int32_encode(state, (&(*input))))));

	log_result(state, res, __func__);
	return res;
}

static bool encode_sensor_data(
		zcbor_state_t *state, const struct sensor_data *input)
{
	zcbor_log("%s\r\n", __func__);
	struct zcbor_string tmp_str;

	bool res = (((zcbor_map_start_encode(state, 3) && (((((zcbor_tstr_encode(state, ((tmp_str.value = (uint8_t *)"seq", tmp_str.len = sizeof("seq") - 1, &tmp_str)))))
	&& ((((*input).sensor_data_seq <= UINT32_MAX)) || (zcbor_error(state, ZCBOR_ERR_WRONG_RANGE), false))
	&& (zcbor_uint32_encode(state, (&(*input).sensor_data_seq))))
	&& (((zcbor_tstr_encode(state, ((tmp_str.value = (uint8_t *)"ts", tmp_str.len = sizeof("ts") - 1, &tmp_str)))))
	&& ((((*input).sensor_data_ts <= UINT32_MAX)) || (zcbor_error(state, ZCBOR_ERR_WRONG_RANGE), false))
	&& (zcbor_uint32_encode(state, (&(*input).sensor_data_ts))))
	&& (((zcbor_tstr_encode(state, ((tmp_str.value = (uint8_t *)"val", tmp_str.len = sizeof("val") - 1, &tmp_str)))))
	&& (((*input).sensor_data_val_choice == val_float32_l_c) ? ((zcbor_list_start_encode(state, 6) && ((zcbor_multi_encode_minmax(1, 6, &(*input).val_float32_l_float32_count, (zcbor_encoder_t *)zcbor_float32_encode, state, (*&(*input).val_float32_l_float32), sizeof(float))) || (zcbor_list_map_end_force_encode(state), false)) && zcbor_list_end_encode(state, 6)))
	: (((*input).sensor_data_val_choice == val_int_l_c) ? ((zcbor_list_start_encode(state, 6) && ((zcbor_multi_encode_minmax(1, 6, &(*input).val_int_l_int_count, (zcbor_encoder_t *)encode_repeated_val_int_l_int, state, (*&(*input).val_int_l_int), sizeof(int32_t))) || (zcbor_list_map_end_force_encode(state), false)) && zcbor_list_end_encode(state, 6)))
	: false)))) || (zcbor_list_map_end_force_encode(state), false)) && zcbor_map_end_encode(state, 3))));

	log_result(state, res, __func__);
	return res;
}

static bool encode_envelope(
		zcbor_state_t *state, const struct envelope *input)
{
	zcbor_log("%s\r\n", __func__);
	struct zcbor_string tmp_str;

	bool res = (((zcbor_map_start_encode(state, 2) && (((((zcbor_tstr_encode(state, ((tmp_str.value = (uint8_t *)"t", tmp_str.len = sizeof("t") - 1, &tmp_str)))))
	&& (((*input).envelope_t_choice == envelope_t_si_tstr_c) ? ((zcbor_tstr_encode(state, ((tmp_str.value = (uint8_t *)"si", tmp_str.len = sizeof("si") - 1, &tmp_str)))))
	: (((*input).envelope_t_choice == envelope_t_sd_tstr_c) ? ((zcbor_tstr_encode(state, ((tmp_str.value = (uint8_t *)"sd", tmp_str.len = sizeof("sd") - 1, &tmp_str)))))
	: false)))
	&& (((zcbor_tstr_encode(state, ((tmp_str.value = (uint8_t *)"d", tmp_str.len = sizeof("d") - 1, &tmp_str)))))
	&& (((*input).envelope_d_choice == envelope_d_session_info_m_c) ? ((encode_session_info(state, (&(*input).envelope_d_session_info_m))))
	: (((*input).envelope_d_choice == envelope_d_sensor_data_m_c) ? ((encode_sensor_data(state, (&(*input).envelope_d_sensor_data_m))))
	: false)))) || (zcbor_list_map_end_force_encode(state), false)) && zcbor_map_end_encode(state, 2))));

	log_result(state, res, __func__);
	return res;
}



int cbor_encode_envelope(
		uint8_t *payload, size_t payload_len,
		const struct envelope *input,
		size_t *payload_len_out)
{
	zcbor_state_t states[7];

	return zcbor_entry_function(payload, payload_len, (void *)input, payload_len_out, states,
		(zcbor_decoder_t *)encode_envelope, sizeof(states) / sizeof(zcbor_state_t), 1);
}
