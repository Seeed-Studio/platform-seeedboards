#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@file xiao_nrf54l15_recover_flash.py
@brief Simplified pyOCD script to unlock (mass erase) and program nRF54L15.
@details This script provides core functionality to erase and flash nRF54L15 devices.
         It is a stripped-down version focusing on the essential features.
@note Requires: pip install pyocd intelhex
@example python xiao_nrf54l15_recover_flash.py --hex application.hex --probe 103E0DC0 --mass-erase
"""

import subprocess
import argparse
import sys
import os
import tempfile
import logging
from typing import Dict, List, Optional

## @brief Automatically install dependencies if missing
try:
    from intelhex import IntelHex
except ImportError:
    print("Installing intelhex...")
    subprocess.run([sys.executable, "-m", "pip", "install", "intelhex"], check=True)
    from intelhex import IntelHex

try:
    from pyocd.core.helpers import ConnectHelper
    from pyocd.flash.file_programmer import FileProgrammer
    from pyocd.core.session import Session
    from pyocd.probe.aggregator import DebugProbeAggregator
except ImportError:
    print("Installing pyocd...")
    subprocess.run([sys.executable, "-m", "pip", "install", "pyocd"], check=True)
    from pyocd.core.helpers import ConnectHelper
    from pyocd.flash.file_programmer import FileProgrammer
    from pyocd.core.session import Session
    from pyocd.probe.aggregator import DebugProbeAggregator

## @brief Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("nrf54l15_flasher")

## @brief nRF54L15 specific configuration
NRF54L15_CORE_DEFINITIONS = {
    "Application": {
        "romBaseAddr": 0x00000000,
        "romSize": 0x00100000,  # 1MB flash
        "uicrBaseAddr": 0x00FF8000,
        "uicrSize": 0x1000,      # 4KB UICR
    },
}
NRF54L15_APPROTECT_ADDRESS = 0x00FF8208  # Application core APPROTECT

## @brief Protection status constants
PROTECTION_STATUS_NONE = "UNPROTECTED"
PROTECTION_STATUS_PROTECTED = "PROTECTED"
PROTECTION_STATUS_UNKNOWN = "UNKNOWN"

def read_word_safely(session: Session, addr: int) -> Optional[int]:
    """
    @brief Safely read a 32-bit word from the target.
    @param session The pyOCD session object.
    @param addr The address to read from.
    @return The 32-bit value read, or None if failed.
    """
    try:
        return session.target.read32(addr)
    except Exception as e:
        logger.debug(f"Read32 failed at 0x{addr:08X}: {e}")
        return None

def detect_protection_status_nrf54l15(session: Session) -> str:
    """
    @brief Detect the protection status of nRF54L15.
    @param session The pyOCD session object.
    @return Protection status string.
    """
    val = read_word_safely(session, NRF54L15_APPROTECT_ADDRESS)
    if val is not None:
        logger.debug(f"Application APPROTECT 0x{NRF54L15_APPROTECT_ADDRESS:08X} = 0x{val:08X}")
        return PROTECTION_STATUS_NONE if (val & 0xFF) == 0xFF else PROTECTION_STATUS_PROTECTED
    return PROTECTION_STATUS_UNKNOWN

def get_core_info(session: Session) -> Dict[str, dict]:
    """
    @brief Get core information and check accessibility.
    @param session The pyOCD session object.
    @return Dictionary of core info with accessibility.
    """
    core_info = {}
    for core_name, core_def in NRF54L15_CORE_DEFINITIONS.items():
        if read_word_safely(session, core_def["romBaseAddr"]) is not None:
            core_info[core_name] = {**core_def, "accessible": True}
            logger.info(f"{core_name} core detected and accessible.")
        else:
            core_info[core_name] = {**core_def, "accessible": False}
            logger.warning(f"{core_name} core not accessible.")
    return core_info

def split_hex_by_core(hex_file: str, core_info: Dict[str, dict]) -> Dict[str, IntelHex]:
    """
    @brief Split the HEX file by core according to memory mapping.
    @param hex_file Path to the HEX file.
    @param core_info Dictionary of core info.
    @return Dictionary of IntelHex objects per core.
    """
    merged_hex = IntelHex(hex_file)
    core_hexes = {}

    for core_name, core_def in core_info.items():
        if not core_def.get("accessible", False):
            continue

        core_hex = IntelHex()
        rom_start, rom_end = core_def["romBaseAddr"], core_def["romBaseAddr"] + core_def["romSize"]
        uicr_start, uicr_end = core_def["uicrBaseAddr"], core_def["uicrBaseAddr"] + core_def["uicrSize"]

        for start, end in merged_hex.segments():
            for addr in range(start, end):
                if (rom_start <= addr < rom_end) or (uicr_start <= addr < uicr_end):
                    core_hex[addr] = merged_hex[addr]
        
        if len(core_hex) > 0:
            core_hexes[core_name] = core_hex
            logger.info(f"Data for {core_name} core extracted from HEX file.")

    return core_hexes

def write_intelhex_to_temp(ih: IntelHex) -> str:
    """
    @brief Write IntelHex object to a temporary file.
    @param ih IntelHex object.
    @return Path to the temporary HEX file.
    """
    fd, tmp_path = tempfile.mkstemp(suffix=".hex", prefix="nrf54l15_")
    os.close(fd)
    ih.write_hex_file(tmp_path)
    return tmp_path

def unlock_and_erase_device(session: Session):
    """
    @brief Perform device recovery (mass erase) to unlock the device.
    @param session The pyOCD session object.
    """
    logger.info("Performing mass erase to unlock and erase the device...")
    try:
        target = session.target
        is_protected = detect_protection_status_nrf54l15(session) == PROTECTION_STATUS_PROTECTED
        if is_protected:
            logger.info("Protected device detected - mass erase is required to unlock.")
        # For nRF54L series, mass_erase is a reliable erase even if not protected
        target.mass_erase()
        logger.info("Mass erase completed successfully.")
        target.reset_and_halt() # Reset is required after erase
        logger.info("Target halted after mass erase.")
    except Exception as e:
        logger.error(f"Mass erase failed: {e}")
        logger.info("This might be due to a hardware connection issue or severe lock state.")
        raise

def program_device(session: Session, core_hexes: Dict[str, IntelHex]):
    """
    @brief Program the split HEX files to all cores.
    @param session The pyOCD session object.
    @param core_hexes Dictionary of IntelHex objects per core.
    """
    temp_files = []
    try:
        for core_name, core_hex in core_hexes.items():
            logger.info(f"Programming {core_name} core...")
            temp_file = write_intelhex_to_temp(core_hex)
            temp_files.append(temp_file)

            fp = FileProgrammer(session, progress=lambda p: logger.info(f"Programming progress: {p * 100:.1f}%"))
            fp.program(temp_file, smart_flash=True)
            logger.info(f"{core_name} core programming completed.")

    finally:
        for temp_file in temp_files:
            if os.path.exists(temp_file):
                os.remove(temp_file)

def main():
    parser = argparse.ArgumentParser(
        description="Simplified pyOCD script to unlock and program nRF54L15."
    )
    parser.add_argument(
        "--hex",
        required=True,
        help="Path to the HEX file to be programmed.",
    )
    parser.add_argument(
        "--mass-erase",
        action="store_true",
        help="Perform a mass erase to unlock and fully erase the chip before programming.",
    )
    parser.add_argument(
        "--probe", 
        help="Specify the unique ID of the debug probe to use."
    )
    args = parser.parse_args()

    # Find or select debug probe
    if args.probe:
        probe_id = args.probe
        logger.info(f"Using specified probe: {probe_id}")
    else:
        probes = DebugProbeAggregator.get_all_connected_probes()
        if not probes:
            logger.error("No connected debug probes found.")
            sys.exit(1)
        elif len(probes) > 1:
            logger.error("Multiple probes connected. Please specify one with --probe <unique_id>:")
            for p in probes:
                logger.error(f"  - {p.unique_id} : {p.description}")
            sys.exit(1)
        else:
            probe_id = probes[0].unique_id
            logger.info(f"Auto-selected probe: {probe_id} ({probes[0].description})")

    session_options = {
        'target_override': 'nrf54l',
    'connect_mode': 'under-reset' # This mode is usually required for protected devices
    }
    session = None

    try:
        logger.info("Connecting to target...")
        with ConnectHelper.session_with_chosen_probe(unique_id=probe_id, **session_options) as session:
            logger.info("Successfully connected to target.")
            
            # Step 1: Unlock and erase (if specified by user)
            if args.mass_erase:
                unlock_and_erase_device(session)

            # Step 2: Prepare programming data
            core_info = get_core_info(session)
            if not any(info.get("accessible") for info in core_info.values()):
                logger.error("No cores are accessible. Cannot proceed with programming.")
                sys.exit(1)
                
            core_hexes = split_hex_by_core(args.hex, core_info)
            if not core_hexes:
                logger.error("No relevant data found in the HEX file for the accessible cores.")
                sys.exit(1)

            # Step 3: Program device
            program_device(session, core_hexes)
            
            # Step 4: Reset and run
            logger.info("Resetting target to run application...")
            session.target.reset()
            logger.info("nRF54L15 programming completed successfully.")

    except KeyboardInterrupt:
        logger.warning("Operation cancelled by user.")
    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        sys.exit(2)

if __name__ == "__main__":
    main()