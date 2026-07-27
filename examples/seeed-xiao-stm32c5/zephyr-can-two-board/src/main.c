/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * XIAO STM32C5 two-board CAN round-trip test -- USB CDC ACM interaction.
 *
 * The SAME image runs on two XIAO boards (no USB-CAN adapter, no UART needed).
 * Role is chosen over the USB CDC serial port:
 *
 *   Board A (initiator): init  <nominal> <data> <can|fd|fd-brs> [count] [fps]
 *   Board B (responder): reply <nominal> <data> <can|fd|fd-brs>
 *
 * The initiator transmits test frames on CAN ID 0x504; the responder echoes each
 * one back verbatim on CAN ID 0x505; the initiator verifies a byte-exact round
 * trip and prints PASS/FAIL plus FDCAN diagnostics -- all back over USB CDC.
 *
 * Why CDC: one of the boards has a broken UART TX (PA9), so USART1 is unusable.
 * Each board's native USB-C (PA11/PA12) shows up as a CDC COM port on the host,
 * so no USB-TTL adapter is needed. The CDC plumbing mirrors the proven
 * zephyr-usb-cdc-echo-1m / zephyr-can-bridge-slcan samples (raw interrupt-driven
 * CDC ACM, line-oriented command parser).
 *
 * Why two boards: zephyr-canfd-data-stress-psis100 fails vs a USB-CAN adapter at
 * 1M/1M and 500k/5M. Two identical boards remove the adapter variable. The
 * nominal/data bit-timing override code paths (1M nominal, 1M/5M/8M data) are
 * copied unchanged from the stress firmware so this test exercises the exact
 * same timing. Carries the PSIS=100MHz overlay to reproduce the failing clock.
 */

#include <errno.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/can.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/byteorder.h>
#include <zephyr/sys/ring_buffer.h>
#include <zephyr/sys/sys_io.h>
#include <zephyr/sys/util.h>

#define CANBUS_NODE DT_CHOSEN(zephyr_canbus)

#define FW_VERSION "2026-07-24.2"

#define TEST_MAGIC 0xc5fd504U
#define STD_CAN_ID_MAX 0x7ffU

#define DEFAULT_INIT_ID 0x504U
#define DEFAULT_ECHO_ID 0x505U

#define TX_QUEUE_DEPTH 3
#define ECHO_MSGQ_DEPTH 16
#define TX_THREAD_STACK_SIZE 2048
#define ECHO_THREAD_STACK_SIZE 2048
#define CMD_THREAD_STACK_SIZE 2048
#define THREAD_PRIORITY 5
#define CMD_PRIORITY 4

#define DEFAULT_COUNT 1000U
#define DRAIN_MS 1000U

/* CDC ACM transport. */
#define CDC_TX_RING_SIZE 4096U
#define CDC_LINE_MAX 128U
#define CDC_CMDQ_DEPTH 8U
#define CDC_PRINTF_BUF 200U

/* Bit-timing constants (copied from zephyr-canfd-data-stress-psis100). */
#define CAN_SYNC_SEG_TQ 1U
#define CANFD_1M_DATA_BITRATE 1000000U
#define CANFD_5M_DATA_BITRATE 5000000U
#define CANFD_8M_DATA_BITRATE 8000000U
#define CANFD_1M_DATA_SAMPLE_POINT 800U
#define CANFD_5M_DATA_SAMPLE_POINT 750U
#define CANFD_8M_DATA_SAMPLE_POINT 800U
#define CAN_NOMINAL_500K_BITRATE 500000U
#define CAN_NOMINAL_500K_SAMPLE_POINT 750U
#define CAN_NOMINAL_1M_BITRATE 1000000U
#define CAN_NOMINAL_1M_SAMPLE_POINT 750U

/* FDCAN2 / RCC register addresses for diagnostics (copied from stress fw). */
#define FDCAN2_BASE_ADDR 0x4000a800UL
#define FDCAN_CONFIG_BASE_ADDR 0x4000a500UL
#define RCC_BASE_ADDR 0x44020c00UL
#define RCC_APB1HRSTR_ADDR (RCC_BASE_ADDR + 0x78UL)
#define RCC_APB1HENR_ADDR (RCC_BASE_ADDR + 0xa0UL)
#define RCC_APB1HLPENR_ADDR (RCC_BASE_ADDR + 0xc8UL)
#define RCC_CCIPR1_ADDR (RCC_BASE_ADDR + 0xd8UL)
#define RCC_FDCANSEL_SHIFT 26U
#define RCC_FDCANSEL_MASK (0x3UL << RCC_FDCANSEL_SHIFT)

enum role {
	ROLE_NONE,
	ROLE_INITIATOR,
	ROLE_RESPONDER,
};

enum frame_format {
	FRAME_CLASSIC_CAN,
	FRAME_FD_NO_BRS,
	FRAME_FD_BRS,
};

struct test_config {
	enum frame_format format;
	uint32_t nominal_bitrate;
	uint32_t data_bitrate;
	uint32_t count;
	uint32_t fps;
	uint32_t init_id;
	uint32_t echo_id;
};

static const struct device *const can_dev = DEVICE_DT_GET(CANBUS_NODE);
static const struct device *const cdc_dev = DEVICE_DT_GET_ONE(zephyr_cdc_acm_uart);

