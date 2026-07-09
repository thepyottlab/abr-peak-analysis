#!/usr/bin/env python

from __future__ import with_statement

import re, os
import numpy
from anecs_read import ANECS
from numpy import array
from datatype import abrwaveform
from datatype import abrseries
from datatype import ABRDataType
from datatype import ABRStimPolarity

def polarity_unsupported_message(fname):
    filename = os.path.splitext(os.path.basename(fname))[0]
    return (
        "%s does not support separate analysis of condensation and "
        "rarefaction stimulus polarity sweep averages. Please disable "
        "'Analyze each stimulus polarity'."
    ) % filename


def supports_stimulus_polarities(fname):
    f, ext = os.path.splitext(fname)
    try:
        with open(fname, encoding='latin-1') as fp:
            data = fp.read()
    except OSError:
        return False

    if ext.lower() == '.csv':
        columns = [c.strip().lower() for c in data.split('\n', 1)[0].split(',')]
        return all(c in columns for c in ('c', 'r', 'avg'))
    if ext.lower() in ('.txt', '.anx'):
        return False
    if data.startswith(('[IHS ABR]', '[Eclipse ABR]', '[CUSTOM ABR]')):
        return False
    if data.startswith('[FAST ABR]'):
        alternate = re.search(r'^Stimulus\.Alternate Polarity\s*=\s*(\w+)',
                              data, re.I | re.M)
        return alternate is None or alternate.group(1).lower() == 'true'
    return data.startswith('[STANDARD ABR]') or 'DATA' in data


def get_expt_id(fname):
    folder, fn = os.path.split(fname)
    p_id = re.compile('([\w]+-[\d]+)-')
    result = p_id.search(fn)
    id = ''
    if not result is None:
        id = result.group(1)
    return id

def get_stim_freq(fname):
    p_freq = re.compile('FREQ: ([\w.]+)')
    p_wav = re.compile('FREQ: ([\s\w.:\\\\]+).wav')
    try:
        freq = 0
        with open(fname) as f:
            data = f.read()

            header, data = data.split('DATA')
            result = p_freq.search(header)
            if not result is None:
                freqStr = result.group(1)
                if freqStr in ('clicks', 'chirp', 'noise'):
                    freq = 0
                elif p_wav.search(header) != None:
                    freq = 0
                else:
                    freq = float(freqStr)

        return freq

    except (AttributeError, ValueError):
        return 0


def _format_window_bound(value):
    return '""' if value == '' else str(value)


def apply_time_range(waveforms, t_min, t_max, fs):
    """Crop waveforms to [t_min, t_max] ms and remap time to start at 0."""
    requested_min, requested_max = t_min, t_max
    t_min = float(t_min or 0)
    t_max = float(t_max or 0)
    if t_min <= 0 and t_max <= 0:
        return waveforms, None
    i_min = int(round(t_min * fs / 1000)) if t_min > 0 else 0
    i_max = int(round(t_max * fs / 1000)) if t_max > 0 else None
    if waveforms:
        file_len = min(len(w.y) for w in waveforms)
        file_max = file_len * 1000.0 / fs
        if i_min >= file_len or (i_max is not None and i_max <= i_min):
            msg = (
                "Waveform window is set to %s to %s ms, but this file spans "
                "0 to %g ms. Modify the waveform window settings."
            ) % (_format_window_bound(requested_min),
                 _format_window_bound(requested_max),
                 file_max)
            print(msg)
            raise IOError(msg)
    for w in waveforms:
        w.y = w.y[i_min:i_max if i_max is not None else len(w.y)]
        w.x = numpy.arange(len(w.y)) * 1000.0 / w.fs
    new_window = len(waveforms[0].y) * 1000.0 / fs if waveforms else None
    return waveforms, new_window


def _select_polarity(data_cond, data_rare, polarity):
    if polarity == ABRStimPolarity.Condensation:
        return data_cond
    if polarity == ABRStimPolarity.Rarefaction:
        return data_rare
    return (data_cond + data_rare) / 2.0


