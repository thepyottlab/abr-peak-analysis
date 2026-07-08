# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

HERE = Path(SPECPATH).resolve()
ROOT = HERE.parents[1]
SOURCE = ROOT / "Source"

a = Analysis(
    [str(SOURCE / "notebook.py")],
    pathex=[str(SOURCE), str(SOURCE / "kpy")],
    binaries=[],
    datas=[(str(SOURCE / "splash.png"), "."),
           (str(SOURCE / "splash_pyottlab.png"), "."),
           (str(SOURCE / "icon.ico"), "."),
           (str(SOURCE / "help"), "help")],
    hiddenimports=["kpy", "kpy.optimize", "kpy.optimize.logistic", "kpy.optimize.power2", "kpy.optimize.sigmoid"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["alabaster",
              "babel",
              "certifi",
              "cryptography",
              "docutils",
              "gevent",
              "Include",
              "IPython",
              "jedi",
              "jsonschemea",
              "lib2to3",
              "lxml",
              "markupsafe",
              "psutil",
              "PyQt5",
              "sphinx",
              "sqlalchemy",
              "sqlite",
              "tornado",
              "win32com",
              "zmq",
              ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="notebook",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="EPL ABR Analysis",
)
app = BUNDLE(
    coll,
    name="EPL ABR Analysis.app",
    icon=str(SOURCE / "icon.icns"),
    bundle_identifier="org.pyottlab.abr-peak-analysis",
)
