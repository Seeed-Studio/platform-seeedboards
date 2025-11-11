#!/usr/bin/env python3
"""
Unified reset/recover tool for Seeed XIAO nRF54L15.

Features:
  * Probe selection (auto, specified via --probe, interactive if multiple)
  * Mass erase with fallback to standard erase (configurable)
  * Optional firmware flashing for factory reset mode
  * Optional virtual environment usage by wrappers (this script assumes deps present)
  * Logging to file (optional) and structured exit codes

Exit codes:
  0 Success
  2 Probe selection/connect error
  3 Erase failure
  4 Flash failure
  5 Argument/usage error

Usage examples:
  Recover only (erase only):
    python reset_tool.py --mode recover
  Factory reset (erase + flash):
    python reset_tool.py --mode factory --firmware firmware.hex
  Specify probe:
    python reset_tool.py --mode factory --firmware firmware.hex --probe 103E0DC0
  Standard only erase:
    python reset_tool.py --mode recover --standard-only
  Force mass erase only:
    python reset_tool.py --mode recover --force-mass
  Skip flash even in factory mode:
    python reset_tool.py --mode factory --firmware firmware.hex --skip-flash
  Log to file:
    python reset_tool.py --mode factory --firmware firmware.hex --log reset.log
"""
from __future__ import annotations
import argparse
import sys
import os
import logging
import subprocess
from typing import Optional, List

# Try to import pyocd; if missing inform user.
try:
    from pyocd.probe.aggregator import DebugProbeAggregator
except ImportError:  # Defer install to wrapper; keep lightweight here.
    print('[ERROR] pyocd not available. Please install pyocd (pip install pyocd).', file=sys.stderr)
    sys.exit(5)

LOG = logging.getLogger('reset_tool')

def configure_logging(log_path: Optional[str], quiet: bool):
    level = logging.INFO if not quiet else logging.WARNING
    LOG.setLevel(level)
    fmt = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    ch.setLevel(level)
    LOG.addHandler(ch)
    if log_path:
        fh = logging.FileHandler(log_path, mode='a', encoding='utf-8')
        fh.setFormatter(fmt)
        fh.setLevel(level)
        LOG.addHandler(fh)
        LOG.info(f'Logging to {log_path}')

def parse_args(argv: List[str]):
    p = argparse.ArgumentParser(description='Unified recover/factory reset tool for nRF54L15.')
    p.add_argument('--mode', choices=['recover', 'factory'], required=True, help='Operation mode.')
    p.add_argument('--probe', help='Unique probe ID to use (skip auto/interactive).')
    p.add_argument('--firmware', help='Path to firmware .hex (required for factory unless --skip-flash).')
    p.add_argument('--frequency', type=int, default=4_000_000, help='Flash frequency Hz (default 4000000).')
    p.add_argument('--skip-flash', action='store_true', help='Skip flashing even in factory mode.')
    p.add_argument('--force-mass', action='store_true', help='Only perform mass erase; fail if it fails.')
    p.add_argument('--standard-only', action='store_true', help='Only perform standard erase; do not mass erase.')
    p.add_argument('--log', help='Log file path.')
    p.add_argument('--quiet', action='store_true', help='Reduce output verbosity.')
    p.add_argument('--no-interactive', action='store_true', help='Fail instead of prompting when multiple probes and none specified.')
    return p.parse_args(argv)

def list_probes():
    return DebugProbeAggregator.get_all_connected_probes()

def select_probe(args) -> str:
    if args.probe:
        for p in list_probes():
            if p.unique_id == args.probe:
                LOG.info(f'Using specified probe: {p.unique_id}')
                return p.unique_id
        LOG.error(f'Specified probe ID {args.probe} not found among connected probes.')
        sys.exit(2)
    probes = list_probes()
    if not probes:
        LOG.error('No debug probes detected.')
        sys.exit(2)
    if len(probes) == 1:
        LOG.info(f'Auto-selected single probe: {probes[0].unique_id} ({probes[0].description})')
        return probes[0].unique_id
    # Multiple probes
    LOG.info('Multiple probes detected:')
    for p in probes:
        LOG.info(f'  - {p.unique_id} : {p.description}')
    if args.no_interactive:
        LOG.error('Multiple probes present and --no-interactive given without --probe.')
        sys.exit(2)
    # Interactive selection
    while True:
        sel = input('Enter probe unique ID: ').strip()
        if not sel:
            LOG.warning('Empty input, retry.')
            continue
        for p in probes:
            if p.unique_id == sel:
                LOG.info(f'Selected probe: {sel}')
                return sel
        LOG.warning(f'Probe {sel} not found. Retry.')

def run_pyocd_cmd(cmd: List[str]) -> int:
    LOG.debug('Running: %s', ' '.join(cmd))
    proc = subprocess.run(cmd)
    return proc.returncode

def perform_erase(probe_id: str, args) -> None:
    # Standard vs mass decision
    if args.standard_only and args.force_mass:
        LOG.error('Cannot specify both --standard-only and --force-mass.')
        sys.exit(5)
    if args.standard_only:
        LOG.info('Performing standard chip erase...')
        rc = run_pyocd_cmd(['pyocd', 'erase', '--target', 'nrf54l', '--chip', '--probe', probe_id])
        if rc != 0:
            LOG.error('Standard erase failed.')
            sys.exit(3)
        LOG.info('Standard erase succeeded.')
        return
    # Try mass then fallback
    LOG.info('Attempting mass erase (will unlock if protected)...')
    rc = run_pyocd_cmd(['pyocd', 'erase', '--mass', '--target', 'nrf54l', '--chip', '--probe', probe_id])
    if rc == 0:
        LOG.info('Mass erase succeeded.')
        return
    if args.force_mass:
        LOG.error('Mass erase failed and --force-mass specified; aborting.')
        sys.exit(3)
    LOG.warning('Mass erase failed, falling back to standard erase...')
    rc2 = run_pyocd_cmd(['pyocd', 'erase', '--target', 'nrf54l', '--chip', '--probe', probe_id])
    if rc2 != 0:
        LOG.error('Standard erase after mass failure also failed.')
        sys.exit(3)
    LOG.info('Standard erase succeeded.')

def perform_flash(probe_id: str, firmware: str, freq: int) -> None:
    LOG.info(f'Flashing firmware: {firmware} (frequency {freq} Hz)...')
    rc = run_pyocd_cmd(['pyocd', 'flash', '--target', 'nrf54l', '--frequency', str(freq), firmware, '--probe', probe_id])
    if rc != 0:
        LOG.error('Flash failed.')
        sys.exit(4)
    LOG.info('Flash completed successfully.')

def main(argv: List[str]):
    args = parse_args(argv)
    configure_logging(args.log, args.quiet)

    if args.mode == 'factory' and not args.skip_flash:
        if not args.firmware:
            LOG.error('Firmware path required for factory mode (use --firmware or add --skip-flash).')
            return 5
        if not os.path.isfile(args.firmware):
            LOG.error(f'Firmware file not found: {args.firmware}')
            return 5

    probe_id = select_probe(args)
    perform_erase(probe_id, args)

    if args.mode == 'factory' and not args.skip_flash:
        perform_flash(probe_id, args.firmware, args.frequency)

    LOG.info('Operation completed successfully.')
    return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