def _polarity_waveforms(data_sum, data_diff, levels, fs, polarity,
                        invert=False, filter=False, fdict=None,
                        t_min=0, t_max=0, exclude_levels=()):
    data_cond = data_sum + data_diff
    data_rare = data_sum - data_diff
    data = _select_polarity(data_cond, data_rare, polarity)
    if invert:
        data = -data
    excluded = set(exclude_levels or ())
    keep = [
        i for i, level in enumerate(levels)
        if level not in excluded and not (data[i] == 0).all()
    ]
    data = data[keep]
    levels = array(levels)[keep]

    waveforms = [abrwaveform(fs, w, l) for w, l in zip(data, levels)]
    if filter:
        waveforms = [w.filtered(**fdict) for w in waveforms]
    return apply_time_range(waveforms, t_min, t_max, fs)


def loadabr(fname, invert=False, filter=False, fdict=None, polarity=ABRStimPolarity.Avg, t_min=0, t_max=0):
    if polarity != ABRStimPolarity.Avg and not supports_stimulus_polarities(fname):
        raise IOError(polarity_unsupported_message(fname))

    f, ext = os.path.splitext(fname)
    if ext == '.csv':
        return loadclinicalabr(fname, invert, filter, fdict, t_min, t_max,
                               polarity)
    if ext.lower() == '.txt':
        return loadtextfile(fname, invert, filter, fdict, t_min, t_max)
    if ext == '.anx':
        return load_anecs_file(fname, invert, filter, fdict, t_min, t_max)

    p_level = re.compile(':LEVELS:([\-0-9.; Inf]+)')
    p_fs = re.compile('SAMPLE \(.sec\): ([0-9.]+)')
    p_freq = re.compile('FREQ: ([\w.]+)')
    p_wav = re.compile('FREQ: ([\s\w.:\\\\]+).wav')
    p_varywhich = re.compile(':Vary signal level: (true|false)', re.I)
    p_control = re.compile(':Control:([\-0-9; Inf NaN]+)')
    time_pattern = '([\d]{1,2}/[\d]{1,2}/[\d]{4}[\t\s]' + \
                  '[\d]{1,2}:[\d]{1,2}(:[\d]{1,2})?\s[APM]{2})'
    p_time = re.compile(time_pattern)

    abr_window = 8500 #usec

    dataType = ABRDataType.CFTS

    folder,fn=os.path.split(fname)
    isVsEP = fn.startswith('VsEP')
    if isVsEP:
        dataType = ABRDataType.VsEP

    try:
        with open(fname, encoding='latin-1') as f:
            data = f.read()

            if data.startswith('[STANDARD ABR]'):
                return load_comprehensive_cfts_data(
                    fname, invert, filter, fdict, polarity,
                    t_min=t_min, t_max=t_max)

            if data.startswith('[FAST ABR]'):
                return load_fast_abr_data(
                    fname, invert, filter, fdict, polarity,
                    t_min=t_min, t_max=t_max)

            if data.startswith(('[IHS ABR]', '[Eclipse ABR]', '[CUSTOM ABR]')):
                return load_custom_abr_data(
                    fname, invert, filter, fdict, polarity,
                    t_min=t_min, t_max=t_max)

            header, data = data.split('DATA')

            levelstring = p_level.search(header).group(1).strip(';').split(';')
            if levelstring[0] == " ":
                levels = array([0], dtype='f')
            else:
                levels = array(levelstring).astype(float)

            sampling_period = float(p_fs.search(header).group(1))
            fs = 1e6/sampling_period
            cutoff = abr_window / sampling_period

            controlStr = p_control.search(header)
            if controlStr == None:
                controlVal = float('-inf')
            else:
                controlVal = float(controlStr.group(1))

            varyWhich = p_varywhich.search(header)
            if varyWhich == None:
                varyMasker = numpy.any(levels == controlVal)
            else:
                varyMasker = varyWhich.group(1).lower() == 'false'

            data = array(data.split()).astype(float)

            cutoff = int(len(data)/len(levels) / 2);
            data = data.reshape(int(len(data) / len(levels)), len(levels)).T

            dataSum = data[:,:cutoff]
            dataDiff = data[:, cutoff:]

            # parse stimulus waveform description
            if isVsEP:
                freq = -1
            else:
                result = p_freq.search(header)
                if result is None:
                    freq = 0
                else:
                    freqStr = p_freq.search(header).group(1)
                    if freqStr in ('clicks', 'chirp', 'noise'):
                        freq = 0
                    elif p_wav.search(header) != None:
                        freq = 0
                    else:
                        freq = float(freqStr)

            waveforms, adjusted_window = _polarity_waveforms(
                dataSum, dataDiff, levels, fs, polarity, invert, filter, fdict,
                t_min, t_max, exclude_levels=[controlVal])
            if adjusted_window is not None:
                abr_window = adjusted_window
            else:
                abr_window = cutoff / fs * 1000

            # Instantiate ABR series
            series = abrseries(waveforms, freq, None, dataType, polarity, varyMasker)
            series.compute_corrcoefs()
            series.filename = fname
            series.time = p_time.search(header).group(1)
            series.Tmax = abr_window

            return series

    except (AttributeError, ValueError):
        msg = 'Could not parse %s.  Most likely not a valid ABR file.' % fname
        raise IOError(msg)


