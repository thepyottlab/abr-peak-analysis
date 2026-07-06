# -*- coding: utf-8 -*-

import numpy as np

import filter_EPL_LabVIEW_ABRIO_File as peakio
from filter_EPL_LabVIEW_ABRIO_File import safeopen

def load_audiogram(datafiles, window=None):
    agram = audiogram(datafiles[0])

    for d in datafiles:
        level_series = peakio.load(d)
        level_series.estimate_threshold()
        level = level_series.best_fit.x
        fit = level_series.best_fit.yfit
        agram.add(level_series.freq, level_series.threshold, level, fit, None)
#        agram.add(get_stim_freq(d), 35, None, None, None)
        if not window is None:
            window.SetStatusText('Processed %s' % d) 
            window.Refresh()
        
    return agram

class audiogram(object):

    def __init__(self, filename):
        self.filename = filename
        self.freqs = np.array([])
        self.thresholds = np.array([])
        self.minLevel = float('Inf')
        self.maxLevel = float('-Inf')
        self.levels = []
        self.fits = []

    def add(self, freq, threshold, levels, fit, adjR2):
        self.freqs = np.append(self.freqs, freq)
        self.thresholds = np.append(self.thresholds, threshold)
        self.levels.append(levels)
        self.minLevel = np.minimum(self.minLevel, np.min(levels))
        self.maxLevel = np.maximum(self.maxLevel, np.max(levels))
        self.fits.append(fit)
        
    def save(self):   
        filename = self.filename + '-audiogram.sqlite'
        #Prepare spreadsheet
        header = 'Freq (kHz)\tThreshold (dB SPL)\n'
        spreadsheet = '\n'.join(['{}\t{}'.format(f,t) for f,t in zip(self.freqs, self.thresholds)])
    
        f = safeopen(filename)
        f.writelines(header + spreadsheet)
        f.close()
    
        return 'Saved audiogram to %s' % filename
