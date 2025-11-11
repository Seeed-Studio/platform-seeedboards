#!/usr/bin/env bash
set -e

# ==============================================
# Recover-only wrapper (Linux/macOS)
# Always uses a dedicated virtual environment
# ==============================================

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
VENV_DIR="$DIR/.venv"
DEP_MARKER="$VENV_DIR/.deps_installed"
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
  echo "[INFO] Installing dependencies into venv (pyocd libusb)..."
  pip install pyocd libusb >/dev/null
  touch "$DEP_MARKER"
else
  echo "[INFO] Dependencies already installed in venv."
fi

python "$DIR/reset_tool.py" --mode recover $EXTRA_ARGS
RC=$?
if [ $RC -ne 0 ]; then
  echo "[ERROR] Recover-only failed (exit code $RC)."
  exit $RC
fi
echo "[SUCCESS] Recover-only completed."
