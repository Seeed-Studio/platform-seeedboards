BLE LBS Peripheral (Zephyr + PlatformIO)
=======================================

This project is the **BLE Peripheral** role. It advertises a custom 128-bit GATT Service and exposes a **write characteristic** so a Central can control the on-board LED.

Hardware & Prerequisites
------------------------

- Board: `Seeed XIAO nRF54L15` (recommended: two boards, one for peripheral and one for central)
- UART log: 115200
- LED/Button: uses Zephyr devicetree `led0` (no button required in this project)

What it Does
------------

- Advertising name: `ble-lbs-peripheral` (from `CONFIG_BT_DEVICE_NAME`)
- The custom service UUID is included in the scan response (the Central uses active scanning to obtain it)
- GATT Service & Characteristics:
	- Service UUID: `8e7f1a23-4b2c-11ee-be56-0242ac120002`
	- Write Characteristic UUID: `8e7f1a24-4b2c-11ee-be56-0242ac120002` (WRITE)
		- Write 1 byte: `0` or `1`
		- Contract: physical GPIO level `0` = LED ON, `1` = LED OFF (many on-board LEDs are active-low, so the code uses “physical level”)
	- Read Characteristic UUID: `8e7f1a25-4b2c-11ee-be56-0242ac120003` (READ)
		- Read 1 byte: current LED physical level (0/1)

LED Status Indication
---------------------

- **Blinking at 2Hz**: advertising and waiting for a connection
- **Solid OFF**: connected (on connect, the LED is forced to OFF and then controlled by Central writes)
- **Solid ON**: advertising start/restart failed (will retry with backoff)

Build & Flash (PlatformIO)
--------------------------

1. Install PlatformIO Core: <https://docs.platformio.org/page/core.html>
2. Clone this repository and enter this folder

Common commands:

```sh
# Build project
pio run

# Upload firmware
pio run --target upload

# Build specific environment
pio run -e seeed-xiao-nrf54l15

# Upload firmware for the specific environment
pio run -e seeed-xiao-nrf54l15 --target upload

# Serial monitor (optional)
pio device monitor -b 115200

# Clean build files
pio run --target clean
```

How to Verify
-------------

1. Flash this project (peripheral) to the first board
2. Flash `../lbs-central` to the second board
3. Open serial monitors for both boards (115200)
4. The peripheral should print and keep `advertising`; the central will scan and connect automatically
5. Press `sw0` on the central board: the peripheral LED should toggle between ON/OFF

Troubleshooting
---------------

- If the peripheral stays solid ON and never prints `advertising`: advertising failed to start; the code retries automatically. Power-cycle the device and/or ensure nothing else is using BLE.
- If the central cannot connect: make sure both boards are powered, close enough, and the central uses **active scanning** (it needs the 128-bit UUID from the scan response).

