/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * XIAO STM32C5 CAN FD data phase stress test.
 */

#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/can.h>
#include <zephyr/kernel.h>
#include <zephyr/shell/shell.h>
#include <zephyr/shell/shell_string_conv.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/byteorder.h>
#include <zephyr/sys/sys_io.h>

#define CANBUS_NODE DT_CHOSEN(zephyr_canbus)

#define TEST_CAN_ID 0x504
#define TEST_MAGIC 0xc5fd504U
#define STD_CAN_ID_MAX 0x7ffU
#define TX_QUEUE_DEPTH 3
#define TX_THREAD_STACK_SIZE 2048
#define STATS_THREAD_STACK_SIZE 2048
#define THREAD_PRIORITY 5
#define FW_VERSION "2026-07-09.1"
#define DLC_BUCKET_COUNT 16
#define CANFD_8M_DATA_BITRATE 8000000U
#define CANFD_8M_DATA_SAMPLE_POINT 800U
#define CAN_SYNC_SEG_TQ 1U

#define FDCAN2_BASE_ADDR 0x4000a800UL
#define FDCAN_CONFIG_BASE_ADDR 0x4000a500UL
#define RCC_BASE_ADDR 0x44020c00UL
#define RCC_APB1HRSTR_ADDR (RCC_BASE_ADDR + 0x78UL)
#define RCC_APB1HENR_ADDR (RCC_BASE_ADDR + 0xa0UL)
#define RCC_APB1HLPENR_ADDR (RCC_BASE_ADDR + 0xc8UL)
#define RCC_CCIPR1_ADDR (RCC_BASE_ADDR + 0xd8UL)
#define RCC_FDCANRST BIT(9)
#define RCC_FDCANSEL_SHIFT 26U
#define RCC_FDCANSEL_MASK (0x3UL << RCC_FDCANSEL_SHIFT)

enum stress_mode {
	MODE_RX_ONLY,
	MODE_TX_ONLY,
	MODE_BIDIRECTIONAL,
};

enum frame_format {
	FRAME_CLASSIC_CAN,
	FRAME_FD_NO_BRS,
	FRAME_FD_BRS,
};

enum payload_pattern {
	PAYLOAD_FIXED,
	PAYLOAD_FIXED_8,
	PAYLOAD_FIXED_64,
	PAYLOAD_ALT_8_64,
	PAYLOAD_MIX_CANFD,
};

struct stress_config {
	enum stress_mode mode;
	enum frame_format format;
	enum payload_pattern pattern;
	bool loopback;
	uint32_t nominal_bitrate;
	uint32_t data_bitrate;
	uint8_t payload_len;
	uint32_t duration_s;
	uint32_t target_fps;
};

struct stress_stats {
	atomic_t tx_ok;
	atomic_t tx_enqueue_fail;
	atomic_t tx_callback_err;
	atomic_t tx_bytes;
	atomic_t rx_frames;
	atomic_t rx_bytes;
	atomic_t rx_checked;
	atomic_t rx_unchecked;
	atomic_t rx_seq_gap;
	atomic_t rx_content_err;
	atomic_t tx_len_frames[DLC_BUCKET_COUNT];
	atomic_t rx_len_frames[DLC_BUCKET_COUNT];
};

static const uint8_t dlc_bucket_bytes[DLC_BUCKET_COUNT] = {
	0, 1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24, 32, 48, 64
};
static const uint8_t mix_canfd_bytes[] = {8, 12, 16, 20, 24, 32, 48, 64};

static const struct device *const can_dev = DEVICE_DT_GET(CANBUS_NODE);
static struct stress_config cfg = {
	.mode = MODE_TX_ONLY,
	.format = FRAME_FD_BRS,
	.pattern = PAYLOAD_FIXED,
	.nominal_bitrate = 500000,
	.data_bitrate = 2000000,
	.payload_len = 64,
	.duration_s = 30,
	.target_fps = 0,
};
static struct stress_stats stats;
static struct k_mutex cfg_lock;
static struct k_sem tx_sem;
static atomic_t running;
static atomic_t can_started;
static uint32_t run_started_ms;
static uint32_t tx_seq;
static uint32_t tx_can_id = TEST_CAN_ID;
static uint32_t rx_last_seq;
static bool rx_have_seq;
static const char *last_config_step;

K_THREAD_STACK_DEFINE(tx_thread_stack, TX_THREAD_STACK_SIZE);
K_THREAD_STACK_DEFINE(stats_thread_stack, STATS_THREAD_STACK_SIZE);
static struct k_thread tx_thread_data;
static struct k_thread stats_thread_data;

static const char *mode_to_str(enum stress_mode mode)
{
	if (cfg.loopback) {
		return "loop";
	}

	switch (mode) {
	case MODE_RX_ONLY:
		return "rx";
	case MODE_TX_ONLY:
		return "tx";
	case MODE_BIDIRECTIONAL:
		return "bidi";
	default:
		return "?";
	}
}

static const char *state_to_str(enum can_state state)
{
	switch (state) {
	case CAN_STATE_ERROR_ACTIVE:
		return "active";
	case CAN_STATE_ERROR_WARNING:
		return "warning";
	case CAN_STATE_ERROR_PASSIVE:
		return "passive";
	case CAN_STATE_BUS_OFF:
		return "bus-off";
	case CAN_STATE_STOPPED:
		return "stopped";
	default:
		return "unknown";
	}
}

