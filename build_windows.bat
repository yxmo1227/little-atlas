@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -m venv .venv || exit /b 1
)
.venv\Scripts\python.exe -m pip --version >nul 2>&1
if errorlevel 1 .venv\Scripts\python.exe -m ensurepip --upgrade || exit /b 1
.venv\Scripts\python.exe -m pip install -r requirements-build.txt || exit /b 1
rem Keep unrelated DLL directories from the calling shell out of the bundle.
set "PATH=%~dp0.venv\Scripts;%SystemRoot%\System32;%SystemRoot%;%SystemRoot%\System32\Wbem"
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --windowed --onedir --name LittleAtlas --icon "dictionary_app\assets\little-atlas.ico" --add-data "dictionary_app\assets;dictionary_app\assets" --collect-all vosk --collect-all sounddevice --collect-all jwt --collect-all cryptography run.py
if errorlevel 1 exit /b 1
echo Build ready at dist\LittleAtlas\LittleAtlas.exe
endlocal
