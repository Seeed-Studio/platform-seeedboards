#include <assert.h>  /* for static_assert in the generated Axon gesture model header */
/*
 * Copyright (c) 2026 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

#include <soc.h>
#include <stddef.h>
#include <string.h>
#include <zephyr/types.h>
#include <zephyr/sys/util.h>

#include <stdio.h>
#include <errno.h>
#include <zephyr/device.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/usb/usb_device.h>
#include <zephyr/sys/atomic.h>

#include <nrf_edgeai/nrf_edgeai.h>
#include <nrf_edgeai_user_model.h>

#include "button/button.h"
#include "led/led.h"
#include "sensor/imu/imu.h"

#if IS_ENABLED(CONFIG_BLE_MODE_HID)
#include "ux_state_manager.h"
#endif
#include "inference_postprocessing.h"
#include "ble/ble_common.h"

#if IS_ENABLED(CONFIG_BLE_MODE_HID)
#include "ble/hid/ble_hid.h"
#elif IS_ENABLED(CONFIG_BLE_MODE_NUS)
#include "ble/nus/ble_nus.h"
#elif IS_ENABLED(CONFIG_BLE_MODE_GATT_CUSTOM)
#include "ble/gatt/ble_gatt.h"
#endif

#define NRF_EDGEAI_INPUT_DATA_LEN (ACCEL_AXIS_NUM + GYRO_AXIS_NUM)

#if IS_ENABLED(CONFIG_LED_NOTIFICATION_BLINK)
#define LED_NOTIFY_BLINK_COUNT	(3)
#define LED_NOTIFY_BLINK_ON_MS	(100)
#define LED_NOTIFY_BLINK_OFF_MS (200)
#else
#define BLINK_LED_TIMER_PERIOD_MS	 (30)
#define LED_BLINK_CHANGE_BRIGHTNESS_STEP (0.005f)
#endif

#define LED_MAX_BRIGHTNESS (0.2f)

LOG_MODULE_REGISTER(main);

typedef int (*led_set_func_t)(float brightness);

#if IS_ENABLED(CONFIG_NRF_EDGEAI_GESTURE_RECOGNITION_MODEL_AXON)
static void execute_inference(flt32_t *input_data);
#else
static void execute_inference(int16_t *input_data);
#endif
static void send_imu_data(int16_t *input_data);
static void hw_modules_init(void);
#if IS_ENABLED(CONFIG_LED_NOTIFICATION_BLINK)
static void led_blink_set_active_led(void);
#else
static void led_glowing_timer_handler(struct k_timer *timer);
#endif
static void handle_inference_result(nrf_edgeai_t *model);

static struct k_sem imu_data_ready_sem;

/* Work queue items for deferring interrupt context LED operations to thread context */
#if IS_ENABLED(CONFIG_LED_NOTIFICATION_BLINK)
static struct k_work led_notify_work;
static struct k_work_delayable led_notify_blink_work;
static int led_notify_remaining;
#else
static struct k_work led_update_work;
#endif

static nrf_edgeai_t *p_model;

#if !IS_ENABLED(CONFIG_LED_NOTIFICATION_BLINK)
K_TIMER_DEFINE(led_timer, led_glowing_timer_handler, NULL);
#endif /* !CONFIG_LED_NOTIFICATION_BLINK */

#if !IS_ENABLED(CONFIG_BLE_MODE_NONE)
void main_ble_connection_notification(bool connected)
{
	(void)connected;
	led_off();
#if IS_ENABLED(CONFIG_LED_NOTIFICATION_BLINK)
	k_work_submit(&led_notify_work);
#endif
}
#endif

