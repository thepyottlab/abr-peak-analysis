import re, os, sqlite3
import numpy
import analysis_sqlite
from walker import ReWalker
from datafile import loadabr
from datatype import ABRStimPolarity
import time

from config import expected_peak_count

abr_re = '^ABR-[0-9]+-[0-9]+(\\.dat)?$'
abr_processed_re = '^ABR-[0-9]+-[0-9]+(\\.dat)?-analyzed.txt$'
numbers = re.compile('[0-9]+')

'''
This module defines the import/export routines for interacting with the data
store.  If you wish to customize this, simply define the functions load(),
save(), list() and sort().

list(location, skip_processed) -- Accepts a location string (provided by the
-d flag or the user options dialog).  In the example below, the location
string is expected to be a directory, but possible variations include a
database connection string.  Skip_Processed is a boolean that indicates
whether or not already processed runs should be skipped (very useful when you
are running the program in automatic mode where the next run in the series is
loaded as soon as analysis of the current run is complete).  This function
should return a list of tuples where the tuple is in the format (name,
run_location).  Name is the string displayed to the user (e.g. 'BNB37 Right, Run
2 at 16kHz'), while run_location is can be any Python object that provides the
information needed by load() to access the data from that run.  It's up to you
to put sufficient information into the run_location variable to be able to find
the data for that specific run (e.g. if all data for the run is stored in a
file, then run_location would hold a pointer to the file).  The contents you put
into run_location will be passed to load, and you can use these contents to find
the data.

load(run_location, invert, filter) -- When the program needs a run loaded, it
will pass the run_location provided by list().  Invert is a boolean flag
indicating whether waveform polarity should be flipped.  Filter is a dictionary
containing the following keys:
    1. ftype: any of None, butterworth, bessel, etc.
    2. fh: highpass cutoff (integer in Hz)
    3. fl: lowpass cutoff (integer in Hz)
All objects of the epl.datatype.Waveform class will accept the filter
dictionary and perform the appropriate filtering.  It is recommended you use the
filtering provided by the Waveform class as the parameters of the filter will
also be recorded.  This function must return an object of the
epl.datatype.ABRSeries class.  See this class for appropriate documentation.

save(ABRseries) -- When the user requests to save the analyzed data, the data,
stored as an ABRseries object, is passed to save().  ABRseries contains the
following attributes:
      1. filename: name of the file that the data was originally loaded from
      2. freq: stimulus frequency
      3. series: a list of waveforms (in the ABRWaveform class format) that
      belong to the series. 
Each waveform of the ABRWaveform class contains the following attributes:
      1. level: stimulus level
      2. zpk: a list containing the history of filtering for the waveform,
      stored as zpk format.  [0] is the earliest filtering, [-1] is the most
      recent.  
      3. points: a dictionary containing the points P1-6 and N1-6.  Each point
      is an object with amplitude and latency attributes.

The save function must return a message.  If there is an error in saving, throw
the appropriate exception.
'''

def load(run, invert=False, filter=None, polarity=ABRStimPolarity.Avg, t_min=0, t_max=0):
    if filter is None or filter['ftype'] == 'None':
        return loadabr(run, filter=False, invert=invert, polarity=polarity,
                       t_min=t_min, t_max=t_max)
    else:
        return loadabr(run, filter=True, fdict=filter, invert=invert, polarity=polarity,
                       t_min=t_min, t_max=t_max)

def _has_saved_analysis(path):
    try:
        return any(
            any(analysis_sqlite.stored_datasets_at_path(
                path + '-analyzed.sqlite', polarity).values())
            for polarity in ABRStimPolarity
        )
    except sqlite3.Error:
        return False

def list(location, skip_processed=False):
    if location is not None and os.path.isdir(location):
        data = os.listdir(location)
        data = [f for f in data
                if 'ch0avg' not in f and not f.lower().endswith('.sqlite')]
        return [{
            'display':  d,
            'data':     os.path.join(location, d),
            'sort_key': d,
            'has_children': os.path.isdir(os.path.join(location, d)),
            'data_string':  os.path.join(location, d),
            'processed': _has_saved_analysis(os.path.join(location, d)),
            } for d in data]

    '''The walker class recursively iterates through all directories and returns
    a list of file paths (relative to the location directory) when list() is
    called.  ReWalker returns only files whose name matches the regex provided.
    '''
    '''
    runs = ReWalker(location, abr_re).list()
    if skip_processed:
        processed_runs = ReWalker(location, abr_processed_re).list()
        processed_runs = [os.path.split(p)[1][:-13] for p in processed_runs]
        runs = [r for r in runs if os.path.split(r)[1] not in processed_runs]
    '''

    '''The next three lines use a decorate-sort-undecorate paradigm where the
    file paths are turned into a list of tuples, with each tuple consisting of
    (sort_key, file_path).  When sort() is called on a list, it always sorts by
    the first element (the sort key in this case), then the second element and
    so on.  Once the list is sorted, we can then remove the sort key and return
    just the file paths.
    '''
    '''
    runs = [([int(n) for n in numbers.findall(r)], r) for r in runs]
    runs.sort()
    runs = [r[1] for r in runs]
    runs = [(os.path.split(r)[1], r) for r in runs]
    return runs
    '''

