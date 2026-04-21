#include <zephyr/kernel.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/logging/log.h>
#include <zephyr/spinlock.h>

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/hci.h>
#include <zephyr/bluetooth/hci_vs.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/sys/byteorder.h>

#define BT_UUID_ONOFF_VAL BT_UUID_128_ENCODE(0x8e7f1a23, 0x4b2c, 0x11ee, 0xbe56, 0x0242ac120002)
#define BT_UUID_ONOFF     BT_UUID_DECLARE_128(BT_UUID_ONOFF_VAL)
#define BT_UUID_ONOFF_ACTION_VAL \
    BT_UUID_128_ENCODE(0x8e7f1a24, 0x4b2c, 0x11ee, 0xbe56, 0x0242ac120002)
#define BT_UUID_ONOFF_ACTION BT_UUID_DECLARE_128(BT_UUID_ONOFF_ACTION_VAL)

#define BT_UUID_ONOFF_READ_VAL \
    BT_UUID_128_ENCODE(0x8e7f1a25, 0x4b2c, 0x11ee, 0xbe56, 0x0242ac120003)
#define BT_UUID_ONOFF_READ BT_UUID_DECLARE_128(BT_UUID_ONOFF_READ_VAL)
#define LBS_TX_PWR_DBM 8

/* devicetree: user said led0/sw0 already exist */
#define LED0_NODE DT_ALIAS(led0)
#define RFSW_CTL_NODE DT_NODELABEL(rfsw_ctl)

static const struct gpio_dt_spec led0 = GPIO_DT_SPEC_GET_OR(LED0_NODE, gpios, { 0 });
static uint8_t led_level;
#if DT_NODE_EXISTS(RFSW_CTL_NODE)
static const struct gpio_dt_spec rfsw_gpio = {
	.port = DEVICE_DT_GET(DT_GPIO_CTLR(RFSW_CTL_NODE, enable_gpios)),
	.pin = DT_GPIO_PIN(RFSW_CTL_NODE, enable_gpios),
	.dt_flags = DT_GPIO_FLAGS(RFSW_CTL_NODE, enable_gpios),
};
#endif

LOG_MODULE_REGISTER(app, LOG_LEVEL_DBG);

static bool gpio_ready(const struct gpio_dt_spec *spec);

/*
 * LED wiring contract (per user spec): physical GPIO level 0 -> LED ON, 1 -> LED OFF.
 * We therefore use gpio_pin_set_raw() (no DT active-low inversion).
 */
#define LED0_ACTIVE_LOW ((DT_GPIO_FLAGS(LED0_NODE, gpios) & GPIO_ACTIVE_LOW) != 0U)
#define LED_PHYS_ON_LEVEL  (LED0_ACTIVE_LOW ? 0U : 1U)
#define LED_PHYS_OFF_LEVEL (LED0_ACTIVE_LOW ? 1U : 0U)

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

