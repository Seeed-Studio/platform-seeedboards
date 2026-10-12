# Edge AI data-collection replacement work report

Status: proposed
(Supplementary material: the English sibling note 2026-08-27-official-edge-ai-data-workflow.md is the canonical decision record for this topic; this file preserves the background detail.)

## 1. Background

The project goal is a complete gesture-recognition pipeline on the Seeed Studio XIAO nRF54LM20B:

```text
IMU data collection -> dataset preparation -> Edge AI Lab training -> Axon NPU deployment -> on-device recognition
```

Early on, to validate USB CDC and the onboard LSM6DS3TR-C IMU quickly, a custom sample was developed:

```text
examples/seeed-xiao-nrf54lm20b/edgeai-gesture-data-collection
```

That sample uses USB CDC commands to control fixed-length recordings; a PC script sends commands automatically, receives CSV, saves by label, and merges everything into an upload file via `prepare_dataset.py`.

This approach suits hardware bring-up and small PoCs, but it does not fully match Nordic's official data collection, labeling, and cleaning flow -- users maintain custom commands, recording timing, labels, and data-conversion logic.

## 2. Official dataset acquisition

Nordic Edge AI Lab's current recommended workflow is:

```text
Data Collection Firmware / Data Forwarder
        v
Data Collection Desktop app
        v
Dataset Builder
        v
Edge AI Lab dataset upload
```

Responsibilities:

- **Data Collection Firmware / Data Forwarder**: continuously forwards raw sensor data from the board.
- **Data Collection Desktop app**: receives and visualizes the data and labels gesture segments.
- **Dataset Builder**: splits, cleans, and organizes the labeled continuous recordings into a training dataset.
- **Edge AI Lab**: selects features, target column, and Session ID; runs training, validation, and model export.

Compared with the current DIY approach, the official flow fits production datasets better: continuous recordings, labels, gesture segmentation, and cleaning all have dedicated tool support.

## 3. Replacement decision

Future production data collection will adopt the official Nordic Data Forwarder + Data Collection Desktop app + Dataset Builder flow, gradually replacing the DIY collection.

The DIY sample stays for now, repositioned as:

- validating the XIAO nRF54LM20B IMU, USB CDC, and sample-rate configuration;
- quickly producing small amounts of PoC data before the official tools support the XIAO nRF54LM20B;
- a regression sample for the underlying CDC data path.

The DIY sample is no longer the long-term production data-collection tool.

## 4. Interfaces to preserve during migration

Whether using the DIY sample or the official tools, data entering training must stay consistent with on-device inference:

| Item | Requirement |
|---|---|
| Sensors | 3-axis accelerometer + 3-axis gyroscope |
| Sample rate | 100 Hz |
| Feature order | `acc_x`, `acc_y`, `acc_z`, `gyro_x`, `gyro_y`, `gyro_z` |
| Target column | numeric `class`, consecutively numbered from `0` |
| Session ID | a distinct numeric ID per independent continuous recording, selected as Session ID on the platform |
| Data values | every feature and auxiliary column must be numeric; no strings or empty values |

The official flow additionally requires segmenting non-continuous gestures so the gesture peak sits mid-window, and discarding invalid data from recording starts, ends, and mistakes.

## 5. DIY vs official comparison

| Item | Current DIY sample | Official recommended flow |
|---|---|---|
| Board output | fixed-length, command-controlled CSV | continuous raw sensor forwarding |
| Labeling | `label <name>` command | annotate recording segments in the Desktop app |
| Data splitting | PC script saving per file, limited splitting | automatic splitting and cleaning in Dataset Builder |
| Data format | needs custom conversion scripts | official tools generate the upload format |
| Fit | bring-up, quick PoC | production datasets and model training |
| Maintenance cost | project maintains its own protocol and scripts | follows the official Nordic toolchain |

## 6. Phased implementation plan

### Phase A: confirm the official toolchain

1. Download and run the official Data Collection Firmware / Data Forwarder.
2. Confirm the Data Collection Desktop app discovers and connects to the target device.
3. Confirm the XIAO nRF54LM20B's USB CDC or another transport is compatible with the official protocol.
4. Use the official Dataset Builder to produce a minimal dataset containing `idle` and `swipe_left`.

### Phase B: adapt the XIAO nRF54LM20B

1. If the official firmware does not directly support the XIAO nRF54LM20B, reuse the current IMU driver and USB CDC configuration.
2. Adjust the board output format to the protocol and fields the Data Forwarder expects.
3. Keep the 100 Hz sample rate, six-axis order, and units consistent with on-device inference.
4. Complete end-to-end validation with the Desktop app and Dataset Builder.

### Phase C: replace the official documentation and example entry

1. Make the official toolchain the README's primary data-collection path.
2. Mark the DIY sample as a PoC / low-level communication validation tool.
3. Keep `prepare_dataset.py` as an offline compatibility tool, but no longer part of the recommended flow.
4. Train and export a model using official Dataset Builder output, then verify on the board.

## 7. Training-validation notes

- For a first end-to-end pass, Edge AI Lab's automatic Holdout Validation (80% train / 20% validation) is fine.
- Upload a separate Holdout Dataset only when independent recording batches or independent-operator data exist.
- Classification needs at least two classes with at least 20 samples each; a production model should also include `idle` and `unknown` to avoid misclassifying non-target motions as target gestures.
- Sensor order, sample rate, and units during training must exactly match on-device inference.

## 8. Official reference links

- [Nordic Edge AI Lab](https://ai.lab.nordicsemi.com)
- [Edge AI Lab documentation](https://docs.nordicsemi.com/bundle/edge-ai-lab)
- [Preparing data for gesture recognition](https://docs.nordicsemi.com/r/bundle/edge-ai-lab/page/get_started.html/preparing-raw-dataset)
- [Dataset requirements](https://docs.nordicsemi.com/r/bundle/edge-ai-lab/page/model_creating_pipeline/dataset_requirements.html)
- [Uploading dataset](https://docs.nordicsemi.com/r/bundle/edge-ai-lab/page/model_creating_pipeline/data_uploading_and_setup.html/uploading-dataset?contentId=6zSAGeHVkrQiNvIvmSG0FA)
- [Data Forwarder sample](https://nrfconnectdocs.nordicsemi.com/addons/addon-edge-ai/latest/samples/data_forwarder/README.html)
- [Compile a model for the Axon NPU](https://docs.nordicsemi.com/r/bundle/edge-ai-lab/page/compile_model.html/compile-for-axon-npu)

## 9. Current conclusion

The DIY sample has proven USB CDC data collection and offline dataset preparation, but it should be treated as an early validation tool. Production data collection should migrate to the official Nordic Data Forwarder, Data Collection Desktop app, and Dataset Builder to reduce the maintenance cost of labeling, splitting, cleaning, and format compatibility.
