/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * XIAO STM32C5 SLCAN (Lawicel) USB<->CAN bridge.
 *
 * Bridges the on-board FDCAN2 (RX=PB5 / TX=PB13, transceiver STB=PB14) to a
 * host over USB CDC ACM, speaking the Lawicel SLCAN ASCII protocol.
 *
 * Host side:
 *   SavvyCAN   : Add Connection -> Lawicel / SLCAN, pick the COM/tty port.
 *   python-can : can.Bus(interface='slcan', channel='/dev/ttyACM0', bitrate=500000)
 *   SocketCAN : slcand -o -s5 -c /dev/ttyACM0 can0 && sudo ip link set can0 up
 *
 * Classic CAN only here: Lawicel SLCAN has no standard FD framing. For CAN FD
 * use the gs_usb firmware variant (firmware A / CANnectivity). Bitrate is set
 * by the S0..S8 Lawicel presets.
 *
 * Power-on default: bitrate 500 kbps, CAN stopped. Go on-bus with:
 *   S5\r   (select 500 kbps)   then   O\r   (open)
 */

#include <ctype.h>
#include <errno.h>
#include <stdint.h>
#include <string.h>

#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/can.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/printk.h>
#include <zephyr/sys/ring_buffer.h>

#define CANBUS_NODE  DT_CHOSEN(zephyr_canbus)

#define CDC_TX_RING_SIZE   1024U
#define SLCAN_LINE_MAX      128U
#define SLCAN_CMDQ_DEPTH      8U
#define CMD_STACK           1536U
#define CMD_PRIO               2U

#define CAN_BITRATE_DEFAULT  500000U

/* Lawicel S0..S8 bitrates. */
static const uint32_t slcan_presets[] = {
	10000U, 20000U, 50000U, 100000U, 125000U,
	250000U, 500000U, 800000U, 1000000U,
};

struct cmd_item {
	char buf[SLCAN_LINE_MAX];
	uint8_t len;
};

static const struct device *const can_dev = DEVICE_DT_GET(CANBUS_NODE);
static const struct device *const cdc_dev = DEVICE_DT_GET_ONE(zephyr_cdc_acm_uart);

static struct ring_buf cdc_tx_rb;
static uint8_t cdc_tx_buf[CDC_TX_RING_SIZE];

K_MSGQ_DEFINE(slcan_cmdq, sizeof(struct cmd_item), SLCAN_CMDQ_DEPTH, 4);

static atomic_t can_started;
static uint32_t can_bitrate = CAN_BITRATE_DEFAULT;

/* CDC RX line accumulator (touched only from the CDC ISR). */
static uint8_t rx_line[SLCAN_LINE_MAX];
static uint8_t rx_line_len;

static void slcan_cmd_thread(void *a1, void *a2, void *a3);
static void cdc_isr(const struct device *dev, void *user_data);
static void can_rx_cb(const struct device *dev, struct can_frame *frame, void *user_data);
static void tx_cb(const struct device *dev, int error, void *user_data);

K_THREAD_DEFINE(slcan_cmd, CMD_STACK, slcan_cmd_thread, NULL, NULL, NULL, CMD_PRIO, 0, 0);

/* ---- helpers ---- */

/* ring_buf has multiple producers (CAN ISR + cmd thread) and one consumer
 * (CDC TX ISR); the producers share the write pointer, so lock around puts.
 */
static void cdc_tx_push(const uint8_t *data, size_t len)
{
	unsigned int key = irq_lock();
	size_t stored = ring_buf_put(&cdc_tx_rb, data, len);
	irq_unlock(key);

	if (stored > 0U) {
		uart_irq_tx_enable(cdc_dev);
	}
	/* TODO: account for dropped bytes when stored < len. */
}

static int hexval(char c)
{
	if (c >= '0' && c <= '9') {
		return c - '0';
	}
	if (c >= 'A' && c <= 'F') {
		return c - 'A' + 10;
	}
	if (c >= 'a' && c <= 'f') {
		return c - 'a' + 10;
	}
	return -1;
}

/* Write fixed-width uppercase hex into p; returns width. */
static int put_hex(char *p, uint32_t v, int width)
{
	for (int i = width - 1; i >= 0; i--) {
		p[i] = "0123456789ABCDEF"[v & 0xFU];
		v >>= 4;
	}
	return width;
}

static void reply_ok(void)
{
	uint8_t c = '\r';
	cdc_tx_push(&c, 1U);
}

static void reply_err(void)
{
	uint8_t c = 0x07U; /* BEL */
	cdc_tx_push(&c, 1U);
}

/* ---- CAN RX -> SLCAN text ---- */