static const char *format_to_str(enum frame_format format)
{
	switch (format) {
	case FRAME_CLASSIC_CAN:
		return "can";
	case FRAME_FD_NO_BRS:
		return "fd";
	case FRAME_FD_BRS:
		return "fd-brs";
	default:
		return "?";
	}
}

static const char *pattern_to_str(enum payload_pattern pattern)
{
	switch (pattern) {
	case PAYLOAD_FIXED:
		return "fixed";
	case PAYLOAD_FIXED_8:
		return "fixed-8";
	case PAYLOAD_FIXED_64:
		return "fixed-64";
	case PAYLOAD_ALT_8_64:
		return "alt-8-64";
	case PAYLOAD_MIX_CANFD:
		return "mix-canfd";
	default:
		return "?";
	}
}

static bool tx_enabled(enum stress_mode mode)
{
	return mode == MODE_TX_ONLY || mode == MODE_BIDIRECTIONAL;
}

static bool parse_mode(const char *text, struct stress_config *new_cfg)
{
	if (strcmp(text, "rx") == 0 || strcmp(text, "rx_only") == 0) {
		new_cfg->mode = MODE_RX_ONLY;
		new_cfg->loopback = false;
		return true;
	}

	if (strcmp(text, "tx") == 0 || strcmp(text, "tx_only") == 0) {
		new_cfg->mode = MODE_TX_ONLY;
		new_cfg->loopback = false;
		return true;
	}

	if (strcmp(text, "bidi") == 0 || strcmp(text, "bidirectional") == 0) {
		new_cfg->mode = MODE_BIDIRECTIONAL;
		new_cfg->loopback = false;
		return true;
	}

	if (strcmp(text, "loop") == 0 || strcmp(text, "loopback") == 0) {
		new_cfg->mode = MODE_TX_ONLY;
		new_cfg->loopback = true;
		return true;
	}

	return false;
}

static bool parse_format(const char *text, enum frame_format *format)
{
	if (strcmp(text, "can") == 0 || strcmp(text, "classic") == 0 ||
	    strcmp(text, "classic-can") == 0 || strcmp(text, "classic_can") == 0) {
		*format = FRAME_CLASSIC_CAN;
		return true;
	}

	if (strcmp(text, "fd") == 0 || strcmp(text, "fd-nobrs") == 0 ||
	    strcmp(text, "fd_nobrs") == 0 || strcmp(text, "nobrs") == 0) {
		*format = FRAME_FD_NO_BRS;
		return true;
	}

	if (strcmp(text, "fd-brs") == 0 || strcmp(text, "fd_brs") == 0 ||
	    strcmp(text, "brs") == 0 || strcmp(text, "fdbrs") == 0) {
		*format = FRAME_FD_BRS;
		return true;
	}

	return false;
}

static bool parse_pattern(const char *text, enum payload_pattern *pattern)
{
	if (strcmp(text, "fixed") == 0) {
		*pattern = PAYLOAD_FIXED;
		return true;
	}

	if (strcmp(text, "fixed-8") == 0 || strcmp(text, "fixed_8") == 0) {
		*pattern = PAYLOAD_FIXED_8;
		return true;
	}

	if (strcmp(text, "fixed-64") == 0 || strcmp(text, "fixed_64") == 0) {
		*pattern = PAYLOAD_FIXED_64;
		return true;
	}

	if (strcmp(text, "alt-8-64") == 0 || strcmp(text, "alt_8_64") == 0 ||
	    strcmp(text, "alternate-8-64") == 0) {
		*pattern = PAYLOAD_ALT_8_64;
		return true;
	}

	if (strcmp(text, "mix-canfd") == 0 || strcmp(text, "mix_canfd") == 0 ||
	    strcmp(text, "mix") == 0) {
		*pattern = PAYLOAD_MIX_CANFD;
		return true;
	}

	return false;
}

static const char *psr_lec_to_str(uint32_t lec)
{
	switch (lec) {
	case 0:
		return "none";
	case 1:
		return "stuff";
	case 2:
		return "form";
	case 3:
		return "ack";
	case 4:
		return "bit1";
	case 5:
		return "bit0";
	case 6:
		return "crc";
	case 7:
		return "no-change";
	default:
		return "?";
	}
}

static void dump_core_clock(const char *prefix)
{
	uint32_t core_clock = 0U;
	int ret = can_get_core_clock(can_dev, &core_clock);

	if (ret == 0) {
		printk("%s can_core_clock=%u Hz\n", prefix, core_clock);
	} else {
		printk("%s can_get_core_clock failed: %d\n", prefix, ret);
	}
}