def load_comprehensive_cfts_data(fname, invert=False, filter=False, fdict=None, polarity=ABRStimPolarity.Avg, t_min=0, t_max=0):

    p_level = re.compile('Levels=([\-0-9.; Inf]+)')
    p_fs = re.compile('Response.Sampling rate \(Hz\)=([0-9.]+)')
    p_win = re.compile('Response.Window \(ms\)=([0-9.]+)')
    p_freq = re.compile('Stimulus.Frequency \(kHz\)=([0-9.]+)')
    p_wav = re.compile('Stimulus.Waveform=([\s\w]+)\n')
    p_time = re.compile('Date=([\w\d/\s:]+)\n')

    try:
        with open(fname, encoding='latin-1') as f:
            data = f.read()

            header, data = data.split('[DATA]')

            levelstring = p_level.search(header).group(1).strip(';').split(';')
            if levelstring[0] == " ":
                levels = array([0], dtype='f')
            else:
                levels = array(levelstring).astype(float)

            p_fs = re.compile('Response.Sampling rate \(Hz\)=([0-9.]+)')

            match = p_fs.search(header)
            if match == None:
                p_fs = re.compile('Response.Fs \(Hz\)=([0-9.]+)')
                match = p_fs.search(header)

            fs = float(p_fs.search(header).group(1))
            abr_window = float(p_win.search(header).group(1))

            data = data.split('\n', 2)
            data = array(data[2].split()).astype(float)

            ncol = len(levels) * 2 + 1
            data = data.reshape(int(len(data) / ncol), ncol).T

            dataSum = data[1:len(levels)+1,:]
            dataDiff = data[(len(levels) + 1):, :]

            waveShape = p_wav.search(header).group(1)

            if waveShape == 'CLICK':
                freq = 0
            else:
                freq = float(p_freq.search(header).group(1))

            dataType = ABRDataType.CFTS
            varyMasker = False

            waveforms, adjusted_window = _polarity_waveforms(
                dataSum, dataDiff, levels, fs, polarity, invert, filter, fdict,
                t_min, t_max)
            if adjusted_window is not None:
                abr_window = adjusted_window

            # Instantiate ABR series
            series = abrseries(waveforms, freq, None, dataType, polarity, varyMasker)
            series.compute_corrcoefs()
            series.filename = fname
            series.time = p_time.search(header).group(1)
            series.Tmax = abr_window

            return series

    except (AttributeError, ValueError):
        msg = 'Could not parse %s.  Most likely not a valid ABR file.' % fname
        raise IOError(msg)


