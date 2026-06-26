#include <zephyr/kernel.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/atomic.h>

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/hci.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/bluetooth/gatt.h>

#include <string.h>

LOG_MODULE_REGISTER(app, LOG_LEVEL_INF);

#define BT_UUID_LBS_MIN_VAL BT_UUID_128_ENCODE(0x8e7f1a23, 0x4b2c, 0x11ee, 0xbe56, 0x0242ac120002)
#define BT_UUID_LBS_MIN BT_UUID_DECLARE_128(BT_UUID_LBS_MIN_VAL)

#define BT_UUID_LBS_MIN_WRITE_VAL \
	BT_UUID_128_ENCODE(0x8e7f1a24, 0x4b2c, 0x11ee, 0xbe56, 0x0242ac120002)
#define BT_UUID_LBS_MIN_WRITE BT_UUID_DECLARE_128(BT_UUID_LBS_MIN_WRITE_VAL)

#define SW0_NODE DT_ALIAS(sw0)

static const struct gpio_dt_spec sw0 = GPIO_DT_SPEC_GET_OR(SW0_NODE, gpios, {0});

static struct bt_conn *default_conn;
static struct bt_conn *discover_conn;
static struct bt_gatt_discover_params discover_params;
static struct bt_gatt_write_params write_params;
static struct gpio_callback sw0_cb;
static struct k_work button_work;
static struct k_work_delayable debounce_work;
static atomic_t write_busy;

static uint16_t svc_start_handle;
static uint16_t svc_end_handle;
static uint16_t write_handle;
static uint8_t remote_led_state;

static bool gpio_ready(const struct gpio_dt_spec *spec)
{
	return spec->port != NULL && device_is_ready(spec->port);
}

static bool ad_has_uuid(struct bt_data *data, void *user_data)
{
	bool *found = user_data;
	struct bt_uuid_128 uuid;

	if (data->type != BT_DATA_UUID128_ALL && data->type != BT_DATA_UUID128_SOME) {
		return true;
	}

	if ((data->data_len % 16U) != 0U) {
		return true;
	}

	for (size_t i = 0; i < data->data_len; i += 16U) {
		memcpy(uuid.val, &data->data[i], 16U);
		uuid.uuid.type = BT_UUID_TYPE_128;
		if (bt_uuid_cmp(&uuid.uuid, BT_UUID_LBS_MIN) == 0) {
			*found = true;
			return false;
		}
	}

	return true;
}

static void start_scan(void);

static void device_found(const bt_addr_le_t *addr, int8_t rssi, uint8_t type,
			 struct net_buf_simple *ad)
{
	bool found = false;
	int err;

	ARG_UNUSED(rssi);

	if (default_conn != NULL) {
		return;
	}

	if (type != BT_GAP_ADV_TYPE_ADV_IND &&
	    type != BT_GAP_ADV_TYPE_ADV_DIRECT_IND &&
	    type != BT_GAP_ADV_TYPE_ADV_SCAN_IND &&
	    type != BT_GAP_ADV_TYPE_SCAN_RSP) {
		return;
	}

	bt_data_parse(ad, ad_has_uuid, &found);
	if (!found) {
		return;
	}

	err = bt_le_scan_stop();
	if (err) {
		LOG_WRN("scan stop failed: %d", err);
	}

	err = bt_conn_le_create(addr, BT_CONN_LE_CREATE_CONN, BT_LE_CONN_PARAM_DEFAULT,
				&default_conn);
	if (err) {
		LOG_ERR("create conn failed: %d", err);
		start_scan();
	} else {
		LOG_INF("connecting to matching peripheral");
	}
}

static void start_scan(void)
{
	int err = bt_le_scan_start(BT_LE_SCAN_ACTIVE, device_found);

	if (err) {
		LOG_ERR("scan start failed: %d", err);
		return;
	}

	LOG_INF("scanning");
}

static uint8_t discover_func(struct bt_conn *conn, const struct bt_gatt_attr *attr,
			     struct bt_gatt_discover_params *params)
{
	if (attr == NULL) {
		memset(params, 0, sizeof(*params));
		if (discover_conn) {
			bt_conn_unref(discover_conn);
			discover_conn = NULL;
		}
		return BT_GATT_ITER_STOP;
	}

	if (params->type == BT_GATT_DISCOVER_PRIMARY) {
		const struct bt_gatt_service_val *svc = attr->user_data;

		svc_start_handle = attr->handle;
		svc_end_handle = svc->end_handle;

		memset(params, 0, sizeof(*params));
		params->uuid = BT_UUID_LBS_MIN_WRITE;
		params->func = discover_func;
		params->start_handle = svc_start_handle + 1U;
		params->end_handle = svc_end_handle;
		params->type = BT_GATT_DISCOVER_CHARACTERISTIC;

		if (bt_gatt_discover(conn, params)) {
			LOG_ERR("characteristic discover failed");
		}

		return BT_GATT_ITER_STOP;
	}

