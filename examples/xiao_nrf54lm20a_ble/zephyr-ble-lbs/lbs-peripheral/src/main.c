#include <zephyr/kernel.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/logging/log.h>

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/hci.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/bluetooth/gatt.h>

LOG_MODULE_REGISTER(app, LOG_LEVEL_INF);

#define BT_UUID_LBS_MIN_VAL BT_UUID_128_ENCODE(0x8e7f1a23, 0x4b2c, 0x11ee, 0xbe56, 0x0242ac120002)
#define BT_UUID_LBS_MIN BT_UUID_DECLARE_128(BT_UUID_LBS_MIN_VAL)

#define BT_UUID_LBS_MIN_WRITE_VAL \
	BT_UUID_128_ENCODE(0x8e7f1a24, 0x4b2c, 0x11ee, 0xbe56, 0x0242ac120002)
#define BT_UUID_LBS_MIN_WRITE BT_UUID_DECLARE_128(BT_UUID_LBS_MIN_WRITE_VAL)

#define BT_UUID_LBS_MIN_READ_VAL \
	BT_UUID_128_ENCODE(0x8e7f1a25, 0x4b2c, 0x11ee, 0xbe56, 0x0242ac120003)
#define BT_UUID_LBS_MIN_READ BT_UUID_DECLARE_128(BT_UUID_LBS_MIN_READ_VAL)

#define LED0_NODE DT_ALIAS(led0)

static const struct gpio_dt_spec led0 = GPIO_DT_SPEC_GET_OR(LED0_NODE, gpios, {0});
static uint8_t led_state;

static bool gpio_ready(const struct gpio_dt_spec *spec)
{
	return spec->port != NULL && device_is_ready(spec->port);
}

static void led_apply(uint8_t value)
{
	if (!gpio_ready(&led0)) {
		return;
	}

	(void)gpio_pin_set_dt(&led0, value ? 1 : 0);
}

static ssize_t read_led(struct bt_conn *conn, const struct bt_gatt_attr *attr,
			void *buf, uint16_t len, uint16_t offset)
{
	const uint8_t *value = attr->user_data;

	return bt_gatt_attr_read(conn, attr, buf, len, offset, value, sizeof(*value));
}

static ssize_t write_led(struct bt_conn *conn, const struct bt_gatt_attr *attr,
			 const void *buf, uint16_t len, uint16_t offset, uint8_t flags)
{
	uint8_t value;

	ARG_UNUSED(conn);
	ARG_UNUSED(attr);
	ARG_UNUSED(flags);

	if (len != 1U) {
		return BT_GATT_ERR(BT_ATT_ERR_INVALID_ATTRIBUTE_LEN);
	}

	if (offset != 0U) {
		return BT_GATT_ERR(BT_ATT_ERR_INVALID_OFFSET);
	}

	value = ((const uint8_t *)buf)[0];
	if (value != 0U && value != 1U) {
		return BT_GATT_ERR(BT_ATT_ERR_VALUE_NOT_ALLOWED);
	}

	led_state = value;
	led_apply(led_state);
	LOG_INF("remote led state=%u", led_state);

	return len;
}

BT_GATT_SERVICE_DEFINE(lbs_min_svc,
	BT_GATT_PRIMARY_SERVICE(BT_UUID_LBS_MIN),
	BT_GATT_CHARACTERISTIC(BT_UUID_LBS_MIN_WRITE, BT_GATT_CHRC_WRITE,
			       BT_GATT_PERM_WRITE, NULL, write_led, NULL),
	BT_GATT_CHARACTERISTIC(BT_UUID_LBS_MIN_READ, BT_GATT_CHRC_READ,
			       BT_GATT_PERM_READ, read_led, NULL, &led_state),
);

static const struct bt_data ad[] = {
	BT_DATA_BYTES(BT_DATA_FLAGS, (BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR)),
	BT_DATA(BT_DATA_NAME_COMPLETE, CONFIG_BT_DEVICE_NAME,
		sizeof(CONFIG_BT_DEVICE_NAME) - 1),
};

static const struct bt_data sd[] = {
	BT_DATA_BYTES(BT_DATA_UUID128_ALL, BT_UUID_LBS_MIN_VAL),
};

static void connected(struct bt_conn *conn, uint8_t err)
{
	ARG_UNUSED(conn);

	if (err) {
		LOG_ERR("connect failed: 0x%02x %s", err, bt_hci_err_to_str(err));
		return;
	}

	LOG_INF("connected");
}

static void disconnected(struct bt_conn *conn, uint8_t reason)
{
	ARG_UNUSED(conn);

	LOG_INF("disconnected: 0x%02x %s", reason, bt_hci_err_to_str(reason));
}

BT_CONN_CB_DEFINE(conn_callbacks) = {
	.connected = connected,
	.disconnected = disconnected,
};

int main(void)
{
	int err;

	led_state = 0U;
	if (gpio_ready(&led0)) {
		err = gpio_pin_configure_dt(&led0, GPIO_OUTPUT_INACTIVE);
		if (err == 0) {
			led_apply(led_state);
		}
	}
	err = bt_enable(NULL);
	if (err) {
		LOG_ERR("bt enable failed: %d", err);
		return err;
	}

	LOG_INF("bluetooth initialized");

	err = bt_le_adv_start(BT_LE_ADV_CONN_FAST_1, ad, ARRAY_SIZE(ad), sd, ARRAY_SIZE(sd));
	if (err) {
		LOG_ERR("advertising failed: %d", err);
		return err;
	}

	LOG_INF("advertising");

	for (;;) {
		k_sleep(K_FOREVER);
	}
}
