#!/usr/bin/env python
# vim: set fileencoding=utf-8

"""
Created: Sat 23 Jun 2007 12:18:30 PM
Modified: Wed 13 Feb 2008 02:47:16 PM
"""

import wx
import matplotlib.ticker as ticker
from abrpanel import WaveformPlot 
from abrpanel import PointPlot
from peakdetect import find_np
from peakdetect import manual_np
from peakdetect import nzc
from datatype import Point
from datatype import ABRDataType
import numpy as np

from config import DefaultValueHolder, expected_peak_count, peak_visibility_defaults
from analysis_helpers import getindices, guess_peaks, guess_troughs, setpoint
import filter_EPL_LabVIEW_ABRIO_File as peakio
#import wx.lib.pubsub as pubsub

from datatype import ThrSource

from kpy.optimize import smooth

#----------------------------------------------------------------------------

class WaveformPresenter(object):

    defaultscale = 7
    minscale = 1
    maxscale = 15

    def __init__(self, model, view, interactor, options=None):
        self._redrawflag = True
        self._plotupdate = True
        self.view = view
        self.plots = []
        self.N = False
        self.P = False
        self.showWork = False
        self.showIO = False
        self.ann = None
        interactor.Install(self, view)
        if model is not None:
            self.load(model, options)

    def _store_saved_positions(self):
        for w in self.model.series:
            w.saved_points = {k: v.index for k, v in getattr(w, 'points', {}).items()}

    def _store_saved_positions_from_indices(self, indices, point_type):
        for k in range(len(self.model.series)):
            w = self.model.series[k]
            if not hasattr(w, 'saved_points'):
                w.saved_points = {}
            for j in range(indices.shape[1]):
                if indices[k, j] >= 0:
                    w.saved_points[(point_type, j+1)] = int(indices[k, j])

    @staticmethod
    def _time_tick_interval(window_ms):
        scale = 1
        while True:
            for limit, interval in ((32, 1), (64, 2), (80, 4), (160, 5)):
                if window_ms <= limit * scale:
                    return interval * scale
            scale *= 10

    @staticmethod
    def _configure_time_axis(axis, add_gridlines=False, window_ms=None):
        if window_ms is None:
            xmin, xmax = axis.get_xlim()
            window_ms = xmax - xmin
        major_interval = WaveformPresenter._time_tick_interval(window_ms)
        axis.xaxis.set_major_locator(ticker.MultipleLocator(major_interval))
        axis.xaxis.set_minor_locator(ticker.MultipleLocator(major_interval / 2.0))
        axis.xaxis.set_minor_formatter(ticker.NullFormatter())
        axis.tick_params(axis='x', which='minor', length=0)
        axis.xaxis.grid(False, which='both')
        axis.yaxis.grid(False, which='both')
        if add_gridlines:
            axis.xaxis.grid(True, which='major', color='0.85', linewidth=0.8)
            axis.xaxis.grid(True, which='minor', color='0.92', linewidth=0.5)

    def _add_gridlines(self):
        plotting = DefaultValueHolder("PhysiologyNotebook", "plotting")
        plotting.SetVariables(addGridlines=True)
        plotting.InitFromConfig()
        return plotting.addGridlines

    def load(self, model, options=None):
        self.options = options
        self.model = model
        if self.model.threshold is None:
            self.guess_p()
            if self.options is not None and self.options.nauto:
                self.guess_n()
        else:
            self.N = True
            self.P = True
        self.plots = [WaveformPlot(w, self.view.subplot) \
                for w in self.model.series]
        xMax = 8.5
        if self.model.dataType == ABRDataType.Clinical:
            xMax = 25
        elif self.model.dataType == ABRDataType.CFTS:
            xMax = self.model.Tmax
        self.view.subplot.axis(xmax=xMax)
        self._configure_time_axis(self.view.subplot, self._add_gridlines(), xMax)
        self.current = len(self.model.series)-1
        self.update_labels()

        # restore analysis if auto option is enabled and file exists        
        restore = DefaultValueHolder("PhysiologyNotebook", "autoRestore")
        restore.SetVariables(value=False)
        restore.InitFromConfig()
        if restore.value and peakio.have_stored_analysis((self.model)):
            self.restore()

    def delete(self):
        self.plots[self.current].remove()
        del self.plots[self.current]
        del self.model.series[self.current]
        self._plotupdate = True
        self.view.subplot.axis

    def save(self):
        if self.P:
            msg = peakio.save(self.model)
            self._store_saved_positions()
            self._redrawflag = True
            self._plotupdate = True
            self.update()
            self.view.GetTopLevelParent().SetStatusText(msg)
        else:
            msg = "Please identify P1-%d before saving" % expected_peak_count()
            wx.MessageBox(msg, "Error")
            
    def restore(self):
        restored = peakio.restore_analysis(self.model)
        msg, pind, nind, thr = restored[:4]
        source = restored[4] if len(restored) > 4 else ''
        method = restored[5] if len(restored) > 5 else ''

        self.model.restore_threshold(thr, source, method)

        has_missing_peaks = (pind == -1).any()
        has_stored_valleys = (nind >= 0).any()
        has_missing_valleys = has_stored_valleys and (nind == -1).any()

        if has_missing_peaks:
            self.guess_p()

        for k in range(pind.shape[0]):
            cur = self.model.series[k]
            for j in range(pind.shape[1]):
                if pind[k, j] >= 0:
                    self.setpoint(cur, (Point.PEAK, j + 1), pind[k, j])

        if has_missing_valleys:
            self.guess_n()

        for k in range(pind.shape[0]):
            cur = self.model.series[k]
            for j in range(nind.shape[1]):
                if nind[k, j] >= 0:
                    self.setpoint(cur, (Point.VALLEY, j + 1), nind[k, j])

        self._store_saved_positions_from_indices(pind, Point.PEAK)
        self._store_saved_positions_from_indices(nind, Point.VALLEY)

        self.view.GetTopLevelParent().SetStatusText(msg)

        self.N = True
        self._plotupdate = True

    def clear_analysis(self):
        self.model.threshold = None
        self.N = False
        for w in self.model.series:
            w.points = {}
        for p in self.plots:
            p.clear_points()


        self.guess_p()
            
        self.view.GetTopLevelParent().SetStatusText('')
        self._plotupdate = True


    def update(self):
        if self._plotupdate:
            self._plotupdate = False
            self._redrawflag = True
            
            for p in self.plots:
                p.update()
            #waveform = self.model.series[-1]
            #ymax = (((waveform.y.max()*self.scale + waveform.level)/5)+1)*5
            #self.view.subplot.axis(ymin=0, ymax=ymax, xmax=8.5)
            if self.model.dataType in (ABRDataType.Clinical, ABRDataType.CFTS):
                xMax = self.model.Tmax
            else:
                xMax = 8.5
            if self.model.dataType == ABRDataType.CFTS:
                xMax = self.model.Tmax
                
            self.view.subplot.axis(xmax=xMax)
            self._configure_time_axis(self.view.subplot, self._add_gridlines(), xMax)
            if self.ann != None:
                self.ann.remove()
                self.ann = None
                
            if not self.model.threshold is None:
                
                self.ann = self.view.subplot.annotate('', 
                                           xy=(0, self.model.threshold), xycoords='data',
                                           xytext=(-0.05*self.view.subplot.get_xlim()[1], self.model.threshold), textcoords=('data'),
                                           arrowprops=dict(facecolor='g', shrink=0.05, headlength=15))
                                           
                titleStr = "Threshold = {:.1f} dB SPL "
                if self.model.thresholdSource == ThrSource.Auto:
                    if self.model.best_fit_type == "power law (noisy)":
                        titleStr += "(auto. WARNING: noisy data, verify result.)"
                    else:
                        titleStr += "(auto)"
                else:
                   titleStr += "(manual)"
                   
                self.view.subplot.set_title(titleStr.format(self.model.threshold), loc='left')
            
            elif self.model.thresholdEstimationFailed:
                self.view.subplot.set_title("Automatic threshold estimation failed", loc='left')
            else:
                self.view.subplot.set_title('', loc='Left')
                
                
            if self.showWork or self.showIO:
                self.view.subplot.set_position([0.125, 0.5, 0.775, 0.4])
            else:
                self.view.subplot.set_position([0.125, 0.1, 0.775, 0.8])

            if self.showIO:
                self.plot_io()
            
            self.view.ccplot.set_visible(self.showWork)
            self.view.cctext.set_visible(self.showWork)
            self.view.ioplot.set_visible(self.showIO)
               
        if self._redrawflag:
            self._redrawflag = False
            self.view.canvas.draw()

    def get_current(self):
        try: return self._current
        except AttributeError: return -1

    def set_current(self, value):
        if value < 0 or value > len(self.model.series)-1: pass
        elif value == self.current: pass
        else:    
            self.iterator = None
            try: self.plots[self.current].current = False
            except IndexError: pass
            self.plots[value].current = True
            self._redrawflag = True
            self._current = value

    current = property(get_current, set_current, None, None)      

    def get_scale(self):
        try: return self._scale
        except AttributeError: return WaveformPresenter.defaultscale

    def set_scale(self, value):
        if value <= WaveformPresenter.minscale: pass
        elif value >= WaveformPresenter.maxscale: pass
        elif value == self.scale: pass
        else:
            self._scale = value
            for p in self.plots:
                p.scale = value
            self.view.set_ylabel(value)    
            self.update_labels()    
            self._plotupdate = True
            self._redrawflag = True

    scale = property(get_scale, set_scale, None, None)      

    def update_labels(self):
        label = u'uV*%d + dB SPL' % self.scale
        if self.normalized:
            self.view.set_ylabel('normalized ' + label)
        else:
            self.view.set_ylabel(label)

    def get_normalized(self):
        try: return self._normalized
        except AttributeError: return False

    def set_normalized(self, value):
        if value == self.normalized: pass
        else:    
            for p in self.plots:
                p.normalized = value
            self._normalized = value
            self.update_labels()    
            self._plotupdate = True

    normalized = property(get_normalized, set_normalized, None, None)      

    def set_threshold(self):
        self.model.set_manual_threshold(self.model.series[self.current].level)
        self._plotupdate = True

    def get_toggle(self):
        try: return self._toggle[self.current]
        except AttributeError: 
            self._toggle = {}
        except KeyError:    
            pass
        return None

    def set_toggle(self, value):
        if value is None:
            if self.toggle is not None:
                self.iterator = None
                self.plots[self.current].toggle = None
                del self._toggle[self.current]
                self._redrawflag = True
            return
        if value == self.toggle: pass
        elif value not in self.model.series[self.current].points: pass
        else:
            self.iterator = None
            self.plots[self.current].toggle = value
            self._toggle[self.current] = value
            self._redrawflag = True
        
    toggle = property(get_toggle, set_toggle, None, None)

    def point_at(self, event):
        for plot_index in self._point_hit_order():
            point_plots = list(self.plots[plot_index].points.items())
            for point, plot in reversed(point_plots):
                if plot.contains(event):
                    return plot_index, point
        return None

    def _point_hit_order(self):
        indices = list(reversed(range(len(self.plots))))
        if self.current in indices:
            indices.remove(self.current)
            indices.insert(0, self.current)
        return indices

    def select_point_hit(self, hit):
        plot_index, point = hit
        self.current = plot_index
        self.toggle = point

    def index_at_x(self, waveform, xdata):
        if xdata is None or not np.isfinite(xdata) or len(waveform.x) == 0:
            return None
        index = int(np.searchsorted(waveform.x, xdata))
        if index <= 0:
            return 0
        if index >= len(waveform.x):
            return len(waveform.x) - 1
        left = index - 1
        if abs(waveform.x[left] - xdata) <= abs(waveform.x[index] - xdata):
            return left
        return index

    def nearest_point_index(self, waveform, index, point_type):
        y = np.asarray(waveform.y)
        candidates = nzc(y if point_type == Point.PEAK else -y)
        if len(candidates) == 0:
            return index
        return int(candidates[np.argmin(np.abs(candidates - index))])

    def move_toggle_to_x(self, xdata, snap=True):
        if self.toggle is None:
            return
        waveform = self.model.series[self.current]
        index = self.index_at_x(waveform, xdata)
        if index is None:
            return
        if snap:
            index = self.nearest_point_index(waveform, index, self.toggle[0])
        self.set_toggle_index(index)

    def set_toggle_index(self, index):
        waveform = self.model.series[self.current]
        waveform.points[self.toggle].index = int(index)
        self.iterator = None
        self.plots[self.current].points[self.toggle].update()
        self._redrawflag = True

    def guess_p(self, start=None):
        self.P = True
        guess_peaks(self.model, start)

    def update_point(self):
        if self.toggle is None:
            self.view.GetTopLevelParent().SetStatusText(
                'Select a peak or trough before updating guesses.')
            return

        for i in reversed(range(self.current)):
            cur = self.model.series[i]
            try:
                index = self.model.series[i+1].points[self.toggle].index
            except KeyError:
                continue
            amplitude = self.model.series[i+1].y[index]
            if self.toggle[0] == Point.PEAK:
                index = find_np(cur.fs, cur.y, algorithm="seed", n=1,
                        seeds=[(index, amplitude)], nzc='noise_filtered')[0]
            else:    
                index = find_np(cur.fs, -cur.y, algorithm="seed", n=1,
                        seeds=[(index, amplitude)], nzc='noise_filtered')[0]
            self.setpoint(cur, self.toggle, index)
        self._plotupdate = True

    def export_waveforms(self):
        try:
            import merge_export_saved
            path, count = merge_export_saved.export_model_waveforms(self.model)
        except Exception as e:
            wx.MessageBox(str(e), 'Export Error', wx.OK | wx.ICON_ERROR)
            return
        self.view.GetTopLevelParent().SetStatusText(
            'Exported %d waveform rows to %s' % (count, path))

    def guess_n(self, start=None):
        self.N = True
        guess_troughs(self.model, start)
        self._plotupdate = True

    def invert(self):
        self.model.invert()
        self.guess_p()
        for p in self.plots:
            p.invert()
        self._plotupdate = True

    def estimate_threshold(self):
        wx.Cursor(wx.StockCursor(wx.CURSOR_WAIT))
        self.model.estimate_threshold()
        self.plot_threshold_estimation_work()
        self._plotupdate = True
        wx.Cursor(wx.StockCursor(wx.CURSOR_DEFAULT))

    def plot_threshold_estimation_work(self):
        cc, level = self.model.get_corrcoefs()