static void dump_regs(const char *prefix)
{
	uint32_t cccr = sys_read32(FDCAN2_BASE_ADDR + 0x018UL);
	uint32_t ecr = sys_read32(FDCAN2_BASE_ADDR + 0x040UL);
	uint32_t psr = sys_read32(FDCAN2_BASE_ADDR + 0x044UL);
	uint32_t ccipr1 = sys_read32(RCC_CCIPR1_ADDR);
	uint32_t fdcan_sel = (ccipr1 & RCC_FDCANSEL_MASK) >> RCC_FDCANSEL_SHIFT;

	printk("%s FDCAN2 CREL=%08x ENDN=%08x DBTP=%08x TEST=%08x CCCR=%08x NBTP=%08x\n",
	       prefix,
	       sys_read32(FDCAN2_BASE_ADDR + 0x000UL),
	       sys_read32(FDCAN2_BASE_ADDR + 0x004UL),
	       sys_read32(FDCAN2_BASE_ADDR + 0x00cUL),
	       sys_read32(FDCAN2_BASE_ADDR + 0x010UL),
	       cccr,
	       sys_read32(FDCAN2_BASE_ADDR + 0x01cUL));
	printk("%s FDCAN2 ECR=%08x PSR=%08x TDCR=%08x IR=%08x IE=%08x RXGFC=%08x TXBC=%08x TXBRP=%08x TXBAR=%08x\n",
	       prefix, ecr, psr,
	       sys_read32(FDCAN2_BASE_ADDR + 0x048UL),
	       sys_read32(FDCAN2_BASE_ADDR + 0x050UL),
	       sys_read32(FDCAN2_BASE_ADDR + 0x054UL),
	       sys_read32(FDCAN2_BASE_ADDR + 0x080UL),
	       sys_read32(FDCAN2_BASE_ADDR + 0x0c0UL),
	       sys_read32(FDCAN2_BASE_ADDR + 0x0c8UL),
	       sys_read32(FDCAN2_BASE_ADDR + 0x0ccUL));
	printk("%s CCCR init=%u cce=%u asm=%u csa=%u csr=%u dar=%u fdoe=%u brse=%u "
	       "ECR rec=%u tec=%u cel=%u PSR lec=%s dlec=%s bo=%u ew=%u ep=%u act=%u\n",
	       prefix,
	       (cccr & BIT(0)) ? 1U : 0U,
	       (cccr & BIT(1)) ? 1U : 0U,
	       (cccr & BIT(2)) ? 1U : 0U,
	       (cccr & BIT(3)) ? 1U : 0U,
	       (cccr & BIT(4)) ? 1U : 0U,
	       (cccr & BIT(6)) ? 1U : 0U,
	       (cccr & BIT(8)) ? 1U : 0U,
	       (cccr & BIT(9)) ? 1U : 0U,
	       (ecr >> 8) & 0x7fU,
	       ecr & 0xffU,
	       (ecr >> 16) & 0xffU,
	       psr_lec_to_str(psr & 0x7U),
	       psr_lec_to_str((psr >> 8) & 0x7U),
	       (psr & BIT(7)) ? 1U : 0U,
	       (psr & BIT(6)) ? 1U : 0U,
	       (psr & BIT(5)) ? 1U : 0U,
	       (psr >> 3) & 0x3U);
	printk("%s RCC APB1HRSTR=%08x APB1HENR=%08x APB1HLPENR=%08x CCIPR1=%08x "
	       "FDCANSEL=%u(0=PCLK1 1=PSIS 2=PSIK 3=HSE) CKDIV=%08x\n",
	       prefix,
	       sys_read32(RCC_APB1HRSTR_ADDR),
	       sys_read32(RCC_APB1HENR_ADDR),
	       sys_read32(RCC_APB1HLPENR_ADDR),
	       ccipr1,
	       fdcan_sel,
	       sys_read32(FDCAN_CONFIG_BASE_ADDR));
}

static int parse_u32(const char *text, uint32_t *value)
{
	int err = 0;
	unsigned long parsed = shell_strtoul(text, 10, &err);

	if (err != 0 || parsed > UINT32_MAX) {
		return -EINVAL;
	}

	*value = (uint32_t)parsed;
	return 0;
}

static int parse_can_id_hex(const char *text, uint32_t *value)
{
	int err = 0;
	unsigned long parsed = shell_strtoul(text, 16, &err);

	if (err != 0 || parsed > STD_CAN_ID_MAX) {
		return -EINVAL;
	}

	*value = (uint32_t)parsed;
	return 0;
}

static int payload_len_bucket(uint8_t payload_len)
{
	for (int i = 0; i < DLC_BUCKET_COUNT; i++) {
		if (dlc_bucket_bytes[i] == payload_len) {
			return i;
		}
	}

	return -1;
}

static uint8_t payload_len_for_frame(const struct stress_config *local_cfg, uint32_t seq)
{
	switch (local_cfg->pattern) {
	case PAYLOAD_FIXED_8:
		return 8;
	case PAYLOAD_FIXED_64:
		return 64;
	case PAYLOAD_ALT_8_64:
		return (seq & 1U) ? 64 : 8;
	case PAYLOAD_MIX_CANFD:
		return mix_canfd_bytes[seq % ARRAY_SIZE(mix_canfd_bytes)];
	case PAYLOAD_FIXED:
	default:
		return local_cfg->payload_len;
	}
}

static void estimate_frame_bits(enum frame_format format, uint8_t payload_len,
				uint32_t *nominal_bits, uint32_t *data_bits)
{
	uint32_t crc_bits = payload_len > 16U ? 21U : 17U;

	if (format == FRAME_CLASSIC_CAN) {
		*nominal_bits = 47U + (payload_len * 8U);
		*data_bits = 0U;
		return;
	}

	if (format == FRAME_FD_NO_BRS) {
		*nominal_bits = 36U + crc_bits + (payload_len * 8U);
		*data_bits = 0U;
		return;
	}

	/*
	 * Approximation without bit stuffing: arbitration/control/ACK/EOF/IFS at
	 * nominal rate, ESI/DLC/payload/CRC at data rate.
	 */
	*nominal_bits = 30U;
	*data_bits = 6U + crc_bits + (payload_len * 8U);
}

