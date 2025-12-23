#include <zephyr/kernel.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/logging/log.h>
#include <zephyr/spinlock.h>

#include <zephyr/sys/atomic.h>

#include <string.h>

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/hci.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/bluetooth/gatt.h>

#include <string.h>

#define BT_UUID_ONOFF_VAL BT_UUID_128_ENCODE(0x8e7f1a23, 0x4b2c, 0x11ee, 0xbe56, 0x0242ac120002)
#define BT_UUID_ONOFF     BT_UUID_DECLARE_128(BT_UUID_ONOFF_VAL)
#define BT_UUID_ONOFF_ACTION_VAL \
    BT_UUID_128_ENCODE(0x8e7f1a24, 0x4b2c, 0x11ee, 0xbe56, 0x0242ac120002)
#define BT_UUID_ONOFF_ACTION BT_UUID_DECLARE_128(BT_UUID_ONOFF_ACTION_VAL)

#define BT_UUID_ONOFF_READ_VAL \
    BT_UUID_128_ENCODE(0x8e7f1a25, 0x4b2c, 0x11ee, 0xbe56, 0x0242ac120003)
#define BT_UUID_ONOFF_READ BT_UUID_DECLARE_128(BT_UUID_ONOFF_READ_VAL)

/* devicetree: user said led0/sw0 already exist */
#define LED0_NODE DT_ALIAS(led0)
#define SW0_NODE  DT_ALIAS(sw0)

static const struct gpio_dt_spec led0 = GPIO_DT_SPEC_GET_OR(LED0_NODE, gpios, { 0 });
static const struct gpio_dt_spec sw0 = GPIO_DT_SPEC_GET_OR(SW0_NODE, gpios, { 0 });

LOG_MODULE_REGISTER(app, LOG_LEVEL_DBG);

static bool gpio_ready(const struct gpio_dt_spec *spec);

/*
 * LED wiring contract (per user spec): physical GPIO level 0 -> LED ON, 1 -> LED OFF.
 * We therefore use gpio_pin_set_raw() (no DT active-low inversion).
 */
#define LED_PHYS_ON_LEVEL  (0)
#define LED_PHYS_OFF_LEVEL (1)

enum led_state {
	LED_STATE_SOLID_ON,
	LED_STATE_SOLID_OFF,
	LED_STATE_BLINK_2HZ,
};

static struct k_spinlock led_lock;
static enum led_state led_mode;
static uint8_t led_blink_phase;

static void led_set_physical_level(uint8_t level)
{
	if (!gpio_ready(&led0)) {
		return;
	}

	(void)gpio_pin_set_raw(led0.port, led0.pin, level);
}

static void led_timer_handler(struct k_timer *timer)
{
	ARG_UNUSED(timer);

	k_spinlock_key_t key = k_spin_lock(&led_lock);
	if (led_mode != LED_STATE_BLINK_2HZ) {
		k_spin_unlock(&led_lock, key);
		return;
	}

	led_blink_phase ^= 1U;
	uint8_t level = (led_blink_phase != 0U) ? LED_PHYS_OFF_LEVEL : LED_PHYS_ON_LEVEL;
	k_spin_unlock(&led_lock, key);

	led_set_physical_level(level);
}

K_TIMER_DEFINE(led_timer, led_timer_handler, NULL);

static void led_set_mode(enum led_state mode)
{
	if (!gpio_ready(&led0)) {
		return;
	}

	k_spinlock_key_t key = k_spin_lock(&led_lock);
	led_mode = mode;
	led_blink_phase = 0U;
	k_spin_unlock(&led_lock, key);

	k_timer_stop(&led_timer);

	switch (mode) {
	case LED_STATE_SOLID_ON:
		led_set_physical_level(LED_PHYS_ON_LEVEL);
		break;
	case LED_STATE_SOLID_OFF:
		led_set_physical_level(LED_PHYS_OFF_LEVEL);
		break;
	case LED_STATE_BLINK_2HZ:
		/* 2 Hz: 250 ms ON, 250 ms OFF */
		led_set_physical_level(LED_PHYS_ON_LEVEL);
		k_timer_start(&led_timer, K_MSEC(250), K_MSEC(250));
		break;
	default:
		break;
	}
}

static bool gpio_ready(const struct gpio_dt_spec *spec)
{
	return spec->port != NULL && device_is_ready(spec->port);
}

