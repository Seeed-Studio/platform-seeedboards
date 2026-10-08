#!/usr/bin/env python3
"""
nrfutil mcu-manager serial uploader for XIAO nRF54LM20B-class boards.

Runs as its own console process so Ctrl+C aborts every wait instantly.
PlatformIO/SCons executes upload actions inside a worker thread where
CPython never raises KeyboardInterrupt on Windows (the SIGINT flag is
only handled on the main thread, which stays parked in an uninterruptible
Thread.join for the whole task), so wait loops living inside the builder
cannot be interrupted at all. As a direct child of the console this
script receives the Ctrl+C event itself and dies immediately, taking the
nrfutil child with it -- the same mechanism that makes the STM32 UF2
uploader (uf2upload.py) interruptible.

Ported from DfuUpload1200 and its helpers in
builder/board_build/nrf/nrf_build.py; the busy-port handling and the
9600-bps line-coding prime before the 1200-bps touch come from PR #100.

Board CDC identities come from the manifest's upload.cdc:
  app_vidpid    : the running user app (Seeed VID 0x2886, CDC_ACM_SERIAL_PID
                  per board, set in the framework board Kconfig).
  loader_vidpids: the DFU loader image (Seeed VID 0x2886, PID baked into the
                  factory USB_DFU.hex). A list so a legacy loader VID:PID can
                  be added in one line.
"""

import argparse
import errno
import platform
import subprocess
import sys
import time

LOADER_WAIT_TIMEOUT = 60   # seconds to poll for the loader CDC
UPLOAD_TIMEOUT = 120       # nrfutil image-upload --timeout
RESET_TIMEOUT = 60         # nrfutil reset --timeout


def _list_ports():
    from serial.tools import list_ports
    return list_ports.comports()


def _vidpid_of(port_info):
    if port_info.vid is None or port_info.pid is None:
        return None
    return "%04X:%04X" % (port_info.vid, port_info.pid)


def _find_port_by_vidpid(vidpid, ports=None):
    vidpid = vidpid.upper()
    for p in ports if ports is not None else _list_ports():
        if _vidpid_of(p) == vidpid:
            return p.device
    return None


def _find_loader_port(loader_vidpids, ports=None):
    for vidpid in loader_vidpids:
        port = _find_port_by_vidpid(vidpid, ports)
        if port:
            return port
    return None


def _wait_for_loader_port(loader_vidpids, timeout=LOADER_WAIT_TIMEOUT):
    for _ in range(timeout):
        port = _find_loader_port(loader_vidpids)
        if port:
            return port
        time.sleep(1)
    return None


def _port_busy(exc):
    """True when a serial open failed because another program holds the
    port.

    Windows serial open failures carry no errno, so match the WinError 5
    text there (the exception class name survives a localized message).
    POSIX chains the original OSError, where only EBUSY means busy:
    EACCES is a permissions problem (e.g. user not in the dialout group,
    or a macOS privacy denial) and must fail fast instead of being
    waited on as if a monitor held the port.
    """
    if platform.system() == "Windows":
        return "PermissionError" in str(exc) or "Access is denied" in str(exc)
    return getattr(exc.__cause__ or exc.__context__, "errno", None) == errno.EBUSY


def _open_close_port(port, baudrate):
    """Open and close a COM port briefly, changing its line coding.

    Returns None on success, "busy" when another program holds the
    port open, or the open error text for other failures.
    """
    import serial
    try:
        ser = serial.Serial(port=port, baudrate=baudrate)
    except serial.SerialException as exc:
        if _port_busy(exc):
            return "busy"
        return str(exc)
    try:
        ser.setDTR(False)
    finally:
        ser.close()
    return None


def _touch_app_port(app_port, loader_vidpids, timeout=LOADER_WAIT_TIMEOUT):
    """Perform the 1200-bps DFU touch, reporting a busy port instead of
    failing silently.

    PlatformIO's env.TouchSerialPort wraps its open/close in a bare
    ``except: pass``, so a port held open by a serial monitor makes the
    touch a silent no-op and the upload then times out pointing at the
    board. A 9600-bps open/close runs first here: it doubles as an
    occupancy probe (while the port is busy, wait for the user to close
    it or to enter DFU via Button 0), and it guarantees the line coding
    moves off 1200 before the touch, because usbser only issues
    SET_LINE_CODING when the baud rate actually changes and a previous
    failed touch leaves the device sitting at 1200.

    Returns True when the 1200-bps touch was performed (or the DFU
    loader is already up), False after printing an error.
    """
    for remaining in range(timeout, -1, -1):
        result = _open_close_port(app_port, 9600)
        if result is None:
            break
        if result != "busy":
            sys.stderr.write("Error: could not open %s: %s\n"
                             % (app_port, result))
            return False
        if remaining == timeout:
            print("Port %s is busy (serial monitor/terminal?). Waiting up "
                  "to %ds for it to be released or for Button 0 DFU "
                  "entry..." % (app_port, timeout))
        if _find_loader_port(loader_vidpids):
            print("Board entered DFU mode while waiting for %s." % app_port)
            return True
        if remaining == 0:
            sys.stderr.write(
                "Error: %s is held by another program. Close the serial "
                "monitor/terminal using it and retry, or hold Button 0 "
                "(P0.09) and press reset to enter DFU mode.\n" % app_port)
            return False
        time.sleep(1)

    result = _open_close_port(app_port, 1200)
    if result is not None:
        # The 9600-bps prime just succeeded, so an error here usually means
        # the application reset in response to the 1200-bps request and the
        # USB device detached underneath the touch (the trigger worked).
        # Let the loader-port wait decide what really happened.
        print("Touch on %s ended early (%s); waiting for the DFU loader..."
              % (app_port, result))
    return True