static void reset_stats(void)
{
	atomic_set(&stats.tx_ok, 0);
	atomic_set(&stats.tx_enqueue_fail, 0);
	atomic_set(&stats.tx_callback_err, 0);
	atomic_set(&stats.tx_bytes, 0);
	atomic_set(&stats.rx_frames, 0);
	atomic_set(&stats.rx_bytes, 0);
	atomic_set(&stats.rx_checked, 0);
	atomic_set(&stats.rx_unchecked, 0);
	atomic_set(&stats.rx_seq_gap, 0);
	atomic_set(&stats.rx_content_err, 0);
	for (int i = 0; i < DLC_BUCKET_COUNT; i++) {
		atomic_set(&stats.tx_len_frames[i], 0);
		atomic_set(&stats.rx_len_frames[i], 0);
	}
	tx_seq = 0;
	rx_last_seq = 0;
	rx_have_seq = false;
}

static void fill_payload(struct can_frame *frame, uint32_t seq, uint8_t payload_len)
{
	if (payload_len >= 4U) {
		sys_put_le32(TEST_MAGIC, &frame->data[0]);
	}

	if (payload_len >= 8U) {
		sys_put_le32(seq, &frame->data[4]);
	}

	if (payload_len >= 12U) {
		sys_put_le32(k_uptime_get_32(), &frame->data[8]);
	}

	for (uint8_t i = 12; i < payload_len; i++) {
		frame->data[i] = (uint8_t)(0xa5U ^ i ^ seq);
	}
}

static void rx_callback(const struct device *dev, struct can_frame *frame, void *user_data)
{
	uint8_t payload_len = can_dlc_to_bytes(frame->dlc);
	int bucket = payload_len_bucket(payload_len);

	ARG_UNUSED(dev);
	ARG_UNUSED(user_data);

	atomic_inc(&stats.rx_frames);
	atomic_add(&stats.rx_bytes, payload_len);
	if (bucket >= 0) {
		atomic_inc(&stats.rx_len_frames[bucket]);
	}

	if (payload_len < 8 || sys_get_le32(&frame->data[0]) != TEST_MAGIC) {
		atomic_inc(&stats.rx_unchecked);
		return;
	}

	uint32_t seq = sys_get_le32(&frame->data[4]);

	if (rx_have_seq) {
		uint32_t expected = rx_last_seq + 1U;

		if (seq != expected) {
			atomic_add(&stats.rx_seq_gap, seq > expected ? seq - expected : 1);
		}
	}

	rx_last_seq = seq;
	rx_have_seq = true;

	for (uint8_t i = 12; i < payload_len; i++) {
		if (frame->data[i] != (uint8_t)(0xa5U ^ i ^ seq)) {
			atomic_inc(&stats.rx_content_err);
			break;
		}
	}

	atomic_inc(&stats.rx_checked);
}

static void tx_callback(const struct device *dev, int error, void *user_data)
{
	uint8_t payload_len = (uint8_t)(uintptr_t)user_data;
	int bucket = payload_len_bucket(payload_len);

	ARG_UNUSED(dev);

	if (error == 0) {
		atomic_inc(&stats.tx_ok);
		atomic_add(&stats.tx_bytes, payload_len);
		if (bucket >= 0) {
			atomic_inc(&stats.tx_len_frames[bucket]);
		}
	} else {
		atomic_inc(&stats.tx_callback_err);
	}

	k_sem_give(&tx_sem);
}

static int stop_can_if_needed(void)
{
	int ret;

	if (!atomic_get(&can_started)) {
		return 0;
	}

	ret = can_stop(can_dev);
	if (ret != 0 && ret != -EALREADY) {
		return ret;
	}

	atomic_set(&can_started, 0);
	return 0;
}

static uint32_t timing_sample_point_permille(const struct can_timing *timing)
{
	uint32_t tseg1 = timing->prop_seg + timing->phase_seg1;
	uint32_t total_tq = CAN_SYNC_SEG_TQ + tseg1 + timing->phase_seg2;

	return (CAN_SYNC_SEG_TQ + tseg1) * 1000U / total_tq;
}

static int set_data_bitrate(const struct stress_config *new_cfg)
{
	struct can_timing timing_data = { 0 };
	uint32_t sample_point;
	int calc_err;
	int ret;

	if (new_cfg->data_bitrate != CANFD_8M_DATA_BITRATE) {
		return can_set_bitrate_data(can_dev, new_cfg->data_bitrate);
	}

	ret = can_calc_timing_data(can_dev, &timing_data, new_cfg->data_bitrate,
				   CANFD_8M_DATA_SAMPLE_POINT);
	if (ret < 0) {
		last_config_step = "can_calc_timing_data(data-8m)";
		return ret;
	}
	calc_err = ret;

	timing_data.sjw = timing_data.phase_seg2;

	ret = can_set_timing_data(can_dev, &timing_data);
	if (ret != 0) {
		last_config_step = "can_set_timing_data(data-8m)";
		return ret;
	}

	sample_point = timing_sample_point_permille(&timing_data);
	printk("data timing override bitrate=%u target_sp=%u.%u%% actual_sp=%u.%u%% "
	       "brp=%u seg1=%u seg2=%u sjw=%u calc_err=%d\n",
	       new_cfg->data_bitrate,
	       CANFD_8M_DATA_SAMPLE_POINT / 10U, CANFD_8M_DATA_SAMPLE_POINT % 10U,
	       sample_point / 10U, sample_point % 10U,
	       timing_data.prescaler, timing_data.prop_seg + timing_data.phase_seg1,
	       timing_data.phase_seg2, timing_data.sjw, calc_err);

	return 0;
}

