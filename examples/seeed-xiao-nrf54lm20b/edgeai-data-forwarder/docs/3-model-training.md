# Part 3 — Model Training

This stage trains the classifier on [Nordic Edge AI Lab](https://ai.lab.nordicsemi.com)
from the `training_ready.csv` produced in
[Part 2](2-dataset-processing.md), and explains what each platform setting
means and why the recommended value is chosen. The worked example is the
two-class IMU activity dataset (`idle` / `move`, six channels at 100 Hz).

- Prev: [Part 2 — Dataset Processing](2-dataset-processing.md) | [Overview](../README.md)

## Solution setup — recommended first-run values

| Edge AI Lab setting | Select | Reason |
| --- | --- | --- |
| Signal Processing | **Enable** | This is time-series IMU data. The platform must window the stream and extract features; leaving it off would treat every row as an independent observation. |
| Data Type | **32-bit Floating point** | Axon / LiteRT accepts FLOAT32 input. |
| Normalization Type | **Unique scale for each feature** | Accelerometer and gyroscope channels have different ranges and units; per-feature scaling prevents one group from dominating. |
| Task Type | **Binary Classification** | The dataset contains exactly two classes: `idle` and `move`. |
| Evaluation Metric | **Balanced Accuracy** | The collected data is imbalanced (`idle` has more windows than `move`), so this reflects both classes better than plain Accuracy. |

Balanced Accuracy is chosen specifically because the collected data is
imbalanced: `idle` and `move` have very different window counts, and
Balanced Accuracy averages the per-class accuracy so the larger `idle`
class cannot dominate the reported score.

## Signal-processing (windowing) settings

| Setting | First-run value | Purpose |
| --- | ---: | --- |
| Windowing mode | **Time Interval** | Defines the window in milliseconds using the measured sampling frequency. |
| Window size | **1,000 ms** | One second at 100 Hz = 100 samples; matches the dataset profile from Part 2. |
| Frequency | **100 Hz** | The sampling rate recorded by Data Forwarder Host. |
| Training sliding shift | **1,000 ms** | Non-overlapping windows. Avoids creating many highly similar samples and is easiest to reproduce. |
| Inference sliding shift | **330 ms** (optional) | About 3 predictions per second (~33 samples). Use 1,000 ms when lower CPU usage matters more. |
| Feature extraction | **Default checked set (11 features)** | Statistical and signal-variation information per axis without an unnecessarily large model. Do not use **Select all** on the first run. |
| Feature selection | **Off** | Keeps the baseline reproducible. Enable later only if the compiled model is too large. |
| Centering | **Off** | `idle` and `move` are continuous activity labels, not peak-centered gestures. |

What signal processing does — the same pipeline runs on the device at
inference time, so the model sees the same kind of input during training
and use:

```text
raw IMU rows -> 1-second windows -> features per axis -> one class prediction
```

### Advanced signal-processing options

- **Raw data**: adds original samples to the model input. Not available for
  Axon / LiteRT — leave off.
- **Sub-windowing**: splits each window into smaller sections to capture
  local changes. Leave off for the baseline; it increases feature count and
  can auto-enable feature selection.
- **Frequency-domain features**: FFT-based spectral information. Leave off
  initially; if enabled, the window must be a power of two between 128 and
  2,048 samples.
- **Estimated SRAM usage**: an early memory estimate; the final value is
  only known after compilation.

### Feature families

Each checked feature is computed independently for `ax, ay, az, gx, gy, gz`
inside one window (11 features x 6 axes = the expected 66 model inputs):

| Feature family | Examples | Intent |
| --- | --- | --- |
| Level | Mean, Absolute Mean | Typical signed level and overall magnitude. |
| Extremes | Min, Max | Motion range and sharp excursions. |
| Variation | Mean Absolute Deviation, Standard Deviation | How much the signal varies around its average. |
| Change | Average Magnitude Difference, Root Difference Square | How quickly adjacent samples change; useful for stillness vs movement. |
| Crossings / proportions | Zero-crossing Rate, Mean-crossing Rate, Percentage over Mean/Zero | Oscillation, direction changes, time above a reference. |

Only the six sensor columns are model inputs. `device_time_ms` must be
assigned the timestamp role (never a feature); `class` and `session_id`
are target/metadata, not features. The regression features (intercept and
slope) are unnecessary for this binary activity task.

## Training page — recommended first-run values

| Setting | Recommended value | Meaning and intent |
| --- | --- | --- |
| Session Name | `idle-move-baseline` | Human-readable name for this training run. Does not affect the model. |
| Training Framework | **LiteRT** | The framework for the Axon target; chosen by the solution technology. |
| Epochs | **200** | Maximum passes through the processed training set. The best validation model is retained. |
| Epochs without improvement | **10** | Early-stopping patience: stop after 10 epochs without validation improvement. Safer than a very small patience on a small, noisy dataset. |
| Batch size | **32** | Training samples per gradient update; a reasonable balance for roughly 400 windows. |
| Learning rate | **0.001** | Step size of each weight update. Keep the stable default for the baseline. |
| Weight Quantization | **Per-Tensor** | One quantization scale per weight tensor; simple and a good first Axon baseline. |
| Weights & Coefficients | **Single-precision 32-bit Floating Point** | Locked by LiteRT/Axon: training uses FLOAT32 and the final model is quantized by LiteRT. |
| Output format | **Floating point 32-bit Probabilities** | Class confidence values in 0–1 range; normally locked for LiteRT. |
| Model Architecture | **Simple Fully Connected** | Compact dense network suitable for 66 input features and a small feasibility dataset. |

The output layer is set automatically (one neuron with softmax for binary
classification); do not edit it manually.

### What each training parameter does

- **Epochs** — how many times the model may revisit the complete processed
  dataset. Too few can underfit; too many can overfit.
- **Epochs without improvement** — early-stopping patience, not extra
  training duration. It prevents wasted time after validation stops
  improving.
- **Batch size** — windows used per gradient update. Smaller values use
  less memory but give noisier updates; larger values are faster per epoch
  but may generalize worse on a small dataset.
- **Learning rate** — how large each update is. Too high can diverge; too
  low learns very slowly.
- **Weight Quantization** — how trained weights are represented for
  deployment. Quantization reduces memory and compute cost with a possible
  accuracy trade-off; per-channel modes (if offered) may improve accuracy
  at some overhead.
- **Model Architecture** — how feature values are combined. A dense layer
  learns weighted combinations of all inputs; a compact preset reduces
  overfitting and device cost. Input and output layers are derived from
  the dataset and task automatically.

### If training behaves poorly

- Stops almost immediately → raise **Epochs without improvement** from 10
  to 20 before touching the learning rate.
- Training and validation both low → collect more varied and longer `move`
  sessions before enlarging the network.
- Training high, validation low → stay on **Simple Fully Connected**, keep
  feature selection for a later run, or collect more independent sessions.
- Compiled model exceeds device memory → reduce feature count or enable
  feature selection before changing the task definition.

## Interpreting the results

- Compare **Balanced Accuracy**, per-class recall, and the confusion
  matrix — with ~311 `idle` vs ~91 `move` windows, a high plain Accuracy
  can hide weak `move` performance.
- The **"data was removed" warning** (a few percent of rows) is expected:
  trailing fragments shorter than one window are dropped (see
  [Part 2](2-dataset-processing.md)). Click **Resume Training** and use
  the retained complete windows.
- This is a feasibility dataset. If `move` recall is weak, collect more
  `move` sessions before tuning the model.

## Deploy

Download the generated solution package, copy its `nrf_edgeai_generated/`
folder into the deployment sample, and follow its README:

- [`edgeai-gesture-idle-move`](../edgeai-gesture-idle-move/) — runs the
  trained idle/move classifier on the Axon NPU and prints predictions over
  USB CDC.

Deployment keeps the same six-axis order, units (micro-SI), sampling rate,
window size, and feature configuration as the trained solution.

## Official references

- [Nordic Edge AI Lab](https://ai.lab.nordicsemi.com)
- [Dataset requirements](https://docs.nordicsemi.com/r/bundle/edge-ai-lab/page/model_creating_pipeline/dataset_requirements.html)
- [Dataset Builder](https://github.com/nordicsemi-neuton/dataset-builder)
