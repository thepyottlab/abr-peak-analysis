from distutils.core import setup
from distutils.core import Distribution
import py2exe
import sys
import glob
import os
import shutil
import matplotlib

#Executable fails to load, unless line 1145 is commented out of 
#"C:\Python27\Lib\site-packages\scipy\stats\mstats_basic.py":
#1145 #trim.__doc__ = trim.__doc__ % trimdoc
# KEH 9/4/2013

# Run py2exe
if len(sys.argv) == 1:
    sys.argv.append("py2exe")
    sys.argv.append("-q")

# Ensure clean build
if os.path.exists("dist"):
    shutil.rmtree("dist")

if os.path.exists("build"):
    shutil.rmtree("build")

manifest_template = '''
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
<assemblyIdentity
    version="5.0.0.0"
    processorArchitecture="x86"
    name="%(prog)s"
    type="win32"
/>
<description>%(prog)s Program</description>
<dependency>
<dependentAssembly>
    <assemblyIdentity
        type="win32"
        name="Microsoft.VC90.CRT"
        version="9.0.30729.4918"
        processorArchitecture="X86"
        publicKeyToken="1fc8b3b9a1e18e3b"
        language="*"
    />
</dependentAssembly>
</dependency>
</assembly>
'''

class Target:
    def __init__(self, **kw):
        self.__dict__.update(kw)
        self.company_name = "Speech and Hearing Bioscience and Technology"
        self.copyright = "2007 by Brad Buran"
        self.name = "ABR Peak Analysis"

excludes = ["pywin", "pywin.debugger", "pywin.debugger.dbgcon",
            "pywin.dialogs", "pywin.dialogs.list", 'MySQLdb',
            "Tkconstants", "Tkinter", "tcl", "_imagingtk", 
            "PIL._imagingtk", "ImageTk", "PIL.ImageTk", "FixTk"]

# matplotlib.numerix deprecated in Python 2.7.5 --KEH
#includes = ['matplotlib.numerix', 'pytz']
includes = ['scipy.sparse.csgraph', 'pytz', 'scipy.special._ufuncs_cxx', 
            'scipy.linalg.cython_lapack', 'scipy.linalg.cython_blas', 'scipy._lib.messagestream',
            'kpy.optimize']

dataFiles = matplotlib.get_py2exe_datafiles()
imgFile = '', ['splash.png', 'splash_pyottlab.png']
missingDLLs = '', ['C:\Python27\Lib\site-packages\scipy\extra-dll\libwrap_dum.OPZRNAD6J4Q2YSFD3XWUEBCZJT4JBF5T.gfortran-win32.dll',
                   'C:\Python27\Lib\site-packages\scipy\extra-dll\lib_blas_su.UCPLJH7M3TZH6H6SS5P55GCHD6KXRUXA.gfortran-win32.dll',
                   'C:\Python27\Lib\site-packages\scipy\extra-dll\liblbfgsb.URM5MZGPDINSGKTAZDD5UIJSEQWWQWXK.gfortran-win32.dll',
                   'C:\Python27\Lib\site-packages\scipy\extra-dll\libansari.Q4BAGRNANLWD2YZJOKYPOAUIOLXW2LXK.gfortran-win32.dll',
                    'C:\Python27\Lib\site-packages\scipy\extra-dll\libnnls.UKOIZ7KCUBCO4AMYLF4QMFY6DUKCW4MU.gfortran-win32.dll']
dataFiles.append(imgFile)
dataFiles.append(missingDLLs)

RT_MANIFEST = 24
manifest = manifest_template % dict(prog="notebook")

notebook = Target(
    version = '1.3.0.32',
    description = "ABR Notebook",
    script = "notebook.py",
    other_resources = [(RT_MANIFEST, 1, manifest)],
    dest_base = "notebook"
    )

setup(
    #cmdclass = {'py2exe': py2exe},
    windows = [notebook],
	 console = [notebook],
    zipfile = 'library.zip',
    data_files = dataFiles,
    options = {
        'py2exe': {
            'compressed': 2,
            'optimize': 2,
            'packages': includes,
            'excludes': excludes,
        }
    })