static int configure_and_start_can(const struct stress_config *new_cfg)
{
	int ret;
	can_mode_t can_mode = 0;

	if (new_cfg->format != FRAME_CLASSIC_CAN) {
		can_mode |= CAN_MODE_FD;
	}

	if (new_cfg->loopback) {
		can_mode |= CAN_MODE_LOOPBACK;
	}

	ret = stop_can_if_needed();
	if (ret != 0) {
		last_config_step = "can_stop";
		return ret;
	}

	ret = can_set_mode(can_dev, can_mode);
	if (ret != 0) {
		last_config_step = "can_set_mode";
		return ret;
	}

	ret = can_set_bitrate(can_dev, new_cfg->nominal_bitrate);
	if (ret != 0) {
		last_config_step = "can_set_bitrate(nominal)";
		return ret;
	}

	if (new_cfg->format != FRAME_CLASSIC_CAN) {
		ret = set_data_bitrate(new_cfg);
		if (ret != 0) {
			last_config_step = "can_set_bitrate_data(data)";
			return ret;
		}
	}

	ret = can_start(can_dev);
	if (ret != 0 && ret != -EALREADY) {
		last_config_step = "can_start";
		dump_core_clock("fail");
		dump_regs("fail");
		return ret;
	}

	last_config_step = "ok";
	atomic_set(&can_started, 1);
	return 0;
}

static void print_stats_line(const char *prefix)
{
	struct can_bus_err_cnt err_cnt = {0};
	enum can_state state = CAN_STATE_STOPPED;
	uint32_t elapsed_s = 0;

	if (run_started_ms != 0U) {
		elapsed_s = (k_uptime_get_32() - run_started_ms) / 1000U;
	}

	(void)can_get_state(can_dev, &state, &err_cnt);

	printk("%s t=%us mode=%s format=%s pattern=%s nominal=%u data=%u len=%u tx_ok=%ld tx_fail=%ld "
	       "tx_cb_err=%ld rx=%ld checked=%ld unchecked=%ld gap=%ld content_err=%ld "
	       "tx_Bps=%ld rx_Bps=%ld state=%s rxerr=%u txerr=%u\n",
	       prefix, elapsed_s, mode_to_str(cfg.mode), format_to_str(cfg.format),
	       pattern_to_str(cfg.pattern), cfg.nominal_bitrate, cfg.data_bitrate,
	       cfg.payload_len, atomic_get(&stats.tx_ok),
	       atomic_get(&stats.tx_enqueue_fail), atomic_get(&stats.tx_callback_err),
	       atomic_get(&stats.rx_frames), atomic_get(&stats.rx_checked),
	       atomic_get(&stats.rx_unchecked), atomic_get(&stats.rx_seq_gap),
	       atomic_get(&stats.rx_content_err),
	       elapsed_s == 0U ? 0 : atomic_get(&stats.tx_bytes) / elapsed_s,
	       elapsed_s == 0U ? 0 : atomic_get(&stats.rx_bytes) / elapsed_s,
	       state_to_str(state), err_cnt.rx_err_cnt, err_cnt.tx_err_cnt);

#ifdef CONFIG_CAN_STATS
	printk("can_stats bit=%u bit0=%u bit1=%u stuff=%u crc=%u form=%u ack=%u rx_overrun=%u\n",
	       can_stats_get_bit_errors(can_dev),
	       can_stats_get_bit0_errors(can_dev),
	       can_stats_get_bit1_errors(can_dev),
	       can_stats_get_stuff_errors(can_dev),
	       can_stats_get_crc_errors(can_dev),
	       can_stats_get_form_errors(can_dev),
	       can_stats_get_ack_errors(can_dev),
	       can_stats_get_rx_overruns(can_dev));
#endif
}

static void print_len_histogram(const char *prefix, atomic_t buckets[DLC_BUCKET_COUNT])
{
	printk("%s_len_hist", prefix);
	for (int i = 0; i < DLC_BUCKET_COUNT; i++) {
		long count = atomic_get(&buckets[i]);

		if (count != 0) {
			printk(" %u:%ld", dlc_bucket_bytes[i], count);
		}
	}
	printk("\n");
}

