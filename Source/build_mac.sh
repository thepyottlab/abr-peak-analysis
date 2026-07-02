#!/bin/bash
set -e

cd "$(dirname "$0")"

NAME="EPL ABR Analysis"
APPNAME="$NAME.app"
VER="1.11.1"

if [[ "$1" != "-package" && "$1" != "-dmg" ]]; then
    echo "Building app..."
#    pythonw setup.py py2app -S
    python -m PyInstaller --noconfirm notebook_mac.spec
    
    echo "Deleting build folder..."
    rm -rf build
fi

if [ "$1" == "-build" ]; then
    echo "Skipping package builds."
    echo "Done."
    exit 0
fi

if [ "$1" != "-dmg" ]; then
    echo "Building packages..."
    rm -rf /tmp/PkgRoot
    echo "Copying app to tmp..."
    mkdir -p "/tmp/PkgRoot/Applications/EPL"
    ditto "dist/$APPNAME" "/tmp/PkgRoot/Applications/EPL/$APPNAME"
    
    echo "Building package installer..."
    od=${PWD}
    cd /tmp
    pkgbuild --root PkgRoot "$NAME $VER.pkg"
    cd "$od"
fi

if [ "$1" != "-package" ]; then   
    echo "Remove folder"
    cd dist
    rm -rf "$NAME"
    cd ..
    
    echo "Rename dist folder..."
    rm -rf "$NAME $VER" "$NAME $VER.dmg"
    mv dist "$NAME $VER"
    
    echo "Create dmg..."
    hdiutil create -volname "$NAME $VER" -srcfolder "$NAME $VER" -ov -format UDZO "$NAME $VER.dmg"  
fi

echo "Done."
