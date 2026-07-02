"""
Collection of classes for handling common data types

Created: Sat 23 Jun 2007 12:18:30 PM
Modified: Sat 16 Aug 2008 11:46:13 AM
"""

from __future__ import generators
from __future__ import division

#import matplotlib.pyplot as plt

__author__ = 'Brad Buran, bburan@alum.mit.edu'

from scipy import signal as sig
import numpy as np
from copy import deepcopy
from enum import IntEnum
from peakdetect import find_spurious_peaks

import os
import operator

from kpy.optimize import power2, sigmoid, smooth

#def Enum(*names):
#   ##assert names, "Empty enums are not supported" # <- Don't like empty enums? Uncomment!
#
#   class EnumClass(object):
#      __slots__ = names
#      def __iter__(self):        return iter(constants)
#      def __len__(self):         return len(constants)
#      def __getitem__(self, i):  return constants[i]
#      def __repr__(self):        return 'Enum' + str(names)
#      def __str__(self):         return 'enum ' + str(constants)
#
#   class EnumValue(object):
#      __slots__ = ('__value')
#      def __init__(self, value): self.__value = value
#      Value = property(lambda self: self.__value)
#      EnumType = property(lambda self: EnumType)
#      def __hash__(self):        return hash(self.__value)
#      def __cmp__(self, other):
#         # C fans might want to remove the following assertion
#         # to make all enums comparable by ordinal value {;))
#         assert self.EnumType is other.EnumType, "Only values from the same enum are comparable"
#         return cmp(self.__value, other.__value)
#      def __invert__(self):      return constants[maximum - self.__value]
#      def __nonzero__(self):     return bool(self.__value)
#      def __repr__(self):        return str(names[self.__value])
#
#   maximum = len(names) - 1
#   constants = [None] * len(names)
#   for i, each in enumerate(names):
#      val = EnumValue(i)
#      setattr(EnumClass, each, val)
#      constants[i] = val
#   constants = tuple(constants)
#   EnumType = EnumClass()
#   return EnumType
from enum import Enum

class Th(Enum):
    SUB = 1
    TH = 2
    SUPRA = 3
    UNK = 4
#Th = Enum('SUB', 'TH', 'SUPRA', 'UNK')
class Point(Enum):
    PEAK = 1
    VALLEY = 2
#Point = Enum('PEAK', 'VALLEY') 
class ThrSource(Enum):
    NoThr = 1
    Auto = 2
    Manual = 3
#ThrSource = Enum('None', 'Auto', 'Manual')

###############################################################################
# Waveforms
###############################################################################
class waveform(object):

    def __init__(self, fs, signal, invert=False, filter=False, 
            normalize=False, zpk=[]):
        self.fs = fs
        #Record of filters that have been applied to waveform
        self._zpk = zpk
        #Time in msec
        self.x = np.arange(len(signal)) * 1000.0 / self.fs
        #Voltage in microvolts
        self.y = signal

        if invert:
            self.invert()
        if filter:
            self.filter()
        if normalize:
            self.normalize()

    def filter(self, N=1, W=(200, 10e3), btype='bandpass', ftype='butterworth',
            method='filtfilt'):

        """Returns waveform filtered using filter paramters specified. If none
        are specified, performs bandpass filtering (1st order butterworth)
        with fl=200Hz and fh=10000Hz.  Note that the default uses filtfilt
        using a 1st order butterworth, which essentially has the same effect
        as a 2nd order with lfilt (but without the phase delay).  
        """
        Wn = np.asarray(W) / (self.fs / 2)
        Wn[1] = min(Wn[1], 0.95)
        kwargs = dict(N=N, Wn=Wn, btype=btype, ftype=ftype)
        
        sos = sig.iirfilter(output='sos', **kwargs)

        zpk = sig.iirfilter(output='zpk', **kwargs)

        self._zpk.append(zpk)
        if method == 'filtfilt': self.y = sig.sosfiltfilt(sos, self.y)
        else: raise NotImplementedError('%s not supported' % method)

    def rectify(self, cutoff=0):
        self.y[self.y<cutoff] = cutoff

    def rectified(self, *args, **kwargs):
        waveform = deepcopy(self)
        waveform.rectify(*args, **kwargs)
        return waveform

    def filtered(self, *args, **kwargs):
        waveform = deepcopy(self)
        waveform.filter(*args, **kwargs)
        return waveform

    def normalize(self):
        '''Returns waveform normalized to one 1(unit) peak to peak
        amplitude.
        ''' 
        amplitude = self.y.max() - self.y.min()
        self.y = self.y / amplitude

    def normalized(self):
        waveform = deepcopy(self)
        waveform.normalize()
        return waveform

    def invert(self):
        self.y = -self.y

    def inverted(self):
        waveform = deepcopy(self)
        waveform.invert()
        return waveform

    def fft(self):
        freq = np.fft.fftfreq(len(self.y), 1/self.fs)
        fourier = np.fft.fft(self.y)
        magnitude = np.abs(fourier)/2**.5
        #magnitude = 20*np.log(magnitude)
        return freq, magnitude

    def freqclip(self, cutoff):
        freq, magnitude = self.fft()
        mask = (freq>cutoff)^(freq<-cutoff)
        magnitude[mask] = 0
        self.y = np.fft.ifft(magnitude)

    def stat(self, bounds, func):
        lb = bounds[0] / ((1/self.fs)*1000)
        ub = bounds[1] / ((1/self.fs)*1000)
        return func(self.y[int(lb):int(ub)])

    def __add__(self, other):
        if not isinstance(other, waveform):
            raise Exception
        if len(other.y) != len(self.y):
            raise Exception
        if other.fs != self.fs:
            raise Exception

        self.y += other.y
        return self

    def __div__(self, other):
        self.y /= other
        return self