int main(void)
{
	hw_modules_init();

	int err = button_init();

	if (err != 0) {
		LOG_ERR("Failed to initialize button module (err %d)", err);
		__ASSERT(false, "button_init failed: %d", err);
	}

#if IS_ENABLED(CONFIG_BLE_MODE_HID)
	err = uxsm_init();
	if (err != 0) {
		LOG_ERR("Failed to initialize UX state manager (err %d)", err);
		__ASSERT(false, "uxsm_init failed: %d", err);
	}
#endif

	p_model = nrf_edgeai_user_model();
	__ASSERT(p_model != NULL, "nrf_edgeai_user_model returned NULL");
	__ASSERT(nrf_edgeai_is_runtime_compatible(p_model),
		 "nRF Edge AI runtime is not compatible with the linked model");

	__maybe_unused nrf_edgeai_err_t res = nrf_edgeai_init(p_model);

	__ASSERT(res == NRF_EDGEAI_ERR_SUCCESS, "nrf_edgeai_init failed: %d", (int)res);

	nrf_edgeai_rt_version_t version = nrf_edgeai_runtime_version();

	LOG_INF("nRF Edge AI Gestures Recognition Demo:");
	LOG_INF("nRF Edge AI Runtime Version: %d.%d.%d", version.field.major, version.field.minor,
		version.field.patch);
	LOG_INF("nRF Edge AI Lab Solution id: %s", nrf_edgeai_solution_id_str(p_model));

	LOG_INF("=== XIAO nRF54LM20B Edge AI: gesture recognition (local) ===");
	LOG_INF("Axon NPU runs the gesture model over the onboard LSM6DSL IMU.");
	LOG_INF("Make a gesture: swipe-left/right, double-shake, double-thumb,");
	LOG_INF("or rotate. Detected gestures are printed here (no Bluetooth).");	imu_data_t imu_data = {0};

	flt32_t input_data_f32[NRF_EDGEAI_INPUT_DATA_LEN];
	int16_t input_data_i16[NRF_EDGEAI_INPUT_DATA_LEN];

	for (;;) {
		/* Wait for the semaphore to be released by IMU data ready interrupt */
		k_sem_take(&imu_data_ready_sem, K_FOREVER);

		status_t status = imu_read(&imu_data);

		if (status != STATUS_SUCCESS) {
			LOG_ERR("Failed to read IMU sample, error = %d", (int)status);
			continue;
		}

		input_data_f32[0] = (flt32_t)(imu_data.accel[0].phys * 1000);
		input_data_f32[1] = (flt32_t)(imu_data.accel[1].phys * 1000);
		input_data_f32[2] = (flt32_t)(imu_data.accel[2].phys * 1000);
		input_data_f32[3] = (flt32_t)(imu_data.gyro[0].phys * 1000);
		input_data_f32[4] = (flt32_t)(imu_data.gyro[1].phys * 1000);
		input_data_f32[5] = (flt32_t)(imu_data.gyro[2].phys * 1000);

		input_data_i16[0] = imu_data.accel[0].raw;
		input_data_i16[1] = imu_data.accel[1].raw;
		input_data_i16[2] = imu_data.accel[2].raw;
		input_data_i16[3] = imu_data.gyro[0].raw;
		input_data_i16[4] = imu_data.gyro[1].raw;
		input_data_i16[5] = imu_data.gyro[2].raw;

		if (IS_ENABLED(CONFIG_DATA_COLLECTION_MODE)) {
			send_imu_data(input_data_i16);
		} else {
#if IS_ENABLED(CONFIG_NRF_EDGEAI_GESTURE_RECOGNITION_MODEL_AXON)
			execute_inference(input_data_f32);
#else
			execute_inference(input_data_i16);
#endif
		}
	}

	return 0;
}

static void imu_data_ready_cb(void)
{
	k_sem_give(&imu_data_ready_sem);
}

static void led_set_active(float brightness)
{
	/* ble_common_is_connected() is safe to call in any BLE mode,
	 * including CONFIG_BLE_MODE_NONE, because ble_common_init() is
	 * always invoked during hw_modules_init().
	 */
	if (ble_common_is_connected()) {

#if IS_ENABLED(CONFIG_BLE_MODE_HID)

		static const led_set_func_t LED_VS_KEYBOARD_MODE[] = {
			[UX_REMOTECTRL_MODE_PRESENTATION] = led_set_led2,
			[UX_REMOTECTRL_MODE_MUSIC] = led_set_led1,
		};
		ux_remotectrl_mode_t mode = uxsm_get_remotectrl_mode();

		__ASSERT_NO_MSG(mode < ARRAY_SIZE(LED_VS_KEYBOARD_MODE));
		led_set_func_t led_set = LED_VS_KEYBOARD_MODE[mode];

		__ASSERT_NO_MSG(led_set != NULL);
		led_set(brightness);
#else
		led_set_led2(brightness);
#endif
	} else {
		led_set_led0(brightness);
	}
}

