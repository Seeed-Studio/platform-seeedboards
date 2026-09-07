# Custom IMU Idle/Move Recognition

This sample runs Nordic Edge AI Lab solution `95957` on the onboard
LSM6DS3TR-C IMU of the Seeed Studio XIAO nRF54LM20B using the Axon NPU.

```text
0 = idle
1 = move
```

The generated model files are stored under `src/nrf_edgeai_generated/` and
were copied from the downloaded `IMU-gesture-3_95957_v1` package. The sample
uses the nRF Edge AI Add-on provided by the PlatformIO Zephyr integration.

## Build and upload

Run from the repository root:

```powershell
pio run -d examples/seeed-xiao-nrf54lm20b/edgeai-gesture-idle-move `
  -e seeed-xiao-nrf54lm20b -t clean

pio run -d examples/seeed-xiao-nrf54lm20b/edgeai-gesture-idle-move `
  -e seeed-xiao-nrf54lm20b

pio run -d examples/seeed-xiao-nrf54lm20b/edgeai-gesture-idle-move `
  -e seeed-xiao-nrf54lm20b -t upload
```

Open the USB CDC console at 115200 baud with `pio device monitor -b 115200`.

The firmware prints predictions such as:

```text
prediction: class=1 label=move probability=0.998
```

## Input contract

The model expects six floating-point values per IMU sample in this order:

```text
accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z
```

Values are converted to micro-SI units (`m/s² × 1,000,000` and
`rad/s × 1,000,000`), matching the Data Forwarder Host recordings used for
training. The generated model buffers 100 samples (one second at 100 Hz),
extracts its 66 trained features, and uses a 33-sample sliding shift for
approximately three predictions per second.

`device_time_ms`, `class`, and `session_id` are not model inputs.

## Deployment notes

- The generated Axon header requires `CONFIG_NRF_AXON_INTERLAYER_BUFFER_SIZE=68`.
- Keep the six-axis order, sampling rate, units, window size, and feature
  configuration identical to the Edge AI Lab solution.
- This is a feasibility model. Test it with new sessions and orientations
  before using it in an application.
