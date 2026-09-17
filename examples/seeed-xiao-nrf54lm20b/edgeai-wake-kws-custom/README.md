# XIAO nRF54LM20B Custom Wake Word & Keyword Spotting (Axon NPU)

This is a locally adapted sample. It reuses the XIAO onboard PDM microphone, nPM1300 microphone supply, USB CDC logging, and the Axon NPU. Two custom models are currently integrated; both are accelerated by the Axon NPU.

- WW: `Hello_Seeed_95647_wake_word.zip`, solution 95647, label `hello seeed`;
- KWS: `seeed_key word_95649_kws.zip`, solution 95649, class order `OTHER, SILENCE, no, ok, opus, stop, yes`.

The models work as follows:

- Wake Word model (WW): listens continuously; on detection it opens the keyword window;
- Keyword Spotting model (KWS): recognizes command words inside the window; after a timeout it returns to wake-word listening.

## Audio interface frozen before training

The firmware uses the onboard MSM261DGT006 PDM microphone; the current audio configuration is defined in `src/dmic.h`. Training data, the Edge AI Lab project, and the final firmware must all match:

- Mono, left channel;
- 16 kHz PCM;
- 16-bit signed samples;
- the model input window size must equal `DMIC_SAMPLES_IN_BLOCK`;
- audio preprocessing (e.g. mel features) is described by the exported Nordic Edge AI model; the firmware must not change its configuration on its own.

Do not casually change the sample rate, block size, or channel configuration in `src/dmic.h` after training. If the exported model window disagrees with the firmware, the assertions in `ww_init()` or `kws_init()` stop the device from running.

## Training & export (Nordic Edge AI Lab)

The current official Nordic Wake Word and Keyword Spotting flows are both **No data required**: type English phrases/commands, and the platform generates training data, trains, and produces models for the nRF54LM20B Axon NPU. Do not create Neuton/CPU models for these two tasks.

1. Sign in to [Nordic Edge AI Lab](https://ai.lab.nordicsemi.com) and pick **Add New Solution** under **My Solutions**.
2. Create the WW: **Model type = Axon**, **Task type = Wake Word Detection**; enter 1-3 English words (4-30 English characters), audition the pronunciation, then click **Start**. Official estimate: about 1 hour.
3. Create the KWS: **Model type = Axon**, **Task type = Keyword Spotting**; add the command words and click **Start**. Prefer single-word commands spoken within about 1 second and avoid similar-sounding words; official estimate: about 2-3 hours.
4. When both projects finish, download each model archive from **Results**. Live-test each with the browser microphone or recordings; run **Auto Tune** for the WW first, then tune **threshold** and **predictions in a row** per command for the KWS.
5. Record each model package's input window, output classes and index order, detection thresholds, and Axon buffer requirements. Recordings made on the real board/target environment are for independent acceptance and threshold calibration only -- they cannot be skipped.

Official links:

- [Wake Word Detection](https://docs.nordicsemi.com/r/bundle/edge-ai-lab/page/wake_word.html)
- [Keyword Spotting](https://docs.nordicsemi.com/r/bundle/edge-ai-lab/page/keyword_spotting.html)
- [Edge AI Add-on (Axon on-device integration)](https://docs.nordicsemi.com/bundle/addon-edge-ai_latest/page/index.html)

## Installing the exported models

Copy the exports **whole** into the following directories; never mix WW and KWS files in the same directory:

```text
src/ww/nrf_edgeai_generated/
src/kws/nrf_edgeai_generated/
```

If only one side has finished training you can replace just that side's directory; the other side keeps using the reference model from sample 23.

The WW package must contain:

```text
nrf_edgeai_generated/nrf_edgeai_user_model.h
```

and provide the model instance function it calls. CMake binds the WW and KWS wrappers to their respective model headers, avoiding the conflict between the two packages' identically named `nrf_edgeai_user_model.h`. For the currently installed models the wrappers call:

```c
nrf_edgeai_user_model_95647();
nrf_edgeai_user_model_95649();
```

If a later Lab export changes the solution ID, only edit the corresponding `src/ww/wakeword.c` or `src/kws/kws.c` -- never edit the generated model files.

## The three places you must change

1. `zephyr/prj.conf`: set `CONFIG_NRF_AXON_INTERLAYER_BUFFER_SIZE` and `CONFIG_NRF_AXON_PSUM_BUFFER_SIZE` to the **larger of the two models' requirements**.
2. `src/kws/kws.c`: update `enum keyword_class` and `keyword_detection_ctxs[]` so order, count, and names match the KWS model output exactly. The indices of `silence` and `unknown` must also be correct.
3. `src/main.c`: change the example phrase/keywords in the startup log to what you trained; tune the WW history threshold and KWS EMA/confidence thresholds in Kconfig based on field testing.

The wake-word wrapper currently treats "the model's highest-probability class" as the detection candidate. If your wake-word model has multiple output classes you must explicitly accept only the class holding the target wake word in `src/ww/wakeword.c` -- do not rely on the highest probability alone.

## Build & flash

From this directory:

```powershell
pio run -e seeed-xiao-nrf54lm20b
pio run -t upload -e seeed-xiao-nrf54lm20b
pio device monitor -b 115200
```

The default mode is "wake word gates the KWS". Test modes can be switched in `zephyr/prj.conf`:

```ini
CONFIG_APP_MODE_WW_GATED_KWS=y  # default
# CONFIG_APP_MODE_WW_ONLY=y
# CONFIG_APP_MODE_KWS_ONLY=y
```

## First acceptance checklist

- Both models confirmed as Axon, not Neuton/CPU packages.
- Device boots; DMIC initialization and Axon initialization report no errors.
- Sample rate, window length, channels, and preprocessing during training match the firmware.
- The KWS output class count matches the `KEYWORDS_COUNT` assertion.
- Measure false wakes, missed wakes, command misrecognitions, and end-to-end latency separately on recordings not used in training and in the real environment.

Record model versions, dataset splits, buffer values, class mappings, and field-test results in `MODEL_CARD.md` in this directory.
