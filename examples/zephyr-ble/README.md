# zephyr-ble

Minimal BLE peripheral with a custom GATT on/off service, used as the
framework-canonical demo for the nRF54 Zephyr boards. It exercises the BLE
stack, connection callbacks and device-tree overlays, which blink/uart do not.

Environments: nRF54L15, nRF54LM20A and nRF54LM20A V2. The sample overlays live
in `zephyr/boards/` and select the board LED/button nodes.

```bash
python scripts/ci/build_examples.py --framework zephyr --clean \
    --only-env seeed-xiao-nrf54l15
```

See `zephyr/prj.conf` for the BLE configuration and `zephyr/boards/*.overlay`
for the per-board wiring.