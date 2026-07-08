@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%.." || exit /b 1
set "ROOT=%CD%"

for /f %%v in ('python -c "from Source.version import APP_VERSION; print(APP_VERSION)"') do set "APP_VERSION=%%v"

set "INSTALLERS=%ROOT%\dist\installers"
set "PYINSTALLER_DIST=%ROOT%\dist\pyinstaller\windows"
set "PYINSTALLER_BUILD=%ROOT%\build\pyinstaller\windows"
set "PYINSTALLER_CONFIG_DIR=%ROOT%\build\pyinstaller\cache"
set "VERSION_FILE=%PYINSTALLER_BUILD%\version_info.txt"

if not exist "%INSTALLERS%" mkdir "%INSTALLERS%"
if exist "%PYINSTALLER_DIST%" rmdir /s /q "%PYINSTALLER_DIST%"
if exist "%PYINSTALLER_BUILD%" rmdir /s /q "%PYINSTALLER_BUILD%"

echo Building Windows installer app...
python -m PyInstaller --noconfirm --clean ^
    --distpath "%PYINSTALLER_DIST%" ^
    --workpath "%PYINSTALLER_BUILD%\regular" ^
    "%ROOT%\packaging\pyinstaller\notebook.spec" || exit /b 1

if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC set "ISCC=ISCC.exe"

echo Building Windows setup installer...
"%ISCC%" "%ROOT%\packaging\windows\ABR_Peak_Analysis_Installer.iss" || (
    echo Set ISCC to Inno Setup ISCC.exe.
    exit /b 1
)

echo Building Windows portable executable...
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name "ABR-Peak-Analysis-%APP_VERSION%-win-x64-portable" ^
    --icon "%ROOT%\Source\icon.ico" ^
    --version-file "%VERSION_FILE%" ^
    --distpath "%INSTALLERS%" ^
    --workpath "%PYINSTALLER_BUILD%\portable" ^
    --specpath "%PYINSTALLER_BUILD%\portable-spec" ^
    --paths "%ROOT%\Source\kpy" ^
    --add-data "%ROOT%\Source\splash.png;." ^
    --add-data "%ROOT%\Source\splash_pyottlab.png;." ^
    --add-data "%ROOT%\Source\icon.ico;." ^
    --add-data "%ROOT%\Source\help;help" ^
    --add-data "%ROOT%\packaging\install_modes\portable\install_mode.txt;." ^
    --hidden-import kpy ^
    --hidden-import kpy.optimize ^
    --hidden-import kpy.optimize.logistic ^
    --hidden-import kpy.optimize.power2 ^
    --hidden-import kpy.optimize.sigmoid ^
    "%ROOT%\Source\notebook.py" || exit /b 1

echo Release artifacts written to "%INSTALLERS%".
popd