def load_fast_abr_data(fname, invert=False, filter=False, fdict=None, polarity=ABRStimPolarity.Avg, t_min=0, t_max=0):

    p_level = re.compile('Levels=([\-0-9.; Inf]+)')
    p_fs = re.compile('Response.Fs \(Hz\)=([0-9.]+)')
    p_win = re.compile('Response.Window \(ms\)=([0-9.]+)')
    p_freq = re.compile('Frequency \(kHz\)=([0-9.]+)')
    p_time = re.compile('Date=([\w\d/\s:]+)\n')

    try:
        with open(fname, encoding='latin-1') as f:
            data = f.read()

            header, data = data.split('[DATA]')

            levelstring = p_level.search(header).group(1).strip(';').split(';')
            if levelstring[0] == " ":
                levels = array([0], dtype='f')
            else:
                levels = array(levelstring).astype(float)

            fs = float(p_fs.search(header).group(1))
            abr_window = float(p_win.search(header).group(1))

            data = data.split('\n', 2)
            data = array(data[2].split()).astype(float)

            ncol = len(levels) * 2 + 1
            data = data.reshape(int(len(data) / ncol), ncol).T

            dataSum = data[1:len(levels)+1,:]
            dataDiff = data[(len(levels) + 1):, :]

            freq = float(p_freq.search(header).group(1))

            dataType = ABRDataType.CFTS
            varyMasker = False

            waveforms, adjusted_window = _polarity_waveforms(
                dataSum, dataDiff, levels, fs, polarity, invert, filter, fdict,
                t_min, t_max)
            if adjusted_window is not None:
                abr_window = adjusted_window

            # Instantiate ABR series
            series = abrseries(waveforms, freq, None, dataType, polarity, varyMasker)
            series.compute_corrcoefs()
            series.filename = fname
            series.time = p_time.search(header).group(1)
            series.Tmax = abr_window

            return series

    except (AttributeError, ValueError):
        msg = 'Could not parse %s.  Most likely not a valid ABR file.' % fname
        raise IOError(msg)


def load_custom_abr_data(fname, invert=False, filter=False, fdict=None, polarity=ABRStimPolarity.Avg, t_min=0, t_max=0):
    if polarity != ABRStimPolarity.Avg:
        raise IOError(polarity_unsupported_message(fname))

    p_level = re.compile('Levels=([\-0-9.; Inf]+)')
    p_fs = re.compile('Response.Fs \(Hz\)=([0-9.]+)')
    p_win = re.compile('Response.Window \(ms\)=([0-9.]+)')
    p_freq = re.compile('Frequency \(kHz\)=([^\n\t]+)')
    p_time = re.compile('Date=([\w\d/\s:]+)\n')

    try:
        with open(fname, encoding='latin-1') as f:
            data = f.read()

            header, data = data.split('[DATA]')

            levelstring = p_level.search(header).group(1).strip(';').split(';')
            if levelstring[0] == " ":
                levels = array([0], dtype='f')
            else:
                levels = array(levelstring).astype(float)

            fs = float(p_fs.search(header).group(1))
            abr_window = float(p_win.search(header).group(1))

            data = data.split('\n', 2)
            data = array(data[2].split()).astype(float)

            ncol = len(levels)
            data = data.reshape(int(len(data) / ncol), ncol).T

            dataSum = data[0:len(levels), :]

            data = dataSum

            if invert:
                data = -data

            waveforms = [abrwaveform(fs, w, l) for w, l in zip(data, levels)]

            # Checks for an ABR I-O bug that sometimes saves zeroed waveforms
            # Also excludes controls
            for w in waveforms[:]:
                if (w.y == 0).all():
                    waveforms.remove(w)

            if filter:
                waveforms = [w.filtered(**fdict) for w in waveforms]

            freqStr = p_freq.search(header).group(1).strip()
            freq = 0 if freqStr.lower() == 'click' else float(freqStr)

            dataType = ABRDataType.CFTS
            varyMasker = False

            waveforms, adjusted_window = apply_time_range(waveforms, t_min, t_max, fs)
            if adjusted_window is not None:
                abr_window = adjusted_window

            # Instantiate ABR series
            series = abrseries(waveforms, freq, None, dataType, polarity, varyMasker)
            series.compute_corrcoefs()
            series.filename = fname
            series.time = p_time.search(header).group(1)
            series.Tmax = abr_window

            return series

    except (AttributeError, ValueError):
        msg = 'Could not parse %s.  Most likely not a valid ABR file.' % fname
        raise IOError(msg)


