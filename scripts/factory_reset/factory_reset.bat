@echo off
setlocal EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
set "VENV_DIR=%SCRIPT_DIR%.venv"
set "DEP_MARKER=%VENV_DIR%\.dependencies_installed"

if not exist "%VENV_DIR%" (
    echo Creating Python virtual environment...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo Failed to create virtual environment.
        exit /b 1
    )
) else (
    echo Reusing existing virtual environment.
)

echo Activating virtual environment...
call "%VENV_DIR%\Scripts\activate.bat"

if not exist "%DEP_MARKER%" (
    echo Installing dependencies...
    pip install pyocd libusb  
    if not errorlevel 1 (
        echo. > "%DEP_MARKER%"
    )
) else (
    echo Dependencies are already installed.
)

REM ================= Probe selection logic =================
set "ARG_PROBE=%~1"
set "PROBE_ID="

if not "%ARG_PROBE%"=="" (
    echo [INFO] Probe ID provided as argument: %ARG_PROBE%
    set "PROBE_ID=%ARG_PROBE%"
    goto HAVE_PROBE
)

set "SCRIPT_DIR=%~dp0"
set "FIRMWARE=%SCRIPT_DIR%firmware.hex"

REM Thin wrapper invoking unified Python tool.
set "ARG_PROBE=%~1"
set "EXTRA_ARGS="
if not "%ARG_PROBE%"=="" set "EXTRA_ARGS=--probe %ARG_PROBE%"

where pyocd >nul 2>&1
if errorlevel 1 (
    echo [INFO] pyocd not found, creating temporary venv and installing dependencies...
    set "VENV_DIR=%SCRIPT_DIR%.venv"
    if not exist "%VENV_DIR%" python -m venv "%VENV_DIR%"
    call "%VENV_DIR%\Scripts\activate.bat"
    pip install pyocd   libusb >nul
)

python "%SCRIPT_DIR%reset_tool.py" --mode factory --firmware "%FIRMWARE%" %EXTRA_ARGS%
if errorlevel 1 (
    echo [ERROR] Factory reset failed.
    exit /b 1
)
echo [SUCCESS] Factory reset completed.
exit /b 0
set "PROBE_ID=!ONLY_PROBE!"

echo [INFO] Single probe auto-selected: !PROBE_ID!
