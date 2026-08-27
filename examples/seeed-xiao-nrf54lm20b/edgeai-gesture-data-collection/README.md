# Edge AI Gesture Data Collection

This sample collects training data from the onboard LSM6DS3TR-C IMU on the
Seeed Studio XIAO nRF54LM20B. It samples the accelerometer and gyroscope at
100 Hz and sends labelled CSV records through the board's USB CDC ACM serial
port.

## What the sample does

The firmware is idle after startup and does not stream sensor data until a
recording is started. A label is selected over USB CDC before recording. While
recording, one line is printed every 10 ms:

```text
accel_x,accel_y,accel_z,gyro_x,gyro_y,gyro_z,label
```

The six sensor values are integers in the same format as the gesture
recognition sample:

- acceleration: `m/s^2 * 1000`
- angular velocity: `rad/s * 1000`
- channel order: `accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z`

The label is appended as the seventh column. Startup messages and command
responses are also printed, so keep only valid seven-column CSV lines when
creating a dataset.

## Requirements

- XIAO nRF54LM20B
- USB cable with data support
- PlatformIO Core
- A serial terminal such as `pio device monitor`, PuTTY, or a Python serial
  tool

The USB CDC port is the board's default console port. The baud rate is not
used by USB CDC, but `115200` is the conventional monitor setting.

## Build and upload

Run these commands from the repository root:

```powershell
pio run -d examples/seeed-xiao-nrf54lm20b/edgeai-gesture-data-collection `
  -e seeed-xiao-nrf54lm20b -t clean

pio run -d examples/seeed-xiao-nrf54lm20b/edgeai-gesture-data-collection `
  -e seeed-xiao-nrf54lm20b -t upload
```

To open the serial monitor:

```powershell
pio device list
pio device monitor -b 115200
```

If more than one serial port is connected, select the board explicitly with
`--port`, for example:

```powershell
pio device monitor --port COM12 -b 115200
```

After flashing, wait for the USB CDC port to reconnect before opening the
monitor.

## USB CDC commands

Send one command followed by Enter. Labels may contain 1–31 ASCII letters,
digits, `_`, or `-`.

```text
help
label idle
label swipe_left
start
stop
status
```

Command behavior:

- `label <name>` selects the label for future records.
- `start` begins streaming. A label must be selected first.
- `stop` stops streaming immediately.
- `status` reports the selected label and recording state.
- `help` prints the command list.

Changing the label while recording is not recommended. Stop the current
recording first, select the next label, and then start again.

## Recommended capture workflow

1. Open the USB CDC serial monitor.
2. Select one class, for example `label swipe_left`.
3. Send `start`.
4. Keep the board still for 1–2 seconds.
5. Perform one gesture.
6. Keep the board still for another 1–2 seconds.
7. Send `stop`.
8. Save the captured lines under the selected class, for example
   `gesture_dataset/swipe_left/user01_001.csv`.
9. Repeat with independent recordings and the other classes.

Recommended initial classes are `idle`, `swipe_left`, `swipe_right`, `shake`,
`rotate_left`, and `rotate_right`. Collect at least 100 independent samples
per class and vary the operator, hand, orientation, speed, and force.

## Example session

```text
XIAO nRF54LM20B Edge AI gesture data collector
format: accel/gyro values are SI units multiplied by 1000
commands: label <name>, start, stop, status, help
select a label, then start recording
label swipe_left
ok: label=swipe_left
start
ok: recording label=swipe_left
9812,-35,104,2,-1,0,swipe_left
9807,-42,98,3,0,-2,swipe_left
stop
ok: stopped
```

For model training, split recordings by capture batch or operator. Do not
randomly split overlapping windows from one continuous recording into the
training, validation, and test sets.

## Automated collection with the PC script

The `tools/gesture_collect.py` script automates the USB CDC interaction and
saves clean, numbered CSV files. It automatically finds a connected XIAO
nRF54LM20B by VID:PID `2886:8013`. Install the only host dependency first:

```powershell
python -m pip install pyserial
```

