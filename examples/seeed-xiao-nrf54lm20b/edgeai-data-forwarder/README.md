# XIAO nRF54LM20B Nordic Edge AI Data Forwarder

This example adapts Nordic Semiconductor's official `sdk-edge-ai` Data
Forwarder sample to the Seeed Studio XIAO nRF54LM20B.

The firmware streams the onboard LSM6DS3TR-C six-axis IMU at 100 Hz through
the board's USB CDC ACM port. It uses Nordic's official CBOR/COBS framed Data
Forwarder protocol, so it can be consumed by the Nordic Data Collection
Desktop application or the `data_forwarder_host` tool.

## Compatibility status

The adaptation is suitable for platform integration:

- official Data Forwarder protocol and UART transport are reused from the
  `sdk-edge-ai` module;
- the XIAO LSM6DS3TR-C is exposed through Zephyr's LSM6DSL-compatible driver;
- the onboard nPM1300 power path is enabled before the deferred IMU probe;
- USB CDC ACM carries only framed sensor data, while diagnostics go to RTT;
- six channels are sent in the order `ax`, `ay`, `az`, `gx`, `gy`, `gz`;
- the nominal stream rate is 100 Hz (the IMU hardware ODR is configured to
  104 Hz, with a 100 Hz host-facing fetch timer).

This sample is protocol-compatible with the official host tools. Physical
validation still requires a real XIAO nRF54LM20B and a USB data connection.

## Requirements

- XIAO nRF54LM20B
- USB cable with data support
- PlatformIO Core
- Nordic Edge AI Data Collection Desktop application, or the
  `sdk-edge-ai/tools/data_forwarder_host` tool

The platform builder automatically provisions the pinned `sdk-edge-ai`
module when it sees `CONFIG_DATA_FWD_PROTO=y`. A developer can override the
module location with `XIAO_EDGE_AI_DIR`.

## Build and flash

Run from the repository root:

```powershell
pio run -d examples/seeed-xiao-nrf54lm20b/edgeai-data-forwarder `
  -e seeed-xiao-nrf54lm20b

pio run -d examples/seeed-xiao-nrf54lm20b/edgeai-data-forwarder `
  -e seeed-xiao-nrf54lm20b -t upload
```

The USB CDC port is the Data Forwarder transport and must not be opened by a
text serial monitor while the host Data Forwarder tool is connected. RTT is
used for boot and diagnostic logs.

## Host-side collection

1. Flash the firmware and connect the board by USB.
2. Start the Nordic **Data Forwarder Host** desktop application. This is the
   current official name for the GUI previously described as the Data
   Collection Desktop application. See the installation instructions below.
3. Select the XIAO nRF54LM20B USB CDC serial device and create a UART session.
4. Confirm that a session with six channels at 100 Hz appears.
5. Enter a recording label, choose an output directory, and click **Record**.
   Perform the gesture while the board continues streaming, then click
   **Stop**. The application saves a CSV recording and a metadata sidecar.
6. Use Dataset Builder to trim, clean, label/split, and export the dataset
   before uploading it to Nordic Edge AI Lab.

### Downloading and opening Data Forwarder Host

Nordic provides a prebuilt standalone executable, so Python does not need to
be installed on the collection computer:

