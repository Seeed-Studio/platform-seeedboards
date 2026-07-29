#!/usr/bin/env sh
set -eu

# Restore a XIAO nRF54LM20A to the known-good Zephyr blink firmware.
# This operation mass-erases the application flash and removes APPROTECT.
# It reuses PlatformIO's tool-openocd package; it does not install pyOCD.

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
FIRMWARE="$SCRIPT_DIR/firmware_lm20a_blink.hex"
OPENOCD_CFG="$SCRIPT_DIR/../../builder/board_build/nrf/nrf54lm20a.cfg"

if [ "$#" -gt 1 ]; then
    echo "Usage: $0 [probe-id]" >&2
    exit 5
fi

if [ ! -f "$FIRMWARE" ]; then
    echo "[ERROR] Recovery firmware not found: $FIRMWARE" >&2
    exit 5
fi

if [ ! -f "$OPENOCD_CFG" ]; then
    echo "[ERROR] LM20A OpenOCD configuration not found: $OPENOCD_CFG" >&2
    exit 5
fi

if ! command -v pio >/dev/null 2>&1; then
    echo "[ERROR] PlatformIO Core (pio) is required to run the bundled OpenOCD." >&2
    exit 5
fi

if [ "$#" -eq 1 ]; then
    pio pkg exec -p tool-openocd -- openocd -f interface/cmsis-dap.cfg \
        -c "adapter serial $1" -f "$OPENOCD_CFG" -c "adapter speed 4000" \
        -c "init; nrf54l_mass_erase; halt; nrf54lm20a-load {$FIRMWARE}; reset run; shutdown"
else
    pio pkg exec -p tool-openocd -- openocd -f interface/cmsis-dap.cfg \
        -f "$OPENOCD_CFG" -c "adapter speed 4000" \
        -c "init; nrf54l_mass_erase; halt; nrf54lm20a-load {$FIRMWARE}; reset run; shutdown"
fi

echo "[SUCCESS] XIAO nRF54LM20A recovered with the blink firmware."
