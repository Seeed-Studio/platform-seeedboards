# Factory Flash Scripts

## factory_provision.ps1 — Full factory provisioning (3 steps)

One-command factory setup for XIAO nRF54LM20B via SWD/JLink.

### Prerequisites
- nRF Util (`nrfutil`) installed (or `nrfutil.exe` next to this script / in PATH)
- JLink probe connected to the board
- PlatformIO GCC ARM toolchain installed (for bin→hex conversion)

### Setup

Copy firmware files into `firmware/`:
```
firmware/
├── USB_DFU.hex        # Merged system (mcuboot + loader + app) from NCS build
├── keyfile.json       # KMU public key (root-ed25519)
└── app.signed.bin     # PIO app (from pio build, or copy manually)
```

### Usage

```powershell
# Auto-detect JLink, use bundled firmware
.\factory_provision.ps1

# Specify JLink serial number
.\factory_provision.ps1 -SerialNumber 000069660778

# Override firmware paths
.\factory_provision.ps1 -MergedHex "C:\path\to\USB_DFU.hex" -AppBin "C:\path\to\signed.bin"
```

### What it does

| Step | Action | Erase |
|------|--------|-------|
| 1 | Flash merged system HEX (mcuboot + loader + app) | ERASE_ALL |
| 2 | Provision KMU key (root-ed25519 public key) | — |
| 3 | Flash PIO app (signed.bin → slot0 @0x6000) | ERASE_NONE |

After provisioning, subsequent updates use **USB DFU** (no JLink needed):
```powershell
pio run -t upload    # 1200-bps touch → mcuboot → mcumgr upload
```

### Tool search (no hardcoded paths)

The script automatically searches for:
- **nrfutil.exe**: script dir → `C:\nrfutil\` → `%LOCALAPPDATA%\nrfutil\` → `%ProgramFiles%\Nordic Semiconductor\` → system PATH → `%SystemDrive%\ncs\toolchains\`
- **JLink serial**: `nrfutil device list` (or `-SerialNumber`)
- **arm-none-eabi-objcopy** (bin→hex): `%USERPROFILE%\.platformio\packages\toolchain-gccarmnoneeabi*\bin\` → system PATH

### Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `-SerialNumber` | (auto) | JLink serial number |
| `-MergedHex` | `firmware/USB_DFU.hex` | Merged system HEX |
| `-KmuKey` | `firmware/keyfile.json` | KMU key file |
| `-AppBin` | `firmware/app.signed.bin` | PIO signed app binary |
| `-Slot0Address` | `0x6000` | Slot0 flash offset (0x7000 for 28KB mcuboot) |
