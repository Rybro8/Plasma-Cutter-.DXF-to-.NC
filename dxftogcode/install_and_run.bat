@echo off
rem dxftogcode installer + launcher.
rem First run: finds (or installs) Python, creates .venv, installs dependencies.
rem Every run: starts the server and opens the app in the browser.
setlocal
cd /d "%~dp0"

set "VENV_PY=%~dp0.venv\Scripts\python.exe"
set "URL=http://127.0.0.1:5000"

if exist "%VENV_PY%" goto deps

echo [1/3] Looking for Python 3...
set "PY="
rem "python -c" also rules out the Microsoft Store stub, which exists but can't run code.
py -3 -c "import sys" >nul 2>&1 && set "PY=py -3"
if not defined PY python -c "import sys; assert sys.version_info >= (3, 10)" >nul 2>&1 && set "PY=python"

if not defined PY (
    echo Python not found. Installing Python 3.12 with winget...
    winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
    if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
        set "PY="%LOCALAPPDATA%\Programs\Python\Python312\python.exe""
    ) else (
        echo.
        echo Could not install Python automatically.
        echo Install Python 3.10+ from https://www.python.org/downloads/ and run this script again.
        pause
        exit /b 1
    )
)

echo [2/3] Creating virtual environment...
%PY% -m venv .venv
if errorlevel 1 (
    echo Failed to create the virtual environment.
    pause
    exit /b 1
)

:deps
echo [3/3] Installing dependencies...
"%VENV_PY%" -m pip install --disable-pip-version-check -q --upgrade pip
"%VENV_PY%" -m pip install --disable-pip-version-check -q -r backend\requirements.txt
if errorlevel 1 (
    echo Failed to install dependencies. Check your internet connection and try again.
    pause
    exit /b 1
)

echo.
echo Starting dxftogcode at %URL%  (close this window to stop it)
rem Open the browser once the server has had a moment to come up.
start "" /b cmd /c "timeout /t 3 /nobreak >nul & start "" %URL%"
"%VENV_PY%" backend\app.py
pause
