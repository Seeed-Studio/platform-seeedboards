/*
 * Generated using zcbor version 0.9.1
 * https://github.com/NordicSemiconductor/zcbor
 * Generated with a --default-max-qty of 6
 */

#ifndef DATA_FORWARDER_ENCODE_TYPES_H__
#define DATA_FORWARDER_ENCODE_TYPES_H__

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <zcbor_common.h>

#ifdef __cplusplus
extern "C" {
#endif

/** Which value for --default-max-qty this file was created with.
 *
 *  The define is used in the other generated file to do a build-time
 *  compatibility check.
 *
 *  See `zcbor --help` for more information about --default-max-qty
 */
#define DEFAULT_MAX_QTY 6

struct session_info {
	uint32_t session_info_sid;
	uint32_t session_info_hz;
	uint32_t session_info_ch;
	struct zcbor_string session_info_ch_n_tstr0_5[6];
	size_t session_info_ch_n_tstr0_5_count;
	uint32_t session_info_st;
	uint32_t session_info_dr;
	struct zcbor_string session_info_name;
};

struct sensor_data {
	uint32_t sensor_data_seq;
	uint32_t sensor_data_ts;
	union {
		struct {
			float val_float32_l_float32[6];
			size_t val_float32_l_float32_count;
		};
		struct {
			int32_t val_int_l_int[6];
			size_t val_int_l_int_count;
		};
	};
	enum {
		val_float32_l_c,
		val_int_l_c,
	} sensor_data_val_choice;
};

struct envelope {
	enum {
		envelope_t_si_tstr_c,
		envelope_t_sd_tstr_c,
	} envelope_t_choice;
	union {
		struct session_info envelope_d_session_info_m;
		struct sensor_data envelope_d_sensor_data_m;
	};
	enum {
		envelope_d_session_info_m_c,
		envelope_d_sensor_data_m_c,
	} envelope_d_choice;
};

#ifdef __cplusplus
}
#endif

#endif /* DATA_FORWARDER_ENCODE_TYPES_H__ */
