# zephyr-adc

Samples the XIAO ADC channels and logs raw/millivolt values. It exercises the
Zephyr ADC driver and the per-board devicetree overlays, complementing the
GPIO-only blink/uart demos.

Environments: nRF54L15, nRF54LM20A and nRF54LM20A V2. The overlays in
`zephyr/` define the `io-channels` used by `src/main.c`.

```bash
python scripts/ci/build_examples.py --framework zephyr --clean \
    --only-env seeed-xiao-nrf54lm20a
```

Connect an analog source to the A0-A7 pads before expecting meaningful values;
the build itself is hardware-independent.