def resolve_upload_port(app_vidpid, loader_vidpids, explicit=None):
    """Resolve the DFU (loader) upload port.

    Handles every board state so a crashed/empty app never bricks the device:
      1) an explicit upload_port (--upload-port / `upload_port =`) is honored;
         its role is detected by VID:PID;
      2) the loader CDC is already present (board already in DFU via Button 0
         + reset, or via the empty-slot NO_APPLICATION auto-loader) -> use it
         directly and skip the 1200-bps touch (the anti-brick fast path);
      3) the app CDC is present (healthy app) -> touch 1200 to reboot into the
         loader, then poll for the loader CDC (matching its VID:PID only, not
         WaitForNewSerialPort's "any new port", so other USB devices cannot be
         grabbed by mistake);
      4) nothing recognized -> prompt the user to enter DFU manually and poll
         for the loader CDC.

    Returns the port to upload to, or None after printing an error.
    """
    # (1) Explicit port: detect its role by VID:PID.
    if explicit:
        if explicit == _find_loader_port(loader_vidpids):
            print("Configured port %s is the DFU loader; using it directly."
                  % explicit)
            return explicit
        # Otherwise treat it as the app port -> fall through to the touch path.
    else:
        # (2) Loader CDC already present -> board already in DFU mode.
        loader_port = _find_loader_port(loader_vidpids)
        if loader_port:
            print("Board already in DFU mode; using loader port %s."
                  % loader_port)
            return loader_port

    # (3) App CDC present -> touch 1200 -> poll for the loader CDC.
    app_port = explicit or _find_port_by_vidpid(app_vidpid)
    if app_port:
        print("Touching %s at 1200 baud → DFU..." % app_port)
        if not _touch_app_port(app_port, loader_vidpids):
            return None
        loader_port = _wait_for_loader_port(loader_vidpids)
        if not loader_port:
            sys.stderr.write(
                "Error: the board did not enter DFU mode after the 1200-bps "
                "touch. Hold Button 0 (P0.09) and press reset, then retry.\n")
            return None
        print("Loader port: %s" % loader_port)
        return loader_port

    # (4) Nothing recognized -> prompt manual DFU and poll for the loader CDC.
    sys.stdout.write(
        "No app CDC (VID:PID=%s) found. To recover, hold Button 0 (P0.09) "
        "and press reset to enter DFU mode. Waiting for the DFU loader CDC "
        "(VID:PID=%s)...\n" % (app_vidpid, "/".join(loader_vidpids)))
    sys.stdout.flush()
    port = _wait_for_loader_port(loader_vidpids)
    if not port:
        sys.stderr.write(
            "Error: could not find the DFU port. Put the board in DFU mode "
            "(hold Button 0 / P0.09 + reset) and retry, or set the port "
            "explicitly: `upload_port = COMxx` in platformio.ini or "
            "`pio run -t upload --upload-port COMxx`.\n")
        return None
    print("DFU port detected: %s" % port)
    return port


def run_nrfutil(nrfutil, arguments):
    """Run nrfutil as a console child; kill it and abort on Ctrl+C.

    The wait is a poll loop rather than Popen.wait(): a blocking wait is
    a C-level call that defers KeyboardInterrupt until the child exits,
    and nrfutil would keep transferring meanwhile.
    """
    print("Running: %s %s" % (nrfutil, " ".join(arguments)))
    child = subprocess.Popen([nrfutil] + arguments)
    try:
        while True:
            returncode = child.poll()
            if returncode is not None:
                return returncode
            time.sleep(0.2)
    except KeyboardInterrupt:
        child.kill()
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Upload a signed MCUboot image over USB CDC ACM via "
                    "nrfutil mcu-manager serial recovery")
    parser.add_argument("--nrfutil", required=True,
                        help="Path to the nrfutil executable")
    parser.add_argument("--app-vidpid", required=True,
                        help="App CDC VID:PID (e.g. 2886:8013)")
    parser.add_argument("--loader-vidpid", required=True, nargs="+",
                        dest="loader_vidpids",
                        help="DFU loader CDC VID:PID candidate(s)")
    parser.add_argument("--port", default=None,
                        help="Explicit upload port (upload_port / "
                             "--upload-port); its role is detected by VID:PID")
    parser.add_argument("--firmware", required=True,
                        help="Path to the signed firmware image")
    parser.add_argument("--upload-timeout", type=int, default=UPLOAD_TIMEOUT,
                        help="nrfutil image-upload timeout in seconds "
                             "(default %d)" % UPLOAD_TIMEOUT)
    parser.add_argument("--reset-timeout", type=int, default=RESET_TIMEOUT,
                        help="nrfutil reset timeout in seconds "
                             "(default %d)" % RESET_TIMEOUT)
    args = parser.parse_args()

    port = resolve_upload_port(args.app_vidpid, args.loader_vidpids,
                               args.port or None)
    if not port:
        return 1

    returncode = run_nrfutil(args.nrfutil, [
        "mcu-manager", "serial", "image-upload",
        "--serial-port", port,
        "--timeout", str(args.upload_timeout),
        "--firmware", args.firmware,
    ])
    if returncode != 0:
        return returncode

    print("Resetting device...")
    returncode = run_nrfutil(args.nrfutil, [
        "mcu-manager", "serial", "reset",
        "--serial-port", port,
        "--timeout", str(args.reset_timeout),
    ])
    return returncode


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nAborted by Ctrl+C.")
        sys.exit(130)
