# XIAO nRF54LM20B Nordic Edge AI Data Forwarder

This sample streams the XIAO nRF54LM20B onboard LSM6DS3TR-C six-axis IMU at
100 Hz over USB CDC ACM using Nordic's official CBOR/COBS-framed Data
Forwarder protocol, so recordings can be captured with Nordic's Data
Forwarder Host tool and turned into a custom Edge AI Lab model.

It is stage 1 of the custom-model workflow:

```text
1. collect            2. process             3. train              4. deploy
(this sample +   ->   dataset-builder   ->   Nordic Edge AI   ->   edgeai-gesture-
 Data Forwarder       merge/validate/        Lab training          idle-move sample
 Host recording)      export
```

## Where to look

Questions about each stage are answered in the matching document:

| Document | Covers |
| --- | --- |
| [docs/1-data-collection.md](docs/1-data-collection.md) | Firmware usage, building and flashing, the **Data Forwarder Host** application (download links, `data-forwarder-host.exe`), step-by-step recording, and collection troubleshooting. |
| [docs/2-dataset-processing.md](docs/2-dataset-processing.md) | Turning recordings into an upload-ready dataset with [dataset-builder](https://github.com/nordicsemi-neuton/dataset-builder): merging sessions, `session_id`, the profile JSON, validate/export commands, and upload settings. |
| [docs/3-model-training.md](docs/3-model-training.md) | Edge AI Lab parameter selection and what every setting means: solution setup, windowing, features, and training-page values, plus result interpretation and deployment. |

## Quick start

```powershell
pio run -d examples/seeed-xiao-nrf54lm20b/edgeai-data-forwarder `
  -e seeed-xiao-nrf54lm20b -t clean

pio run -d examples/seeed-xiao-nrf54lm20b/edgeai-data-forwarder `
  -e seeed-xiao-nrf54lm20b -t upload
```

Then capture recordings with Data Forwarder Host — see
[docs/1-data-collection.md](docs/1-data-collection.md).

## Technical notes

- The protocol, generated CBOR encoder, and UART transport are reused from
  Nordic's pinned `sdk-edge-ai` Data Forwarder sample; the platform builder
  provisions the module automatically when it sees `CONFIG_DATA_FWD_PROTO=y`
  (override with `XIAO_EDGE_AI_DIR`).
- Six channels are sent in the order `ax, ay, az, gx, gy, gz` as 32-bit
  micro-SI integers (micro m/s² and micro rad/s), the units required by the
  official protocol.
- The nominal stream rate is 100 Hz (IMU hardware ODR 104 Hz with a 100 Hz
  host-facing fetch timer); the stream starts automatically after boot.
- The USB CDC endpoint carries only binary frames — never open it with a
  text serial monitor while the host tool is connected. Diagnostics go to
  RTT.
- The IMU is powered through the board `power_en` regulator and the nPM1300
  `imu_vdd` LDO1, both enabled at boot by the board devicetree; the sensor
  wrapper only performs the deferred device probe, since the nPM13xx
  regulator init (priority 92) runs after sensor init (priority 90).

## Source layout

```text
edgeai-data-forwarder/
├── cddl/data_forwarder.cddl       Official CBOR schema
├── docs/                          Three-stage workflow documentation
├── src/protocol/                  Official protocol and generated CBOR encoder
├── src/transport/                 USB CDC/UART transport adapter
├── src/sensor/lsm6dsl.c           XIAO LSM6DS3TR-C wrapper
└── zephyr/                        Board overlay, Kconfig, and build glue
```

## Official references

- [Nordic Edge AI Lab](https://ai.lab.nordicsemi.com)
- [Official Data Forwarder sample](https://nrfconnectdocs.nordicsemi.com/addons/addon-edge-ai/latest/samples/data_forwarder/README.html)
- [Data Forwarder Host tool](https://nrfconnectdocs.nordicsemi.com/addons/addon-edge-ai/latest/tools/data_forwarder_host.html)
- [Dataset requirements](https://docs.nordicsemi.com/r/bundle/edge-ai-lab/page/model_creating_pipeline/dataset_requirements.html)