static void print_final_metrics(void)
{
	uint32_t elapsed_ms = run_started_ms == 0U ? 0U : k_uptime_get_32() - run_started_ms;
	uint64_t elapsed = elapsed_ms == 0U ? 1U : elapsed_ms;
	uint64_t tx_ok = (uint64_t)atomic_get(&stats.tx_ok);
	uint64_t tx_fail = (uint64_t)atomic_get(&stats.tx_enqueue_fail);
	uint64_t tx_cb_err = (uint64_t)atomic_get(&stats.tx_callback_err);
	uint64_t rx_frames = (uint64_t)atomic_get(&stats.rx_frames);
	uint64_t rx_checked = (uint64_t)atomic_get(&stats.rx_checked);
	uint64_t rx_seq_gap = (uint64_t)atomic_get(&stats.rx_seq_gap);
	uint64_t rx_content_err = (uint64_t)atomic_get(&stats.rx_content_err);
	uint64_t tx_bytes = (uint64_t)atomic_get(&stats.tx_bytes);
	uint64_t rx_bytes = (uint64_t)atomic_get(&stats.rx_bytes);
	uint64_t tx_attempts = tx_ok + tx_fail + tx_cb_err;
	uint64_t tx_frame_errors = tx_fail + tx_cb_err;
	uint64_t rx_expected = rx_checked + rx_seq_gap;
	uint64_t rx_frame_errors = rx_seq_gap + rx_content_err;
	uint64_t frame_errors = tx_frame_errors + rx_frame_errors;
	uint64_t frame_total = tx_attempts + rx_expected + rx_content_err;
	uint64_t est_nominal_bits = 0U;
	uint64_t est_data_bits = 0U;
	uint64_t total_payload_bps;
	uint64_t tx_payload_bps;
	uint64_t rx_payload_bps;
	uint64_t tx_fps;
	uint64_t rx_fps;
	uint64_t rx_checked_fps;
	uint64_t total_error_permille;
	uint64_t tx_error_permille;
	uint64_t rx_loss_permille;

	for (int i = 0; i < DLC_BUCKET_COUNT; i++) {
		uint32_t nominal_bits;
		uint32_t data_bits;
		uint64_t count = (uint64_t)atomic_get(&stats.tx_len_frames[i]) +
				 (uint64_t)atomic_get(&stats.rx_len_frames[i]);

		if (count == 0U) {
			continue;
		}

		estimate_frame_bits(cfg.format, dlc_bucket_bytes[i], &nominal_bits, &data_bits);
		est_nominal_bits += count * nominal_bits;
		est_data_bits += count * data_bits;
	}

	tx_payload_bps = tx_bytes * 8U * 1000U / elapsed;
	rx_payload_bps = rx_bytes * 8U * 1000U / elapsed;
	total_payload_bps = (tx_bytes + rx_bytes) * 8U * 1000U / elapsed;
	tx_fps = tx_ok * 1000U / elapsed;
	rx_fps = rx_frames * 1000U / elapsed;
	rx_checked_fps = rx_checked * 1000U / elapsed;
	tx_error_permille = tx_attempts == 0U ? 0U : tx_frame_errors * 1000U / tx_attempts;
	rx_loss_permille = rx_expected == 0U ? 0U : rx_seq_gap * 1000U / rx_expected;
	total_error_permille = frame_total == 0U ? 0U : frame_errors * 1000U / frame_total;

	printk("perf elapsed_ms=%u tx_fps=%llu rx_fps=%llu rx_checked_fps=%llu "
	       "tx_payload_bps=%llu rx_payload_bps=%llu total_payload_bps=%llu\n",
	       elapsed_ms,
	       (unsigned long long)tx_fps,
	       (unsigned long long)rx_fps,
	       (unsigned long long)rx_checked_fps,
	       (unsigned long long)tx_payload_bps,
	       (unsigned long long)rx_payload_bps,
	       (unsigned long long)total_payload_bps);
	printk("quality tx_error_permille=%llu rx_loss_permille=%llu total_error_permille=%llu "
	       "tx_attempts=%llu tx_ok=%llu tx_frame_errors=%llu rx_checked=%llu "
	       "rx_seq_gap=%llu rx_content_err=%llu\n",
	       (unsigned long long)tx_error_permille,
	       (unsigned long long)rx_loss_permille,
	       (unsigned long long)total_error_permille,
	       (unsigned long long)tx_attempts,
	       (unsigned long long)tx_ok,
	       (unsigned long long)tx_frame_errors,
	       (unsigned long long)rx_checked,
	       (unsigned long long)rx_seq_gap,
	       (unsigned long long)rx_content_err);
	printk("estimate configured_nominal_bps=%u configured_data_bps=%u "
	       "est_nominal_phase_bps=%llu est_data_phase_bps=%llu "
	       "est_total_bus_bps_no_stuff=%llu\n",
	       cfg.nominal_bitrate, cfg.data_bitrate,
	       (unsigned long long)(est_nominal_bits * 1000U / elapsed),
	       (unsigned long long)(est_data_bits * 1000U / elapsed),
	       (unsigned long long)((est_nominal_bits + est_data_bits) * 1000U / elapsed));
	print_len_histogram("tx", stats.tx_len_frames);
	print_len_histogram("rx", stats.rx_len_frames);
}

static void stop_run(bool print_summary)
{
	k_mutex_lock(&cfg_lock, K_FOREVER);
	atomic_set(&running, 0);
	if (print_summary) {
		print_stats_line("summary");
		print_final_metrics();
	}
	(void)stop_can_if_needed();
	k_mutex_unlock(&cfg_lock);
}

