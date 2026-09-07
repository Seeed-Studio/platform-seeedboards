/* Minimal XIAO IMU interface used by the gesture data collector. */
#ifndef XIAO_GESTURE_IMU_H
#define XIAO_GESTURE_IMU_H

#include <stdint.h>

#define IMU_NUM_AXES 3
#define ACCEL_AXIS_NUM 3
#define GYRO_AXIS_NUM 3

typedef enum {
	STATUS_SUCCESS = 0,
	STATUS_INVALID_PARAM = -22,
	STATUS_HARDWARE_ERROR = -5,
} status_t;

typedef enum {
	IMU_ACCEL_SCALE_2G = 2,
	IMU_ACCEL_SCALE_4G = 4,
	IMU_ACCEL_SCALE_8G = 8,
	IMU_ACCEL_SCALE_16G = 16,
} imu_accel_scale_t;

typedef enum {
	IMU_GYRO_SCALE_125DPS = 125,
	IMU_GYRO_SCALE_250DPS = 250,
	IMU_GYRO_SCALE_500DPS = 500,
	IMU_GYRO_SCALE_1000DPS = 1000,
	IMU_GYRO_SCALE_2000DPS = 2000,
} imu_gyro_scale_t;

typedef struct {
	imu_accel_scale_t accel_fs_g;
	imu_gyro_scale_t gyro_fs_dps;
	uint16_t data_rate_hz;
} imu_config_t;

typedef struct {
	struct { float phys; int16_t raw; } accel[IMU_NUM_AXES];
	struct { float phys; int16_t raw; } gyro[IMU_NUM_AXES];
} imu_data_t;

typedef void (*generic_cb_t)(void);

status_t imu_init(const imu_config_t *config, generic_cb_t data_ready_cb);
status_t imu_read(imu_data_t *data);

#endif