static struct test_config cfg = {
	.format = FRAME_FD_BRS,
	.nominal_bitrate = 500000,
	.data_bitrate = 2000000,
	.count = DEFAULT_COUNT,
	.fps = 0,
	.init_id = DEFAULT_INIT_ID,
	.echo_id = DEFAULT_ECHO_ID,
};

static struct k_mutex cfg_lock;
static struct k_sem tx_sem;

/* CDC TX ring buffer + line accumulator (touched only from the CDC ISR). */
static struct ring_buf cdc_tx_rb;
static uint8_t cdc_tx_buf[CDC_TX_RING_SIZE];
static uint8_t cdc_rx_line[CDC_LINE_MAX];
static uint8_t cdc_rx_line_len;

/* Run state. */
static atomic_t role = ATOMIC_INIT(ROLE_NONE);
static atomic_t running = ATOMIC_INIT(0);
static atomic_t can_started = ATOMIC_INIT(0);
static int rx_filter_id = -1;
static const char *last_config_step;

/* Initiator counters. */
static atomic_t echoed;
static atomic_t echo_gap;
static atomic_t echo_content_err;
static atomic_t tx_ok;
static atomic_t tx_enqueue_fail;
static atomic_t tx_callback_err;
static uint32_t init_sent;
static uint32_t tx_seq;
static uint32_t echo_last_seq;
static bool echo_have_seq;
static bool result_printed;

/* Responder counters. */
static atomic_t resp_rx;
static atomic_t resp_echoed;
static atomic_t resp_dropped;
static atomic_t resp_echo_err;

struct cmd_item {
	char buf[CDC_LINE_MAX];
	uint8_t len;
};

K_MSGQ_DEFINE(echo_q, sizeof(struct can_frame), ECHO_MSGQ_DEPTH, 4);
K_MSGQ_DEFINE(cdc_cmdq, sizeof(struct cmd_item), CDC_CMDQ_DEPTH, 4);
K_THREAD_STACK_DEFINE(tx_thread_stack, TX_THREAD_STACK_SIZE);
K_THREAD_STACK_DEFINE(echo_thread_stack, ECHO_THREAD_STACK_SIZE);
K_THREAD_STACK_DEFINE(cmd_thread_stack, CMD_THREAD_STACK_SIZE);
static struct k_thread tx_thread_data;
static struct k_thread echo_thread_data;
static struct k_thread cmd_thread_data;

/* ===================================================================== */
/* CDC ACM transport (ring-buffered TX, interrupt-driven RX -> cmd queue).*/
/* Mirrors zephyr-can-bridge-slcan / zephyr-usb-cdc-echo-1m.              */
/* ===================================================================== */

static void cdc_tx_push(const uint8_t *data, size_t len)
{
	unsigned int key = irq_lock();
	size_t stored = ring_buf_put(&cdc_tx_rb, data, len);

	irq_unlock(key);

	if (stored > 0U) {
		uart_irq_tx_enable(cdc_dev);
	}
	/* If the ring is full (host not draining), the remainder is dropped so
	 * we never block a thread -- matches the slcan/echo-1m behavior.
	 */
}

static void cdc_puts(const char *s)
{
	cdc_tx_push((const uint8_t *)s, strlen(s));
}

static void cdc_printf(const char *fmt, ...)
{
	char buf[CDC_PRINTF_BUF];
	va_list ap;
	int n;

	va_start(ap, fmt);
	n = vsnprintf(buf, sizeof(buf), fmt, ap);
	va_end(ap);

	if (n < 0) {
		return;
	}
	if (n > (int)sizeof(buf)) {
		n = (int)sizeof(buf);
	}
	cdc_tx_push((const uint8_t *)buf, (size_t)n);
}

static void cdc_isr(const struct device *dev, void *user_data)
{
	uint8_t buf[64];
	int len;

	ARG_UNUSED(user_data);

	/* Standard Zephyr interrupt-driven UART pattern: wrap rx/tx in the
	 * update/pending loop or the ready flags never fire.
	 */
	while (uart_irq_update(dev) && uart_irq_is_pending(dev)) {
		if (uart_irq_rx_ready(dev)) {
			len = uart_fifo_read(dev, buf, sizeof(buf));
			for (int i = 0; i < len; i++) {
				uint8_t ch = buf[i];

				if (ch == '\r' || ch == '\n') {
					if (cdc_rx_line_len > 0U) {
						struct cmd_item item;

						memcpy(item.buf, cdc_rx_line, cdc_rx_line_len);
						item.buf[cdc_rx_line_len] = '\0';
						item.len = cdc_rx_line_len;
						(void)k_msgq_put(&cdc_cmdq, &item, K_NO_WAIT);
						cdc_rx_line_len = 0U;
					}
				} else if (cdc_rx_line_len < (CDC_LINE_MAX - 1U)) {
					cdc_rx_line[cdc_rx_line_len++] = ch;
				}
			}
		}

		if (uart_irq_tx_ready(dev)) {
			len = (int)ring_buf_get(&cdc_tx_rb, buf, sizeof(buf));
			if (len == 0) {
				uart_irq_tx_disable(dev);
			} else {
				int sent = uart_fifo_fill(dev, buf, len);

				if (sent > 0 && sent < len) {
					unsigned int key = irq_lock();

					(void)ring_buf_put(&cdc_tx_rb, &buf[sent],
							   (size_t)len - (size_t)sent);
					irq_unlock(key);
				}
			}
		}
	}
}

