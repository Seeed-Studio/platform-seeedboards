# arduino-usb-keyboard

ESP32-S3 USB HID keyboard echo: bytes received on the serial console are typed
as the next ASCII character. It exercises the ESP32 Arduino USB stack
(`USB.h` / `USBHIDKeyboard.h`), not just UART.

Only the ESP32-S3 XIAO boards carry the required USB-OTG peripheral; C3/C5/C6
are intentionally not listed.

```bash
python scripts/ci/build_examples.py --framework arduino --clean \
    --only-env seeed-xiao-esp32-s3-sense
```