static void tx_thread(void *arg1, void *arg2, void *arg3)
{
	ARG_UNUSED(arg1);
	ARG_UNUSED(arg2);
	ARG_UNUSED(arg3);

	while (true) {
		struct stress_config local_cfg;
		struct can_frame frame = { 0 };
		uint32_t seq;
		uint8_t payload_len;
		int ret;

		if (!atomic_get(&running)) {
			k_sleep(K_MSEC(100));
			continue;
		}

		k_mutex_lock(&cfg_lock, K_FOREVER);
		local_cfg = cfg;
		frame.id = tx_can_id;
		k_mutex_unlock(&cfg_lock);

		if (!tx_enabled(local_cfg.mode)) {
			k_sleep(K_MSEC(100));
			continue;
		}

		if (local_cfg.format == FRAME_FD_NO_BRS) {
			frame.flags = CAN_FRAME_FDF;
		} else if (local_cfg.format == FRAME_FD_BRS) {
			frame.flags = CAN_FRAME_FDF | CAN_FRAME_BRS;
		} else {
			frame.flags = 0;
		}

		seq = tx_seq++;
		payload_len = payload_len_for_frame(&local_cfg, seq);
		frame.dlc = can_bytes_to_dlc(payload_len);
		payload_len = can_dlc_to_bytes(frame.dlc);
		fill_payload(&frame, seq, payload_len);

		if (k_sem_take(&tx_sem, K_MSEC(100)) != 0) {
			atomic_inc(&stats.tx_enqueue_fail);
			continue;
		}

		ret = can_send(can_dev, &frame, K_NO_WAIT, tx_callback,
			       (void *)(uintptr_t)payload_len);
		if (ret != 0) {
			atomic_inc(&stats.tx_enqueue_fail);
			k_sem_give(&tx_sem);
			k_sleep(K_MSEC(1));
			continue;
		}

		if (local_cfg.target_fps != 0U) {
			k_sleep(K_USEC(1000000U / local_cfg.target_fps));
		}
	}
}

static void stats_thread(void *arg1, void *arg2, void *arg3)
{
	ARG_UNUSED(arg1);
	ARG_UNUSED(arg2);
	ARG_UNUSED(arg3);

	while (true) {
		k_sleep(K_SECONDS(1));

		if (!atomic_get(&running)) {
			continue;
		}

		print_stats_line("stat");

		if (cfg.duration_s != 0U &&
		    k_uptime_get_32() - run_started_ms >= cfg.duration_s * 1000U) {
			stop_run(true);
		}
	}
}

static int cmd_start(const struct shell *sh, size_t argc, char **argv)
{
	struct stress_config new_cfg = cfg;
	uint32_t parsed;
	int ret;

	if (!parse_mode(argv[1], &new_cfg)) {
		shell_error(sh, "mode must be tx, rx, bidi, or loop");
		return -EINVAL;
	}

	if (argc > 2) {
		ret = parse_u32(argv[2], &new_cfg.nominal_bitrate);
		if (ret != 0) {
			shell_error(sh, "invalid nominal bitrate");
			return ret;
		}
	}

	if (argc > 3) {
		ret = parse_u32(argv[3], &new_cfg.data_bitrate);
		if (ret != 0) {
			shell_error(sh, "invalid data bitrate");
			return ret;
		}
	}

	if (argc > 4) {
		ret = parse_u32(argv[4], &parsed);
		if (ret != 0 || parsed > 64U) {
			shell_error(sh, "payload bytes must be 0..64");
			return -EINVAL;
		}
		new_cfg.payload_len = (uint8_t)parsed;
		new_cfg.pattern = PAYLOAD_FIXED;
	}

	if (argc > 5) {
		ret = parse_u32(argv[5], &new_cfg.duration_s);
		if (ret != 0) {
			shell_error(sh, "invalid duration");
			return ret;
		}
	}

	if (argc > 6) {
		ret = parse_u32(argv[6], &new_cfg.target_fps);
		if (ret != 0) {
			shell_error(sh, "invalid fps");
			return ret;
		}
	}

	if (argc > 7) {
		if (!parse_format(argv[7], &new_cfg.format)) {
			shell_error(sh, "format must be can, fd, or fd-brs");
			return -EINVAL;
		}
	}

	if (argc > 8) {
		if (!parse_pattern(argv[8], &new_cfg.pattern)) {
			shell_error(sh, "pattern must be fixed, fixed-8, fixed-64, alt-8-64, or mix-canfd");
			return -EINVAL;
		}
	}

	switch (new_cfg.pattern) {
	case PAYLOAD_FIXED_8:
		new_cfg.payload_len = 8U;
		break;
	case PAYLOAD_FIXED_64:
	case PAYLOAD_ALT_8_64:
	case PAYLOAD_MIX_CANFD:
		new_cfg.payload_len = 64U;
		break;
	case PAYLOAD_FIXED:
	default:
		break;
	}

	if (new_cfg.format == FRAME_CLASSIC_CAN &&
	    (new_cfg.payload_len > 8U || new_cfg.pattern == PAYLOAD_FIXED_64 ||
	     new_cfg.pattern == PAYLOAD_ALT_8_64 || new_cfg.pattern == PAYLOAD_MIX_CANFD)) {
		shell_error(sh, "classic CAN supports only fixed payload bytes 0..8");
		return -EINVAL;
	}

	if (new_cfg.payload_len > 8U) {
		new_cfg.payload_len = can_dlc_to_bytes(can_bytes_to_dlc(new_cfg.payload_len));
	}

	k_mutex_lock(&cfg_lock, K_FOREVER);
	atomic_set(&running, 0);
	cfg = new_cfg;
	reset_stats();
	k_sem_init(&tx_sem, TX_QUEUE_DEPTH, TX_QUEUE_DEPTH);

	ret = configure_and_start_can(&cfg);
	if (ret == 0) {
		run_started_ms = k_uptime_get_32();
		atomic_set(&running, 1);
	}
	k_mutex_unlock(&cfg_lock);

	if (ret != 0) {
		shell_error(sh, "failed to configure/start CAN at %s: %d",
			    last_config_step ? last_config_step : "unknown", ret);
		return ret;
	}

	shell_print(sh, "started mode=%s format=%s pattern=%s tx_id=0x%03x nominal=%u data=%u len=%u duration=%us fps=%u",
		    mode_to_str(cfg.mode), format_to_str(cfg.format),
		    pattern_to_str(cfg.pattern), tx_can_id, cfg.nominal_bitrate, cfg.data_bitrate, cfg.payload_len,
		    cfg.duration_s, cfg.target_fps);
	return 0;
}