	if (params->type == BT_GATT_DISCOVER_CHARACTERISTIC) {
		const struct bt_gatt_chrc *chrc = attr->user_data;

		if (bt_uuid_cmp(chrc->uuid, BT_UUID_LBS_MIN_WRITE) == 0) {
			write_handle = chrc->value_handle;
			LOG_INF("write handle found: 0x%04x", write_handle);
			return BT_GATT_ITER_STOP;
		}
	}

	return BT_GATT_ITER_CONTINUE;
}

static void discover_lbs_service(struct bt_conn *conn)
{
	svc_start_handle = 0U;
	svc_end_handle = 0U;
	write_handle = 0U;

	if (discover_conn) {
		bt_conn_unref(discover_conn);
	}

	discover_conn = bt_conn_ref(conn);

	memset(&discover_params, 0, sizeof(discover_params));
	discover_params.uuid = BT_UUID_LBS_MIN;
	discover_params.func = discover_func;
	discover_params.start_handle = BT_ATT_FIRST_ATTRIBUTE_HANDLE;
	discover_params.end_handle = BT_ATT_LAST_ATTRIBUTE_HANDLE;
	discover_params.type = BT_GATT_DISCOVER_PRIMARY;

	if (bt_gatt_discover(conn, &discover_params)) {
		LOG_ERR("service discover failed");
	} else {
		LOG_INF("discovering LBS service");
	}
}

static void write_cb(struct bt_conn *conn, uint8_t err, struct bt_gatt_write_params *params)
{
	ARG_UNUSED(conn);
	ARG_UNUSED(params);

	atomic_set(&write_busy, 0);

	if (err) {
		LOG_ERR("write failed: 0x%02x", err);
		return;
	}

	LOG_INF("write ok");
}

static void button_work_handler(struct k_work *work)
{
	uint8_t next_state;
	int err;

	ARG_UNUSED(work);

	if (default_conn == NULL || write_handle == 0U) {
		return;
	}

	if (!atomic_cas(&write_busy, 0, 1)) {
		return;
	}

	next_state = remote_led_state ? 0U : 1U;
	remote_led_state = next_state;
	LOG_INF("button press -> write 0x%02x", remote_led_state);

	write_params.handle = write_handle;
	write_params.offset = 0U;
	write_params.data = &remote_led_state;
	write_params.length = sizeof(remote_led_state);
	write_params.func = write_cb;

	err = bt_gatt_write(default_conn, &write_params);
	if (err) {
		atomic_set(&write_busy, 0);
		LOG_ERR("write start failed: %d", err);
	} else {
		LOG_INF("write started");
	}
}

static void debounce_handler(struct k_work *work)
{
	ARG_UNUSED(work);

	if (gpio_pin_get_dt(&sw0) > 0) {
		LOG_INF("button debounced");
		k_work_submit(&button_work);
	}
}

static void sw0_isr(const struct device *dev, struct gpio_callback *cb, uint32_t pins)
{
	ARG_UNUSED(dev);
	ARG_UNUSED(cb);
	ARG_UNUSED(pins);

	k_work_reschedule(&debounce_work, K_MSEC(30));
}

static int init_button(void)
{
	int err;

	if (!gpio_ready(&sw0)) {
		return -ENODEV;
	}

	err = gpio_pin_configure_dt(&sw0, GPIO_INPUT);
	if (err) {
		return err;
	}

	k_work_init(&button_work, button_work_handler);
	k_work_init_delayable(&debounce_work, debounce_handler);

	gpio_init_callback(&sw0_cb, sw0_isr, BIT(sw0.pin));
	err = gpio_add_callback(sw0.port, &sw0_cb);
	if (err) {
		return err;
	}

	return gpio_pin_interrupt_configure_dt(&sw0, GPIO_INT_EDGE_TO_ACTIVE);
}

static void connected(struct bt_conn *conn, uint8_t err)
{
	if (err) {
		LOG_ERR("connect failed: 0x%02x %s", err, bt_hci_err_to_str(err));
		if (default_conn) {
			bt_conn_unref(default_conn);
			default_conn = NULL;
		}
		start_scan();
		return;
	}

	LOG_INF("connected");
	discover_lbs_service(conn);
}

static void disconnected(struct bt_conn *conn, uint8_t reason)
{
	ARG_UNUSED(conn);

	LOG_INF("disconnected: 0x%02x %s", reason, bt_hci_err_to_str(reason));

	if (default_conn) {
		bt_conn_unref(default_conn);
		default_conn = NULL;
	}

	write_handle = 0U;
	atomic_set(&write_busy, 0);
	start_scan();
}

BT_CONN_CB_DEFINE(conn_callbacks) = {
	.connected = connected,
	.disconnected = disconnected,
};

int main(void)
{
	int err;

	remote_led_state = 0U;

	err = init_button();
	if (err) {
		LOG_WRN("button init failed: %d", err);
	}

	err = bt_enable(NULL);
	if (err) {
		LOG_ERR("bt enable failed: %d", err);
		return err;
	}

	LOG_INF("bluetooth initialized");
	start_scan();

	for (;;) {
		k_sleep(K_FOREVER);
	}
}