- [Data Forwarder Host standalone downloads](https://files.nordicsemi.com/artifactory/edge-ai/external/tools/dfh)
- [Windows: `data-forwarder-host.exe`](https://files.nordicsemi.com/artifactory/edge-ai/external/tools/dfh/windows/data-forwarder-host.exe)
- [Linux: `data-forwarder-host`](https://files.nordicsemi.com/artifactory/edge-ai/external/tools/dfh/linux/data-forwarder-host)
- [Official Data Forwarder Host documentation](https://nrfconnectdocs.nordicsemi.com/addons/addon-edge-ai/latest/tools/data_forwarder_host.html)
- [Source and release instructions on GitHub](https://github.com/nrfconnect/sdk-edge-ai/tree/main/tools/data_forwarder_host)

On Windows, download the Windows executable, save it locally, and double-click
it to open the GUI. If Windows displays a SmartScreen warning, verify that the
file was downloaded from the Nordic link above before choosing **More info** →
**Run anyway**. On Linux, download the corresponding executable, mark it
executable if necessary, and launch it from the file manager or a terminal.

In the application:

1. Select **Session → New session…**.
2. Choose **UART** as the data source.
3. Select the COM port created by the XIAO nRF54LM20B USB CDC ACM device.
4. Click **Create session**; streaming starts automatically.
5. Enter a label and output directory, then use **Record** and **Stop** to
   save each recording.

Do not open the same USB CDC port with `pio device monitor`, PuTTY, or another
serial terminal while Data Forwarder Host is connected. This endpoint carries
binary CBOR/COBS frames rather than human-readable log text. Boot and
diagnostic logs are routed to RTT in this sample.

### Troubleshooting: no session information

This firmware starts the IMU stream automatically after boot. It does not wait
for `label`, `start`, or `stop` commands. If the host shows **Awaiting session
info from device** and **Record** is disabled, the host has not received a
valid Data Forwarder session-info frame yet.

The most common cause is that the older
`edgeai-gesture-data-collection` firmware is still running. That firmware
prints a text command banner and waits for `label`/`start`; it is not compatible
with Data Forwarder Host. Rebuild and upload this directory explicitly:

```powershell
pio run -d examples/seeed-xiao-nrf54lm20b/edgeai-data-forwarder `
  -e seeed-xiao-nrf54lm20b -t clean
pio run -d examples/seeed-xiao-nrf54lm20b/edgeai-data-forwarder `
  -e seeed-xiao-nrf54lm20b -t upload
```

After USB reconnects, close any serial monitor and create a new **UART**
session in Data Forwarder Host. The **Record** button becomes enabled after
the first session-info frame arrives. If it remains disabled, verify that the
selected COM port is the newly enumerated XIAO USB CDC port and that no other
application has opened it.

If a standalone binary is not available for your platform, clone the Nordic
`sdk-edge-ai` repository and run the GUI from its
`tools/data_forwarder_host` source directory with Python 3.12 or newer:

```powershell
cd sdk-edge-ai/tools/data_forwarder_host
python -m pip install -r requirements.txt
python -m data_forwarder_host
```

The protocol session metadata reports the following channel names:

```text
ax, ay, az, gx, gy, gz
```

The integer values use micro-SI units, as required by the official protocol:

- acceleration: micro m/s²;
- angular velocity: micro rad/s.

## Hardware notes

The XIAO board powers the IMU through the nPM1300 `power_en` regulator and
`imu_vdd` LDO1. The overlay removes the boot-on property from LDO1 so the
sensor wrapper can power the IMU and then perform the deferred device probe.

The USB CDC ACM endpoint is selected as `ncs,data-forwarder-uart`. Do not use
the same endpoint for a shell or a text console in this application because
binary COBS frames contain arbitrary bytes, including zero delimiters.

## Source layout

```text
edgeai-data-forwarder/
├── cddl/data_forwarder.cddl       Official CBOR schema
├── src/protocol/                  Official protocol and generated CBOR encoder
├── src/transport/                 USB CDC/UART transport adapter
├── src/sensor/lsm6dsl.c           XIAO LSM6DS3TR-C wrapper
└── zephyr/                        Board overlay, Kconfig, and build glue
```

The protocol, generated encoder, and transport files are kept in this example
so the sample is reviewable and buildable independently. They are sourced from
the pinned Nordic `sdk-edge-ai` Data Forwarder implementation; changes to the
upstream protocol should be reviewed before updating these files.

## Related documentation

- [Nordic Edge AI Lab](https://ai.lab.nordicsemi.com)
- [Data Forwarder sample](https://nrfconnectdocs.nordicsemi.com/addons/addon-edge-ai/latest/samples/data_forwarder/README.html)
- [Data Forwarder host tool](https://github.com/nrfconnect/sdk-edge-ai/tree/main/tools/data_forwarder_host)
- [Preparing raw data for Edge AI Lab](https://docs.nordicsemi.com/r/bundle/edge-ai-lab/page/get_started.html/preparing-raw-dataset)
- [Dataset requirements](https://docs.nordicsemi.com/r/bundle/edge-ai-lab/page/model_creating_pipeline/dataset_requirements.html)