From the repository root, collect 100 three-second recordings for one class:

```powershell
python examples/seeed-xiao-nrf54lm20b/edgeai-gesture-data-collection/tools/gesture_collect.py `
  --label swipe_left `
  --count 100 `
  --duration 3 `
  --output gesture_dataset
```

The script creates files such as:

```text
gesture_dataset/swipe_left/swipe_left_001.csv
gesture_dataset/swipe_left/swipe_left_002.csv
```

Each recording includes a two-second preparation countdown. Use `--prepare 0`
to disable it. If automatic detection is not available, select the CDC port
manually:

```powershell
python examples/seeed-xiao-nrf54lm20b/edgeai-gesture-data-collection/tools/gesture_collect.py `
  --port COM12 --label shake --count 20
```

Keep the board still during the countdown, perform exactly one gesture during
each recording, and wait until the script reports `Saved` before moving to the
next sample.

## Train a model with Nordic Edge AI Lab

Use the official Nordic Edge AI Lab to upload the collected CSV files, train a
gesture classification model, evaluate it, and export a model for deployment:

- [Nordic Edge AI Lab](https://ai.lab.nordicsemi.com)
- [Edge AI Lab documentation](https://docs.nordicsemi.com/bundle/edge-ai-lab)
- [Preparing data for gesture recognition](https://docs.nordicsemi.com/r/bundle/edge-ai-lab/page/get_started.html/preparing-data-for-gesture-recognition?contentId=mI0oi_sFCmGnPTyqdX8TRQ)
- [Compile a model for the Axon NPU](https://docs.nordicsemi.com/r/bundle/edge-ai-lab/page/compile_model.html/compile-for-axon-npu)

For this sample, configure the data upload with the six sensor columns in
this order:

```text
accel_x,accel_y,accel_z,gyro_x,gyro_y,gyro_z
```

Use `label` as the target column and set the sampling rate to `100 Hz`. Start
with a one-second window (approximately 100 samples), then adjust the window
and shift according to the generated model requirements.

The Lab accepts one `.csv` or one `.zip` file for a dataset. Do not upload the
individual recording files one by one and expect them to be combined into one
training dataset. The official documentation says to combine distributed CSV
files before uploading because one model uses one dataset.

The safest ZIP layout is a single final CSV at the archive root. The CSV base
name must match the ZIP base name:

```text
gesture_dataset.zip
└── gesture_dataset.csv
```

Avoid nesting the CSV under the local `gesture_dataset/swipe_left/` directory.
If you use a ZIP, verify that it contains only the prepared dataset file.

The `tools/prepare_dataset.py` helper performs this preparation automatically.
It selects label directories, merges their recordings, converts the collector
column names to the Nordic gesture schema, adds numeric class IDs and a
numeric `session_id` for each recording, and creates a ZIP with the matching
CSV at its root. Numeric session IDs are intentional: Edge AI Lab requires all
data values, including an optional session identifier, to be numeric.

For example, to prepare only a small two-class smoke-test dataset:

```powershell
python tools/prepare_dataset.py `
  --input tools/gesture_dataset `
  --labels idle swipe_left `
  --max-files-per-label 5 `
  --output tools/gesture_dataset_upload.zip `
  --keep-csv
```

The command creates:

```text
tools/gesture_dataset_upload.csv
tools/gesture_dataset_upload.zip
└── gesture_dataset_upload.csv
```

Without `--labels`, all label directories are included. Without
`--max-files-per-label`, every recording is included. The default class IDs
are assigned alphabetically; use `--class-map idle=0 swipe_left=1` when a
specific mapping is required.

For the generic Lab upload, the target column can be selected in the dataset
options. For the official Nordic gesture-recognition workflow, follow its
canonical schema when requested: `acc_x`, `acc_y`, `acc_z`, `gyro_x`,
`gyro_y`, `gyro_z`, plus a numeric `class` column whose class IDs start at
`0`. The current collector keeps human-readable `accel_*` names and string
`label` values to match this repository's firmware; rename/map them during
dataset preparation if the Lab validation requires the canonical schema.