def loadclinicalabr(fname, invert=False, filter=False, fdict=None, t_min=0, t_max=0, polarity=ABRStimPolarity.Avg):

    try:
        with open(fname) as f:
            data = f.read()
            header, data = data.split('\n', 1)

            columns = [c.strip().lower() for c in header.split(',')]
            numCols = len(columns)

            data = array(data.replace(',', ' ').split()).astype(float)
            data = data.reshape(int(len(data)/numCols), numCols).T

            t = data[0,:]
            sampling_period = t[1] - t[0]
            fs = 1/sampling_period

            if all(c in columns for c in ('c', 'r', 'avg')):
                column = {
                    ABRStimPolarity.Avg: 'avg',
                    ABRStimPolarity.Condensation: 'c',
                    ABRStimPolarity.Rarefaction: 'r',
                }[polarity]
                data_selected = 1e6 * data[[columns.index(column)], :]
                levels = [0]
                if invert:
                    data_selected = -data_selected
                waveforms = [
                    abrwaveform(fs, w, l)
                    for w, l in zip(data_selected, levels)
                ]
                if filter:
                    waveforms = [w.filtered(**fdict) for w in waveforms]
                waveforms, adjusted_window = apply_time_range(
                    waveforms, t_min, t_max, fs)
            else:
                if polarity != ABRStimPolarity.Avg:
                    raise IOError(polarity_unsupported_message(fname))
                if numCols > 4:
                    data = data[3:5, :]
                else:
                    data = data[1:, :]

                levels = list(range(len(data)))
                data = 1e6 * data

                if invert:
                    data = -data

#                waveforms = [abrwaveform(fs, data(1,:), 0), abrwaveform(fs, data(2,:), 1), abrwaveform(fs, data(3,:), 2)]
                waveforms = [abrwaveform(fs, w, l) for w, l in zip(data, levels)]

                #Checks for a ABR I-O bug that sometimes saves zeroed waveforms
                for w in waveforms[:]:
                    if (w.y==0).all():
                        waveforms.remove(w)

                if filter:
                    waveforms = [w.filtered(**fdict) for w in waveforms]

                waveforms, adjusted_window = apply_time_range(waveforms, t_min, t_max, fs)

            if adjusted_window is not None:
                abr_window = adjusted_window
            else:
                abr_window = max(t) * 1000

            freq = -1

            series = abrseries(waveforms, freq, None, ABRDataType.Clinical, polarity)
            series.filename = fname
            series.time = t
            series.Tmax = abr_window
            return series

    except (AttributeError, ValueError):
        msg = 'Could not parse %s.  Most likely not a valid CSV file.' % fname
        raise IOError(msg)

def loadtextfile(fname, invert=False, filter=False, fdict=None, t_min=0, t_max=0):

#    p_level = re.compile(':LEVELS:([\-0-9;]+)')
#    p_fs = re.compile('SAMPLE \(.sec\): ([0-9]+)')
#    p_freq = re.compile('FREQ: ([\w.]+)')

    try:
        with open(fname) as f:
            data = f.read()

            if data.startswith('Identifier:'):
                return load_caspary_text_file(fname, invert, filter, fdict, t_min, t_max)

            header, data = data.split('\n', 1)

            cols = header.split('\t')
            numCols = len(cols)

#            levelString = re.findall('kHz([0-9]+)dB', header)
            levelString = re.findall('([0-9]+)[\s]+dBSPL', header)
            if not levelString:
                levelString = re.findall('kHz([0-9]+)dB', header)
            levels = array(levelString).astype(float)

            data = array(data.replace(',', ' ').split()).astype(float)
            nrows = (int)(len(data)/numCols)
            data = data.reshape(nrows, numCols).T

            t = data[0,:]
            data = 1e6 * data[1:, :]

            sampling_period = t[1] - t[0]
            fs = 1/sampling_period

            if invert:
                data = -data

            waveforms = [abrwaveform(fs, w, l) for w, l in zip(data, levels)]

            if filter:
                waveforms = [w.filtered(**fdict) for w in waveforms]

            waveforms, adjusted_window = apply_time_range(waveforms, t_min, t_max, fs)
            if adjusted_window is not None:
                abr_window = adjusted_window
            else:
                abr_window = max(t) * 1000

            #freq = float(re.search('([0-9]+)kHz', header).group(1))
            freq = 0
            series = abrseries(waveforms, freq, None, ABRDataType.CFTS, ABRStimPolarity.Avg)
            series.compute_corrcoefs()
            series.filename = fname

            #Temporary -- add code to convert to actual date/time object
            series.time = t
            series.Tmax = abr_window
            return series

    except (AttributeError, ValueError):
        msg = 'Could not parse %s.  Most likely not a valid CSV file.' % fname
        raise IOError(msg)

