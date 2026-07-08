import operator

from numpy import array, concatenate

from config import DefaultValueHolder, expected_peak_count
from datafile import loadabr
from datatype import ABRStimPolarity, Point, waveformpoint
from peakdetect import find_np


def load_model(fname, invert=False, polarity=ABRStimPolarity.Avg, useNoiseFloor=False):
    filt = DefaultValueHolder("PhysiologyNotebook", "filter")
    filt.SetVariables(ftype="butterworth", fl=10000, fh=200, N=1)
    filt.InitFromConfig()

    time_min = DefaultValueHolder("PhysiologyNotebook", "timeRangeMin")
    time_min.SetVariables(value=float(0))
    time_min.InitFromConfig()

    time_max = DefaultValueHolder("PhysiologyNotebook", "timeRangeMax")
    time_max.SetVariables(value="")
    time_max.InitFromConfig()

    fdict = {'ftype': filt.ftype, 'W': (filt.fh, filt.fl), 'N': filt.N}
    do_filter = filt.ftype != 'None'
    noise_floor = getattr(useNoiseFloor, 'value', useNoiseFloor)
    model = loadabr(fname, filter=do_filter, fdict=fdict, invert=invert,
                    polarity=polarity, noiseFloor=noise_floor,
                    t_min=time_min.value, t_max=time_max.value)
    model.filter_settings = fdict
    return model


def setpoint(waveform, point, index):
    if not hasattr(waveform, 'points'):
        setattr(waveform, 'points', {})
    try:
        waveform.points[point].index = index
    except KeyError:
        waveform.points[point] = waveformpoint(waveform, index, point)


def getindices(waveform, point):
    points = [(v.point[1], v.index) for v in
              waveform.points.values() if v.point[0] == point]
    points.sort(key=operator.itemgetter(0))
    return [p for i, p in points]


def guess_peaks(model, start=None):
    minlatency = DefaultValueHolder('PhysiologyNotebook', 'minlatency')
    minlatency.SetVariables(value=float(0.9))
    minlatency.InitFromConfig()

    if start is None:
        start = len(model.series)
    peak_count = expected_peak_count()

    for i in reversed(range(start)):
        cur = model.series[i]
        if i == len(model.series) - 1:
            p_indices = find_np(cur.fs, cur.y, min_latency=minlatency.value, n=peak_count)
        else:
            prev = model.series[i + 1]
            i_peaks = getindices(prev, Point.PEAK)
            a_peaks = prev.y[i_peaks]
            p_indices = find_np(cur.fs, cur.y, algorithm='seed',
                                seeds=list(zip(i_peaks, a_peaks)),
                                nzc='noise_filtered', n=peak_count)

        for j, v in enumerate(p_indices):
            setpoint(cur, (Point.PEAK, j + 1), v)


def guess_troughs(model, start=None):
    if start is None:
        start = len(model.series)
    for i in reversed(range(start)):
        cur = model.series[i]
        p_indices = getindices(cur, Point.PEAK)
        bounds = concatenate((p_indices, array([len(cur.y) - 1])))
        try:
            prev = model.series[i + 1]
            i_valleys = getindices(prev, Point.VALLEY)
            a_valleys = prev.y[i_valleys]
            n_indices = find_np(cur.fs, -cur.y, algorithm='bound',
                                seeds=list(zip(i_valleys, a_valleys)),
                                bounds=bounds, bounded_algorithm='seed',
                                dev=0.5, n=len(p_indices))
        except IndexError:
            n_indices = find_np(cur.fs, -cur.y, bounds=bounds,
                                algorithm='bound', bounded_algorithm='y_fun',
                                dev=0.5, n=len(p_indices))
        for j, v in enumerate(n_indices):
            setpoint(cur, (Point.VALLEY, j + 1), v)


def visible_troughs_enabled():
    visible = DefaultValueHolder('PhysiologyNotebook', 'peakVisibility')
    from config import peak_visibility_defaults
    visible.SetVariables(peak_visibility_defaults())
    visible.InitFromConfig()
    return any(getattr(visible, 'n%d' % i) for i in range(1, expected_peak_count() + 1))
