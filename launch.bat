@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Installing Little Atlas for this Windows user...
  py -m venv .venv || exit /b 1
)
.venv\Scripts\python.exe -m pip --version >nul 2>&1
if errorlevel 1 .venv\Scripts\python.exe -m ensurepip --upgrade || exit /b 1
.venv\Scripts\python.exe -m pip install -r requirements.txt || exit /b 1
start "" ".venv\Scripts\pythonw.exe" -m dictionary_app
endlocal
