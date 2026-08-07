/*
 * Button adapter for the XIAO nRF54LM20B gesture-recognition sample.
 *
 * It keeps the official button module API, but adds visible press/release
 * logs and a release-time long-press fallback.  The fallback matters during
 * BLE pairing because the pairing window is short and the button is the only
 * confirmation path.
 */

#include "button/button.h"

#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/util.h>

LOG_MODULE_REGISTER(button, CONFIG_LOG_DEFAULT_LEVEL);

#define SW0_NODE DT_ALIAS(sw0)
#if !DT_NODE_HAS_STATUS(SW0_NODE, okay)
#error "Unsupported board: sw0 devicetree alias is not defined"
#endif

#define BUTTON_DEBOUNCE_MSEC 50
#define BUTTON_CHECK_PERIOD_MSEC 100

static const struct gpio_dt_spec button_sw0 = GPIO_DT_SPEC_GET_OR(SW0_NODE, gpios, {0});

static struct gpio_callback button_cb_data;
static struct k_work_delayable button_check_work;

static button_click_handler_t button_click_handler;
static bool button_pressed_state;
static int64_t press_start_uptime_ms;
static bool long_already_reported;

static void emit_click(button_click_t click)
{
	LOG_INF("Button click: %s", click == BUTTON_CLICK_LONG ? "LONG" : "SHORT");

	if (button_click_handler != NULL) {
		button_click_handler(click);
	} else {
		LOG_WRN("Click detected but no handler registered");
	}
}

static int read_button_pressed(bool *pressed)
{
	int logical = gpio_pin_get_dt(&button_sw0);

	if (logical < 0) {
		LOG_ERR("Failed to read button pin (err %d)", logical);
		return logical;
	}

	*pressed = (logical != 0);
	return 0;
}

static void handle_press_edge(int64_t now_ms)
{
	if (button_pressed_state) {
		return;
	}

	button_pressed_state = true;
	press_start_uptime_ms = now_ms;
	long_already_reported = false;

	LOG_INF("Button pressed");
	k_work_reschedule(&button_check_work, K_MSEC(BUTTON_CHECK_PERIOD_MSEC));
}

static void handle_release_edge(int64_t now_ms)
{
	int64_t held_ms;

	if (!button_pressed_state) {
		LOG_INF("Button release ignored; no debounced press was active");
		return;
	}

	held_ms = now_ms - press_start_uptime_ms;
	button_pressed_state = false;
	(void)k_work_cancel_delayable(&button_check_work);

	LOG_INF("Button released after %lld ms", (long long)held_ms);

	if (long_already_reported) {
		return;
	}

	if (held_ms >= BUTTON_LONG_CLICK_MSEC) {
		emit_click(BUTTON_CLICK_LONG);
	} else if (held_ms < BUTTON_SHORT_CLICK_MSEC) {
		emit_click(BUTTON_CLICK_SHORT);
	} else {
		LOG_INF("Button click ignored after %lld ms", (long long)held_ms);
	}
}

static void button_check_work_fn(struct k_work *work)
{
	bool sampled_pressed;
	int ret;
	int64_t now_ms;

	ARG_UNUSED(work);

	ret = read_button_pressed(&sampled_pressed);
	if (ret != 0) {
		return;
	}

	now_ms = k_uptime_get();

	if (sampled_pressed != button_pressed_state) {
		if (sampled_pressed) {
			handle_press_edge(now_ms);
		} else {
			handle_release_edge(now_ms);
		}
		return;
	}

	if (button_pressed_state) {
		int64_t held_ms = now_ms - press_start_uptime_ms;

		if (!long_already_reported && held_ms >= BUTTON_LONG_CLICK_MSEC) {
			long_already_reported = true;
			LOG_INF("Button long threshold reached after %lld ms", (long long)held_ms);
			emit_click(BUTTON_CLICK_LONG);
		}

		k_work_reschedule(&button_check_work, K_MSEC(BUTTON_CHECK_PERIOD_MSEC));
	}
}

static void button_isr(const struct device *dev, struct gpio_callback *cb, uint32_t pins)
{
	ARG_UNUSED(dev);
	ARG_UNUSED(cb);
	ARG_UNUSED(pins);

	k_work_reschedule(&button_check_work, K_MSEC(BUTTON_DEBOUNCE_MSEC));
}

int button_init(void)
{
	bool initially_pressed;
	int ret;

	if (!device_is_ready(button_sw0.port)) {
		LOG_ERR("Button GPIO device %s is not ready", button_sw0.port->name);
		return -ENODEV;
	}

	ret = gpio_pin_configure_dt(&button_sw0, GPIO_INPUT);
	if (ret != 0) {
		LOG_ERR("Failed to configure button pin %u (err %d)", button_sw0.pin, ret);
		return ret;
	}

	ret = read_button_pressed(&initially_pressed);
	if (ret != 0) {
		return ret;
	}

	button_pressed_state = initially_pressed;
	press_start_uptime_ms = initially_pressed ? k_uptime_get() : 0;
	long_already_reported = false;

	k_work_init_delayable(&button_check_work, button_check_work_fn);

	gpio_init_callback(&button_cb_data, button_isr, BIT(button_sw0.pin));
	ret = gpio_add_callback(button_sw0.port, &button_cb_data);
	if (ret != 0) {
		LOG_ERR("Failed to add GPIO callback (err %d)", ret);
		return ret;
	}

	ret = gpio_pin_interrupt_configure_dt(&button_sw0, GPIO_INT_EDGE_BOTH);
	if (ret != 0) {
		LOG_ERR("Failed to configure interrupt on button pin %u (err %d)",
			button_sw0.pin, ret);
		return ret;
	}

	LOG_INF("Button ready on %s pin %u, initial state: %s",
		button_sw0.port->name, button_sw0.pin,
		initially_pressed ? "pressed" : "released");

	if (initially_pressed) {
		k_work_reschedule(&button_check_work, K_MSEC(BUTTON_CHECK_PERIOD_MSEC));
	}

	return 0;
}

void button_reg_click_handler(button_click_handler_t click_handler)
{
	button_click_handler = click_handler;
}
