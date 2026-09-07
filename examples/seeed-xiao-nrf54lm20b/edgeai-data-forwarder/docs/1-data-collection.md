# Part 1 — Data Collection

This stage records labeled IMU data from the XIAO nRF54LM20B using the
firmware in this sample and Nordic's **Data Forwarder Host** desktop
application. It is the first stage of the custom-model workflow:

```text
collect (this doc)  ->  process (Part 2)  ->  train (Part 3)  ->  deploy
```

- Prev/next: [Overview](../README.md) | [Part 2 — Dataset Processing](2-dataset-processing.md)

## What the firmware does

The firmware streams the onboard LSM6DS3TR-C six-axis IMU over the board's
USB CDC ACM port using Nordic's official CBOR/COBS-framed Data Forwarder
protocol:

- six channels in the order `ax, ay, az, gx, gy, gz`;
- integer values in micro-SI units (acceleration: micro m/s², angular
  velocity: micro rad/s), as required by the official protocol;
- nominal stream rate 100 Hz (the IMU hardware ODR is set to 104 Hz with a
  100 Hz host-facing fetch timer);
- the stream starts automatically after boot — no `label`/`start`/`stop`
  text commands are needed;
- the USB CDC port carries only binary frames; boot and diagnostic logs go
  to RTT.

The protocol implementation, generated CBOR encoder, and transport adapter
are reused from Nordic's pinned `sdk-edge-ai` Data Forwarder sample. See the
[official Data Forwarder sample documentation][official-sample] for the
protocol reference this sample follows.

## Build and flash

Run from the repository root:

```powershell
pio run -d examples/seeed-xiao-nrf54lm20b/edgeai-data-forwarder `
  -e seeed-xiao-nrf54lm20b -t clean

pio run -d examples/seeed-xiao-nrf54lm20b/edgeai-data-forwarder `
  -e seeed-xiao-nrf54lm20b -t upload
```

If upload waits for a DFU port, hold Button 0 (P0.09) while pressing reset
to enter the bootloader, then run the upload command again.

The platform builder provisions the pinned `sdk-edge-ai` module
automatically (override with `XIAO_EDGE_AI_DIR` if needed).

## The host application: Data Forwarder Host

Recordings are captured with Nordic's **Data Forwarder Host**
(`data-forwarder-host.exe` on Windows), the host tool officially
recommended by nRF Connect SDK's Edge AI add-on. It is a standalone GUI —
Python is not required on the collection computer.

Downloads:

- [Data Forwarder Host downloads](https://files.nordicsemi.com/ui/native/edge-ai/external/tools/dfh) — Nordic file browser; open `windows/data-forwarder-host.exe` for Windows or `linux/data-forwarder-host` for Linux
- [Official Data Forwarder Host documentation](https://nrfconnectdocs.nordicsemi.com/addons/addon-edge-ai/latest/tools/data_forwarder_host.html)
- [Source on GitHub](https://github.com/nrfconnect/sdk-edge-ai/tree/main/tools/data_forwarder_host)

On Windows, download the executable and double-click it. If Windows
SmartScreen warns, verify the file came from the Nordic link above, then
choose **More info → Run anyway**. If a standalone binary is not available
for your platform, run the GUI from source:

```powershell
cd sdk-edge-ai/tools/data_forwarder_host
python -m pip install -r requirements.txt
python -m data_forwarder_host
```

## Recording a session

1. Flash the firmware and connect the board with a USB data cable.
2. Start Data Forwarder Host.
3. Select **Session → New session…** and choose **UART** as the data source.
4. Select the COM port of the XIAO nRF54LM20B USB CDC ACM device and click
   **Create session**; streaming starts automatically.
5. Confirm the session reports six channels at 100 Hz.
6. Enter a recording label (for example `idle` or `move`), choose an output
   directory, click **Record**, perform the activity, then click **Stop**.

Each recording is saved as one CSV plus a metadata sidecar (`.txt`), with
columns:

```text
device_time_ms,ax,ay,az,gx,gy,gz,label
```

### Collection tips

- Use one label per recording and one recording per continuous activity —
  the recording boundary becomes a session boundary in Part 2, which keeps
  training windows from mixing activities.
- Collect several separate sessions per class, in different board
  orientations and mounting positions; class imbalance and single-orientation
  data are the two most common reasons a first model underperforms.
- Do not open the same USB CDC port with `pio device monitor`, PuTTY, or
  any other serial terminal while Data Forwarder Host is connected — the
  endpoint carries binary COBS frames, not text. Diagnostics use RTT.

## Troubleshooting

**Host shows "Awaiting session info from device" / Record stays disabled.**
The host has not received a valid session-info frame. The most common cause
is older collector firmware still on the board (a text-command based
custom collector). Rebuild and upload this sample explicitly, then create a
new UART session. If it persists, verify the selected COM port is the newly
enumerated XIAO CDC port and that no other application has it open.

**No COM port appears.** Check the cable carries data (not charge-only),
and see [Part 1 — Build and flash](#build-and-flash) for the DFU
bootloader recovery.

## Official references

- [Official Data Forwarder sample (nRF Connect SDK Edge AI add-on)][official-sample]
- [Data Forwarder Host tool](https://nrfconnectdocs.nordicsemi.com/addons/addon-edge-ai/latest/tools/data_forwarder_host.html)
- [Nordic Edge AI Lab](https://ai.lab.nordicsemi.com)

[official-sample]: https://nrfconnectdocs.nordicsemi.com/addons/addon-edge-ai/latest/samples/data_forwarder/README.html
