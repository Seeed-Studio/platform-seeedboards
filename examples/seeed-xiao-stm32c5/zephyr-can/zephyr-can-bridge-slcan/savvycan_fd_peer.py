# SPDX-License-Identifier: Apache-2.0
"""Send or receive SavvyCAN LAWICEL CAN FD frames with a second XIAO board."""

import argparse
import time

import serial
import serial.tools.list_ports

SEEED_VID = 0x2886
SERIAL_BAUD = 115200


def find_available_port(explicit_port=None):
    candidates = [explicit_port] if explicit_port else [
        port.device
        for port in serial.tools.list_ports.comports()
        if port.vid == SEEED_VID
    ]

    for device in candidates:
        try:
            connection = serial.Serial(device, SERIAL_BAUD, timeout=0.35)
            connection.dtr = True
            connection.rts = False
            time.sleep(0.4)
            connection.reset_input_buffer()
            return connection
        except (OSError, serial.SerialException) as error:
            print(f"Skipping {device}: {error}")

    raise RuntimeError(
        "No available Seeed CDC port. Close SavvyCAN on the peer port or "
        "specify the unused port with --port."
    )


def command(connection, text, response_wait=0.08):
    connection.reset_input_buffer()
    connection.write((text + "\r").encode("ascii"))
    connection.flush()
    time.sleep(response_wait)
    response = connection.read(256)
    if b"\x07" in response:
        raise RuntimeError(f"Firmware rejected command {text!r}: {response!r}")
    if b"\r" not in response:
        raise RuntimeError(f"No acknowledgement for {text!r}: {response!r}")
    return response


def open_can_fd(connection):
    command(connection, "C")
    command(connection, "S6")  # 500 kbit/s nominal bitrate
    command(connection, "Y2")  # 2 Mbit/s CAN FD data bitrate
    command(connection, "O")


def send_frames(connection, duration):
    frames = [
        "d2009000102030405060708090A0B",  # 12-byte standard FD, no BRS
        "b201F" + "".join(f"{value:02X}" for value in range(64)),
        "B001ABCDE9AABBCCDDEEFF001122334455",  # 12-byte extended FD with BRS
    ]
    deadline = time.monotonic() + duration
    sent = 0

    print("Sending IDs 0x200, 0x201, and 0x1ABCDE to SavvyCAN...")
    while time.monotonic() < deadline:
        for frame in frames:
            command(connection, frame, response_wait=0.04)
            sent += 1
            time.sleep(0.16)
    print(f"Transmission complete: {sent} acknowledged CAN FD frames.")


def receive_frames(connection, duration):
    deadline = time.monotonic() + duration
    print("Waiting for CAN FD frames sent by SavvyCAN...")
    connection.reset_input_buffer()
    while time.monotonic() < deadline:
        line = connection.read_until(b"\r")
        if line:
            print(line.decode("ascii", errors="replace").strip())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("send", "receive"))
    parser.add_argument(
        "--port",
        help="Unused peer port, for example COM4 or /dev/ttyACM1",
    )
    parser.add_argument("--duration", type=float, default=12.0)
    args = parser.parse_args()

    connection = find_available_port(args.port)
    print(f"Using {connection.port} at {SERIAL_BAUD} baud")
    try:
        open_can_fd(connection)
        if args.mode == "send":
            send_frames(connection, args.duration)
        else:
            receive_frames(connection, args.duration)
        command(connection, "C")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
