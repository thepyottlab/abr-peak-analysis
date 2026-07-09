#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON="${PYTHON:-python}"
cd "$ROOT"

APP_NAME="EPL ABR Analysis"
APP_BUNDLE="$APP_NAME.app"
VERSION="$("$PYTHON" -c 'from Source.version import APP_VERSION; print(APP_VERSION)')"

INSTALLERS="$ROOT/dist/installers"
PYINSTALLER_DIST="$ROOT/dist/pyinstaller/macos"
PYINSTALLER_BUILD="$ROOT/build/pyinstaller/macos"
PKG_ROOT="$ROOT/build/pkgroot"
PKG_NAME="ABR-Peak-Analysis-${VERSION}-macos-arm64.pkg"
COMPONENT_PLIST="$ROOT/packaging/macos/components.plist"
SCRIPTS_DIR="$ROOT/packaging/macos/scripts"

export PYINSTALLER_CONFIG_DIR="$ROOT/build/pyinstaller/cache"

mkdir -p "$INSTALLERS"
rm -rf "$PYINSTALLER_DIST" "$PYINSTALLER_BUILD" "$PKG_ROOT"
rm -f "$INSTALLERS/$PKG_NAME"

echo "Building macOS app..."
"$PYTHON" -m PyInstaller --noconfirm --clean \
    --distpath "$PYINSTALLER_DIST" \
    --workpath "$PYINSTALLER_BUILD" \
    "$ROOT/packaging/pyinstaller/notebook_mac.spec"

echo "Staging package..."
mkdir -p "$PKG_ROOT/Applications"
ditto "$PYINSTALLER_DIST/$APP_BUNDLE" "$PKG_ROOT/Applications/$APP_BUNDLE"
mkdir -p "$PKG_ROOT/Applications/$APP_BUNDLE/Contents/Resources"
cp "$ROOT/packaging/install_modes/installer/install_mode.txt" \
    "$PKG_ROOT/Applications/$APP_BUNDLE/Contents/Resources/install_mode.txt"

echo "Building package installer..."
pkgbuild \
    --root "$PKG_ROOT" \
    --component-plist "$COMPONENT_PLIST" \
    --scripts "$SCRIPTS_DIR" \
    --identifier "org.pyottlab.abr-peak-analysis" \
    --version "$VERSION" \
    "$INSTALLERS/$PKG_NAME"

echo "Release artifact written to $INSTALLERS/$PKG_NAME."
