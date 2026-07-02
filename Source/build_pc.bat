@echo off
setlocal
cd /d "%~dp0"

python -m PyInstaller --noconfirm notebook.spec || exit /b 1

if not defined VERPATCH set "VERPATCH=verpatch.exe"
"%VERPATCH%" ".\dist\notebook\notebook.exe" 1.11.1.0 /va || (
    echo Set VERPATCH to verpatch.exe.
    exit /b 1
)

if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC set "ISCC=ISCC.exe"
"%ISCC%" "..\Installer\ABR_Peak_Analysis_Installer.iss" || (
    echo Set ISCC to Inno Setup ISCC.exe.
    exit /b 1
)
