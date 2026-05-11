import wx
from datatype import Point
from config import DefaultValueHolder
#import wx.lib.pubsub as pubsub

class KeyInteractor(object):

    KEYS = {
            wx.WXK_LEFT:    'left',
            wx.WXK_RIGHT:   'right',
            wx.WXK_DOWN:    'down',
            wx.WXK_UP:      'up',
            wx.WXK_RETURN:  'return',
            43:             'plus',
            45:             'minus', 
            61:             'plus',   # Mac            
            388:            'plus',   # numeric keypad
            390:            'minus'   # numeric keypad
 
        }

    def Install(self, presenter, view):
        self.presenter = presenter
        self.view = view

        #Events to capture
        self.view.canvas.Bind(wx.EVT_KEY_UP, self.__keyup)
        self.view.canvas.Bind(wx.EVT_KEY_DOWN, self.__keydown)
        self.view.canvas.Bind(wx.EVT_IDLE, self.__idle)

    def __idle(self, evt):
        self.presenter.update()

    def __keyup(self, evt):
        self.__dispatch('ku_', evt)

    def __keydown(self, evt):
        self.__dispatch('kd_', evt)

    def __dispatch(self, type, evt):
        keycode = evt.GetKeyCode()
        if keycode in KeyInteractor.KEYS:
            mname = type + KeyInteractor.KEYS[keycode]
            if hasattr(self, mname):
                getattr(self, mname)(evt)
        elif keycode < 256:
            if chr(keycode) in ['1', '2', '3', '4', '5']:
                keychar = chr(keycode)
                mname = type + 'number'
                if hasattr(self, mname):
                    if evt.ShiftDown():
                        polarity = Point.VALLEY
                    else:
                        polarity = Point.PEAK
                    pv = DefaultValueHolder('PhysiologyNotebook', 'peakVisibility')
                    pv.SetVariables(p1=True, p2=True, p3=True, p4=True, p5=True,
                                    n1=True, n2=True, n3=True, n4=True, n5=True)
                    pv.InitFromConfig()
                    peak_num = int(chr(keycode))
                    vis_key = 'p%d' % peak_num if polarity == Point.PEAK else 'n%d' % peak_num
                    if not getattr(pv, vis_key):
                        return
                    getattr(self, mname)((polarity, peak_num))
            else:
                mname = type + chr(keycode).lower()
                if hasattr(self, mname):
                    getattr(self, mname)()

#----------------------------------------------------------------------------

class WaveformInteractor(KeyInteractor):

    def kd_up(self, evt):
        self.presenter.current += 1

    def kd_down(self, evt):
        self.presenter.current -= 1

    def ku_return(self, evt):
        self.presenter.set_threshold()

    def kd_plus(self, evt):
        self.presenter.scale += 1

    def kd_minus(self, evt):
        self.presenter.scale -= 1

    def kd_left(self, evt):
        if evt.ShiftDown():
            move = ('index', -5)
        else:
            move = ('zc', -1)
        self.presenter.move(move)    

    def kd_right(self, evt):
        if evt.ShiftDown():
            move = ('index', 5)
        else:
            move = ('zc', 1)
        self.presenter.move(move)    

    def ku_number(self, value):
        self.presenter.toggle = value
        
    def ku_u(self):
        '''Updates guesses for waveforms further down'''
        self.presenter.update_point()

    def ku_n(self):
        self.presenter.normalized = not self.presenter.normalized

    def ku_s(self):
        self.presenter.save()

    def ku_r(self):
        dlg = wx.MessageDialog(None, 'Restoring the previous analysis will lose the current work on this data set.\nContinue?',
              'Question', wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION)
        response = dlg.ShowModal()
        if response == wx.ID_YES:
            self.presenter.restore()

    def ku_x(self):
        dlg = wx.MessageDialog(None, 'This will clear the current work on this data set.\nContinue?',
              'Question', wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION)
        response = dlg.ShowModal()
        if response == wx.ID_YES:
            self.presenter.clear_analysis()

    def ku_p(self):
        self.presenter.invert()

    def ku_t(self):
        self.presenter.estimate_threshold()

    def ku_w(self):
        self.presenter.toggle_show_work()

    def ku_l(self):
        self.presenter.toggle_show_io()

    def ku_i(self):    
        self.presenter.guess_n()

#    def ku_z(self):
#        pubsub.Publisher().sendMessage("UNDO")

#    def ku_p(self):
#        pubsub.Publisher().sendMessage("NEXT")

    def ku_d(self):
        self.presenter.delete()

    def ku_e(self):
        self.presenter.export()

#----------------------------------------------------------------------------

class AudiogramInteractor(KeyInteractor):

    def ku_s(self):
        self.presenter.save()

