#!/usr/bin/env python3
"""
UF2 (USB Flashing Format) converter.

Converts a .bin firmware file to .uf2 format for use with TinyUF2 bootloader.

Reference: https://github.com/microsoft/uf2
"""

import struct
import sys
import argparse

# UF2 magic numbers
UF2_MAGIC_START_0 = 0x0A324655  # "UF2\n"
UF2_MAGIC_START_1 = 0x9E5D5157
UF2_MAGIC_END = 0x0AB16F30

# Flags
UF2_FLAG_NOT_MAIN_FLASH = 0x0001
UF2_FLAG_FILE_CONTAINER = 0x1000
UF2_FLAG_FAMILY_ID = 0x2000
UF2_FLAG_EXTENSION_ID = 0x4000

# Default payload size per UF2 block
UF2_PAYLOAD_SIZE = 256
UF2_BLOCK_SIZE = 512

# Board family IDs
FAMILY_IDS = {
    "stm32c5": 0x00C5C5C5,
    "stm32f4": 0x57755A57,
    "stm32f3": 0x6B846188,
    "stm32h5": 0x4E8F1C5D,
    "rp2040": 0xE48BFF56,
    "rp2350": 0xE48BFF57,
    "atmel-samd": 0x68ED2B88,
    "esp32": 0x1C5E21E0,
    "nrf52": 0x1B57745F,
}


def convert_bin_to_uf2(bin_data, base_addr, family_id=0x00C5C5C5,
                       payload_size=UF2_PAYLOAD_SIZE):
    """Convert binary firmware data to UF2 format.

    Args:
        bin_data: bytes - raw firmware binary
        base_addr: int - absolute flash address where firmware starts
        family_id: int - UF2 family ID
        payload_size: int - bytes of data per UF2 block (usually 256)

    Returns:
        bytes - UF2 formatted data
    """
    # Pad bin_data to multiple of payload_size
    padding = (payload_size - len(bin_data) % payload_size) % payload_size
    if padding:
        bin_data = bin_data + b"\xFF" * padding

    num_blocks = len(bin_data) // payload_size
    blocks = []

    for block_idx in range(num_blocks):
        offset = block_idx * payload_size
        chunk = bin_data[offset:offset + payload_size]

        header = struct.pack(
            "<IIIIIIII",
            UF2_MAGIC_START_0,          # magicStart0
            UF2_MAGIC_START_1,          # magicStart1
            UF2_FLAG_FAMILY_ID,          # flags
            base_addr + offset,          # targetAddr
            payload_size,                # payloadSize
            block_idx,                   # blockNo
            num_blocks,                  # numBlocks
            family_id,                   # fileSize / familyID
        )

        # Pad chunk to fill the data portion (476 bytes max)
        data_pad = b"\x00" * (476 - payload_size)
        footer = struct.pack("<I", UF2_MAGIC_END)

        block = header + chunk + data_pad + footer
        assert len(block) == UF2_BLOCK_SIZE
        blocks.append(block)

    return b"".join(blocks)


def main():
    parser = argparse.ArgumentParser(
        description="Convert .bin firmware to .uf2 format"
    )
    parser.add_argument(
        "-i", "--input", required=True,
        help="Input .bin file"
    )
    parser.add_argument(
        "-o", "--output", default=None,
        help="Output .uf2 file (default: input with .uf2 extension)"
    )
    parser.add_argument(
        "-b", "--base", type=lambda x: int(x, 0), required=True,
        help="Base address (hex, e.g. 0x08008000)"
    )
    parser.add_argument(
        "-f", "--family", default="stm32c5",
        choices=list(FAMILY_IDS.keys()),
        help="Board family (default: stm32c5)"
    )
    parser.add_argument(
        "--family-id", type=lambda x: int(x, 0), default=None,
        help="Raw family ID (overrides --family)"
    )

    args = parser.parse_args()

    # Determine output path
    if args.output:
        output = args.output
    else:
        if args.input.endswith(".bin"):
            output = args.input[:-4] + ".uf2"
        else:
            output = args.input + ".uf2"

    # Determine family ID
    family_id = args.family_id if args.family_id else FAMILY_IDS[args.family]

    # Read input
    with open(args.input, "rb") as f:
        bin_data = f.read()

    # Convert
    uf2_data = convert_bin_to_uf2(bin_data, args.base, family_id)

    # Write output
    with open(output, "wb") as f:
        f.write(uf2_data)

    print(f"Converted: {args.input} -> {output}")
    print(f"  Size: {len(bin_data)} -> {len(uf2_data)} bytes")
    print(f"  Base: 0x{args.base:08X}")
    print(f"  Family ID: 0x{family_id:08X}")
    print(f"  Blocks: {len(uf2_data) // UF2_BLOCK_SIZE}")


if __name__ == "__main__":
    main()
