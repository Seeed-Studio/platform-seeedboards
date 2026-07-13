/*
 * nPM1300 charging indicator sample for XIAO nRF54LM20A.
 *
 * LEDDRV1 is controlled from VBUS, VBAT, and IBAT measurements only.
 * The nPM1300 D00 charger COMPLETE status is intentionally not used.
 */

#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/led.h>
#include <zephyr/drivers/mfd/npm13xx.h>
#include <zephyr/drivers/sensor.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/util.h>

LOG_MODULE_REGISTER(npm1300_charge_indicator, CONFIG_LOG_DEFAULT_LEVEL);

#define PMIC_NODE      DT_NODELABEL(pmic)
#define CHARGER_NODE   DT_NODELABEL(pmic_charger)
#define PMIC_LEDS_NODE DT_NODELABEL(pmic_leds)

BUILD_ASSERT(DT_NODE_HAS_STATUS(PMIC_NODE, okay), "nPM1300 PMIC node is not enabled");
BUILD_ASSERT(DT_NODE_HAS_STATUS(CHARGER_NODE, okay), "nPM1300 charger node is not enabled");
BUILD_ASSERT(DT_NODE_HAS_STATUS(PMIC_LEDS_NODE, okay), "nPM1300 LED node is not enabled");

static const struct device *const pmic = DEVICE_DT_GET(PMIC_NODE);
static const struct device *const charger = DEVICE_DT_GET(CHARGER_NODE);
static const struct device *const pmic_leds = DEVICE_DT_GET(PMIC_LEDS_NODE);
static bool charge_led_ready;
static bool charge_led_on = true;

#define SLEEP_TIME_MS 1000
#define NPM1300_LED1  1U

#define NPM1300_VBUS_BASE             0x02U
#define NPM1300_VBUSINSTATUS_OFFSET   0x07U
#define NPM1300_VBUS_PRESENT_MASK     BIT(0)

#define BATTERY_PRESENT_MIN_MV           2000LL
/* nPM1300 trickle current is 10% of the programmed charge current (ISET). */
#define CHARGE_CURRENT_MIN_UA \
	((int64_t)DT_PROP(CHARGER_NODE, current_microamp) / 10LL)
#define CHARGE_TERM_VOLTAGE_MV          ((int64_t)DT_PROP(CHARGER_NODE, term_microvolt) / 1000LL)
#define CHARGE_TERM_VOLTAGE_TOLERANCE_MV 25LL
#define CHARGE_FULL_VOLTAGE_MIN_MV \
	(CHARGE_TERM_VOLTAGE_MV - CHARGE_TERM_VOLTAGE_TOLERANCE_MV)

struct charger_measurement {
	int64_t voltage_mv;
	int64_t current_ua;
};

static int npm1300_read_reg(uint8_t base, uint8_t offset, uint8_t *value)
{
	return mfd_npm13xx_reg_read(pmic, base, offset, value);
}

static int set_charge_led(bool on)
{
	int ret;

	if (!charge_led_ready || charge_led_on == on) {
		return 0;
	}

	ret = on ? led_on(pmic_leds, NPM1300_LED1) : led_off(pmic_leds, NPM1300_LED1);
	if (ret == 0) {
		charge_led_on = on;
	}

	return ret;
}

static int read_charger_measurement(struct charger_measurement *measurement)
{
	struct sensor_value value;
	int ret;

	ret = sensor_sample_fetch(charger);
	if (ret < 0) {
		return ret;
	}

	ret = sensor_channel_get(charger, SENSOR_CHAN_GAUGE_VOLTAGE, &value);
	if (ret < 0) {
		return ret;
	}
	measurement->voltage_mv = sensor_value_to_milli(&value);

	ret = sensor_channel_get(charger, SENSOR_CHAN_GAUGE_AVG_CURRENT, &value);
	if (ret < 0) {
		return ret;
	}
	measurement->current_ua = sensor_value_to_micro(&value);

	return 0;
}

static bool charge_led_should_be_on(uint8_t vbus_status,
				    const struct charger_measurement *measurement)
{
	return (vbus_status & NPM1300_VBUS_PRESENT_MASK) != 0U &&
	       measurement->voltage_mv >= BATTERY_PRESENT_MIN_MV &&
	       measurement->current_ua >= CHARGE_CURRENT_MIN_UA;
}

static bool battery_is_full(const struct charger_measurement *measurement)
{
	return measurement->voltage_mv >= CHARGE_FULL_VOLTAGE_MIN_MV &&
	       measurement->current_ua >= 0LL &&
	       measurement->current_ua < CHARGE_CURRENT_MIN_UA;
}

int main(void)
{
	int ret;

	if (!device_is_ready(pmic)) {
		LOG_ERR("nPM1300 PMIC device is not ready");
		return 0;
	}

	if (!device_is_ready(charger)) {
		LOG_ERR("nPM1300 charger device is not ready");
		return 0;
	}

	if (!device_is_ready(pmic_leds)) {
		LOG_ERR("nPM1300 LED device is not ready");
		return 0;
	}

	charge_led_ready = true;
	charge_led_on = true;

	ret = set_charge_led(false);
	if (ret < 0) {
		LOG_ERR("Failed to turn off nPM1300 LEDDRV1: %d", ret);
		return 0;
	}

	LOG_INF("nPM1300 charging indicator started");
	LOG_INF("LEDDRV1 uses VBUS, VBAT, and IBAT; D00 COMPLETE status is not used");
	LOG_INF("Charge current: %d mA, charge-detect threshold: %lld mA",
		DT_PROP(CHARGER_NODE, current_microamp) / 1000,
		(long long)CHARGE_CURRENT_MIN_UA / 1000LL);
	LOG_INF("Termination voltage: %lld mV, full-voltage threshold: %lld mV",
		(long long)CHARGE_TERM_VOLTAGE_MV,
		(long long)CHARGE_FULL_VOLTAGE_MIN_MV);

	while (1) {
		uint8_t vbus_status = 0U;
		struct charger_measurement measurement = { 0 };
		bool led_on;
		bool full;

		ret = npm1300_read_reg(NPM1300_VBUS_BASE, NPM1300_VBUSINSTATUS_OFFSET,
				       &vbus_status);
		if (ret < 0) {
			LOG_ERR("Failed to read VBUSINSTATUS 0x0207: %d", ret);
			(void)set_charge_led(false);
			k_msleep(SLEEP_TIME_MS);
			continue;
		}

		ret = read_charger_measurement(&measurement);
		if (ret < 0) {
			LOG_ERR("Failed to read charger measurement: %d", ret);
			(void)set_charge_led(false);
			k_msleep(SLEEP_TIME_MS);
			continue;
		}

		led_on = charge_led_should_be_on(vbus_status, &measurement);
		full = battery_is_full(&measurement);
		ret = set_charge_led(led_on);
		if (ret < 0) {
			LOG_ERR("Failed to control nPM1300 LEDDRV1: %d", ret);
		}

		LOG_INF("VBUSINSTATUS[0x0207]=0x%02x present=%u, VBAT=%lld mV, "
			"IBAT=%lld uA, full=%u, nPM_LED1=%s",
			vbus_status, (vbus_status & NPM1300_VBUS_PRESENT_MASK) != 0U,
			(long long)measurement.voltage_mv,
			(long long)measurement.current_ua,
			full, led_on ? "on" : "off");

		k_msleep(SLEEP_TIME_MS);
	}
}