static void led_show_value(uint8_t physical_level)
{
	if (physical_level == LED_PHYS_ON_LEVEL) {
		led_set_mode(LED_STATE_SOLID_ON);
	} else {
		led_set_mode(LED_STATE_SOLID_OFF);
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

static int init_antenna_path(void)
{
#if DT_NODE_EXISTS(RFSW_CTL_NODE)
	if (!gpio_ready(&rfsw_gpio)) {
		LOG_ERR("RF switch GPIO device not ready");
		return -ENODEV;
	}

	int err = gpio_pin_configure_dt(&rfsw_gpio, GPIO_OUTPUT);
	if (err) {
		LOG_ERR("RF switch GPIO configure failed: %d", err);
		return err;
	}

	/* xiao_nrf54l15: logical 0 selects the external antenna path. */
	err = gpio_pin_set_dt(&rfsw_gpio, 0);
	if (err) {
		LOG_ERR("RF switch GPIO set failed: %d", err);
		return err;
	}

	LOG_INF("RF path: external antenna selected");
#else
	LOG_INF("RF path: fixed antenna (no RF switch)");
#endif

	return 0;
}

static int set_tx_power(uint8_t handle_type, uint16_t handle, int8_t tx_power_dbm)
{
	struct bt_hci_cp_vs_write_tx_power_level *cp;
	struct bt_hci_rp_vs_write_tx_power_level *rp;
	struct net_buf *buf;
	struct net_buf *rsp = NULL;

	buf = bt_hci_cmd_alloc(K_FOREVER);
	if (buf == NULL) {
		return -ENOMEM;
	}

	cp = net_buf_add(buf, sizeof(*cp));
	cp->handle_type = handle_type;
	cp->handle = sys_cpu_to_le16(handle);
	cp->tx_power_level = tx_power_dbm;

	int err = bt_hci_cmd_send_sync(BT_HCI_OP_VS_WRITE_TX_POWER_LEVEL, buf, &rsp);
	if (err) {
		LOG_ERR("set tx power failed: type=%u handle=0x%04x err=%d",
			handle_type, handle, err);
		return err;
	}

	rp = (void *)rsp->data;
	LOG_INF("tx power set: type=%u handle=0x%04x selected=%d dBm",
		rp->handle_type, sys_le16_to_cpu(rp->handle), rp->selected_tx_power);
	net_buf_unref(rsp);
	return 0;
}

static const struct bt_data ad[] = {
	BT_DATA_BYTES(BT_DATA_FLAGS, (BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR)),
	BT_DATA_BYTES(BT_DATA_UUID128_ALL, BT_UUID_ONOFF_VAL),
};

static const struct bt_data sd[] = {
	BT_DATA(BT_DATA_NAME_COMPLETE, CONFIG_BT_DEVICE_NAME, sizeof(CONFIG_BT_DEVICE_NAME) - 1),
};

static struct k_work_delayable adv_restart_work;
static uint8_t adv_retry_attempt;

static int adv_start(void)
{
	/* Best-effort stop first to avoid -EALREADY loops. */
	int err = bt_le_adv_stop();
	if (err && err != -EALREADY) {
		LOG_DBG("adv stop ignored: %d", err);
	}

	err = bt_le_adv_start(BT_LE_ADV_CONN_FAST_1, ad, ARRAY_SIZE(ad), sd, ARRAY_SIZE(sd));
	if (err == -EALREADY) {
		return 0;
	}

	if (err == 0) {
		int tx_err = set_tx_power(BT_HCI_VS_LL_HANDLE_TYPE_ADV, 0U, LBS_TX_PWR_DBM);
		if (tx_err) {
			LOG_WRN("advertising tx power setup failed: %d", tx_err);
		}
	}
	return err;
}

static void adv_schedule_retry(bool reset_backoff)
{
	if (reset_backoff) {
		adv_retry_attempt = 0U;
	}

	uint32_t delay_ms = 200U;
	if (adv_retry_attempt < 6U) {
		delay_ms <<= adv_retry_attempt;
	}
	if (delay_ms > 5000U) {
		delay_ms = 5000U;
	}

	if (adv_retry_attempt < 10U) {
		adv_retry_attempt++;
	}

	k_work_reschedule(&adv_restart_work, K_MSEC(delay_ms));
}

static void adv_restart_handler(struct k_work *work)
{
	ARG_UNUSED(work);

	int err = adv_start();
	if (err) {
		LOG_ERR("advertising restart failed: %d", err);
		led_set_mode(LED_STATE_SOLID_ON);
		adv_schedule_retry(false);
		return;
	}

	LOG_INF("advertising");
	led_set_mode(LED_STATE_BLINK_2HZ);
	adv_retry_attempt = 0U;
}

static ssize_t read_onoff_val(struct bt_conn *conn, const struct bt_gatt_attr *attr,
			      void *buf, uint16_t len, uint16_t offset)
{
	const uint8_t *value = attr->user_data;
	return bt_gatt_attr_read(conn, attr, buf, len, offset, value, sizeof(*value));
}

static ssize_t write_onoff_val(struct bt_conn *conn, const struct bt_gatt_attr *attr,
			       const void *buf, uint16_t len, uint16_t offset, uint8_t flags)
{
	ARG_UNUSED(conn);
	ARG_UNUSED(flags);
	ARG_UNUSED(attr);

	if (len != 1U) {
		return BT_GATT_ERR(BT_ATT_ERR_INVALID_ATTRIBUTE_LEN);
	}

	if (offset != 0U) {
		return BT_GATT_ERR(BT_ATT_ERR_INVALID_OFFSET);
	}

	uint8_t val = *((const uint8_t *)buf);
	if (val != 0U && val != 1U) {
		return BT_GATT_ERR(BT_ATT_ERR_VALUE_NOT_ALLOWED);
	}

	led_level = val;
	LOG_INF("rx write: led_level=%u", led_level);
	led_show_value(led_level);
	return len;
}

BT_GATT_SERVICE_DEFINE(lbs_svc,
	BT_GATT_PRIMARY_SERVICE(BT_UUID_ONOFF),
	BT_GATT_CHARACTERISTIC(BT_UUID_ONOFF_ACTION, BT_GATT_CHRC_WRITE,
		BT_GATT_PERM_WRITE, NULL, write_onoff_val, NULL),
	BT_GATT_CHARACTERISTIC(BT_UUID_ONOFF_READ, BT_GATT_CHRC_READ,
		BT_GATT_PERM_READ, read_onoff_val, NULL, &led_level),
);

static void connected(struct bt_conn *conn, uint8_t err)
{
	ARG_UNUSED(conn);
	if (err) {
		LOG_ERR("connection failed (0x%02x)", err);
		return;
	}

	LOG_INF("connected");
	uint16_t conn_handle;
	int tx_err = bt_hci_get_conn_handle(conn, &conn_handle);
	if (tx_err == 0) {
		tx_err = set_tx_power(BT_HCI_VS_LL_HANDLE_TYPE_CONN, conn_handle, LBS_TX_PWR_DBM);
	}
	if (tx_err) {
		LOG_WRN("connection tx power setup failed: %d", tx_err);
	}
	/* On connect: force LED OFF, then wait for central to control it via GATT write. */
	led_level = LED_PHYS_OFF_LEVEL;
	led_set_mode(LED_STATE_SOLID_OFF);
}

static void disconnected(struct bt_conn *conn, uint8_t reason)
{
	ARG_UNUSED(conn);
	LOG_WRN("disconnected (0x%02x)", reason);

	/* Defer restart out of callback context; retry on transient failures. */
	adv_schedule_retry(true);
}

BT_CONN_CB_DEFINE(conn_callbacks) = {
	.connected = connected,
	.disconnected = disconnected,
};

int main(void)
{
	int err;

	LOG_INF("boot: role=peripheral");

	err = init_led0();
	if (err) {
		LOG_WRN("led0 init failed: %d (continuing without LED)", err);
		err = 0;
	} else {
		LOG_INF("led0 ready (port=%s pin=%u)", led0.port->name, led0.pin);
	}

	err = bt_enable(NULL);
	if (err < 0) {
		LOG_ERR("bluetooth enable failed: %d", err);
		return err;
	}

	LOG_INF("bluetooth enabled");

	err = init_antenna_path();
	if (err) {
		LOG_ERR("antenna path init failed: %d", err);
		return err;
	}

	k_work_init_delayable(&adv_restart_work, adv_restart_handler);
	adv_retry_attempt = 0U;

	led_level = LED_PHYS_OFF_LEVEL;
	err = adv_start();
	if (err < 0) {
		LOG_ERR("advertising start failed: %d", err);
		led_set_mode(LED_STATE_SOLID_ON);
		adv_schedule_retry(false);
	} else {
		LOG_INF("advertising");
		led_set_mode(LED_STATE_BLINK_2HZ);
	}

	for (;;) {
		k_sleep(K_FOREVER);
	}
}
