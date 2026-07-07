@echo off
setlocal
cd /d "%~dp0"

for /f %%v in ('python -c "from version import APP_VERSION; print(APP_VERSION)"') do set "APP_VERSION=%%v"
set "INSTALLERS=%~dp0..\Installers"
if not exist "%INSTALLERS%" mkdir "%INSTALLERS%"

echo Building Windows installer app...
python -m PyInstaller --noconfirm notebook.spec || exit /b 1

if not defined VERPATCH set "VERPATCH=verpatch.exe"
"%VERPATCH%" ".\dist\notebook\notebook.exe" %APP_VERSION%.0 /va || (
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

echo Building Windows portable executable...
python -m PyInstaller --noconfirm --onefile --windowed ^
    --name "ABR-Peak-Analysis-%APP_VERSION%-win-x64-portable" ^
    --icon icon.ico ^
    --distpath "%INSTALLERS%" ^
    --workpath "build\portable" ^
    --paths kpy ^
    --add-data "splash.png;." ^
    --add-data "splash_pyottlab.png;." ^
    --add-data "icon.ico;." ^
    --add-data "help;help" ^
    --hidden-import kpy ^
    --hidden-import kpy.optimize ^
    --hidden-import kpy.optimize.logistic ^
    --hidden-import kpy.optimize.power2 ^
    --hidden-import kpy.optimize.sigmoid ^
    notebook.py || exit /b 1

echo Release artifacts written to "%INSTALLERS%".
