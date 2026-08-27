# Official Edge AI data collection workflow

Status: proposed

## Context

The Nordic Edge AI Lab currently presents an official workflow based on a Data
Collection Firmware/Data Forwarder sample, the Data Collection Desktop app, and
Dataset Builder. The firmware forwards raw sensor readings, the desktop app
visualizes and labels recordings, and Dataset Builder cleans, segments, and
exports an upload-ready dataset. This differs from the repository's
`edgeai-gesture-data-collection` sample, which combines labeling, fixed-length
recording, CSV filtering, and file creation in a PC script.

## Proposal

Use the official Data Forwarder/Desktop app/Dataset Builder workflow as the
reference for a future production-oriented collection path. Keep the current
USB CDC collector as a lightweight board bring-up and proof-of-concept tool
until protocol compatibility and the target board firmware are verified.

For Nordic Edge AI Lab classification uploads:

- Upload one combined CSV or a ZIP containing one matching CSV at the archive
  root.
- Keep every data value numeric, including an optional numeric `session_id`.
- Select the `class` column as the target column.
- Select `session_id` as Session ID when recordings are kept as separate
  continuous sessions; do not use it as a feature.
- Keep `acc_x`, `acc_y`, `acc_z`, `gyro_x`, `gyro_y`, and `gyro_z` as features.
- Use at least two classes with at least 20 samples per class.

## Holdout validation guidance

For an initial pipeline smoke test, leave automatic holdout validation enabled:
the Lab creates an 80% training and 20% validation split. Upload a separate
holdout dataset only when independent recordings are available for a realistic
final evaluation; never reuse training recordings for holdout validation.

## Alternatives considered

The repository collector is faster to run and useful for validating the XIAO
nRF54LM20B CDC/IMU path, but it is not yet a replacement for the official
desktop labeling and dataset-building workflow.

## Validation

The official documentation was inspected on 2026-08-27. The exact Data
Forwarder sample URL supplied during investigation is:

<https://nrfconnectdocs.nordicsemi.com/addons/addon-edge-ai/latest/samples/data_forwarder/README.html>

The Edge AI Lab dataset requirements page confirms numeric feature values,
numeric classification targets starting at 0, at least two classes with at
least 20 samples per class, and optional Session ID handling.

## Related files

- `examples/seeed-xiao-nrf54lm20b/edgeai-gesture-data-collection/`
- `examples/seeed-xiao-nrf54lm20b/edgeai-gesture-data-collection/tools/prepare_dataset.py`
