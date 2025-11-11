@echo off
setlocal

REM ==============================================
REM Recover-only wrapper
REM ==============================================
set "SCRIPT_DIR=%~dp0"
set "VENV_DIR=%SCRIPT_DIR%.venv"
set "DEP_MARKER=%VENV_DIR%\.deps_installed"
set "ARG_PROBE=%~1"
set "EXTRA_ARGS="
if not "%ARG_PROBE%"=="" set "EXTRA_ARGS=--probe %ARG_PROBE%"

REM ---------- Create or reuse venv ----------
if not exist "%VENV_DIR%" (
  echo [INFO] Creating Python virtual environment...
  python -m venv "%VENV_DIR%"
  if errorlevel 1 (
    echo [ERROR] Failed to create virtual environment.
    exit /b 1
  )
) else (
  echo [INFO] Reusing existing virtual environment.
)

REM ---------- Activate venv ----------
call "%VENV_DIR%\Scripts\activate.bat"
if errorlevel 1 (
  echo [ERROR] Failed to activate virtual environment.
  exit /b 1
)

REM ---------- Install dependencies (once) ----------
if not exist "%DEP_MARKER%" (
  echo [INFO] Installing dependencies into venv (pyocd libusb)...
  pip install pyocd libusb >nul
  if errorlevel 1 (
    echo [ERROR] Dependency installation failed.
    exit /b 1
  )
  echo. > "%DEP_MARKER%"
) else (
  echo [INFO] Dependencies already installed in venv.
)

REM ---------- Invoke unified tool ----------
python "%SCRIPT_DIR%reset_tool.py" --mode recover %EXTRA_ARGS%
if errorlevel 1 goto FAIL
echo [SUCCESS] Recover-only completed.
exit /b 0

:FAIL
echo [ERROR] Recover-only failed.
exit /b 1
endlocal
