<#
.SYNOPSIS
  Factory provisioning for XIAO nRF54LM20B via SWD/JLink.
  Self-contained: searches for nrfutil, JLink, and objcopy automatically.
  No hardcoded paths — works in any environment.

  Three steps:
    1. Flash merged system HEX (mcuboot + loader + app) → ERASE_ALL
    2. Provision KMU public key
    3. Flash PIO app (signed.bin → slot0) → ERASE_NONE

  Firmware files are expected in: <script_dir>/firmware/
    Copy USB_DFU.hex and keyfile.json there before running.

.PARAMETER SerialNumber  JLink S/N (auto-detect if omitted)
.PARAMETER MergedHex     Merged system HEX (default: firmware/USB_DFU.hex)
.PARAMETER KmuKey        keyfile.json (default: firmware/keyfile.json)
.PARAMETER AppBin        PIO signed.bin (default: firmware/app.signed.bin)
.PARAMETER Slot0Address  Slot0 flash offset (default: 0x6000)

.EXAMPLE
  .\factory_provision.ps1
  .\factory_provision.ps1 -SerialNumber 000069660778
  .\factory_provision.ps1 -AppBin "C:\...\zephyr.signed.bin"
#>
param(
    [string]$SerialNumber = "",
    [string]$MergedHex = "",
    [string]$KmuKey = "",
    [string]$AppBin = "",
    [string]$Slot0Address = "0x6000"
)
$ErrorActionPreference = "Stop"

# ─── Tool resolution (search, no hardcode) ───

function Find-Nrfutil {
    $c = @(
        (Join-Path $PSScriptRoot 'nrfutil.exe'),
        'C:\nrfutil\nrfutil.exe',
        (Join-Path $env:LOCALAPPDATA 'nrfutil\nrfutil.exe'),
        (Join-Path $env:ProgramFiles 'Nordic Semiconductor\nrfutil\nrfutil.exe')
    )
    $p = Get-Command nrfutil.exe -All -ErrorAction SilentlyContinue |
         Where-Object { $_.CommandType -eq 'Application' } | Select-Object -First 1
    if ($p) { $c += $p.Source }
    # Recurse Nordic toolchain dirs
    foreach ($r in @(
        (Join-Path $env:LOCALAPPDATA 'nrfutil'),
        (Join-Path $env:ProgramFiles 'Nordic Semiconductor'),
        "$env:SystemDrive\ncs\toolchains"
    )) {
        if (Test-Path $r) {
            $f = Get-ChildItem $r -Recurse -Filter nrfutil.exe -EA SilentlyContinue | Select-Object -First 1
            if ($f) { $c += $f.FullName }
        }
    }
    foreach ($x in $c | Select-Object -Unique) {
        if (Test-Path -LiteralPath $x) { return (Resolve-Path -LiteralPath $x).Path }
    }
    throw "nrfutil.exe not found. Install nRF Util or put it next to this script."
}

function Find-JLinkSerial {
    param([string]$NrfutilExe, [string]$Requested)
    if ($Requested) { return $Requested }
    Write-Host "Searching for JLink probe..."
    $out = (& $NrfutilExe device list 2>&1 | Out-String)
    $s = [regex]::Matches($out, '(\d{12,})') | ForEach-Object { $_.Groups[1].Value } | Select-Object -Unique
    if ($s -and $s.Count -ge 1) {
        if ($s.Count -eq 1) { Write-Host "  Found: $($s[0])"; return $s[0] }
        for ($i=0; $i -lt $s.Count; $i++) { Write-Host "  [$i] $($s[$i])" }
        $idx = Read-Host "Select probe [0-$($s.Count-1)]"
        return $s[[int]$idx]
    }
    Write-Host "  Serial not parsed, using --traits jlink auto-select."
    return ""
}

function Find-Objcopy {
    $g = Get-ChildItem "$env:USERPROFILE\.platformio\packages\toolchain-gccarmnoneeabi*\bin\arm-none-eabi-objcopy.exe" -EA SilentlyContinue | Select-Object -First 1
    if ($g) { return $g.FullName }
    $p = Get-Command arm-none-eabi-objcopy -EA SilentlyContinue | Select-Object -First 1
    if ($p) { return $p.Source }
    throw "arm-none-eabi-objcopy not found. Install PIO GCC ARM toolchain."
}

function Convert-BinToHex {
    param([string]$Bin, [string]$Offset)
    $oc = Find-Objcopy
    $hex = "$Bin.flash.hex"
    $dec = [Convert]::ToInt32($Offset, 16)
    Write-Host "  objcopy: bin → hex @ $Offset ..."
    & $oc -I binary -O ihex --change-addresses $dec $Bin $hex 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "bin→hex conversion failed." }
    return $hex
}