#-------------------------------------------------------------------------------

class waveformpoint(object):

    def __init__(self, parent, index, point):
        self.parent = parent
        self.index = index
        self.point = point

    def get_x(self):
        return self.parent.x[self.index]

    def get_y(self):
        return self.parent.y[self.index]

    x = property(get_x, None, None, None)
    y = property(get_y, None, None, None)

    def get_latency(self):
        if self.parent.threshold in (Th.UNK, Th.SUB):
            return -np.abs(self.x)
        else:
            return self.x

    def get_amplitude(self):
        return self.y

    latency = property(get_latency, None, None, None)
    amplitude = property(get_amplitude, None, None, None)

#-------------------------------------------------------------------------------

class abrwaveform(waveform):
    
    def __init__(self, fs, signal, level, cc=float('nan'), invert=False, filter=False, 
            normalize=False, zpk=[]):
        waveform.__init__(self, fs, signal, invert, filter, normalize, zpk)
        self.level = level
        self.threshold = Th.UNK
        self.corrcoef = cc 

#-------------------------------------------------------------------------------

class series(object):
    
    pass

class sortedseries(series):
    """Container for a group of objects that vary along a single parametric axis 
    (such as level or frequency).  The objects are sorted via __cmp__
    """

    def __init__(self, series, key=None):
        series.sort(key=key)
        self.series = series

#-------------------------------------------------------------------------------
class ABRDataType(IntEnum):
    CFTS = 1
    VsEP = 2
    Clinical = 3

#-------------------------------------------------------------------------------
class ABRStimPolarity(IntEnum):
    Avg = 1
    Condensation = 2
    Rarefaction = 3

#-------------------------------------------------------------------------------
def GetABRDataType(fname):
    
    dtype = ABRDataType.CFTS    
    
    fn, ext = os.path.splitext(fname)
    if ext == '.csv':
        dtype = ABRDataType.Clinical

    if fn.startswith('VsEP'):
        dtype = ABRDataType.VsEP
        
    return dtype
#-------------------------------------------------------------------------------

class abrseries(sortedseries):

    def __init__(self, waveforms, freq=None, threshold=None, dataType=ABRDataType.CFTS, stimPol=ABRStimPolarity.Avg, varyMasker=False):
        sortedseries.__init__(self, waveforms, operator.attrgetter('level'))
        self.freq = freq
        self.dataType = dataType
        self.stimPol = stimPol

        self._varymasker = varyMasker
        if varyMasker:
            self.series = np.flipud(self.series)
                
        if threshold is None:
            for w in self.series: w.threshold = Th.UNK
        else:
            self.threshold = threshold

        self.thresholdCriterion = 0.35            
        self.adjR2Criterion = 0.7
        self._p2Result = None
        self._sigResult = None
        self.thresholdEstimationFailed = False
        self.thresholdSource = ThrSource.NoThr
        self._bestFit = None
        self._bestFitType = None
        
        self.useNoiseFloor = False
        self.noiseFloor = 0;
        self.randomPeaks = None

    def invert(self):
        for w in self.series:
            w.invert()

    def set_threshold(self, threshold):
        if not self.threshold == threshold:
            self.__threshold = threshold
            for w in self.series:
                if threshold is None:
                    w.threshold = Th.UNK
                elif (w.level >= threshold and not self.varymasker) or (w.level <= threshold and self.varymasker):
                    w.threshold = Th.SUPRA
                elif w.level == threshold:
                    w.threshold = Th.TH
                else:
                    w.threshold = Th.SUB

    def get_threshold(self):
        try: return self.__threshold
        except AttributeError: return None

    threshold = property(get_threshold, set_threshold, None, None)

    def set_manual_threshold(self, threshold):
        self.set_threshold(threshold)
        self.thresholdSource = ThrSource.Manual

    def restore_threshold(self, threshold, source='', method=''):
        self.threshold = threshold
        self._bestFitType = None
        source = (source or '').lower()
        method_key = (method or '').lower()
        if threshold is None:
            self.thresholdSource = ThrSource.NoThr
        elif source in ('automatic', 'auto') or (method_key and method_key != 'manual'):
            self.thresholdSource = ThrSource.Auto
            if method_key not in ('', 'automatic', 'auto', 'manual'):
                self._bestFitType = method
        else:
            self.thresholdSource = ThrSource.Manual
        
    def compute_corrcoefs(self, tmin=0, tmax=8.5):
        for w,wnext in zip(self.series[0:len(self.series)-1], self.series[1:]):
            iwin_min = np.round(tmin * w.fs/1000).astype(int)
            iwin_max = np.round(tmax * w.fs/1000).astype(int)
            w.corrcoef = np.corrcoef(w.y[iwin_min:iwin_max], wnext.y[iwin_min:iwin_max])[0, 1]

    def get_corrcoefs(self):
        # iterate over waveforms, extract levels and corrcoefs
        level = np.array([w.level for w in self.series])
        cc = np.array([w.corrcoef for w in self.series])

        # because corrcoefs are computed between consecutive levels, the last
        # value is meaningless
        return [cc[:len(cc)-1], level[:len(level)-1]]

    def get_auto_thresholded(self):
        return self.thresholdSource is ThrSource.Auto
        
    auto_thresholded = property(get_auto_thresholded, None, None, None)
    
    def get_power2_result(self):
        return self._p2Result

    def get_sigmoid_result(self):
        return self._sigResult

    def get_best_fit(self):
        return self._bestFit

    def get_best_fit_type(self):
        return self._bestFitType

    power2_result = property(get_power2_result, None, None, None)
    sigmoid_result = property(get_sigmoid_result, None, None, None)
    best_fit = property(get_best_fit, None, None, None)
    best_fit_type = property(get_best_fit_type, None, None, None)
    
    def estimate_threshold(self):
        # Kirupa's method; following flowchart, updated 4/23/2019:
        # 1. Retrieve corrcoef and level arrays
        cc, level = self.get_corrcoefs()
        if cc.size == 0:
            self.threshold = None
            self.thresholdSource = ThrSource.NoThr
            self.thresholdEstimationFailed = True
            self._p2Result = None
            self._sigResult = None
            self._bestFit = None
            self._bestFitType = None
            return

