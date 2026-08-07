<#
.SYNOPSIS
  Flash firmware to XIAO nRF54LM20B via SWD/JLink using nrfutil device program.

.DESCRIPTION
  Two modes:
  1. App-only SWD update (default): Flash the PIO-built signed app (zephyr.signed.bin)
     to slot0 (address 0x6000). Board must already have mcuboot + loader.
  2. Factory/merged HEX: Flash a complete image (mcuboot+loader+app) with -Firmware <.hex>.

.PARAMETER Firmware
  Path to firmware. Default: the PIO build's zephyr.signed.bin.
  .hex  → flashed directly (addresses in file).
  .bin  → converted to .hex at -Address, then flashed.

.PARAMETER Address
  Flash offset for .bin files (slot0 base). Default: 0x6000 (old bootloader,
  mcuboot 24 KiB). Use 0x7000 for the 28 KiB (logging) mcuboot.

.PARAMETER SerialNumber
  JLink serial number. If omitted, auto-detects.

.EXAMPLE
  # Default: flash PIO signed app to slot0
  .\factory_flash.ps1
  # Factory: flash merged HEX (mcuboot+loader+app)
  .\factory_flash.ps1 -Firmware "D:\...\06-USB-DFU.hex"
  # Specify JLink S/N
  .\factory_flash.ps1 -SerialNumber 000069660778
#>

param(
    [string]$Firmware = "",
    [string]$Address = "0x6000",
    [string]$SerialNumber = "",
    [string]$Nrfutil = "",
    [switch]$EraseAll
)

$ErrorActionPreference = "Stop"

function Resolve-NrfutilPath {
    param([string]$RequestedPath)
    $candidates = @()
    if ($RequestedPath) { $candidates += $RequestedPath }
    $candidates += @(
        (Join-Path $PSScriptRoot 'nrfutil.exe'),
        'C:\nrfutil\nrfutil.exe'
    )
    $pathCommands = @(Get-Command nrfutil.exe -All -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandType -eq 'Application' })
    $windowsDir = [System.IO.Path]::GetFullPath($env:WINDIR).TrimEnd('\')
    $fromPath = $pathCommands |
        Where-Object {
            $source = [System.IO.Path]::GetFullPath($_.Source)
            -not $source.StartsWith($windowsDir, [System.StringComparison]::OrdinalIgnoreCase)
        } | Select-Object -First 1
    if ($fromPath) { $candidates += $fromPath.Source }
    foreach ($candidate in $candidates | Select-Object -Unique) {
        if (Test-Path -LiteralPath $candidate) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    throw 'nrfutil.exe not found. Put it in C:\nrfutil\nrfutil.exe, or add to PATH.'
}

# --- Resolve firmware (default: PIO signed.bin) ---
$pioSignedBin = "D:\workspace\xiao_nrf54lm20b\platform-seeedboards\examples\seeed-xiao-nrf54lm20b\zephyr-blink\.pio\build\seeed-xiao-nrf54lm20b\zephyr\zephyr.signed.bin"

if (-not $Firmware) {
    if (Test-Path -LiteralPath $pioSignedBin) {
        $Firmware = $pioSignedBin
    } else {
        throw "No firmware specified. Build first with 'pio run', or use -Firmware <path>."
    }
}
if (-not (Test-Path -LiteralPath $Firmware)) {
    throw "Firmware not found: $Firmware"
}
$Firmware = (Resolve-Path -LiteralPath $Firmware).Path

# --- If .bin, convert to .hex at the slot0 offset ---
$flashFile = $Firmware
if ($Firmware -match '\.bin$') {
    $offset = [Convert]::ToInt32($Address, 16)
    Write-Host "Converting $($Firmware) to .hex at offset $Address ..."
    # Find a Python with intelhex (the PIO Zephyr venv has it)
    $pyExe = "C:\Users\seeed\.platformio\penv\.zephyr-4.4.0\Scripts\python.exe"
    if (-not (Test-Path $pyExe)) {
        $pyExe = (Get-Command python -ErrorAction SilentlyContinue).Source
    }
    if (-not $pyExe) { $pyExe = 'python' }
    $convertScript = @"
from intelhex import IntelHex
ih = IntelHex()
with open(r'$Firmware', 'rb') as f:
    ih.frombytes(f.read(), offset=$offset)
ih.write_hex_file(r'$Firmware.flash.hex')
print('OK')
"@
    $convertResult = & $pyExe -c $convertScript 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to convert .bin to .hex: $convertResult"
    }
    $flashFile = "$Firmware.flash.hex"
    Write-Host "Converted: $flashFile"
}

# --- Detect JLink serial number ---
$nrfutilExe = Resolve-NrfutilPath -RequestedPath $Nrfutil
if (-not $SerialNumber) {
    Write-Host "Auto-detecting JLink probe..."
    $output = (& $nrfutilExe device list 2>&1 | Out-String)
    $serials = [regex]::Matches($output, '(\d{12,})') |
        ForEach-Object { $_.Groups[1].Value } | Select-Object -Unique
    if ($serials.Count -eq 1) {
        $SerialNumber = $serials[0]
        Write-Host "Found JLink: $SerialNumber"
    } elseif ($serials.Count -gt 1) {
        Write-Host "Multiple probes:"
        for ($i = 0; $i -lt $serials.Count; $i++) { Write-Host "  [$i] $($serials[$i])" }
        $choice = Read-Host "Select [0-$($serials.Count - 1)]"
        $SerialNumber = $serials[[int]$choice]
    } else {
        throw "No JLink detected. Specify -SerialNumber."
    }
}

# --- Flash ---
Write-Host ""
Write-Host "=== SWD Flash XIAO nRF54LM20B ==="
Write-Host "nrfutil:    $nrfutilExe"
Write-Host "Firmware:   $flashFile"
Write-Host "JLink S/N:  $SerialNumber"
Write-Host ""

$eraseMode = if ($EraseAll) { 'ERASE_ALL' } else { 'ERASE_NONE' }
$args = @(
    'device', 'program',
    '--serial-number', $SerialNumber,
    '--family', 'nrf54l',
    '--firmware', $flashFile,
    '--swd-clock-frequency', '1000',
    '--options', "chip_erase_mode=$eraseMode,reset=RESET_SYSTEM,verify=VERIFY_READ"
)
Write-Host "> nrfutil $($args -join ' ')"
& $nrfutilExe @args
if ($LASTEXITCODE -ne 0) { throw "Flash failed (exit $LASTEXITCODE)." }

Write-Host ""
Write-Host "=== Flash complete ==="
Write-Host "Board reset. App should now boot."
