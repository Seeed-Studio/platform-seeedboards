#!/usr/bin/env python3
"""
UF2 upload tool for TinyUF2 bootloader.

Detects the UF2 mass storage device, optionally triggers bootloader mode
via serial 1200-baud touch (for boards with USB CDC support), and writes
the .uf2 firmware file to the virtual FAT drive.

Supports: Linux, Windows, macOS
"""

import os
import sys
import time
import argparse
import subprocess
import platform

# ---------------------------------------------------------------------------
# UF2 drive detection
# ---------------------------------------------------------------------------

UF2_VOLUME_LABEL = "XIAOC5BOOT"
UF2_DRIVE_TIMEOUT = 30  # seconds to wait for drive to appear


def set_volume_label(label):
    """Override the default volume label for UF2 drive detection."""
    global UF2_VOLUME_LABEL
    UF2_VOLUME_LABEL = label


def _find_uf2_drive_linux():
    """Find UF2 drive on Linux using /dev/disk/by-label or lsblk."""
    # Method 1: /dev/disk/by-label/
    by_label = "/dev/disk/by-label"
    if os.path.isdir(by_label):
        for entry in os.listdir(by_label):
            if entry.upper() == UF2_VOLUME_LABEL.upper():
                dev = os.path.realpath(os.path.join(by_label, entry))
                # Find mount point
                try:
                    result = subprocess.run(
                        ["lsblk", "-no", "MOUNTPOINT", dev],
                        capture_output=True, text=True, timeout=5
                    )
                    mount = result.stdout.strip()
                    if mount and os.path.isdir(mount):
                        return mount
                except Exception:
                    pass
                # Try to mount
                mnt = "/mnt/uf2_upload"
                try:
                    os.makedirs(mnt, exist_ok=True)
                    subprocess.run(["mount", dev, mnt], capture_output=True, timeout=10)
                    time.sleep(0.5)
                    if os.path.ismount(mnt):
                        return mnt
                except Exception:
                    pass

    # Method 2: lsblk
    try:
        result = subprocess.run(
            ["lsblk", "-no", "LABEL,MOUNTPOINT", "-l"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.strip().split("\n"):
            parts = line.strip().split(None, 1)
            if len(parts) == 2 and parts[0].upper() == UF2_VOLUME_LABEL.upper():
                mount = parts[1].strip()
                if mount and os.path.isdir(mount):
                    return mount
    except Exception:
        pass

    return None


def _find_uf2_drive_windows():
    """Find UF2 drive on Windows using powershell."""
    try:
        result = subprocess.run(
            ["powershell", "-Command",
             "(Get-WmiObject Win32_LogicalDisk | "
             "Where-Object { $_.VolumeName -eq '" + UF2_VOLUME_LABEL
             + "' }).DeviceID"],
            capture_output=True, text=True, timeout=10
        )
        drive = result.stdout.strip()
        if drive and os.path.isdir(drive):
            return drive
    except Exception:
        pass
    return None


def _find_uf2_drive_macos():
    """Find UF2 drive on macOS."""
    mnt = "/Volumes/" + UF2_VOLUME_LABEL
    if os.path.isdir(mnt):
        return mnt
    return None


def find_uf2_drive():
    """Find the UF2 mass storage device by volume label."""
    system = platform.system()
    if system == "Linux":
        return _find_uf2_drive_linux()
    elif system == "Windows":
        return _find_uf2_drive_windows()
    elif system == "Darwin":
        return _find_uf2_drive_macos()
    return None


def wait_for_uf2_drive(timeout=UF2_DRIVE_TIMEOUT):
    """Wait for UF2 drive to appear, return path or None."""
    start = time.time()
    dots = 0
    while time.time() - start < timeout:
        drive = find_uf2_drive()
        if drive:
            return drive
        time.sleep(0.5)
        dots += 1
        if dots % 4 == 0:
            sys.stdout.write(".\n")
            sys.stdout.flush()
        else:
            sys.stdout.write(".")
            sys.stdout.flush()
    return None


# ---------------------------------------------------------------------------
# Bootloader trigger
# ---------------------------------------------------------------------------

def trigger_bootloader_1200baud(port):
    """Trigger bootloader via 1200 baud touch.

    This is the standard mechanism used by CircuitPython, Adafruit UF2,
    and Arduino boards. When the application firmware detects a 1200 baud
    connection, it writes the double-tap magic to RAM and resets into
    bootloader mode.

    Works only if the application firmware implements USB CDC with
    1200-baud detection.
    """
    try:
        import serial
    except ImportError:
        return False

    try:
        # Open at 1200 baud - this is the "magic" signal
        s = serial.Serial(port, 1200)
        time.sleep(0.1)
        # Toggle DTR to ensure the signal is sent
        s.dtr = False
        time.sleep(0.05)
        s.dtr = True
        time.sleep(0.05)
        s.close()
        return True
    except Exception:
        return False


def trigger_bootloader_dtr_double_tap(port):
    """Trigger bootloader via DTR double-tap simulation.

    For boards where the USB-serial chip's DTR is connected to the MCU's
    NRST pin (e.g. via a capacitor). Toggles DTR twice within the 500ms
    double-tap window of TinyUF2.
    """
    try:
        import serial
    except ImportError:
        return False

    try:
        s = serial.Serial(port, 115200)
        # First reset
        s.dtr = False
        time.sleep(0.05)
        s.dtr = True
        # Wait within the 500ms double-tap window
        time.sleep(0.2)
        # Second reset (double-tap)
        s.dtr = False
        time.sleep(0.05)
        s.dtr = True
        time.sleep(0.1)
        s.close()
        return True
    except Exception:
        return False


def trigger_bootloader(port):
    """Try all bootloader trigger methods on a serial port."""
    # Method 1: 1200 baud touch (standard UF2 mechanism)
    if trigger_bootloader_1200baud(port):
        return True
    # Method 2: DTR double-tap (hardware reset connection)
    if trigger_bootloader_dtr_double_tap(port):
        return True
    return False


# ---------------------------------------------------------------------------
# UF2 file copy
# ---------------------------------------------------------------------------

def write_uf2_to_drive(uf2_path, drive_path):
    """Write UF2 firmware to the bootloader drive using raw binary I/O.

    Uses raw chunked write instead of shutil.copy2 because TinyUF2's
    virtual FAT filesystem (ghostfat) does not support file metadata
    operations. shutil.copy2 fails with WinError 433 on Windows.

    The bootloader intercepts sector writes and processes UF2 blocks
    in real-time. When all blocks are received, the device resets
    automatically (drive disappears).
    """
    dest = os.path.join(drive_path, os.path.basename(uf2_path))
    chunk_size = 512  # Match UF2 block / FAT sector size

    try:
        with open(uf2_path, "rb") as src:
            with open(dest, "wb") as dst:
                while True:
                    chunk = src.read(chunk_size)
                    if not chunk:
                        break
                    dst.write(chunk)
                dst.flush()
                try:
                    os.fsync(dst.fileno())
                except OSError:
                    pass
        return True
    except OSError as e:
        # If the drive disappears after writing, the bootloader received
        # the firmware and is resetting - this is actually success.
        errno = getattr(e, "winerror", getattr(e, "errno", 0))
        if errno == 433:  # WinError 433: device does not exist
            # Check if the drive is gone (device reset = upload success)
            time.sleep(1)
            if not find_uf2_drive():
                return True
        print(f"  Write error: {e}")
        return False


def write_uf2_cmd(uf2_path, drive_path):
    """Fallback: use OS copy command for writing UF2 file."""
    dest = os.path.join(drive_path, os.path.basename(uf2_path))
    system = platform.system()

    try:
        if system == "Windows":
            # Use xcopy for better compatibility with virtual filesystems
            result = subprocess.run(
                ["cmd", "/c", "copy", "/B", "/Y", uf2_path, dest],
                capture_output=True, text=True, timeout=30
            )
            return result.returncode == 0
        elif system == "Linux":
            subprocess.run(["cp", uf2_path, dest], timeout=30, check=True)
            subprocess.run(["sync"], timeout=10)
            return True
        else:  # macOS
            subprocess.run(["cp", uf2_path, dest], timeout=30, check=True)
            return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Main upload flow
# ---------------------------------------------------------------------------

def upload_uf2(uf2_path, serial_port=None, timeout=UF2_DRIVE_TIMEOUT):
    """Complete UF2 upload flow.

    Args:
        uf2_path: path to .uf2 firmware file
        serial_port: optional serial port for bootloader trigger
        timeout: seconds to wait for UF2 drive

    Returns:
        True on success, False on failure
    """
    if not os.path.isfile(uf2_path):
        print(f"Error: UF2 file not found: {uf2_path}")
        return False

    print(f"UF2 Upload: {uf2_path}")
    print(f"  Volume label: {UF2_VOLUME_LABEL}")
    print(f"  Firmware size: {os.path.getsize(uf2_path)} bytes")

    # Step 1: Check if drive already exists
    drive = find_uf2_drive()
    if drive:
        print(f"  Found UF2 drive: {drive}")
    else:
        # Step 2: Try serial trigger
        if serial_port:
            print(f"  Triggering bootloader via {serial_port}...")
            trigger_bootloader(serial_port)
        else:
            print("  Attempting serial bootloader trigger...")
            for candidate in _detect_serial_ports():
                trigger_bootloader(candidate)

        # Step 3: Wait for drive
        print(f"  Waiting for UF2 drive (double-tap RESET if needed, "
              f"timeout {timeout}s)...", end="")
        sys.stdout.flush()

        drive = wait_for_uf2_drive(timeout)
        if not drive:
            print("\nError: UF2 drive not found.")
            print(f"  Please double-tap the RESET button on your board "
                  f"to enter bootloader mode.")
            print(f"  The drive should appear as '{UF2_VOLUME_LABEL}'.")
            return False
        print(f"\n  Found UF2 drive: {drive}")

    # Step 4: Write .uf2 file (try raw I/O first, fallback to OS command)
    print("  Writing firmware...")
    if write_uf2_to_drive(uf2_path, drive):
        # Give the bootloader time to process and reset
        time.sleep(2)
        if not find_uf2_drive():
            # Drive disappeared = device reset = upload success
            print("  Upload complete! Board is restarting.")
        else:
            print("  Upload complete! Board will restart shortly.")
        return True

    # Fallback: try OS copy command
    print("  Raw write failed, trying OS copy command...")
    if write_uf2_cmd(uf2_path, drive):
        time.sleep(2)
        print("  Upload complete!")
        return True

    print("  Error: Failed to write UF2 file.")
    return False


def _detect_serial_ports():
    """Auto-detect available serial ports."""
    ports = []
    try:
        import serial.tools.list_ports
        for info in serial.tools.list_ports.comports():
            ports.append(info.device)
    except Exception:
        if platform.system() == "Linux":
            for p in ["/dev/ttyACM0", "/dev/ttyACM1",
                      "/dev/ttyUSB0", "/dev/ttyUSB1"]:
                if os.path.exists(p):
                    ports.append(p)
        elif platform.system() == "Windows":
            for i in range(256):
                candidate = f"COM{i}"
                try:
                    import serial
                    s = serial.Serial(candidate)
                    s.close()
                    ports.append(candidate)
                except Exception:
                    pass
    return ports


def main():
    parser = argparse.ArgumentParser(
        description="Upload UF2 firmware to TinyUF2 bootloader"
    )
    parser.add_argument(
        "uf2_file",
        help="Path to .uf2 firmware file"
    )
    parser.add_argument(
        "-p", "--port", default=None,
        help="Serial port for bootloader trigger"
    )
    parser.add_argument(
        "--label", default=None,
        help="Volume label of UF2 drive (default: XIAOC5BOOT)"
    )
    parser.add_argument(
        "-t", "--timeout", type=int, default=UF2_DRIVE_TIMEOUT,
        help=f"Timeout in seconds (default: {UF2_DRIVE_TIMEOUT})"
    )
    parser.add_argument(
        "--trigger-only", action="store_true",
        help="Only trigger bootloader, do not upload"
    )

    args = parser.parse_args()

    if args.label:
        set_volume_label(args.label)

    if args.trigger_only:
        if args.port:
            print(f"Triggering bootloader via {args.port}...")
            trigger_bootloader(args.port)
        else:
            for port in _detect_serial_ports():
                print(f"Trying {port}...")
                trigger_bootloader(port)
        return

    success = upload_uf2(args.uf2_file, args.port or None, args.timeout)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