#       Smoothing removed 4/23
#        cc_smooth = smooth(cc, 3)
        cc_smooth = cc

        # 2. Fit 'power2' curve (y = a*x^b + c)
        self._p2Result = power2.fit(level, cc_smooth)
        
        # 3. Fit 'sigmoid' curve (sigmoid)
        self._sigResult = sigmoid.fit(level, cc_smooth)        
        
        # 4. Use the fit to find level where corrcoef reaches the criterion
        # value. (criterion should be stored in a config file or something, so
        # it can be accessed externally.)
        threshold = None
        
        # 5. sigmoid fit wins if:
        # slope is within range...
        slope = self._sigResult.param[1];
        logFitWins = slope>=0.005 and slope<=0.999
        # ...and RMS error is better than power2 fit...
        logFitWins = logFitWins and self._sigResult.stats.sse < self._p2Result.stats.sse
        # ...and min value is below the cross-correlation criterion...
        logFitWins = logFitWins and self._sigResult.param[3] < self.thresholdCriterion
        # ...and max value is greater than the cross-correlation criterion
        logFitWins = logFitWins and self._sigResult.param[0]+self._sigResult.param[3] > self.thresholdCriterion

        if logFitWins:
            self._bestFit = self._sigResult
            self._bestFitType = 'sigmoid'
            threshold = sigmoid.inverse(self.thresholdCriterion, *self._sigResult.param)

        elif self._p2Result.stats.adj_r2 > self.adjR2Criterion:
            self._bestFit = self._p2Result
            self._bestFitType = 'power law'
            threshold = power2.inverse(self.thresholdCriterion, *self._p2Result.param) - self._p2Result.xoff   

        elif np.amax(cc) > self.thresholdCriterion:
            self._bestFit = self._p2Result
            self._bestFitType = 'power law (noisy)'
            threshold = power2.inverse(self.thresholdCriterion, *self._p2Result.param) - self._p2Result.xoff               
                        
        if not threshold is None:
            self.threshold = threshold
            self.thresholdSource = ThrSource.Auto
        else:
            self.thresholdEstimationFailed = True
            if self._p2Result.stats.adj_r2 > self._sigResult.stats.adj_r2:
                self._bestFit = self._p2Result
                self._bestFitType = 'power law'
            else:
                self._bestFit = self._sigResult
                self._bestFitType = 'sigmoid'

    def find_noise_floor(self, cm, maxLevel=70):
        allPeaks = []
        self.useNoiseFloor = True
        self.randomPeaks = []
        for i in range(len(self.series)):
            cur = self.series[i]
            if cur.level < maxLevel:
                peaks = find_spurious_peaks(cur.fs, cm[i,:], min_latency=0)
                self.randomPeaks.append(peaks)
                allPeaks = np.r_[allPeaks, peaks]
        
        self.noiseFloor = np.median(allPeaks)           
        
    def get_varymasker(self):
        try: return self._varymasker
        except AttributeError: return None
        
    varymasker = property(get_varymasker, None, None, None)
   
    def get(self, level):
        for w in self.series:
            if w.level == level: return w
        return None
