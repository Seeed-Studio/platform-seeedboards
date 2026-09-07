#!/usr/bin/env bash
set -e

# ==============================================
# Factory reset wrapper (Linux/macOS)
# ==============================================

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
FIRMWARE="${DIR}/firmware.hex"
VENV_DIR="$DIR/.venv"
# Bump the marker to force a reinstall from requirements.txt; older venvs
# still hold stock pyOCD, which faults on nRF54LM20A (issue #69).
DEP_MARKER="$VENV_DIR/.deps_forked_pyocd_v1"
REQ_PROBE="$1"
EXTRA_ARGS=""
if [ -n "$REQ_PROBE" ]; then
    EXTRA_ARGS="--probe $REQ_PROBE"
fi

echo "[INFO] Using virtual environment: $VENV_DIR"
if [ ! -d "$VENV_DIR" ]; then
    echo "[INFO] Creating Python virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

if [ ! -f "$DEP_MARKER" ]; then
    echo "[INFO] Installing dependencies into venv (forked pyocd + libusb)..."
    pip install -r "$DIR/requirements.txt" >/dev/null
    touch "$DEP_MARKER"
else
    echo "[INFO] Dependencies already installed in venv."
fi

if [ ! -f "$FIRMWARE" ]; then
    echo "[ERROR] Firmware file not found: $FIRMWARE"
    exit 2
fi

python "$DIR/reset_tool.py" --mode factory --firmware "$FIRMWARE" $EXTRA_ARGS
RC=$?
if [ $RC -ne 0 ]; then
    echo "[ERROR] Factory reset failed (exit code $RC)."
    exit $RC
fi
echo "[SUCCESS] Factory reset completed."