#if IS_ENABLED(CONFIG_LED_NOTIFICATION_BLINK)

static void led_blink_set_active_led(void)
{
	led_set_active(LED_MAX_BRIGHTNESS);
}

/**
 * Notification blink state machine.
 * Total steps = LED_NOTIFY_BLINK_COUNT * 2 (on + off per blink).
 * Even remaining → turn LED on, schedule off.
 * Odd remaining  → turn LED off, schedule next on (or stop).
 */
static void led_notify_blink_handler(struct k_work *work)
{
	if (led_notify_remaining <= 0) {
		return;
	}

	if (led_notify_remaining % 2 == 0) {
		/* LED-on phase */
		led_blink_set_active_led();
		led_notify_remaining--;
		k_work_schedule(&led_notify_blink_work, K_MSEC(LED_NOTIFY_BLINK_ON_MS));
	} else {
		/* LED-off phase */
		led_off();
		led_notify_remaining--;
		if (led_notify_remaining > 0) {
			k_work_schedule(&led_notify_blink_work, K_MSEC(LED_NOTIFY_BLINK_OFF_MS));
		}
	}
}

static void led_notify_start_work_handler(struct k_work *work)
{
	/* Cancel any ongoing sequence before starting a new one */
	k_work_cancel_delayable(&led_notify_blink_work);
	led_off();

	/* Each blink = on + off step */
	led_notify_remaining = LED_NOTIFY_BLINK_COUNT * 2;

	/* Kick off immediately */
	led_notify_blink_handler(NULL);
}

#else /* !CONFIG_LED_NOTIFICATION_BLINK */

static void led_glowing_timer_handler(struct k_timer *timer)
{
	(void)timer;
	k_work_submit(&led_update_work);
}

static void led_update_work_handler(struct k_work *work)
{
	static bool rising = true;
	static float brightness;

	led_set_active(brightness);

	if (rising) {
		brightness += LED_BLINK_CHANGE_BRIGHTNESS_STEP;
		if (brightness >= LED_MAX_BRIGHTNESS) {
			rising = false;
		}
	} else {
		brightness -= LED_BLINK_CHANGE_BRIGHTNESS_STEP;
		if (brightness <= 0) {
			rising = true;
		}
	}
}

#endif /* CONFIG_LED_NOTIFICATION_BLINK */

