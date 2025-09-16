@echo off
setlocal

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
    pip install git+https://github.com/pyocd/pyOCD.git libusb intelhex
    if not errorlevel 1 (
        echo. > "%DEP_MARKER%"
    )
) else (
    echo Dependencies are already installed.
)

echo Running recovery script...
python "%SCRIPT_DIR%xiao_nrf54l15_recover_flash.py" --hex "%SCRIPT_DIR%firmware.hex" --mass-erase

echo Done. The virtual environment is kept at %VENV_DIR%
endlocal

