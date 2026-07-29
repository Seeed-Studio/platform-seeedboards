@echo off
setlocal

REM Restore a XIAO nRF54LM20A to the known-good Zephyr blink firmware.
REM This operation mass-erases the application flash and removes APPROTECT.
REM It reuses PlatformIO's tool-openocd package; it does not install pyOCD.

set "SCRIPT_DIR=%~dp0"
set "FIRMWARE=%SCRIPT_DIR%firmware_lm20a_blink.hex"
set "OPENOCD_CFG=%SCRIPT_DIR%..\..\builder\board_build\nrf\nrf54lm20a.cfg"

if not exist "%FIRMWARE%" (
    echo [ERROR] Recovery firmware not found: %FIRMWARE%
    exit /b 5
)

if not exist "%OPENOCD_CFG%" (
    echo [ERROR] LM20A OpenOCD configuration not found: %OPENOCD_CFG%
    exit /b 5
)

where pio >nul 2>&1
if errorlevel 1 (
    echo [ERROR] PlatformIO Core ^(pio^) is required to run the bundled OpenOCD.
    exit /b 5
)

set "FIRMWARE_OC=%FIRMWARE:\=/%"

if "%~1"=="" (
    pio pkg exec -p tool-openocd -- openocd -f interface/cmsis-dap.cfg -f "%OPENOCD_CFG%" -c "adapter speed 4000" -c "init; nrf54l_mass_erase; halt; nrf54lm20a-load {%FIRMWARE_OC%}; reset run; shutdown"
) else (
    pio pkg exec -p tool-openocd -- openocd -f interface/cmsis-dap.cfg -c "adapter serial %~1" -f "%OPENOCD_CFG%" -c "adapter speed 4000" -c "init; nrf54l_mass_erase; halt; nrf54lm20a-load {%FIRMWARE_OC%}; reset run; shutdown"
)

if errorlevel 1 (
    echo [ERROR] XIAO nRF54LM20A recovery failed.
    exit /b 1
)

echo [SUCCESS] XIAO nRF54LM20A recovered with the blink firmware.
exit /b 0
