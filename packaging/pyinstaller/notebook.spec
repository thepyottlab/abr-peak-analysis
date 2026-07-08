# -*- mode: python -*-

from pathlib import Path
import sys

HERE = Path(SPECPATH).resolve()
ROOT = HERE.parents[1]
SOURCE = ROOT / "Source"

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))

from pyinstaller_version_info import write_version_info

VERSION_FILE = ROOT / "build" / "pyinstaller" / "windows" / "version_info.txt"
write_version_info(VERSION_FILE)

block_cipher = None

a = Analysis([str(SOURCE / "notebook.py")],
             pathex=[str(SOURCE), str(SOURCE / "kpy")],
             binaries=[],
             datas=[(str(SOURCE / "splash.png"), "."),
                    (str(SOURCE / "splash_pyottlab.png"), "."),
                    (str(SOURCE / "icon.ico"), "."),
                    (str(SOURCE / "help"), "help")],
             hiddenimports=["kpy", "kpy.optimize", "kpy.optimize.logistic",
                            "kpy.optimize.power2", "kpy.optimize.sigmoid"],
             hookspath=[],
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
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)

pyz = PYZ(a.pure, a.zipped_data,
          cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          [],
          exclude_binaries=True,
          name="notebook",
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          console=False,
          icon=str(SOURCE / "icon.ico"),
          version=str(VERSION_FILE))
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=True,
               name="notebook")