#        cc_smooth = smooth(cc, 3)

        p2 = self.model.power2_result
        sig = self.model.sigmoid_result                
        
        self.view.ccplot.plot(level, cc, 'ko')   
#        self.view.ccplot.plot(level, cc, 'ko', color='#d8dcd6')   
#        self.view.ccplot.plot(level, cc_smooth, 'ko')   
        self.view.ccplot.plot(p2.x, p2.yfit, 'r-')
        self.view.ccplot.plot(level, sig.yfit, 'b-')
        self.view.ccplot.autoscale(False)
        thr = self.model.threshold
        crit = self.model.thresholdCriterion
        self.view.ccplot.plot(np.array([level[0], thr]), np.array([crit, crit]), 'k:')
        self.view.ccplot.plot(np.array([thr, thr]), np.array([crit, self.view.ccplot.get_ylim()[0]]), 'k:')

        self.view.ccplot.set_xlim(np.min(level)-5, np.max(level)+5)

        self.view.cctext.annotate('power2\nSSE = {:.4f}\nR2 = {:.4f}\nadjR2 = {:.4f}'.format(p2.stats.sse, p2.stats.r2, p2.stats.adj_r2),
                     xy=(0,1), xycoords=('axes fraction'), 
                     color='red', va='top')

        self.view.cctext.annotate('sigmoid\nSSE = {:.4f}\nR2 = {:.4f}\nadjR2 = {:.4f}\nslope = {:.3f}'.format(sig.stats.sse, sig.stats.r2, sig.stats.adj_r2, sig.param[1]),
                     xy=(0,0), xycoords=('axes fraction'), 
                     color='blue', va='bottom')

    def plot_io(self):
        self.view.ioplot.clear()
        self.view.ioplot.set_xlabel('Level (dB SPL)')
        self.view.ioplot.set_ylabel('Amplitude (uV)')

        level = np.array([w.level for w in self.model.series])
        values = []
        for k in range(expected_peak_count()):
            label = k + 1
            if not self._point_visible(Point.PEAK, label):
                continue
            trough_visible = self._point_visible(Point.VALLEY, label)
            y = np.array([
                self._io_amplitude(w, label, trough_visible)
                for w in self.model.series
            ])
            values.extend(y[np.isfinite(y)])
            self.view.ioplot.plot(level, y, '-', color=PointPlot.COLORS[k])

        self.view.ioplot.set_xlim(np.min(level)-5, np.max(level)+5)
        finite = np.array(values)
        finite = finite[np.isfinite(finite)]
        if len(finite):
            ymin = min(0, float(np.min(finite)))
            ymax = max(0, float(np.max(finite)))
            pad = (ymax - ymin) * 0.05 or 1
            self.view.ioplot.set_ylim(ymin - pad, ymax + pad)
        else:
            self.view.ioplot.set_ylim(0, 1)

    def _point_visible(self, point_type, label):
        visible = DefaultValueHolder('PhysiologyNotebook', 'peakVisibility')
        visible.SetVariables(peak_visibility_defaults())
        visible.InitFromConfig()
        prefix = 'p' if point_type == Point.PEAK else 'n'
        return getattr(visible, '%s%d' % (prefix, label))

    def _point_amplitude(self, waveform, point):
        value = getattr(waveform, 'points', {}).get(point)
        if value is None or value.index < 0 or value.index >= len(waveform.y):
            return np.nan
        return value.amplitude

    def _io_amplitude(self, waveform, label, trough_visible):
        peak = self._point_amplitude(waveform, (Point.PEAK, label))
        if not np.isfinite(peak):
            return np.nan
        if trough_visible:
            trough = self._point_amplitude(waveform, (Point.VALLEY, label))
            if np.isfinite(trough):
                return peak - trough
        return peak
        

    def toggle_show_work(self):
        self.showWork = not self.showWork and self.model.auto_thresholded
        self.showIO = self.showIO and not self.showWork
        self._plotupdate = True

    def toggle_show_io(self):
        self.showIO = not self.showIO
        self.showWork = self.showWork and not self.showIO
        self._plotupdate = True

        
    def setpoint(self, waveform, point, index):
        setpoint(waveform, point, index)
        self._redrawflag = True

    def getindices(self, waveform, point):
        return getindices(waveform, point)

    def get_iterator(self):
        try:
            if self._iterator[self.current] is not None:
                return self._iterator[self.current]
        except AttributeError:
            self._iterator = {}
        except KeyError:
            pass
        if self.toggle is not None:
            waveform = self.model.series[self.current]
            start_index = waveform.points[self.toggle].index
            if self.toggle[0] == Point.PEAK:
                iterator = manual_np(waveform.fs, waveform.y, start_index)
            else:    
                iterator = manual_np(waveform.fs, -waveform.y, start_index)
            next(iterator)
#            iterator.next()
            self._iterator[self.current] = iterator
            return self._iterator[self.current]    
        else:
            return None

    def set_iterator(self, value):
        try:
            self._iterator[self.current] = value
        except AttributeError:
            self._iterator = {}
            self._iterator[self.current] = value

    iterator = property(get_iterator, set_iterator, None, None)

    def move(self, step):
        if self.toggle is None:
            return
        else:
            waveform = self.model.series[self.current]
            waveform.points[self.toggle].index = self.iterator.send(step)
            self.plots[self.current].points[self.toggle].update()
            self._redrawflag = True