static void hw_modules_init(void)
{
	int ret;

#if IS_ENABLED(CONFIG_LED_NOTIFICATION_BLINK)
	k_work_init(&led_notify_work, led_notify_start_work_handler);
	k_work_init_delayable(&led_notify_blink_work, led_notify_blink_handler);
#else
	k_work_init(&led_update_work, led_update_work_handler);
#endif

	ret = led_init();
	if (ret != 0) {
		LOG_ERR("Failed to initialize LEDs module, error = %d", ret);
		__ASSERT(false, "led_init failed: %d", ret);
	}
#if IS_ENABLED(CONFIG_LED_NOTIFICATION_BLINK)
	/* Blink once at startup to confirm the device is alive */
	k_work_submit(&led_notify_work);
#else
	k_timer_start(&led_timer, K_MSEC(BLINK_LED_TIMER_PERIOD_MS),
		      K_MSEC(BLINK_LED_TIMER_PERIOD_MS));
#endif

	imu_config_t imu_config = {.accel_fs_g = IMU_ACCEL_SCALE_4G,
				   .gyro_fs_dps = IMU_GYRO_SCALE_1000DPS,
				   .data_rate_hz = 100};

	status_t status = imu_init(&imu_config, imu_data_ready_cb);

	if (status != STATUS_SUCCESS) {
		LOG_ERR("Failed to initialize IMU sensor, error = %d", (int)status);
		__ASSERT(false, "imu_init failed: %d", (int)status);
	}
	k_sem_init(&imu_data_ready_sem, 0, 1);

	/* Always initialize the common BLE state holder.
	 * It is mode-agnostic and must be ready before any other module
	 * (e.g. led_set_active()) queries ble_common_is_connected().
	 */
	ble_common_init();

#if IS_ENABLED(CONFIG_BLE_MODE_HID)
	ret = ble_hid_init();
	if (ret != 0) {
		LOG_ERR("Failed to initialize BLE HID service");
		__ASSERT(false, "ble_hid_init failed: %d", ret);
	}
#elif IS_ENABLED(CONFIG_BLE_MODE_NUS)
	ret = ble_nus_init();
	if (ret != 0) {
		LOG_ERR("Failed to initialize BLE NUS service");
		__ASSERT(false, "ble_nus_init failed: %d", ret);
	}
#elif IS_ENABLED(CONFIG_BLE_MODE_GATT_CUSTOM)
	ret = ble_gatt_init(NULL);
	if (ret != 0) {
		LOG_ERR("Failed to initialize BLE GATT service");
		__ASSERT(false, "ble_gatt_init failed: %d", ret);
	}
#endif
}

#if IS_ENABLED(CONFIG_BLE_MODE_HID)
static void send_bt_keyboard_key(const class_label_t class_label)
{
	static const ble_hid_key_t LABEL_VS_KEY_BY_MODE[2][8] = {
		[UX_REMOTECTRL_MODE_PRESENTATION] = {
				[CLASS_LABEL_IDLE] = BLE_HID_KEYS_count,
				[CLASS_LABEL_UNKNOWN] = BLE_HID_KEYS_count,
				[CLASS_LABEL_SWIPE_RIGHT] = BLE_HID_KEY_ARROW_RIGHT,
				[CLASS_LABEL_SWIPE_LEFT] = BLE_HID_KEY_ARROW_LEFT,
				[CLASS_LABEL_DOUBLE_SHAKE] = BLE_HID_KEY_F5,
				[CLASS_LABEL_DOUBLE_THUMB] = BLE_HID_KEY_ESC,
				[CLASS_LABEL_ROTATION_RIGHT] = BLE_HID_KEYS_count,
				[CLASS_LABEL_ROTATION_LEFT] = BLE_HID_KEYS_count,
			},
		[UX_REMOTECTRL_MODE_MUSIC] = {
				[CLASS_LABEL_IDLE] = BLE_HID_KEYS_count,
				[CLASS_LABEL_UNKNOWN] = BLE_HID_KEYS_count,
				[CLASS_LABEL_SWIPE_RIGHT] = BLE_HID_KEY_MEDIA_NEXT_TRACK,
				[CLASS_LABEL_SWIPE_LEFT] = BLE_HID_KEY_MEDIA_PREV_TRACK,
				[CLASS_LABEL_DOUBLE_SHAKE] = BLE_HID_KEY_MEDIA_PLAY_PAUSE,
				[CLASS_LABEL_DOUBLE_THUMB] = BLE_HID_KEY_MEDIA_MUTE,
				[CLASS_LABEL_ROTATION_RIGHT] = BLE_HID_KEY_MEDIA_VOLUME_UP,
				[CLASS_LABEL_ROTATION_LEFT] = BLE_HID_KEY_MEDIA_VOLUME_DOWN,
			},
	};

	ux_remotectrl_mode_t mode = uxsm_get_remotectrl_mode();

	__ASSERT_NO_MSG(class_label < CLASS_LABEL_COUNT);
	__ASSERT_NO_MSG(mode < ARRAY_SIZE(LABEL_VS_KEY_BY_MODE));
	ble_hid_send_key(LABEL_VS_KEY_BY_MODE[mode][class_label]);
}
#endif