def save(model):
    return analysis_sqlite.save(model)


def legacy_analysis_path(model):
    filename = model.filename
    if model.stimPol == ABRStimPolarity.Condensation:
        filename = filename + '-cond'
    if model.stimPol == ABRStimPolarity.Rarefaction:
        filename = filename + '-rare'

    return filename + '-analyzed.txt'


def have_stored_analysis(model):
    return analysis_sqlite.have_analysis(model) or os.path.isfile(legacy_analysis_path(model))

def restore_analysis(model):
    if analysis_sqlite.have_analysis(model):
        return analysis_sqlite.restore(model)

    return restore_text_analysis(model)


def restore_text_analysis(model):
    filename = legacy_analysis_path(model)
    
    msg = ""
    pind = []
    nind = []
    thr = float('NaN')
    
    if not os.path.isfile(filename):
        msg = "Analyzed data not found for '" + model.filename + "'"
        return msg, pind, nind, thr

    p_thr = re.compile(r'Threshold \(dB SPL\):\s*([+-]?\d+(?:\.\d+)?)?')
    p_header = re.compile(r'Level')
    p_latency = re.compile(r'P(\d+)\s+Latency', re.I)
    n_latency = re.compile(r'N(\d+)\s+Latency', re.I)
    
    try:
        with open(filename, encoding='latin-1') as f:
            data = f.read()
            thr = None
            
            res = p_thr.search(data)
            if res is not None and res.group(1):
                thr = float(res.group(1))
            
            res = p_header.search(data)
            lines = data[res.start():].split('\n')
            
            fs = model.series[0].fs / 1000
            n = len(lines) - 1

            header_cols = lines[0].split('\t')
            p_map = {}
            n_map = {}
            for ci, col in enumerate(header_cols):
                col = col.strip()
                pm = p_latency.match(col)
                if pm:
                    p_map[int(pm.group(1))] = ci
                    continue
                nm = n_latency.match(col)
                if nm:
                    n_map[int(nm.group(1))] = ci

            restored_peaks = tuple(p_map) + tuple(n_map)
            peak_count = max((expected_peak_count(),) + restored_peaks)
            pind = numpy.full((n, peak_count), -1, dtype=int)
            nind = numpy.full((n, peak_count), -1, dtype=int)

            for k in range(n):
                values = lines[k + 1].split('\t')
                for peak_num, col_index in p_map.items():
                    if col_index < len(values):
                        pval = values[col_index].strip()
                        if pval:
                            pind[n - k - 1, peak_num - 1] = round(abs(float(pval)) * fs)
                for valley_num, col_index in n_map.items():
                    if col_index < len(values):
                        val = values[col_index].strip()
                        if val:
                            nind[n - k - 1, valley_num - 1] = round(abs(float(val)) * fs)
                
    except (AttributeError, ValueError):
        msg = 'Could not parse %s' % filename
        raise IOError(msg)

    msg = "Loaded data from '" + model.filename + "'"
    
    
    return msg, pind, nind, thr

def safeopen(file):
    '''Checks to see if a file already exists.  If it does, it is archived
    using the earlier of the file creation time or the file modified time.  In
    my experience, the file creation time changes when the file is copied to a
    new filesystem; however, the file modified time usually is not updated on
    this copy.  Another complication is that Windows does not change the file
    creation time if the same filename is deleted and then recreated within a
    certain period.  We only use file modification time.

    '''
    if os.path.exists(file):
        base, fname = os.path.split(file)
        filetime = os.path.getmtime(file)
        filestring = time.strftime('%Y-%m-%d-%H-%M-%S-',
                time.gmtime(filetime))
        new_fname = os.path.join(base, filestring+fname)
        os.rename(file, new_fname) 
    return open(file, 'w')
