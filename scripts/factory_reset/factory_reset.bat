@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "VENV_DIR=%SCRIPT_DIR%.venv"

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

echo Running recovery script...
python "%SCRIPT_DIR%xiao_nrf54l15_recover_flash.py" --hex "%SCRIPT_DIR%firmware.hex" --mass-erase

echo Done. The virtual environment is kept at %VENV_DIR%
endlocal