static void can_rx_cb(const struct device *dev, struct can_frame *frame, void *user_data)
{
	ARG_UNUSED(dev);
	ARG_UNUSED(user_data);

	char line[SLCAN_LINE_MAX];
	int n = 0;
	bool ext = (frame->flags & CAN_FRAME_IDE) != 0U;
	bool rtr = (frame->flags & CAN_FRAME_RTR) != 0U;

	line[n++] = rtr ? (ext ? 'R' : 'r') : (ext ? 'T' : 't');
	n += put_hex(&line[n], ext ? frame->id : (frame->id & CAN_STD_ID_MASK),
		    ext ? 8 : 3);
	line[n++] = "0123456789ABCDEF"[frame->dlc & 0xFU];

	if (!rtr) {
		uint8_t bytes = can_dlc_to_bytes(frame->dlc);

		for (uint8_t i = 0U; i < bytes; i++) {
			n += put_hex(&line[n], frame->data[i], 2);
		}
	}
	line[n++] = '\r';

	cdc_tx_push((uint8_t *)line, (size_t)n);
}

/* ---- SLCAN text -> CAN TX ---- */

static int parse_id(const char *s, int idw, uint32_t *out)
{
	uint32_t id = 0U;

	for (int i = 0; i < idw; i++) {
		int h = hexval(s[1 + i]);

		if (h < 0) {
			return -1;
		}
		id = (id << 4) | (uint32_t)h;
	}
	*out = id;
	return 0;
}

static int slcan_send(const char *s, bool rtr)
{
	bool ext = (s[0] == 'T') || (s[0] == 'R');
	int idw = ext ? 8 : 3;
	uint32_t id;

	if (parse_id(s, idw, &id) < 0) {
		return -1;
	}

	int dlcp = hexval(s[1 + idw]);
	if (dlcp < 0 || dlcp > 8) {
		return -1;
	}

	struct can_frame frame;

	memset(&frame, 0, sizeof(frame));
	frame.dlc = can_bytes_to_dlc((uint8_t)dlcp);
	if (ext) {
		frame.flags = CAN_FRAME_IDE;
		frame.id = id & CAN_EXT_ID_MASK;
	} else {
		frame.id = id & CAN_STD_ID_MASK;
	}
	if (rtr) {
		frame.flags |= CAN_FRAME_RTR;
	}

	if (!rtr) {
		for (int i = 0; i < dlcp; i++) {
			int hi = hexval(s[1 + idw + 1 + i * 2]);
			int lo = hexval(s[1 + idw + 1 + i * 2 + 1]);

			if (hi < 0 || lo < 0) {
				return -1;
			}
			frame.data[i] = (uint8_t)((hi << 4) | lo);
		}
	}

	if (!atomic_get(&can_started)) {
		return -1;
	}

	return can_send(can_dev, &frame, K_MSEC(50), tx_cb, NULL);
}

static void tx_cb(const struct device *dev, int error, void *user_data)
{
	ARG_UNUSED(dev);
	ARG_UNUSED(user_data);
	ARG_UNUSED(error);
}

/* ---- CDC interrupt handler ---- */