static int init_led0(void)
{
	if (!gpio_ready(&led0)) {
		LOG_ERR("led0 GPIO device not ready");
		return -ENODEV;
	}

	int err = gpio_pin_configure_dt(&led0, GPIO_OUTPUT);
	if (err) {
		return err;
	}

	/* Start from LED OFF (physical high). */
	led_set_physical_level(LED_PHYS_OFF_LEVEL);
	return 0;
}

/* Central role implementation (this project is lbs-central). */

static struct bt_conn *default_conn;
static uint16_t onoff_action_handle;
static uint16_t onoff_service_end_handle;
static uint16_t onoff_service_start_handle;

static struct gpio_callback sw0_cb;
static struct k_work button_work;
static struct k_work_delayable sw0_debounce_work;
static uint8_t remote_led_level = LED_PHYS_OFF_LEVEL;

static struct bt_gatt_discover_params svc_discover_params;
static struct bt_gatt_discover_params chrc_discover_params;
static struct k_work discover_work;
static struct bt_conn *discover_conn;
static bool onoff_service_found;
static bool onoff_action_found;

static atomic_t scanning;
static atomic_t connecting;
static struct k_work_delayable scan_retry_work;
static uint8_t scan_retry_attempt;

static struct bt_gatt_write_params write_params;

static void start_scan(void);
static void schedule_scan_retry(bool reset_backoff);
static void discover_onoff_service(struct bt_conn *conn);
static void discover_work_handler(struct k_work *work);
static void gatt_write_cb(struct bt_conn *conn, uint8_t err,
			  struct bt_gatt_write_params *params);

static void scan_retry_handler(struct k_work *work)
{
	ARG_UNUSED(work);
	start_scan();
}

static uint8_t led_level_toggle(uint8_t level)
{
	return (level == LED_PHYS_ON_LEVEL) ? LED_PHYS_OFF_LEVEL : LED_PHYS_ON_LEVEL;
}

static uint32_t backoff_delay_ms(uint8_t attempt, uint32_t base_ms, uint32_t max_ms,
				 uint8_t max_shift)
{
	uint32_t delay_ms = base_ms;
	uint8_t shift = (attempt < max_shift) ? attempt : max_shift;
	while (shift--) {
		delay_ms <<= 1U;
		if (delay_ms >= max_ms) {
			return max_ms;
		}
	}

	return (delay_ms > max_ms) ? max_ms : delay_ms;
}

static void button_work_handler(struct k_work *work)
{
	ARG_UNUSED(work);

	if (default_conn == NULL || onoff_action_handle == 0U) {
		LOG_DBG("button: no conn/handle yet (conn=%p handle=0x%04x)", (void *)default_conn,
			onoff_action_handle);
		return;
	}

	write_params.handle = onoff_action_handle;
	write_params.offset = 0U;
	write_params.data = &remote_led_level;
	write_params.length = sizeof(remote_led_level);
	write_params.func = gatt_write_cb;

	int err = bt_gatt_write(default_conn, &write_params);
	if (err) {
		LOG_ERR("GATT write (with rsp) start failed: %d", err);
	} else {
		LOG_INF("button: write started remote led=%u (handle=0x%04x)", remote_led_level,
			onoff_action_handle);
	}
}

static void gatt_write_cb(struct bt_conn *conn, uint8_t err,
			  struct bt_gatt_write_params *params)
{
	ARG_UNUSED(conn);
	ARG_UNUSED(params);

	if (err) {
		LOG_ERR("GATT write failed (att err 0x%02x)", err);
		return;
	}

	LOG_INF("GATT write ok (remote led=%u)", remote_led_level);
}

static void sw0_debounce_handler(struct k_work *work)
{
	ARG_UNUSED(work);

	/* gpio_pin_get_dt() returns the logical (DT-aware) value; active -> pressed. */
	int pressed = gpio_pin_get_dt(&sw0);
	if (pressed <= 0) {
		return;
	}

	remote_led_level = led_level_toggle(remote_led_level);
	LOG_DBG("button: debounced press, remote_led_level=%u", remote_led_level);
	k_work_submit(&button_work);
}

