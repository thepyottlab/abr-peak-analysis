#!python

"""
I'm pretty sure the only dependencies for this program are:

    wxWidgets -- http://www.wxwidgets.org/
    wxPython -- http://www.wxpython.org/
    numpy -- http://numpy.scipy.org/
    scipy -- http://www.scipy.org/
    matplotlib -- http://matplotlib.sourceforge.net/

Alternatively, python(x,y) contains all of these libraries and more in one
install (http://www.pythonxy.com/foreword.php).

To build a distributable that does not require installation of the above
libraries, use the PyInstaller scripts documented in README.md.

Basic comments to following the code underlying this program.  ABR data is
stored in an object of type ABRSeries (defined in datatype.py).  A single
ABRSeries contains an arbitrary number of ABRWaveform objects.  Each ABRWaveform
object contains the raw time and amplitude data for that stimulus level.

On program launch, the window is created (defined in frame.py).  The GUI is
created using the wxWindows library (a very nice cross-platform library that
works on Windows, MacOS and Linux).  This library is very easy to use and offers
some great control widgets that we take advantage of to make the user interface
very friendly (e.g. directory browsing, drag and drop of files from the desktop
to the program window, persistent memory that remembers the user's preferred
window size across sessions, etc).  We are extra-careful to ensure that we use
only wxWindows widgets for the user interface and file handling as they are
designed to be completely cross-platform.

When the GUI detects that the user wishes to open a file (through one of several
mechanisms including control+F, double clicking on a file in the list on the
left, or dragging and dropping), it calls the load() function in the peakio
module.  Currently, peakio is defined to point to the
filter_EPL_LabVIEW_ABRIO_File.py module which defines a load() function that
knows how to import data stored in the ABR-XX-XX files.  For an example of an
alternate file format, see filter_database.py, which is designed to load ABR run
data from my database.

When an ABR run is loaded, a Model-View-Presenter (MVP, defined respectively by
datatype.py, abrcanvas.py, and presenter.py) paradigm is used to control
interaction with the user.  The "model" is the ABRSeries object, the "view" is
the plotting canvas, and the "interactor" detects keypresses when the canvas is
currently in focus (e.g. the GUI will detect keypresses and pass them to the
interactor who decides what type of action to take based on this information.
The interactor then tells the presenter what type of action to take (e.g. if the
"N" key is pressed, then call the appropriate presenter function such as
"normalize waveforms").  The presenter contains all necessary routines to
manipulate the state of the view.
D
For more detail on this model, see http://wiki.wxpython.org/ModelViewPresenter/
"""
# wxPython has a lot of DeprecationWarnings so we ignore these
import warnings; warnings.simplefilter('ignore', DeprecationWarning)

import os, sys

if sys.platform == 'win32':
    import numpy.core._dtype_ctypes # needed for PyInstaller on Windows

import logging
#logger = logging.getLogger(__name__)
#handler = logging.FileHandler('C:\\Users\\hancock\\Desktop\\notebook.log')
#handler.setLevel(logging.DEBUG)
#logger.addHandler(handler)
#logger.debug('adsfadfs')
#logging.basicConfig(filename='C:\\Users\\hancock\\Desktop\\notebook.log', level=logging.DEBUG)

from optparse import OptionParser
from frame import PhysiologyFrame
import wx

#---------------------------------------------------------------------------- 

def normal_mode():
    if sys.platform == 'win32':
        # icon = wx.Icon('icon.ico') # the frame restores the previous folder
        iconFile = os.path.join(os.path.dirname(__file__), 'icon.ico')    
        icon = wx.Icon(iconFile) # the frame restores the previous folder
    x = PhysiologyFrame(title='ABR Notebook',parent=None,splash=True)
    
    if sys.platform == 'win32':
        x.SetIcon(icon)

    x.Show()
    x.Restore()

# def automatic_mode():
    #runs = peakio.list(options.dir, options.skip)
#     runs = peakio.listall(None)
#     frame = AutomaticFrame(runs, params=options)

#----------------------------------------------------------------------------



if __name__ == '__main__':
    usage = "usage: \%prog [-i] [-n] [-a -s [-d dirname]]"
    parser = OptionParser(usage)

    parser.add_option('-a', '--automatic', action='store_true',
            dest='automatic', default=False, help="Enable automatic mode")
    parser.add_option('-d', '--dir', action='store', dest='dir', 
            help="Start directory")
    parser.add_option('-i', '--invert', action='store_true',
            dest='invert', default=False,
            help="Invert waveform polarity")
    parser.add_option('-n', '--ninterpolate', action='store_true',
            default=False, dest='nauto', 
            help="Interpolate N when waveforms are loaded")
    parser.add_option('-s', '--skip', action='store_true', dest='skip',
            default=False, help="Skip already processed files")

    options, args = parser.parse_args()

    logging.info('Starting...')

    app = wx.App(0)
    normal_mode()
    try:
        app.MainLoop()
    except:
        print('wx error')
