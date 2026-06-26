BLE LBS Minimal Peripheral
==========================

This sample extends the working `zephyr-ble-min` baseline with a small custom
GATT service.

- connectable advertising
- custom 128-bit service UUID
- one writable characteristic to control `led0`
- one readable characteristic to read current LED state
