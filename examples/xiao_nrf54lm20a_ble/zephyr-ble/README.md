BLE Minimal Peripheral (Zephyr + PlatformIO)
===========================================

This is the smallest BLE baseline sample for PlatformIO on Seeed XIAO nRF54 boards.
It only does three things:

- enables the Bluetooth stack
- starts connectable advertising
- prints connection and disconnection logs

There is no custom GATT service and no button or LED application logic.
Use this sample first to verify that basic BLE works in the current PlatformIO environment.