static void sw0_isr(const struct device *dev, struct gpio_callback *cb, uint32_t pins)
{
	ARG_UNUSED(dev);
	ARG_UNUSED(cb);
	ARG_UNUSED(pins);

	/* 30ms software debounce */
	k_work_reschedule(&sw0_debounce_work, K_MSEC(30));
}

static int init_sw0(void)
{
	if (!gpio_ready(&sw0)) {
		LOG_ERR("sw0 GPIO device not ready");
		return -ENODEV;
	}

	int err = gpio_pin_configure_dt(&sw0, GPIO_INPUT);
	if (err) {
		LOG_ERR("sw0 configure failed: %d", err);
		return err;
	}

	err = gpio_pin_interrupt_configure_dt(&sw0, GPIO_INT_EDGE_TO_ACTIVE);
	if (err) {
		LOG_ERR("sw0 interrupt config failed: %d", err);
		return err;
	}

	gpio_init_callback(&sw0_cb, sw0_isr, BIT(sw0.pin));
	err = gpio_add_callback(sw0.port, &sw0_cb);
	if (err) {
		LOG_ERR("sw0 add callback failed: %d", err);
		return err;
	}

	k_work_init(&button_work, button_work_handler);
	k_work_init_delayable(&sw0_debounce_work, sw0_debounce_handler);
	LOG_INF("sw0 ready (port=%s pin=%u)", sw0.port->name, sw0.pin);
	return 0;
}

static bool adv_has_onoff_uuid(struct bt_data *data, void *user_data)
{
	bool *found = user_data;

	if (data->type != BT_DATA_UUID128_ALL && data->type != BT_DATA_UUID128_SOME) {
		return true;
	}

	if (data->data_len % 16U != 0U) {
		return true;
	}

	struct bt_uuid_128 uuid;

	for (size_t i = 0; i < data->data_len; i += 16U) {
		memcpy(uuid.val, &data->data[i], 16U);
		uuid.uuid.type = BT_UUID_TYPE_128;

		if (bt_uuid_cmp(&uuid.uuid, BT_UUID_ONOFF) == 0) {
			*found = true;
			return false;
		}
	}

	return true;
}

static void device_found(const bt_addr_le_t *addr, int8_t rssi, uint8_t type,
			 struct net_buf_simple *ad)
{
	ARG_UNUSED(rssi);

	if (default_conn != NULL || atomic_get(&connecting)) {
		return;
	}

	/*
	 * Peripheral advertises the 128-bit service UUID in scan response (sd[]).
	 * With active scanning enabled, we must also accept SCAN_RSP reports.
	 */
	if (type != BT_GAP_ADV_TYPE_ADV_IND && type != BT_GAP_ADV_TYPE_ADV_DIRECT_IND &&
		type != BT_GAP_ADV_TYPE_ADV_SCAN_IND && type != BT_GAP_ADV_TYPE_SCAN_RSP) {
		return;
	}

	bool found = false;
	bt_data_parse(ad, adv_has_onoff_uuid, &found);
	if (!found) {
		return;
	}

	LOG_INF("found peripheral with ONOFF service; connecting...");

	/* Keep scanning indication separate: do not blink during connection attempt. */
	led_set_mode(LED_STATE_SOLID_ON);

	atomic_set(&connecting, 1);
	int err = bt_le_scan_stop();
	if (err) {
		LOG_ERR("scan stop failed: %d", err);
		/* Continue anyway; we may already be stopped. */
	}
	atomic_set(&scanning, 0);

	err = bt_conn_le_create(addr, BT_CONN_LE_CREATE_CONN, BT_LE_CONN_PARAM_DEFAULT,
				 &default_conn);
	if (err) {
		LOG_ERR("create conn failed: %d", err);
		atomic_set(&connecting, 0);
		led_set_mode(LED_STATE_SOLID_ON);
		schedule_scan_retry(false);
	}
}

static void start_scan(void)
{
	if (default_conn != NULL) {
		return;
	}

	if (atomic_cas(&scanning, 0, 1) == false) {
		return;
	}

	atomic_set(&connecting, 0);

	int err = bt_le_scan_start(BT_LE_SCAN_ACTIVE, device_found);
	if (err) {
		atomic_set(&scanning, 0);
		if (err == -EALREADY) {
			/* Treat as success (scan already running). */
			atomic_set(&scanning, 1);
			/* Scanning -> blink 2Hz. */
			led_set_mode(LED_STATE_BLINK_2HZ);
			LOG_INF("scanning...");
			return;
		}
		LOG_ERR("scan start failed: %d", err);
		schedule_scan_retry(false);
	} else {
		/* Scanning -> blink 2Hz. */
		led_set_mode(LED_STATE_BLINK_2HZ);
		LOG_INF("scanning...");
	}
}

