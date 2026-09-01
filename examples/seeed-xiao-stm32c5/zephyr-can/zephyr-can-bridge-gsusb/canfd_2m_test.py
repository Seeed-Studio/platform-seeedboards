# SPDX-License-Identifier: Apache-2.0
"""Send or receive CAN FD frames at 500 kbit/s nominal and 2 Mbit/s data."""

import argparse
import time

import can

NOMINAL_BITRATE = 500_000
DATA_BITRATE = 2_000_000


def open_bus(interface, channel, serial_number=None, loop_back=False):
    if interface == "socketcan":
        options = {
            "interface": "socketcan",
            "channel": channel,
            "fd": True,
        }
    else:
        try:
            candle_channel = int(channel)
        except ValueError:
            candle_channel = channel
        options = {
            "interface": "candle",
            "channel": candle_channel,
            "fd": True,
            "bitrate": NOMINAL_BITRATE,
            "data_bitrate": DATA_BITRATE,
            "loop_back": loop_back,
            "ignore_config": True,
        }
        if serial_number:
            options["serial_number"] = serial_number
    return can.Bus(**options)


def make_test_frames():
    payload_12 = bytes(range(12))
    payload_64 = bytes(range(64))
    return (
        can.Message(
            arbitration_id=0x200,
            is_extended_id=False,
            is_fd=True,
            bitrate_switch=True,
            data=payload_12,
        ),
        can.Message(
            arbitration_id=0x201,
            is_extended_id=False,
            is_fd=True,
            bitrate_switch=True,
            data=payload_64,
        ),
    )


def send_frames(bus, count, interval):
    frames = make_test_frames()

    acknowledged = 0
    for _ in range(count):
        for frame in frames:
            try:
                bus.send(frame, timeout=1.0)
                acknowledged += 1
                print(
                    f"TX ID={frame.arbitration_id:#05x} len={len(frame.data)} "
                    f"FD={frame.is_fd} BRS={frame.bitrate_switch}"
                )
            except can.CanError as error:
                print(f"TX failed for ID {frame.arbitration_id:#05x}: {error}")
            time.sleep(interval)

    print(f"Transmission complete: {acknowledged} CAN FD frames submitted")


def loopback_test(bus, count, interval):
    frames = make_test_frames()
    passed = 0
    expected = count * len(frames)

    for _ in range(count):
        for frame in frames:
            bus.send(frame, timeout=1.0)
            deadline = time.monotonic() + 1.0
            received = None

            while time.monotonic() < deadline:
                candidate = bus.recv(timeout=0.1)
                if candidate is None:
                    continue
                if (
                    candidate.arbitration_id == frame.arbitration_id
                    and candidate.is_fd
                    and candidate.bitrate_switch
                    and bytes(candidate.data) == bytes(frame.data)
                ):
                    received = candidate
                    break

            if received is None:
                print(
                    f"FAIL ID={frame.arbitration_id:#05x}: "
                    "no matching loopback frame"
                )
            else:
                passed += 1
                print(
                    f"PASS ID={received.arbitration_id:#05x} "
                    f"len={len(received.data)} FD={received.is_fd} "
                    f"BRS={received.bitrate_switch}"
                )
            time.sleep(interval)

    print(f"Loopback complete: {passed}/{expected} CAN FD frames passed")
    if passed != expected:
        raise RuntimeError("CAN FD loopback test failed")


def receive_frames(bus, duration):
    deadline = time.monotonic() + duration
    received = 0
    while time.monotonic() < deadline:
        frame = bus.recv(timeout=0.5)
        if frame is None:
            continue
        received += 1
        print(
            f"RX ID={frame.arbitration_id:#x} len={len(frame.data)} "
            f"FD={frame.is_fd} BRS={frame.bitrate_switch} "
            f"data={bytes(frame.data).hex().upper()}"
        )
    print(f"Reception complete: {received} frames")


def main():
    parser = argparse.ArgumentParser(
        description="XIAO STM32C5 gs_usb CAN FD 500k/2M test"
    )
    parser.add_argument("mode", choices=("send", "receive", "loopback"))
    parser.add_argument(
        "--interface",
        choices=("candle", "socketcan"),
        default="candle",
        help="candle uses direct USB; socketcan uses a Linux canX interface",
    )
    parser.add_argument(
        "--channel",
        default="0",
        help="candle channel number or SocketCAN interface name such as can0",
    )
    parser.add_argument("--serial-number", help="USB serial number for board selection")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--interval", type=float, default=0.1)
    parser.add_argument("--duration", type=float, default=10.0)
    args = parser.parse_args()

    print(
        f"Opening {args.interface} channel {args.channel}: "
        f"nominal={NOMINAL_BITRATE}, "
        f"data={DATA_BITRATE}, FD enabled, "
        f"loopback={args.mode == 'loopback'}"
    )
    bus = open_bus(
        args.interface,
        args.channel,
        args.serial_number,
        loop_back=args.mode == "loopback",
    )
    try:
        if args.mode == "send":
            send_frames(bus, args.count, args.interval)
        elif args.mode == "receive":
            receive_frames(bus, args.duration)
        else:
            loopback_test(bus, args.count, args.interval)
    finally:
        bus.shutdown()


if __name__ == "__main__":
    main()
