# Part 2 — Dataset Processing

Raw Data Forwarder Host recordings are one CSV per session and are not yet
in the form Nordic Edge AI Lab expects. This stage merges them, adds a
session boundary column, validates against the platform's dataset rules,
and exports one upload-ready CSV using the
[nordicsemi-neuton/dataset-builder][repo] tool.

- Prev/next: [Part 1 — Data Collection](1-data-collection.md) | [Part 3 — Model Training](3-model-training.md)

## Why processing is required

Edge AI Lab requires a single combined, time-ordered CSV with numeric class
labels and a session column that prevents training windows from crossing
recording boundaries. Data Forwarder Host writes each recording to a
separate CSV with a text `label` column and no `session_id` column, so:

- the per-recording `label` (`idle`/`move`) is converted to a numeric
  `class` (`0`/`1`);
- a unique numeric `session_id` is added to each source recording so
  non-overlapping training windows never straddle two activities;
- the recordings are concatenated into one time-ordered dataset.

`session_id` is not an IMU signal and does not come from the device; it is
a boundary marker added during this stage.

## Get dataset-builder

```powershell
git clone https://github.com/nordicsemi-neuton/dataset-builder.git
cd dataset-builder
python -m pip install -r requirements.txt
```

Requires Python 3.11+ with numpy, pandas, scipy. The launcher is
`data-builder.py` and works on Windows, macOS, and Linux.

## The dataset profile

A profile JSON describes how the tool should interpret the merged data:
its sensor columns, time and session columns, sampling rate, label
encoding, and window settings. Copy the worked example in
`data/skill-presets/nordic-gesture-demo.json` and edit it to match the
idle/move dataset:

```json
{
  "signal_columns": ["ax", "ay", "az", "gx", "gy", "gz"],
  "timestamp_column": "device_time_ms",
  "session_column": "session_id",
  "sampling_rate_hz": 100,
  "class_column": "class",
  "class_map": { "idle": 0, "move": 1 },
  "window_size": 100,
  "center": false
}
```

`center` is `false` because `idle` and `move` are continuous activity
classes, not discrete gestures whose peaks should be aligned to the window
center.

## Merge the recordings

Concatenate the source recordings into one time-ordered CSV with numeric
`class` and `session_id`. A small repeatable script (for example
`prepare_idle_move.py`) reads each source CSV in order, assigns an
incrementing `session_id`, converts `label` to `class`, and writes a merged
file such as `training_input.csv`:

```text
device_time_ms,ax,ay,az,gx,gy,gz,class,session_id
```

Keep the original recording CSVs untouched; the merge is a pure, repeatable
transformation over them.

## Validate and export

Run from the dataset-builder checkout:

```powershell
python data-builder.py validate `
  training_input.csv `
  --profile idle_move_profile.json

python data-builder.py prep `
  training_input.csv `
  --profile idle_move_profile.json `
  --out training_ready.csv `
  --window 100 `
  --no-center
```

`validate` reports `PASS`, `FIX-REQUIRED`, or `WILL-LOSE-DATA` against the
platform's dataset rules (encoding, separators, column names, label
encoding, sampling rate, missing values). `prep --out` produces the
upload-ready `training_ready.csv` and (if emitted) a class
`..._dictionary.json`.

Useful extra commands:

```powershell
python data-builder.py quality-report idle_*.csv move_*.csv `
  --profile idle_move_profile.json
```

## Reading the result

After a successful export, sanity-check the numbers before training:

| Check | Expected |
| --- | --- |
| Columns | the six sensor columns + `class` + `session_id` |
| Missing values | none |
| Sampling rate | 100 Hz, single rate across all sessions |
| Window count | one non-overlapping 100-sample window per second of data |
| Class balance | `idle` and `move` window counts; note the imbalance |

For the reference idle/move dataset the export keeps roughly 311 `idle` and
91 `move` non-overlapping windows. The classes are imbalanced, so review
the model with **Balanced Accuracy** (or Weighted F1) rather than plain
Accuracy — see [Part 3](3-model-training.md).

A "data was removed" warning is normal: with a 1000 ms window and a 1000 ms
training shift, a short trailing fragment at the end of a session that
cannot form a complete window is dropped. It does **not** mean the sensor
columns are invalid. To reduce discarded tails, use a smaller training
shift (for example 500 ms), but that creates overlapping windows and
increases class imbalance; it is not necessary for a first baseline.

## Upload to Edge AI Lab

Upload only `training_ready.csv` to [Nordic Edge AI Lab](https://ai.lab.nordicsemi.com).
In the dataset setup:

- target column: `class`;
- session column: `session_id`;
- input columns: `ax, ay, az, gx, gy, gz` (keep this order);
- sampling rate: 100 Hz;
- input data type: **FLOAT32** (Axon / LiteRT target);
- signal processing: **enabled**, with a 1000 ms (100-sample) training
  window and 1000 ms training shift.

Then proceed to [Part 3 — Model Training](3-model-training.md) for the
full parameter rationale.

## Official references

- [Dataset Builder (source)][repo]
- [Edge AI Lab dataset requirements](https://docs.nordicsemi.com/r/bundle/edge-ai-lab/page/model_creating_pipeline/dataset_requirements.html)
- [Preparing raw data for Edge AI Lab](https://docs.nordicsemi.com/r/bundle/edge-ai-lab/page/get_started.html/preparing-raw-dataset)

[repo]: https://github.com/nordicsemi-neuton/dataset-builder