/* ===================================================================== */
/* Helpers (format/state strings, parsing).                              */
/* ===================================================================== */

static const char *role_to_str(enum role r)
{
	switch (r) {
	case ROLE_INITIATOR:
		return "init";
	case ROLE_RESPONDER:
		return "reply";
	default:
		return "none";
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

static int parse_u32(const char *text, uint32_t *value)
{
	char *end;
	unsigned long parsed;

	if (text == NULL || text[0] == '\0') {
		return -EINVAL;
	}

	errno = 0;
	parsed = strtoul(text, &end, 10);
	if (errno != 0 || *end != '\0' || parsed > UINT32_MAX) {
		return -EINVAL;
	}

	*value = (uint32_t)parsed;
	return 0;
}

static int parse_can_id_hex(const char *text, uint32_t *value)
{
	char *end;
	unsigned long parsed;

	if (text == NULL || text[0] == '\0') {
		return -EINVAL;
	}

	errno = 0;
	parsed = strtoul(text, &end, 16);
	if (errno != 0 || *end != '\0' || parsed > STD_CAN_ID_MAX) {
		return -EINVAL;
	}

	*value = (uint32_t)parsed;
	return 0;
}

static uint8_t payload_len_for_format(enum frame_format format)
{
	return format == FRAME_CLASSIC_CAN ? 8U : 64U;
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

/* ===================================================================== */
/* Bit-timing overrides + diagnostics (copied verbatim from the stress   */
/* firmware so the failing code paths are exercised identically).        */
/* ===================================================================== */

static void dump_core_clock(const char *prefix)
{
	uint32_t core_clock = 0U;
	int ret = can_get_core_clock(can_dev, &core_clock);

	if (ret == 0) {
		cdc_printf("%s can_core_clock=%u Hz\r\n", prefix, core_clock);
	} else {
		cdc_printf("%s can_get_core_clock failed: %d\r\n", prefix, ret);
	}
}

static void dump_regs(const char *prefix)
{
	uint32_t cccr = sys_read32(FDCAN2_BASE_ADDR + 0x018UL);
	uint32_t ecr = sys_read32(FDCAN2_BASE_ADDR + 0x040UL);
	uint32_t psr = sys_read32(FDCAN2_BASE_ADDR + 0x044UL);
	uint32_t ccipr1 = sys_read32(RCC_CCIPR1_ADDR);
	uint32_t fdcan_sel = (ccipr1 & RCC_FDCANSEL_MASK) >> RCC_FDCANSEL_SHIFT;

	cdc_printf("%s FDCAN2 CREL=%08x ENDN=%08x DBTP=%08x TEST=%08x CCCR=%08x NBTP=%08x\r\n",
		   prefix,
		   sys_read32(FDCAN2_BASE_ADDR + 0x000UL),
		   sys_read32(FDCAN2_BASE_ADDR + 0x004UL),
		   sys_read32(FDCAN2_BASE_ADDR + 0x00cUL),
		   sys_read32(FDCAN2_BASE_ADDR + 0x010UL),
		   cccr,
		   sys_read32(FDCAN2_BASE_ADDR + 0x01cUL));
	cdc_printf("%s FDCAN2 ECR=%08x PSR=%08x TDCR=%08x IR=%08x IE=%08x RXGFC=%08x TXBC=%08x TXBRP=%08x TXBAR=%08x\r\n",
		   prefix, ecr, psr,
		   sys_read32(FDCAN2_BASE_ADDR + 0x048UL),
		   sys_read32(FDCAN2_BASE_ADDR + 0x050UL),
		   sys_read32(FDCAN2_BASE_ADDR + 0x054UL),
		   sys_read32(FDCAN2_BASE_ADDR + 0x080UL),
		   sys_read32(FDCAN2_BASE_ADDR + 0x0c0UL),
		   sys_read32(FDCAN2_BASE_ADDR + 0x0c8UL),
		   sys_read32(FDCAN2_BASE_ADDR + 0x0ccUL));
	cdc_printf("%s CCCR init=%u cce=%u asm=%u csa=%u csr=%u dar=%u fdoe=%u brse=%u ECR rec=%u tec=%u cel=%u PSR lec=%s dlec=%s bo=%u ew=%u ep=%u act=%u\r\n",
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
	cdc_printf("%s RCC APB1HRSTR=%08x APB1HENR=%08x APB1HLPENR=%08x CCIPR1=%08x FDCANSEL=%u(0=PCLK1 1=PSIS 2=PSIK 3=HSE) CKDIV=%08x\r\n",
		   prefix,
		   sys_read32(RCC_APB1HRSTR_ADDR),
		   sys_read32(RCC_APB1HENR_ADDR),
		   sys_read32(RCC_APB1HLPENR_ADDR),
		   ccipr1, fdcan_sel,
		   sys_read32(FDCAN_CONFIG_BASE_ADDR));
}

static uint32_t timing_sample_point_permille(const struct can_timing *timing)
{
	uint32_t tseg1 = timing->prop_seg + timing->phase_seg1;
	uint32_t total_tq = CAN_SYNC_SEG_TQ + tseg1 + timing->phase_seg2;

	return (CAN_SYNC_SEG_TQ + tseg1) * 1000U / total_tq;
}

static int set_data_bitrate(const struct test_config *new_cfg)
{
	struct can_timing timing_data = { 0 };
	uint16_t target_sample_point;
	bool use_override = true;
	bool predefined_timing = false;
	bool maximize_sjw = false;
	uint32_t sample_point;
	int calc_err;
	int ret;

	switch (new_cfg->data_bitrate) {
	case CANFD_1M_DATA_BITRATE:
		target_sample_point = CANFD_1M_DATA_SAMPLE_POINT;
		timing_data.prescaler = 5U;
		timing_data.phase_seg1 = 15U;
		timing_data.phase_seg2 = 4U;
		timing_data.sjw = 2U;
		predefined_timing = true;
		break;
	case CANFD_5M_DATA_BITRATE:
		target_sample_point = CANFD_5M_DATA_SAMPLE_POINT;
		break;
	case CANFD_8M_DATA_BITRATE:
		target_sample_point = CANFD_8M_DATA_SAMPLE_POINT;
		maximize_sjw = true;
		break;
	default:
		use_override = false;
		break;
	}

	if (!use_override) {
		return can_set_bitrate_data(can_dev, new_cfg->data_bitrate);
	}

	if (predefined_timing) {
		calc_err = 0;
	} else {
		ret = can_calc_timing_data(can_dev, &timing_data, new_cfg->data_bitrate,
					   target_sample_point);
		if (ret < 0) {
			last_config_step = "can_calc_timing_data(data)";
			return ret;
		}
		calc_err = ret;
	}

	if (maximize_sjw) {
		timing_data.sjw = timing_data.phase_seg2;
	}

	ret = can_set_timing_data(can_dev, &timing_data);
	if (ret != 0) {
		last_config_step = "can_set_timing_data(data)";
		return ret;
	}

	sample_point = timing_sample_point_permille(&timing_data);
	cdc_printf("data timing override bitrate=%u target_sp=%u.%u%% actual_sp=%u.%u%% brp=%u seg1=%u seg2=%u sjw=%u calc_err=%d\r\n",
		   new_cfg->data_bitrate,
		   target_sample_point / 10U, target_sample_point % 10U,
		   sample_point / 10U, sample_point % 10U,
		   timing_data.prescaler, timing_data.prop_seg + timing_data.phase_seg1,
		   timing_data.phase_seg2, timing_data.sjw, calc_err);

	return 0;
}

static int set_nominal_bitrate(const struct test_config *new_cfg)
{
	struct can_timing timing = { 0 };
	uint16_t target_sample_point;
	bool predefined_timing = false;
	uint32_t sample_point;
	int calc_err;
	int ret;

	if (new_cfg->nominal_bitrate == CAN_NOMINAL_1M_BITRATE) {
		target_sample_point = CAN_NOMINAL_1M_SAMPLE_POINT;
		timing.prescaler = 5U;
		timing.phase_seg1 = 14U;
		timing.phase_seg2 = 5U;
		timing.sjw = 2U;
		predefined_timing = true;
	} else if (new_cfg->nominal_bitrate == CAN_NOMINAL_500K_BITRATE) {
		target_sample_point = CAN_NOMINAL_500K_SAMPLE_POINT;
	} else {
		return can_set_bitrate(can_dev, new_cfg->nominal_bitrate);
	}

	if (predefined_timing) {
		calc_err = 0;
	} else {
		ret = can_calc_timing(can_dev, &timing, new_cfg->nominal_bitrate,
				      target_sample_point);
		if (ret < 0) {
			last_config_step = "can_calc_timing(nominal)";
			return ret;
		}
		calc_err = ret;
	}

	ret = can_set_timing(can_dev, &timing);
	if (ret != 0) {
		last_config_step = "can_set_timing(nominal)";
		return ret;
	}

	sample_point = timing_sample_point_permille(&timing);
	cdc_printf("nominal timing override bitrate=%u target_sp=%u.%u%% actual_sp=%u.%u%% brp=%u seg1=%u seg2=%u sjw=%u calc_err=%d\r\n",
		   new_cfg->nominal_bitrate,
		   target_sample_point / 10U, target_sample_point % 10U,
		   sample_point / 10U, sample_point % 10U,
		   timing.prescaler, timing.prop_seg + timing.phase_seg1,
		   timing.phase_seg2, timing.sjw, calc_err);

	return 0;
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

static int configure_and_start_can(const struct test_config *new_cfg)
{
	can_mode_t can_mode = 0;
	int ret;

	if (new_cfg->format != FRAME_CLASSIC_CAN) {
		can_mode |= CAN_MODE_FD;
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

	ret = set_nominal_bitrate(new_cfg);
	if (ret != 0) {
		last_config_step = "set_nominal_bitrate";
		return ret;
	}

	if (new_cfg->format != FRAME_CLASSIC_CAN) {
		ret = set_data_bitrate(new_cfg);
		if (ret != 0) {
			last_config_step = "set_data_bitrate";
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

/* ===================================================================== */
/* RX filters and callbacks.                                             */
/* ===================================================================== */

static void echo_rx_callback(const struct device *dev, struct can_frame *frame,
			     void *user_data)
{
	uint8_t payload_len = can_dlc_to_bytes(frame->dlc);

	ARG_UNUSED(dev);
	ARG_UNUSED(user_data);

	atomic_inc(&echoed);

	if (payload_len < 8U || sys_get_le32(&frame->data[0]) != TEST_MAGIC) {
		return;
	}

	uint32_t seq = sys_get_le32(&frame->data[4]);

	if (echo_have_seq) {
		uint32_t expected = echo_last_seq + 1U;

		if (seq != expected) {
			atomic_add(&echo_gap, seq > expected ? seq - expected : 1U);
		}
	}

	echo_last_seq = seq;
	echo_have_seq = true;

	for (uint8_t i = 12U; i < payload_len; i++) {
		if (frame->data[i] != (uint8_t)(0xa5U ^ i ^ seq)) {
			atomic_inc(&echo_content_err);
			break;
		}
	}
}

static void init_tx_callback(const struct device *dev, int error, void *user_data)
{
	ARG_UNUSED(dev);
	ARG_UNUSED(user_data);

	if (error == 0) {
		atomic_inc(&tx_ok);
	} else {
		atomic_inc(&tx_callback_err);
	}

	k_sem_give(&tx_sem);
}

static void resp_rx_callback(const struct device *dev, struct can_frame *frame,
			     void *user_data)
{
	ARG_UNUSED(dev);
	ARG_UNUSED(user_data);

	atomic_inc(&resp_rx);

	if (k_msgq_put(&echo_q, frame, K_NO_WAIT) != 0) {
		atomic_inc(&resp_dropped);
	}
}

static void echo_tx_callback(const struct device *dev, int error, void *user_data)
{
	ARG_UNUSED(dev);
	ARG_UNUSED(user_data);

	if (error == 0) {
		atomic_inc(&resp_echoed);
	} else {
		atomic_inc(&resp_echo_err);
	}

	k_sem_give(&tx_sem);
}

/* ===================================================================== */
/* Worker threads.                                                       */
/* ===================================================================== */

static void build_test_frame(struct can_frame *frame, uint32_t seq)
{
	uint8_t payload_len = payload_len_for_format(cfg.format);

	memset(frame, 0, sizeof(*frame));
	frame->id = cfg.init_id;

	if (cfg.format == FRAME_FD_NO_BRS) {
		frame->flags = CAN_FRAME_FDF;
	} else if (cfg.format == FRAME_FD_BRS) {
		frame->flags = CAN_FRAME_FDF | CAN_FRAME_BRS;
	} else {
		frame->flags = 0;
	}

	frame->dlc = can_bytes_to_dlc(payload_len);
	fill_payload(frame, seq, payload_len);
}

static void report_initiator_result(void)
{
	struct can_bus_err_cnt err_cnt = { 0 };
	enum can_state state = CAN_STATE_STOPPED;
	uint32_t sent = init_sent;
	long got = atomic_get(&echoed);
	uint32_t loss = sent > (uint32_t)got ? sent - (uint32_t)got : 0U;
	long txfail = atomic_get(&tx_enqueue_fail) + atomic_get(&tx_callback_err);
	bool pass;

	(void)can_get_state(can_dev, &state, &err_cnt);

	pass = (loss == 0U) && (atomic_get(&echo_content_err) == 0) &&
	       (state != CAN_STATE_BUS_OFF) && (state != CAN_STATE_STOPPED);

	cdc_puts("\r\n==== ROUND-TRIP RESULT ====\r\n");
	cdc_printf("nominal=%u data=%u %s sent=%u echoed=%ld loss=%u\r\n",
		   cfg.nominal_bitrate, cfg.data_bitrate, format_to_str(cfg.format),
		   sent, got, loss);
	cdc_printf("gap=%ld content_err=%ld tx_fail=%ld state=%s rxerr=%u txerr=%u\r\n",
		   atomic_get(&echo_gap), atomic_get(&echo_content_err), txfail,
		   state_to_str(state), err_cnt.rx_err_cnt, err_cnt.tx_err_cnt);

#ifdef CONFIG_CAN_STATS
	cdc_printf("can_stats bit=%u bit0=%u bit1=%u stuff=%u crc=%u form=%u ack=%u rx_overrun=%u\r\n",
		   can_stats_get_bit_errors(can_dev),
		   can_stats_get_bit0_errors(can_dev),
		   can_stats_get_bit1_errors(can_dev),
		   can_stats_get_stuff_errors(can_dev),
		   can_stats_get_crc_errors(can_dev),
		   can_stats_get_form_errors(can_dev),
		   can_stats_get_ack_errors(can_dev),
		   can_stats_get_rx_overruns(can_dev));
#endif

	cdc_printf("==== %s ====\r\n\r\n", pass ? "PASS" : "FAIL");

	if (!pass) {
		cdc_puts("TDCR note: TDCR=0000 at high data bitrate + BRS means Transmitter\r\n"
			 "  Delay Compensation is OFF -- prime suspect for 5M+BRS failure.\r\n"
			 "  lec/dlec in PSR above show the last protocol error type.\r\n");
		dump_core_clock("fail");
		dump_regs("fail");
	}
}

static void tx_thread(void *arg1, void *arg2, void *arg3)
{
	ARG_UNUSED(arg1);
	ARG_UNUSED(arg2);
	ARG_UNUSED(arg3);

	while (true) {
		struct can_frame frame;
		uint32_t seq;
		int ret;

		if (atomic_get(&role) != ROLE_INITIATOR || !atomic_get(&running)) {
			k_sleep(K_MSEC(100));
			continue;
		}

		if (init_sent < cfg.count) {
			k_mutex_lock(&cfg_lock, K_FOREVER);
			seq = tx_seq++;
			build_test_frame(&frame, seq);
			k_mutex_unlock(&cfg_lock);

			if (k_sem_take(&tx_sem, K_MSEC(100)) != 0) {
				atomic_inc(&tx_enqueue_fail);
				k_sleep(K_MSEC(1));
				continue;
			}

			ret = can_send(can_dev, &frame, K_NO_WAIT, init_tx_callback, NULL);
			if (ret != 0) {
				atomic_inc(&tx_enqueue_fail);
				k_sem_give(&tx_sem);
				k_sleep(K_MSEC(1));
				continue;
			}

			init_sent++;

			if (cfg.fps != 0U) {
				k_sleep(K_USEC(1000000U / cfg.fps));
			}
		} else if (!result_printed) {
			k_sleep(K_MSEC(DRAIN_MS));
			report_initiator_result();
			result_printed = true;
			atomic_set(&running, 0);
		} else {
			k_sleep(K_MSEC(100));
		}
	}
}

static void echo_thread(void *arg1, void *arg2, void *arg3)
{
	ARG_UNUSED(arg1);
	ARG_UNUSED(arg2);
	ARG_UNUSED(arg3);

	while (true) {
		struct can_frame frame;
		int ret;

		if (atomic_get(&role) != ROLE_RESPONDER || !atomic_get(&running)) {
			k_sleep(K_MSEC(100));
			continue;
		}

		if (k_msgq_get(&echo_q, &frame, K_MSEC(100)) != 0) {
			continue;
		}

		/* Echo verbatim on echo_id; keep flags (FDF/BRS), dlc, data. */
		frame.id = cfg.echo_id;

		if (k_sem_take(&tx_sem, K_MSEC(100)) != 0) {
			atomic_inc(&resp_dropped);
			continue;
		}

		ret = can_send(can_dev, &frame, K_NO_WAIT, echo_tx_callback, NULL);
		if (ret != 0) {
			atomic_inc(&resp_dropped);
			k_sem_give(&tx_sem);
			k_sleep(K_MSEC(1));
		}
	}
}

/* ===================================================================== */
/* Run control.                                                          */
/* ===================================================================== */

static void reset_initiator_counters(void)
{
	atomic_set(&echoed, 0);
	atomic_set(&echo_gap, 0);
	atomic_set(&echo_content_err, 0);
	atomic_set(&tx_ok, 0);
	atomic_set(&tx_enqueue_fail, 0);
	atomic_set(&tx_callback_err, 0);
	init_sent = 0;
	tx_seq = 0;
	echo_last_seq = 0;
	echo_have_seq = false;
	result_printed = false;
}

static void reset_responder_counters(void)
{
	atomic_set(&resp_rx, 0);
	atomic_set(&resp_echoed, 0);
	atomic_set(&resp_dropped, 0);
	atomic_set(&resp_echo_err, 0);
	k_msgq_purge(&echo_q);
}

static void remove_rx_filter_if_needed(void)
{
	if (rx_filter_id >= 0) {
		can_remove_rx_filter(can_dev, rx_filter_id);
		rx_filter_id = -1;
	}
}

static void stop_run(bool print_summary)
{
	k_mutex_lock(&cfg_lock, K_FOREVER);
	atomic_set(&running, 0);
	if (print_summary) {
		cdc_printf("stopped role=%s\r\n", role_to_str(atomic_get(&role)));
	}
	remove_rx_filter_if_needed();
	(void)stop_can_if_needed();
	atomic_set(&role, ROLE_NONE);
	k_mutex_unlock(&cfg_lock);
}

static int start_role(enum role r, struct test_config *new_cfg)
{
	const struct can_filter filter = {
		.flags = 0,
		.id = (r == ROLE_INITIATOR) ? new_cfg->echo_id : new_cfg->init_id,
		.mask = CAN_STD_ID_MASK,
	};
	int ret;

	k_mutex_lock(&cfg_lock, K_FOREVER);
	atomic_set(&running, 0);
	remove_rx_filter_if_needed();

	if (r == ROLE_INITIATOR) {
		reset_initiator_counters();
	} else {
		reset_responder_counters();
	}

	cfg = *new_cfg;
	k_sem_init(&tx_sem, TX_QUEUE_DEPTH, TX_QUEUE_DEPTH);

	ret = configure_and_start_can(&cfg);
	if (ret == 0) {
		rx_filter_id = can_add_rx_filter(can_dev,
						 r == ROLE_INITIATOR ? echo_rx_callback : resp_rx_callback,
						 NULL, &filter);
		if (rx_filter_id < 0) {
			cdc_printf("can_add_rx_filter failed: %d\r\n", rx_filter_id);
			(void)stop_can_if_needed();
			k_mutex_unlock(&cfg_lock);
			return rx_filter_id;
		}
		atomic_set(&role, r);
		atomic_set(&running, 1);
	}
	k_mutex_unlock(&cfg_lock);

	if (ret != 0) {
		cdc_printf("failed to configure/start CAN at %s: %d\r\n",
			   last_config_step ? last_config_step : "unknown", ret);
		return ret;
	}

	cdc_printf("started role=%s format=%s nominal=%u data=%u init_id=0x%03x echo_id=0x%03x%s\r\n",
		   role_to_str(r), format_to_str(cfg.format), cfg.nominal_bitrate, cfg.data_bitrate,
		   cfg.init_id, cfg.echo_id,
		   r == ROLE_INITIATOR ? "" : "  (echo loop until 'stop')");
	return 0;
}

/* ===================================================================== */
/* Command dispatch (line parser over CDC).                              */
/* ===================================================================== */

static void print_status(void)
{
	struct can_bus_err_cnt err_cnt = { 0 };
	enum can_state state = CAN_STATE_STOPPED;

	(void)can_get_state(can_dev, &state, &err_cnt);

	switch (atomic_get(&role)) {
	case ROLE_INITIATOR:
		cdc_printf("role=init format=%s nominal=%u data=%u sent=%u echoed=%ld gap=%ld content_err=%ld tx_fail=%ld running=%u state=%s rxerr=%u txerr=%u\r\n",
			   format_to_str(cfg.format), cfg.nominal_bitrate, cfg.data_bitrate,
			   init_sent, atomic_get(&echoed), atomic_get(&echo_gap),
			   atomic_get(&echo_content_err),
			   atomic_get(&tx_enqueue_fail) + atomic_get(&tx_callback_err),
			   atomic_get(&running), state_to_str(state),
			   err_cnt.rx_err_cnt, err_cnt.tx_err_cnt);
		break;
	case ROLE_RESPONDER:
		cdc_printf("role=reply format=%s nominal=%u data=%u rx=%ld echoed=%ld dropped=%ld echo_err=%ld running=%u state=%s rxerr=%u txerr=%u\r\n",
			   format_to_str(cfg.format), cfg.nominal_bitrate, cfg.data_bitrate,
			   atomic_get(&resp_rx), atomic_get(&resp_echoed),
			   atomic_get(&resp_dropped), atomic_get(&resp_echo_err),
			   atomic_get(&running), state_to_str(state),
			   err_cnt.rx_err_cnt, err_cnt.tx_err_cnt);
		break;
	default:
		cdc_printf("idle state=%s\r\n", state_to_str(state));
		break;
	}
}

static void print_help(void)
{
	cdc_puts(
		"two-board CAN round-trip. Same image on two boards.\r\n"
		"  init <nominal> <data> <can|fd|fd-brs> [count] [fps]   (initiator)\r\n"
		"  reply <nominal> <data> <can|fd|fd-brs>                (responder)\r\n"
		"  stop | status | id [init] [echo] | clock | regs | help\r\n"
		"example: init 500000 2000000 fd-brs   /   reply 500000 2000000 fd-brs\r\n"
		"failing combos to probe: 1M/1M and 500k/5M fd-brs\r\n");
}

static bool parse_rates(int argc, char **argv, struct test_config *c)
{
	uint32_t nominal;
	uint32_t data;

	if (parse_u32(argv[1], &nominal) != 0) {
		cdc_puts("err: invalid nominal bitrate\r\n");
		return false;
	}
	if (parse_u32(argv[2], &data) != 0) {
		cdc_puts("err: invalid data bitrate\r\n");
		return false;
	}
	if (!parse_format(argv[3], &c->format)) {
		cdc_puts("err: format must be can, fd, or fd-brs\r\n");
		return false;
	}
	if (c->format == FRAME_CLASSIC_CAN && data != 0U && data != nominal) {
		cdc_puts("err: classic CAN ignores data bitrate (pass 0 or = nominal)\r\n");
		return false;
	}

	c->nominal_bitrate = nominal;
	c->data_bitrate = data;
	return true;
}

static void handle_line(char *line)
{
	char *argv[8];
	char *save;
	char *tok;
	char *end;
	int argc = 0;

	/* Diagnostic + UX: echo the received line. The length reveals any hidden
	 * CR/LF/space that the terminal prepends/appends but you can't see.
	 */
	cdc_printf("[rx %u] %s\r\n", (unsigned)strlen(line), line);

	/* Sanitize: strip leading/trailing whitespace, CR, LF in place -- so a
	 * terminal that sends "init\r\n" or " init " still parses argv[0]=="init".
	 */
	while (*line == ' ' || *line == '\t' || *line == '\r' || *line == '\n') {
		line++;
	}
	end = line + strlen(line);
	while (end > line &&
	       (end[-1] == ' ' || end[-1] == '\t' || end[-1] == '\r' || end[-1] == '\n')) {
		*--end = '\0';
	}

	tok = strtok_r(line, " \t\r\n", &save);
	while (tok != NULL && argc < 8) {
		argv[argc++] = tok;
		tok = strtok_r(NULL, " \t\r\n", &save);
	}

	if (argc == 0) {
		return;
	}

	if (strcmp(argv[0], "init") == 0) {
		struct test_config c = cfg;
		uint32_t parsed;

		if (argc < 4) {
			cdc_puts("usage: init <nominal> <data> <can|fd|fd-brs> [count] [fps]\r\n");
			return;
		}
		if (!parse_rates(argc, argv, &c)) {
			return;
		}
		c.count = (argc > 4 && parse_u32(argv[4], &parsed) == 0 && parsed > 0U)
				  ? parsed : DEFAULT_COUNT;
		c.fps = (argc > 5 && parse_u32(argv[5], &parsed) == 0) ? parsed : 0U;
		(void)start_role(ROLE_INITIATOR, &c);
	} else if (strcmp(argv[0], "reply") == 0) {
		struct test_config c = cfg;

		if (argc < 4) {
			cdc_puts("usage: reply <nominal> <data> <can|fd|fd-brs>\r\n");
			return;
		}
		if (!parse_rates(argc, argv, &c)) {
			return;
		}
		(void)start_role(ROLE_RESPONDER, &c);
	} else if (strcmp(argv[0], "stop") == 0) {
		stop_run(true);
	} else if (strcmp(argv[0], "status") == 0) {
		print_status();
	} else if (strcmp(argv[0], "id") == 0) {
		uint32_t init_id;
		uint32_t echo_id;

		if (argc == 1) {
			cdc_printf("init_id=0x%03x echo_id=0x%03x\r\n", cfg.init_id, cfg.echo_id);
			return;
		}
		if (parse_can_id_hex(argv[1], &init_id) != 0) {
			cdc_puts("err: init id must be hex 0..7ff (e.g. 504)\r\n");
			return;
		}
		if (argc > 2) {
			if (parse_can_id_hex(argv[2], &echo_id) != 0) {
				cdc_puts("err: echo id must be hex 0..7ff (e.g. 505)\r\n");
				return;
			}
		} else {
			echo_id = (init_id == DEFAULT_INIT_ID) ? DEFAULT_ECHO_ID : init_id + 1U;
		}
		if (init_id == echo_id) {
			cdc_puts("err: init id and echo id must differ\r\n");
			return;
		}
		k_mutex_lock(&cfg_lock, K_FOREVER);
		cfg.init_id = init_id;
		cfg.echo_id = echo_id;
		k_mutex_unlock(&cfg_lock);
		cdc_printf("init_id=0x%03x echo_id=0x%03x\r\n", cfg.init_id, cfg.echo_id);
	} else if (strcmp(argv[0], "clock") == 0) {
		dump_core_clock("diag");
	} else if (strcmp(argv[0], "regs") == 0) {
		dump_core_clock("diag");
		dump_regs("diag");
	} else if (strcmp(argv[0], "help") == 0 || strcmp(argv[0], "?") == 0) {
		print_help();
	} else {
		cdc_printf("unknown cmd '%s' (try 'help')\r\n", argv[0]);
	}
}

static void cmd_thread(void *arg1, void *arg2, void *arg3)
{
	struct cmd_item item;

	ARG_UNUSED(arg1);
	ARG_UNUSED(arg2);
	ARG_UNUSED(arg3);

	while (k_msgq_get(&cdc_cmdq, &item, K_FOREVER) == 0) {
		handle_line(item.buf);
	}
}

/* ===================================================================== */
/* main.                                                                 */
/* ===================================================================== */

int main(void)
{
	if (!device_is_ready(can_dev)) {
		cdc_puts("CAN device not ready\r\n");
		return 0;
	}
	if (!device_is_ready(cdc_dev)) {
		return 0; /* printk-less: nothing to say if CDC itself is down */
	}

	k_mutex_init(&cfg_lock);
	k_sem_init(&tx_sem, TX_QUEUE_DEPTH, TX_QUEUE_DEPTH);
	ring_buf_init(&cdc_tx_rb, sizeof(cdc_tx_buf), cdc_tx_buf);

	(void)uart_irq_callback_user_data_set(cdc_dev, cdc_isr, NULL);
	uart_irq_rx_enable(cdc_dev);
#ifdef CONFIG_UART_LINE_CTRL
	(void)uart_line_ctrl_set(cdc_dev, UART_LINE_CTRL_DCD, 1);
	(void)uart_line_ctrl_set(cdc_dev, UART_LINE_CTRL_DSR, 1);
#endif

	k_thread_create(&tx_thread_data, tx_thread_stack,
			K_THREAD_STACK_SIZEOF(tx_thread_stack),
			tx_thread, NULL, NULL, NULL, THREAD_PRIORITY, 0, K_NO_WAIT);
	k_thread_create(&echo_thread_data, echo_thread_stack,
			K_THREAD_STACK_SIZEOF(echo_thread_stack),
			echo_thread, NULL, NULL, NULL, THREAD_PRIORITY, 0, K_NO_WAIT);
	k_thread_create(&cmd_thread_data, cmd_thread_stack,
			K_THREAD_STACK_SIZEOF(cmd_thread_stack),
			cmd_thread, NULL, NULL, NULL, CMD_PRIORITY, 0, K_NO_WAIT);

	cdc_puts("\r\n========================================\r\n");
	cdc_printf("XIAO STM32C5 two-board CAN round-trip fw=%s\r\n", FW_VERSION);
	cdc_puts("USB CDC ACM. Open this COM port, then type commands.\r\n");
	cdc_puts("----------------------------------------\r\n");
	cdc_puts("Wire CANH/CANH, CANL/CANL, GND/GND, 120R both ends.\r\n");
	cdc_puts("  Board A: init  500000 2000000 fd-brs\r\n");
	cdc_puts("  Board B: reply 500000 2000000 fd-brs\r\n");
	cdc_puts("Then try the failing combos: 1M/1M and 500k/5M fd-brs.\r\n");
	cdc_puts("(type 'help')\r\n");
	cdc_puts("========================================\r\n\r\n");

	return 0;
}