def load_caspary_text_file(fname, invert=False, filter=False, fdict=None, t_min=0, t_max=0):

    try:
        with open(fname) as f:
            data = f.read()

            levelStr = re.compile('Intensity:([\d,]+)').search(data).group(1)
            levelList = re.compile(',+([\d]+)').findall(levelStr)
            levels = [float(x) for x in levelList]

            dtStr = re.compile('Smp. Period:([\d\.,]+)').search(data).group(1)
            dtList = re.compile(',+([\d\.]+)').findall(dtStr)
            dt = [float(x) for x in dtList]

            freqStr = re.compile('Stim. Freq.([\d,]+)').search(data).group(1)
            freqList = re.compile(',+([\d]+)').findall(freqStr)
            freqs = [float(x) for x in freqList]

            zeroStr = re.compile('Zero Position:([\d,]+)').search(data).group(1)
            zeroList = re.compile(',+([\d]+)').findall(zeroStr)
            zeroPositions = [float(x) for x in zeroList]
            izero = int(zeroPositions[0])

            dataStr = data.split('Data Pnt')[1].split('\n', 1)[1]
            a = array(dataStr.replace(',', ' ').split()).astype(float)
            numCols = len(levels) * 6 + 1
            y = a.reshape(int(len(a) / numCols), numCols).T

            t = (y[0,:] - y[0,0]) * dt[0] * 1e-6
            t0 = t[izero]

            istart = (abs(y[1,:])!=0).argmax()
            istart = izero
            y = y[:, istart:]
            t = t[istart:] - t0

            data = y[2::6, :]

            fs = 1e6 / dt[0]

            if invert:
                data = -data

            waveforms = [abrwaveform(fs, w, l) for w, l in zip(data, levels)]

            if filter:
                waveforms = [w.filtered(**fdict) for w in waveforms]

            waveforms, adjusted_window = apply_time_range(waveforms, t_min, t_max, fs)
            if adjusted_window is not None:
                abr_window = adjusted_window
            else:
                abr_window = max(t) * 1000

            series = abrseries(waveforms, freqs[0] / 1000, None, ABRDataType.CFTS, ABRStimPolarity.Avg)
            series.compute_corrcoefs()
            series.filename = fname

            #Temporary -- add code to convert to actual date/time object
            series.time = t
            series.Tmax = abr_window
            return series

    except (AttributeError, ValueError):
        msg = 'Could not parse %s.  Most likely not a valid CSV file.' % fname
        raise IOError(msg)

def load_anecs_file(fname, invert=False, filter=False, fdict=None, t_min = 0, t_max = 0):

    try:
        anecs = ANECS(fname)
        levels = anecs.inner.vals

        ichan = int(anecs.inner.channels)
        freq = anecs.stim.channels[ichan-1].param[0].value

        fs = anecs.resp.samplingRate * 1000
        t = anecs.waveforms.time_s
        data = anecs.waveforms.data_uV

        if invert:
            data = -data

        waveforms = [abrwaveform(fs, w, l) for w, l in zip(data, levels)]

        if filter:
            waveforms = [w.filtered(**fdict) for w in waveforms]

        waveforms, adjusted_window = apply_time_range(waveforms, t_min, t_max, fs)
        if adjusted_window is not None:
            abr_window = adjusted_window
        else:
            abr_window = max(t) * 1000

        series = abrseries(waveforms, freq, None, ABRDataType.CFTS, ABRStimPolarity.Avg)
        series.compute_corrcoefs()
        series.filename = fname

        #Temporary -- add code to convert to actual date/time object
        series.time = t
        series.Tmax = abr_window
        return series

    except (AttributeError, ValueError):
        msg = 'Could not parse %s.  Most likely not a valid ANECS data file.' % fname
        raise IOError(msg)
