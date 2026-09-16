# XIAO nRF54LM20B custom wake word & keyword spotting (Axon NPU)

This is a locally adapted sample. It reuses the on-board XIAO PDM microphone,
the nPM1300 microphone supply, USB CDC logging, and the Axon NPU. It currently
ships two custom models, both accelerated by the Axon NPU:

- WW: `Hello_Seeed_95647_wake_word.zip`, solution 95647, label `hello seeed`;
- KWS: `seeed_key word_95649_kws.zip`, solution 95649, class order
  `OTHER, SILENCE, no, ok, opus, stop, yes`.

The models are:

- Wake word model (WW): continuously listens; on a detection it opens the
  keyword window;
- Keyword spotting model (KWS): recognizes command words inside the window;
  on timeout it returns to wake-word listening.

## Audio interface fixed before training

The firmware uses the on-board MSM261DGT006 PDM microphone; the audio
configuration is defined by `src/dmic.h`. The training data, the Edge AI Lab
project, and the final firmware must all agree:

- mono, left channel;
- 16 kHz PCM;
- 16-bit signed samples;
- the model's input window size must equal `DMIC_SAMPLES_IN_BLOCK`;
- audio preprocessing (e.g. mel features) is described by the exported
  Nordic Edge AI Lab model; the firmware must not change its configuration
  on its own.

Do not casually change the sample rate, block size, or channel configuration
in `src/dmic.h` after training. If a model's exported window disagrees with
the firmware, an assertion in `ww_init()` or `kws_init()` blocks the device
from running.

## Training & export (Nordic Edge AI Lab)

Nordic's official Wake Word and Keyword Spotting are both **No data
required** flows: you enter English phrase/command text and the platform
auto-generates training data, trains, and produces a model for the
nRF54LM20B Axon NPU. Do not create Neuton/CPU models for these two tasks.

1. Sign in to [Nordic Edge AI Lab](https://ai.lab.nordicsemi.com) and, under
   **My Solutions**, choose **Add New Solution**.
2. Create the WW: **Model type = Axon**, **Task type = Wake Word
   Detection**; enter 1–3 English words (4–30 English characters), preview
   the pronunciation, then click **Start**. The official ETA is ~1 hour.
3. Create the KWS: **Model type = Axon**, **Task type = Keyword Spotting**;
   add the command words and click **Start**. Prefer single-word commands,
   spoken in ~1 second, with distinct pronunciations; official ETA ~2–3
   hours.
4. Once both projects finish training, download each model archive from
   **Results**. Live Test each with a browser microphone or recording; run
   **Auto Tune** on the WW first, then tune **threshold** and **predictions
   in a row** per command on the KWS.
5. Record each model package's input window, output classes and index order,
   detection threshold, and Axon buffer requirements. Recordings taken on
   the real board / in the target environment are for independent acceptance
   and threshold calibration only and cannot be skipped.

Official links:

- [Wake Word Detection](https://docs.nordicsemi.com/r/bundle/edge-ai-lab/page/wake_word.html)
- [Keyword Spotting](https://docs.nordicsemi.com/r/bundle/edge-ai-lab/page/keyword_spotting.html)
- [Edge AI Add-on (Axon on-device integration)](https://docs.nordicsemi.com/bundle/addon-edge-ai_latest/page/index.html)

## Installing the exported models

Copy each export **in full** into the directory below; do not mix WW and KWS
files in the same directory:

```text
src/ww/nrf_edgeai_generated/
src/kws/nrf_edgeai_generated/
```

If you only finished training one side, you may replace just that side's
directory; the other side keeps using sample 23's reference model.

The WW package must contain:

```text
nrf_edgeai_generated/nrf_edgeai_user_model.h
```

plus the model instance function it calls. CMake binds the WW and KWS
wrappers to their respective model headers separately, so the two packages'
same-named `nrf_edgeai_user_model.h` files do not collide. For the models
currently installed, the wrappers call:

```c
nrf_edgeai_user_model_95647();
nrf_edgeai_user_model_95649();
```

If a later Lab export changes the solution ID, edit only the corresponding
`src/ww/wakeword.c` or `src/kws/kws.c`; do not edit the generated model files.

## The three places you must edit

1. `zephyr/prj.conf`: set `CONFIG_NRF_AXON_INTERLAYER_BUFFER_SIZE` and
   `CONFIG_NRF_AXON_PSUM_BUFFER_SIZE` to the **larger of the two models'
   required values**.
2. `src/kws/kws.c`: update `enum keyword_class` and
   `keyword_detection_ctxs[]` so the order, count, and names strictly match
   the KWS model's output. The indices for `silence` and `unknown` must also
   be correct.
3. `src/main.c`: update the example phrase/keywords in the boot log to what
   you trained; tune the WW history threshold and the KWS EMA/confidence
   thresholds in Kconfig based on on-site testing.

The wake-word wrapper currently treats "the model's highest-probability
class" as the detection candidate. If your wake-word model has multiple
output classes, you must explicitly accept only the target wake-word class
in `src/ww/wakeword.c`; do not rely on the top probability alone.

## Build & flash

From this directory:

```powershell
pio run -e seeed-xiao-nrf54lm20b
pio run -t upload -e seeed-xiao-nrf54lm20b
pio device monitor -b 115200
```

The default run mode is "wake word gates KWS". Test modes can be switched in
`zephyr/prj.conf`:

```ini
CONFIG_APP_MODE_WW_GATED_KWS=y  # default
# CONFIG_APP_MODE_WW_ONLY=y
# CONFIG_APP_MODE_KWS_ONLY=y
```

## First acceptance checklist

- Both models are confirmed to be Axon, not Neuton/CPU packages.
- The device boots; DMIC and Axon initialization complete without errors.
- The training sample rate, window length, channel, and preprocessing match
  the firmware.
- The KWS output class count matches the `KEYWORDS_COUNT` assertion.
- Count false wakes, missed wakes, command misrecognitions, and end-to-end
  latency separately on recordings not used in training and in the real
  environment.

Record model versions, dataset splits, buffer values, class mappings, and
on-site test results in `MODEL_CARD.md` in the same directory.
