# arduino-wifiscan

Scans nearby WiFi networks and prints SSID/RSSI on the serial console. This
is the ESP32 Arduino canonical smoke demo (the `arduino-blink`/`uart` pair
does not exercise the WiFi stack).

Environments cover every ESP32 XIAO: C3, C5, C6, S3 Plus, S3 Sense.

```bash
python scripts/ci/build_examples.py --framework arduino --clean \
    --only-env seeed-xiao-esp32-c3
```

For the full list, run `pio run -d examples/arduino-wifiscan`.