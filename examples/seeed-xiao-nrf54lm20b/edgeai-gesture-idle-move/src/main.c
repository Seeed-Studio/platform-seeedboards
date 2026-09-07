/* XIAO nRF54LM20B idle/move inference using a custom Nordic Edge AI Lab model. */
#include <assert.h>
#include <stdio.h>

#include <zephyr/device.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

#include <nrf_edgeai/nrf_edgeai.h>
#include "imu.h"
#include "nrf_edgeai_user_model.h"

LOG_MODULE_REGISTER(main, LOG_LEVEL_INF);

#define INPUT_FEATURES 6

static struct k_sem imu_ready_sem;
static nrf_edgeai_t *model;

static void imu_ready(void)
{
	k_sem_give(&imu_ready_sem);
}

static void print_prediction(void)
{
	uint16_t predicted = model->decoded_output.classif.predicted_class;
	const flt32_t *probabilities = model->decoded_output.classif.probabilities.p_f32;
	const char *name = predicted == 0U ? "idle" :
		(predicted == 1U ? "move" : "unknown");

	printk("prediction: class=%u label=%s probability=%.3f\r\n",
	       predicted, name, (double)probabilities[predicted]);
}

int main(void)
{
	imu_config_t imu_config = {
		.accel_fs_g = IMU_ACCEL_SCALE_4G,
		.gyro_fs_dps = IMU_GYRO_SCALE_1000DPS,
		.data_rate_hz = 100,
	};
	imu_data_t sample;
	flt32_t input[INPUT_FEATURES];
	nrf_edgeai_err_t err;

	k_sem_init(&imu_ready_sem, 0, 1);
	if (imu_init(&imu_config, imu_ready) != STATUS_SUCCESS) {
		LOG_ERR("Failed to initialize the LSM6DS3TR-C IMU");
		return -1;
	}

	model = nrf_edgeai_user_model();
	__ASSERT(model != NULL, "Generated model is NULL");
	__ASSERT(nrf_edgeai_is_runtime_compatible(model),
		 "Generated model is incompatible with the Edge AI runtime");
	err = nrf_edgeai_init(model);
	__ASSERT(err == NRF_EDGEAI_ERR_SUCCESS, "nrf_edgeai_init failed: %d", (int)err);

	printk("XIAO nRF54LM20B custom IMU idle/move recognition\r\n");
	printk("Edge AI Lab solution: %s\r\n", nrf_edgeai_solution_id_str(model));
	printk("Classes: 0=idle, 1=move\r\n");

	for (;;) {
		k_sem_take(&imu_ready_sem, K_FOREVER);
		if (imu_read(&sample) != STATUS_SUCCESS) {
			LOG_ERR("Failed to read IMU sample");
			continue;
		}

		for (int i = 0; i < 3; ++i) {
			/* Match Data Forwarder Host's micro-SI units used for training. */
			input[i] = (flt32_t)(sample.accel[i].phys * 1000000.0f);
			input[i + 3] = (flt32_t)(sample.gyro[i].phys * 1000000.0f);
		}

		err = nrf_edgeai_feed_inputs(model, input, INPUT_FEATURES);
		if (err == NRF_EDGEAI_ERR_SUCCESS) {
			err = nrf_edgeai_run_inference(model);
			if (err == NRF_EDGEAI_ERR_SUCCESS) {
				print_prediction();
			} else {
				LOG_WRN("Inference failed: %d", (int)err);
			}
		} else if (err != NRF_EDGEAI_ERR_INPROGRESS) {
			LOG_WRN("Input feed failed: %d", (int)err);
		}
	}
}
