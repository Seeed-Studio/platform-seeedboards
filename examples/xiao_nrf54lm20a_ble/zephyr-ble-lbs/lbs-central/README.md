BLE LBS Minimal Central
=======================

This sample extends the working `zephyr-ble-min` baseline with a minimal client
for the matching custom LBS service.

- scans for the matching 128-bit service UUID
- connects automatically
- discovers one writable characteristic
- toggles the remote LED when `sw0` is pressed