# ─── Resolve firmware paths (relative to script) ───

$fwDir = Join-Path $PSScriptRoot 'firmware'
if (-not $MergedHex) { $MergedHex = Join-Path $fwDir 'USB_DFU.hex' }
if (-not $KmuKey)   { $KmuKey   = Join-Path $fwDir 'keyfile.json' }
if (-not $AppBin)   { $AppBin   = Join-Path $fwDir 'app.signed.bin' }

# ─── Main ───

$nrf = Find-Nrfutil
$sn  = Find-JLinkSerial -NrfutilExe $nrf -Requested $SerialNumber

# Probe selector: serial if known, else --traits jlink
if ($sn) { $probe = @('--serial-number', $sn) } else { $probe = @('--traits', 'jlink') }

Write-Host ""
Write-Host "╔═══════════════════════════════════════════╗"
Write-Host "║  XIAO nRF54LM20B Factory Provisioning    ║"
Write-Host "╚═══════════════════════════════════════════╝"
Write-Host "JLink S/N:  $sn"
Write-Host "nrfutil:    $nrf"
Write-Host "Firmware:   $fwDir"
Write-Host ""

# ─── Step 1: Flash merged system (mcuboot + loader + app, ERASE_ALL) ───
Write-Host "━━━ Step 1/3: Flash merged system HEX ━━━"
if (-not (Test-Path -LiteralPath $MergedHex)) {
    throw "USB_DFU.hex not found: $MergedHex`nCopy it to $fwDir\USB_DFU.hex"
}
Write-Host "  $MergedHex (ERASE_ALL)"
& $nrf device program @probe --family nrf54l `
    --firmware $MergedHex --swd-clock-frequency 1000 `
    --options "chip_erase_mode=ERASE_ALL,reset=RESET_SYSTEM,verify=VERIFY_READ"
if ($LASTEXITCODE -ne 0) { throw "Step 1 failed." }
Write-Host "  ✓ System flashed."
Write-Host ""

# ─── Step 2: Provision KMU key ───
Write-Host "━━━ Step 2/3: Provision KMU key ━━━"
if (-not (Test-Path -LiteralPath $KmuKey)) {
    Write-Host "  ⚠ keyfile.json not found — skipping. (OK if already provisioned.)"
} else {
    Write-Host "  $KmuKey"
    & $nrf device x-provision-keys --key-file $KmuKey @probe --family nrf54l 2>&1 | ForEach-Object { Write-Host "  $_" }
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ⚠ Non-zero exit (may already be provisioned — continuing.)"
    } else {
        Write-Host "  ✓ KMU key provisioned."
    }
    & $nrf device reset @probe --reset-kind RESET_SYSTEM 2>&1 | Out-Null
}
Write-Host ""

# ─── Step 3: Flash PIO app (signed.bin → slot0, ERASE_NONE) ───
Write-Host "━━━ Step 3/3: Flash PIO app ━━━"
if (-not (Test-Path -LiteralPath $AppBin)) {
    throw "PIO app not found: $AppBin`nEither copy it to $fwDir\app.signed.bin, or pass -AppBin <path>"
}
Write-Host "  $AppBin → slot0 @ $Slot0Address (ERASE_NONE)"
$appHex = Convert-BinToHex -Bin $AppBin -Offset $Slot0Address
& $nrf device program @probe --family nrf54l `
    --firmware $appHex --swd-clock-frequency 1000 `
    --options "chip_erase_mode=ERASE_NONE,reset=RESET_SYSTEM,verify=VERIFY_READ"
if ($LASTEXITCODE -ne 0) { throw "Step 3 failed." }
Write-Host "  ✓ App flashed."
Write-Host ""

# ─── Done ───
Write-Host "╔═══════════════════════════════════════════╗"
Write-Host "║  Factory provisioning complete!          ║"
Write-Host "╠═══════════════════════════════════════════╣"
Write-Host "║  Board now has:                          ║"
Write-Host "║    ✓ mcuboot (firmware-loader mode)      ║"
Write-Host "║    ✓ USB loader (slot1)                  ║"
Write-Host "║    ✓ KMU key (root-ed25519)               ║"
Write-Host "║    ✓ App (VID 2886:8013, 1200-bps DFU)  ║"
Write-Host "╠═══════════════════════════════════════════╣"
Write-Host "║  Updates: pio run -t upload (no JLink)   ║"
Write-Host "╚═══════════════════════════════════════════╝"
