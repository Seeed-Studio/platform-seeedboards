#!/bin/bash
set -e

# Get the directory of the script
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
VENV_DIR="$DIR/.venv"
DEP_MARKER="$VENV_DIR/.dependencies_installed"

if [ ! -d "$VENV_DIR" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv "$VENV_DIR"
else
    echo "Reusing existing virtual environment."
fi

echo "Activating virtual environment..."
source "$VENV_DIR/bin/activate"

if [ ! -f "$DEP_MARKER" ]; then
    echo "Installing dependencies..."
    pip install git+https://github.com/pyocd/pyOCD.git libusb intelhex && touch "$DEP_MARKER"
else
    echo "Dependencies are already installed."
fi

echo "Running recovery script..."
python "$DIR/xiao_nrf54l15_recover_flash.py" --hex "$DIR/firmware.hex" --mass-erase

echo "Done. The virtual environment is kept at $VENV_DIR"