static int cmd_stop(const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(argc);
	ARG_UNUSED(argv);

	stop_run(true);
	shell_print(sh, "stopped");
	return 0;
}

static int cmd_status(const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(sh);
	ARG_UNUSED(argc);
	ARG_UNUSED(argv);

	print_stats_line(atomic_get(&running) ? "status" : "idle");
	return 0;
}

static int cmd_id(const struct shell *sh, size_t argc, char **argv)
{
	uint32_t new_id;
	int ret;

	if (argc == 1) {
		shell_print(sh, "tx_id=0x%03x", tx_can_id);
		return 0;
	}

	ret = parse_can_id_hex(argv[1], &new_id);
	if (ret != 0) {
		shell_error(sh, "standard CAN ID must be hex 0..7ff, for example 504 or 0x505");
		return ret;
	}

	k_mutex_lock(&cfg_lock, K_FOREVER);
	tx_can_id = new_id;
	k_mutex_unlock(&cfg_lock);

	shell_print(sh, "tx_id=0x%03x", tx_can_id);
	return 0;
}

static int cmd_clock(const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(sh);
	ARG_UNUSED(argc);
	ARG_UNUSED(argv);

	dump_core_clock("diag");
	return 0;
}

static int cmd_regs(const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(sh);
	ARG_UNUSED(argc);
	ARG_UNUSED(argv);

	dump_core_clock("diag");
	dump_regs("diag");
	return 0;
}

SHELL_STATIC_SUBCMD_SET_CREATE(cfd_cmds,
	SHELL_CMD_ARG(start, NULL,
		      "start <tx|rx|bidi|loop> [nominal] [data] [bytes] [seconds] [fps] [can|fd|fd-brs] [fixed|fixed-8|fixed-64|alt-8-64|mix-canfd]",
		      cmd_start, 2, 7),
	SHELL_CMD(stop, NULL, "stop current test", cmd_stop),
	SHELL_CMD(status, NULL, "print current statistics", cmd_status),
	SHELL_CMD_ARG(id, NULL, "get/set standard TX CAN ID, hex: [000..7ff]", cmd_id, 1, 1),
	SHELL_CMD(clock, NULL, "print CAN core clock from Zephyr API", cmd_clock),
	SHELL_CMD(regs, NULL, "dump FDCAN/RCC diagnostic registers", cmd_regs),
	SHELL_SUBCMD_SET_END
);

SHELL_CMD_REGISTER(cfd, &cfd_cmds, "CAN FD data phase stress commands", NULL);

int main(void)
{
	const struct can_filter std_filter = {
		.flags = 0,
		.id = 0,
		.mask = 0,
	};
	const struct can_filter ext_filter = {
		.flags = CAN_FILTER_IDE,
		.id = 0,
		.mask = 0,
	};
	int ret;

	printk("XIAO STM32C5 CAN FD data phase stress fw=%s\n", FW_VERSION);

	if (!device_is_ready(can_dev)) {
		printk("CAN device %s is not ready\n", can_dev->name);
		return 0;
	}

	k_mutex_init(&cfg_lock);
	k_sem_init(&tx_sem, TX_QUEUE_DEPTH, TX_QUEUE_DEPTH);

	ret = can_add_rx_filter(can_dev, rx_callback, NULL, &std_filter);
	if (ret < 0) {
		printk("Failed to add standard RX filter: %d\n", ret);
		return 0;
	}
	printk("Standard RX filter id: %d\n", ret);

	ret = can_add_rx_filter(can_dev, rx_callback, NULL, &ext_filter);
	if (ret < 0) {
		printk("Failed to add extended RX filter: %d\n", ret);
		return 0;
	}
	printk("Extended RX filter id: %d\n", ret);

	k_thread_create(&tx_thread_data, tx_thread_stack,
			K_THREAD_STACK_SIZEOF(tx_thread_stack),
			tx_thread, NULL, NULL, NULL,
			THREAD_PRIORITY, 0, K_NO_WAIT);

	k_thread_create(&stats_thread_data, stats_thread_stack,
			K_THREAD_STACK_SIZEOF(stats_thread_stack),
			stats_thread, NULL, NULL, NULL,
			THREAD_PRIORITY, 0, K_NO_WAIT);

	printk("Use shell command: cfd start tx 500000 2000000 64 30 0 fd-brs\n");
	return 0;
}
