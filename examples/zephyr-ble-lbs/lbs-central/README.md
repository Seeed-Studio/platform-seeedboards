BLE LBS Central (Zephyr + PlatformIO)
====================================

This project is the **BLE Central** role. It actively scans for nearby advertisements, filters devices that expose the custom 128-bit service UUID, connects automatically, performs GATT discovery, and then uses the on-board button `sw0` to write 1 byte to the Peripheral’s **WRITE characteristic** to control the remote LED.

Hardware & Prerequisites
------------------------

- Board: `Seeed XIAO nRF54L15` (recommended: two boards, one for central and one for peripheral)
- UART log: 115200
- LED/Button: uses Zephyr devicetree `led0` and `sw0`

What it Does
------------

- Device name: `ble-lbs-central` (from `CONFIG_BT_DEVICE_NAME`)
- Scan strategy: **Active Scanning** (because the Peripheral puts the 128-bit UUID in the scan response)
- After connecting:
	1. Discover Primary Service: `8e7f1a23-4b2c-11ee-be56-0242ac120002`
	2. Discover characteristics within the service range and find:
		 - Action (WRITE) UUID: `8e7f1a24-4b2c-11ee-be56-0242ac120002`
	3. Save the value handle for button-triggered writes

Button Behavior (`sw0`)
----------------------

- `sw0` uses 30ms software debounce
- Each valid press toggles between `0` and `1` and writes the value to the Peripheral’s Action (WRITE) characteristic
- Write contract (same as peripheral): physical GPIO level `0` = LED ON, `1` = LED OFF

Central LED Status Indication
-----------------------------

- **Blinking at 2Hz**: scanning
- **Solid ON**: idle / attempting to connect / error waiting to retry
- **Solid OFF**: connected (the central LED is status-only and does not represent the remote LED)

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

1. Flash `../lbs-peripheral` to the first board and power it on
2. Flash this project (central) to the second board and power it on
3. Open the central serial monitor and look for logs like `scanning...` -> `connected` -> `found action handle`
4. Press `sw0` on the central board: the central should print `GATT write ok`, the peripheral should print `rx write: led_level=...`, and the peripheral LED should change

Troubleshooting
---------------

- If it connects but never finds the characteristic (then disconnects): ensure the peripheral UUIDs match the central code, and the peripheral really includes the service UUID in advertisement/scan response.
- If the button does nothing: verify the board has a `sw0` devicetree alias and check for `sw0 init failed` logs.