static void cdc_isr(const struct device *dev, void *user_data)
{
	ARG_UNUSED(user_data);

	uint8_t buf[64];
	int len;

	/* Zephyr 中断驱动 UART 标准模式：必须先 uart_irq_update + uart_irq_is_pending
	 * 作外壳，否则 rx/tx ready 不上报（之前 CDC 对任何命令都无响应的根因）。 */
	while (uart_irq_update(dev) && uart_irq_is_pending(dev)) {
		/* RX: 累积成行，CR/LF 结尾入队。Lawicel 大小写敏感，原样存（不 toupper）。 */
		if (uart_irq_rx_ready(dev)) {
			len = uart_fifo_read(dev, buf, sizeof(buf));
			for (int i = 0; i < len; i++) {
				uint8_t ch = buf[i];

				if (ch == '\r' || ch == '\n') {
					if (rx_line_len > 0U) {
						struct cmd_item item;

						memcpy(item.buf, rx_line, rx_line_len);
						item.buf[rx_line_len] = '\0';
						item.len = rx_line_len;
						(void)k_msgq_put(&slcan_cmdq, &item, K_NO_WAIT);
						rx_line_len = 0U;
					}
				} else if (rx_line_len < (SLCAN_LINE_MAX - 1U)) {
					rx_line[rx_line_len++] = ch;
				}
			}
		}

		/* TX: 排空 ring buffer；空了就关 TX 中断。 */
		if (uart_irq_tx_ready(dev)) {
			len = (int)ring_buf_get(&cdc_tx_rb, buf, sizeof(buf));
			if (len == 0U) {
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

/* ---- command thread ---- */

static void slcan_cmd_thread(void *a1, void *a2, void *a3)
{
	ARG_UNUSED(a1);
	ARG_UNUSED(a2);
	ARG_UNUSED(a3);

	struct cmd_item item;

	while (k_msgq_get(&slcan_cmdq, &item, K_FOREVER) == 0) {
		const char *s = item.buf;
		char cmd = s[0];
		int ret = 0;

		switch (cmd) {
		case 'O': /* open / go on-bus */
			if (!atomic_get(&can_started)) {
				ret = can_start(can_dev);
				if (ret == 0 || ret == -EALREADY) {
					atomic_set(&can_started, 1);
					ret = 0;
				}
			}
			break;
		case 'C': /* close / go off-bus */
			if (atomic_get(&can_started)) {
				ret = can_stop(can_dev);
				if (ret == 0 || ret == -EALREADY) {
					atomic_set(&can_started, 0);
					ret = 0;
				}
			}
			break;
		case 'S': { /* set bitrate preset S0..S8 */
			int idx = s[1] - '0';

			if (idx < 0 || idx > 8) {
				ret = -1;
				break;
			}
			bool was = atomic_get(&can_started);

			if (was) {
				(void)can_stop(can_dev);
			}
			ret = can_set_bitrate(can_dev, slcan_presets[idx]);
			if (ret == 0) {
				can_bitrate = slcan_presets[idx];
			}
			if (was && ret == 0) {
				ret = can_start(can_dev);
			}
			break;
		}
		case 't': /* TX standard 11-bit:  tiiiLdd.. */
		case 'T': /* TX extended 29-bit:  TiiiiiiiiLdd.. */
		case 'r': /* RTR standard */
		case 'R': /* RTR extended */
			ret = slcan_send(s, (cmd == 'r' || cmd == 'R'));
			break;
		case 'V': { /* firmware version */
			static const char v[] = "V1013\r";
			cdc_tx_push((const uint8_t *)v, sizeof(v) - 1);
			continue;
		}
		case 'N': { /* serial number */
			static const char v[] = "N0001\r";
			cdc_tx_push((const uint8_t *)v, sizeof(v) - 1);
			continue;
		}
		case 'F': { /* status flags */
			static const char v[] = "F00\r";
			cdc_tx_push((const uint8_t *)v, sizeof(v) - 1);
			continue;
		}
		case 'Z': /* timestamp toggle  */
		case 'M': /* acceptance code  */
		case 'm': /* acceptance mask  */
		case 'L': /* listen-only      */
		case 'l':
			/* accepted but not implemented beyond accept-all */
			break;
		default:
			ret = -1;
			break;
		}

		if (ret == 0) {
			reply_ok();
		} else {
			reply_err();
		}
	}
}

/* ---- main ---- */

int main(void)
{
	int ret;

	if (!device_is_ready(can_dev)) {
		printk("SLCAN: CAN device not ready\n");
		return 0;
	}
	if (!device_is_ready(cdc_dev)) {
		printk("SLCAN: CDC ACM device not ready\n");
		return 0;
	}

	ring_buf_init(&cdc_tx_rb, sizeof(cdc_tx_buf), cdc_tx_buf);

	ret = can_set_mode(can_dev, CAN_MODE_NORMAL);
	if (ret != 0) {
		printk("SLCAN: can_set_mode failed: %d\n", ret);
	}
	ret = can_set_bitrate(can_dev, can_bitrate);
	if (ret != 0) {
		printk("SLCAN: can_set_bitrate(%u) failed: %d\n", can_bitrate, ret);
	}

	static const struct can_filter accept_all_std = {
		.flags = 0,
		.id = 0,
		.mask = 0,
	};
	static const struct can_filter accept_all_ext = {
		.flags = CAN_FILTER_IDE,
		.id = 0,
		.mask = 0,
	};

	(void)can_add_rx_filter(can_dev, can_rx_cb, NULL, &accept_all_std);
	(void)can_add_rx_filter(can_dev, can_rx_cb, NULL, &accept_all_ext);

	(void)uart_irq_callback_user_data_set(cdc_dev, cdc_isr, NULL);
	uart_irq_rx_enable(cdc_dev);
#ifdef CONFIG_UART_LINE_CTRL
	(void)uart_line_ctrl_set(cdc_dev, UART_LINE_CTRL_DCD, 1);
	(void)uart_line_ctrl_set(cdc_dev, UART_LINE_CTRL_DSR, 1);
#endif

	printk("SLCAN bridge ready. Default %u bps, CAN stopped.\n", can_bitrate);
	printk("Open bus: send 'S5\\r' (500k) then 'O\\r'.\n");

	return 0;
}