#if IS_ENABLED(CONFIG_BLE_MODE_GATT_CUSTOM)
static void ble_send_recognized_class(const class_label_t class_label, size_t probability_pct)
{
	static char send_buff[15];

	int message_len = snprintf(send_buff, sizeof(send_buff), "%d,%d", (int)class_label,
				   (int)probability_pct);

	__ASSERT_NO_MSG(message_len > 0 && message_len < sizeof(send_buff));
	ble_gatt_send_raw_data((const uint8_t *)send_buff, (size_t)message_len);
}
#endif

#if IS_ENABLED(CONFIG_NRF_EDGEAI_GESTURE_RECOGNITION_MODEL_AXON)
static void execute_inference(flt32_t *input_data)
#else
static void execute_inference(int16_t *input_data)
#endif
{
	nrf_edgeai_err_t res;

	res = nrf_edgeai_feed_inputs(p_model, (void *)input_data, NRF_EDGEAI_INPUT_DATA_LEN);

	if (res == NRF_EDGEAI_ERR_SUCCESS) {
		res = nrf_edgeai_run_inference(p_model);

		if (res == NRF_EDGEAI_ERR_SUCCESS) {
			handle_inference_result(p_model);
		} else {
			LOG_WRN("Failed to run inference, error = %d", (int)res);
		}
		/* INPROGRESS is expected 32/33 times, as we have 33 samples in the
		 * INPUT_WINDOW_SHIFT
		 */
	} else if (res != NRF_EDGEAI_ERR_INPROGRESS) {
		LOG_WRN("Failed to feed inputs, error = %d", (int)res);
	}
}

static void send_imu_data(int16_t *input_data)
{
#if IS_ENABLED(CONFIG_BLE_MODE_NUS)
	(void)ble_nus_send(input_data);
#else
	printk("%d,%d,%d,%d,%d,%d\r\n", input_data[0], input_data[1], input_data[2], input_data[3],
	       input_data[4], input_data[5]);
#endif
}

static bool should_act_on_prediction(const class_label_t class_label)
{
	static const uint32_t PREDICTION_TIMEOUT_MS = 800U;
	static uint32_t last_prediction_time_ms;
	uint32_t current_time_ms;

	if (class_label <= CLASS_LABEL_UNKNOWN) {
		return false;
	}

	current_time_ms = k_uptime_get();

	if ((class_label == CLASS_LABEL_ROTATION_RIGHT) ||
	    (class_label == CLASS_LABEL_ROTATION_LEFT) ||
	    (current_time_ms - last_prediction_time_ms) > PREDICTION_TIMEOUT_MS) {
		last_prediction_time_ms = current_time_ms;
		return true;
	}

	return false;
}

static void log_prediction_message(const char *class_name, const float probability)
{
	__ASSERT_NO_MSG(class_name != NULL);
	LOG_INF("Predicted class: %s, with probability %d %%", class_name,
		(int)(100 * probability));
}

static void handle_inference_result(nrf_edgeai_t *model)
{
	uint16_t predicted_target;
	const flt32_t *p_probabilities;

	__ASSERT_NO_MSG(model != NULL);

	predicted_target = model->decoded_output.classif.predicted_class;
	p_probabilities = model->decoded_output.classif.probabilities.p_f32;
	__ASSERT_NO_MSG(p_probabilities != NULL);

	LOG_DBG("Predicted target: %d, Probability: %f", predicted_target,
		(double)p_probabilities[predicted_target]);

	prediction_ctx_t result =
		inference_postprocess(predicted_target, p_probabilities[predicted_target]);
	if (should_act_on_prediction((class_label_t)result.target)) {
		const char *class_name = inference_get_class_name((class_label_t)result.target);

		log_prediction_message(class_name, result.probability);
#if IS_ENABLED(CONFIG_BLE_MODE_HID)
		send_bt_keyboard_key((class_label_t)result.target);
#elif IS_ENABLED(CONFIG_BLE_MODE_GATT_CUSTOM)
		ble_send_recognized_class((class_label_t)result.target,
					  (size_t)(100.0f * result.probability));
#endif
	}
}