static void schedule_scan_retry(bool reset_backoff)
{
	if (reset_backoff) {
		scan_retry_attempt = 0U;
	}

	uint32_t delay_ms = backoff_delay_ms(scan_retry_attempt, 200U, 5000U, 6U);

	if (scan_retry_attempt < 10U) {
		scan_retry_attempt++;
	}

	k_work_reschedule(&scan_retry_work, K_MSEC(delay_ms));
}

static uint8_t discover_func(struct bt_conn *conn, const struct bt_gatt_attr *attr,
				struct bt_gatt_discover_params *params)
{
	ARG_UNUSED(conn);

	if (attr == NULL) {
		if (params->type == BT_GATT_DISCOVER_PRIMARY) {
			if (!onoff_service_found) {
				LOG_ERR("ONOFF service not found during discovery; disconnecting");
				if (default_conn) {
					(void)bt_conn_disconnect(default_conn,
							      BT_HCI_ERR_REMOTE_USER_TERM_CONN);
				}
			} else {
				/* Start characteristic discovery only after service discovery is fully done. */
				k_work_submit(&discover_work);
			}
			memset(params, 0, sizeof(*params));
			return BT_GATT_ITER_STOP;
		}

		if (params->type == BT_GATT_DISCOVER_CHARACTERISTIC) {
			if (!onoff_action_found) {
				LOG_ERR("ONOFF action characteristic not found during discovery; disconnecting");
				if (default_conn) {
					(void)bt_conn_disconnect(default_conn,
							      BT_HCI_ERR_REMOTE_USER_TERM_CONN);
				}
			}
			if (discover_conn) {
				bt_conn_unref(discover_conn);
				discover_conn = NULL;
			}
			memset(params, 0, sizeof(*params));
			return BT_GATT_ITER_STOP;
		}

		memset(params, 0, sizeof(*params));
		return BT_GATT_ITER_STOP;
	}

	if (params->type == BT_GATT_DISCOVER_PRIMARY) {
		const struct bt_gatt_service_val *svc = attr->user_data;
		onoff_service_start_handle = attr->handle;
		onoff_service_end_handle = svc->end_handle;
		onoff_service_found = true;
		LOG_INF("found ONOFF service: start=0x%04x end=0x%04x", onoff_service_start_handle,
			onoff_service_end_handle);
		/*
		 * Keep iterating so the stack can deliver the completion callback (attr == NULL).
		 * Our next step (characteristic discovery) is triggered from that completion path.
		 */
		return BT_GATT_ITER_CONTINUE;
	}

	if (params->type == BT_GATT_DISCOVER_CHARACTERISTIC) {
		const struct bt_gatt_chrc *chrc = attr->user_data;
		char uuid_str[BT_UUID_STR_LEN];

		bt_uuid_to_str(chrc->uuid, uuid_str, sizeof(uuid_str));
		LOG_DBG("discovered chrc: decl=0x%04x value=0x%04x uuid=%s", attr->handle,
			chrc->value_handle, uuid_str);

		if (!onoff_action_found && bt_uuid_cmp(chrc->uuid, BT_UUID_ONOFF_ACTION) == 0) {
			onoff_action_handle = chrc->value_handle;
			onoff_action_found = true;
			LOG_INF("found action handle: 0x%04x", onoff_action_handle);
		}

		/* Allow completion (attr == NULL) to run cleanup/unref. */
		return BT_GATT_ITER_CONTINUE;
	}

	return BT_GATT_ITER_CONTINUE;
}

