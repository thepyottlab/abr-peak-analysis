# -*- mode: python -*-

import os
import sys

block_cipher = None
HERE = os.path.abspath(SPECPATH)
sys.path.insert(0, HERE)

from pyinstaller_version_info import write_version_info

VERSION_FILE = os.path.join(HERE, 'build', 'version_info.txt')
write_version_info(VERSION_FILE)


a = Analysis(['notebook.py'],
             pathex=[HERE, os.path.join(HERE, 'kpy')],
             binaries=[],
             datas=[('splash.png', '.'),
                    ('splash_pyottlab.png', '.'),
                    ('icon.ico', '.'),
                    ('help', 'help')],
             hiddenimports=['kpy', 'kpy.optimize', 'kpy.optimize.logistic',
                            'kpy.optimize.power2', 'kpy.optimize.sigmoid'],
             hookspath=[],
             runtime_hooks=[],
             excludes=['alabaster', 
                       'babel',
                       'certifi',
                       'cryptography',
                       'docutils',
                       'gevent',
                       'Include',
                       'IPython',
                       'jedi',
                       'jsonschemea',
                       'lib2to3',
                       'lxml',
                       'markupsafe',
                       'psutil',
                       'PyQt5', 
                       'sphinx',
                       'sqlalchemy',
                       'sqlite',
                       'tornado',
                       'win32com',
                       'zmq',
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
          name='notebook',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          console=False,
          icon='icon.ico',
          version=VERSION_FILE)
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=True,
               name='notebook')