static void discover_onoff_service(struct bt_conn *conn)
{
	onoff_action_handle = 0U;
	onoff_service_start_handle = 0U;
	onoff_service_end_handle = 0U;
	onoff_service_found = false;
	onoff_action_found = false;

	if (discover_conn) {
		bt_conn_unref(discover_conn);
		discover_conn = NULL;
	}
	discover_conn = bt_conn_ref(conn);

	memset(&svc_discover_params, 0, sizeof(svc_discover_params));
	svc_discover_params.uuid = BT_UUID_ONOFF;
	svc_discover_params.func = discover_func;
	svc_discover_params.start_handle = BT_ATT_FIRST_ATTRIBUTE_HANDLE;
	svc_discover_params.end_handle = BT_ATT_LAST_ATTRIBUTE_HANDLE;
	svc_discover_params.type = BT_GATT_DISCOVER_PRIMARY;

	int err = bt_gatt_discover(conn, &svc_discover_params);
	if (err) {
		LOG_ERR("discover services failed: %d", err);
	}
}

static void discover_work_handler(struct k_work *work)
{
	ARG_UNUSED(work);

	if (discover_conn == NULL) {
		return;
	}

	if (onoff_service_end_handle == 0U || onoff_service_start_handle == 0U) {
		LOG_ERR("cannot discover characteristic: missing service handles");
		return;
	}

	memset(&chrc_discover_params, 0, sizeof(chrc_discover_params));
	/* Discover all characteristics in the service, then match UUID in discover_func(). */
	chrc_discover_params.uuid = NULL;
	chrc_discover_params.func = discover_func;
	chrc_discover_params.start_handle = onoff_service_start_handle + 1U;
	chrc_discover_params.end_handle = onoff_service_end_handle;
	chrc_discover_params.type = BT_GATT_DISCOVER_CHARACTERISTIC;

	int err = bt_gatt_discover(discover_conn, &chrc_discover_params);
	if (err) {
		LOG_ERR("discover action characteristic failed: %d", err);
	}
}

static void connected(struct bt_conn *conn, uint8_t err)
{
	if (err) {
		LOG_ERR("connection failed (0x%02x)", err);
		atomic_set(&connecting, 0);
		atomic_set(&scanning, 0);
		if (default_conn) {
			bt_conn_unref(default_conn);
			default_conn = NULL;
		}
		led_set_mode(LED_STATE_SOLID_ON);
		schedule_scan_retry(false);
		return;
	}

	LOG_INF("connected");
	atomic_set(&connecting, 0);
	atomic_set(&scanning, 0);
	scan_retry_attempt = 0U;
	k_work_cancel_delayable(&scan_retry_work);
	/* Central LED is a pure status LED: connected => OFF. */
	led_set_mode(LED_STATE_SOLID_OFF);
	discover_onoff_service(conn);
}

static void disconnected(struct bt_conn *conn, uint8_t reason)
{
	ARG_UNUSED(conn);
	LOG_WRN("disconnected (0x%02x)", reason);
	atomic_set(&connecting, 0);
	atomic_set(&scanning, 0);

	onoff_action_handle = 0U;
	onoff_service_start_handle = 0U;
	onoff_service_end_handle = 0U;

	if (discover_conn) {
		bt_conn_unref(discover_conn);
		discover_conn = NULL;
	}

	if (default_conn) {
		bt_conn_unref(default_conn);
		default_conn = NULL;
	}

	led_set_mode(LED_STATE_SOLID_ON);
	schedule_scan_retry(true);
}

BT_CONN_CB_DEFINE(conn_callbacks) = {
	.connected = connected,
	.disconnected = disconnected,
};

int main(void)
{
	int err;

	LOG_INF("boot: role=central");

	err = init_led0();
	if (err) {
		LOG_WRN("led0 init failed: %d (continuing without LED)", err);
		err = 0;
	} else {
		LOG_INF("led0 ready (port=%s pin=%u)", led0.port->name, led0.pin);
	}
	err = init_sw0();
	if (err) {
		LOG_WRN("sw0 init failed: %d (continuing without button)", err);
		err = 0;
	}

	err = bt_enable(NULL);
	if (err < 0) {
		LOG_ERR("bluetooth enable failed: %d", err);
		return err;
	}

	LOG_INF("bluetooth enabled");
	k_work_init(&discover_work, discover_work_handler);
	k_work_init_delayable(&scan_retry_work, scan_retry_handler);
	atomic_set(&scanning, 0);
	atomic_set(&connecting, 0);
	scan_retry_attempt = 0U;

	led_set_mode(LED_STATE_SOLID_ON);
	schedule_scan_retry(true);

	for (;;) {
		k_sleep(K_FOREVER);
	}
}