import wx
from datatype import Point
from config import DefaultValueHolder, MAX_PEAKS, peak_visibility_defaults
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
    MENU_KEYCODES = {wx.WXK_RETURN, 43, 45, 61, 388, 390}
    MENU_KEYCHARS = set('deilnprstuwx') | {str(i) for i in range(1, MAX_PEAKS + 1)}

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
        for modifier in ('CmdDown', 'ControlDown', 'AltDown', 'MetaDown'):
            if getattr(evt, modifier, lambda: False)():
                return
        keycode = evt.GetKeyCode()
        if self.__menu_owns_key(keycode):
            return
        if keycode in KeyInteractor.KEYS:
            mname = type + KeyInteractor.KEYS[keycode]
            if hasattr(self, mname):
                getattr(self, mname)(evt)
        elif keycode < 256:
            if chr(keycode) in [str(i) for i in range(1, MAX_PEAKS + 1)]:
                keychar = chr(keycode)
                mname = type + 'number'
                if hasattr(self, mname):
                    if evt.ShiftDown():
                        polarity = Point.VALLEY
                    else:
                        polarity = Point.PEAK
                    pv = DefaultValueHolder('PhysiologyNotebook', 'peakVisibility')
                    pv.SetVariables(peak_visibility_defaults())
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

    def __menu_owns_key(self, keycode):
        if keycode in KeyInteractor.MENU_KEYCODES:
            return True
        if keycode >= 256:
            return False
        return chr(keycode).lower() in KeyInteractor.MENU_KEYCHARS

#----------------------------------------------------------------------------

class WaveformInteractor(KeyInteractor):

    def Install(self, presenter, view):
        super(WaveformInteractor, self).Install(presenter, view)
        self._dragging_point = False
        self._hand_cursor = False
        self.view.canvas.mpl_connect('button_press_event', self._button_press)
        self.view.canvas.mpl_connect('motion_notify_event', self._motion)
        self.view.canvas.mpl_connect('button_release_event', self._button_release)
        self.view.canvas.mpl_connect('figure_leave_event', self._leave)

    def _leftdown(self, evt):
        self.presenter.toggle = None
        evt.Skip()

    def _button_press(self, event):
        if not self._left_button(event):
            return
        self.view.canvas.SetFocus()
        hit = self.presenter.point_at(event)
        if hit is None:
            self.presenter.toggle = None
            self._dragging_point = False
            self._set_hand_cursor(False)
            return
        self.presenter.select_point_hit(hit)
        self._dragging_point = True
        self._set_hand_cursor(True)

    def _motion(self, event):
        if self._dragging_point:
            if event.inaxes == self.view.subplot:
                self.presenter.move_toggle_to_x(event.xdata,
                                                snap=not self._shift_down(event))
            self._set_hand_cursor(True)
            return
        self._update_cursor(event)

    def _button_release(self, event):
        if not self._left_button(event):
            return
        self._dragging_point = False
        self._update_cursor(event)

    def _leave(self, event):
        if not self._dragging_point:
            self._set_hand_cursor(False)

    def _update_cursor(self, event):
        self._set_hand_cursor(self.presenter.point_at(event) is not None)

    def _set_hand_cursor(self, hand):
        if hand == self._hand_cursor:
            return
        cursor = wx.CURSOR_HAND if hand else wx.CURSOR_DEFAULT
        self.view.canvas.SetCursor(wx.StockCursor(cursor))
        self._hand_cursor = hand

    def _left_button(self, event):
        button = getattr(event, 'button', None)
        return button == 1 or getattr(button, 'name', None) == 'LEFT'

    def _shift_down(self, event):
        gui_event = getattr(event, 'guiEvent', None)
        if gui_event is not None and hasattr(gui_event, 'ShiftDown'):
            return gui_event.ShiftDown()
        key = getattr(event, 'key', None)
        return isinstance(key, str) and 'shift' in key.lower()

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
            move = ('index', -1)
        else:
            move = ('zc', -1)
        self.presenter.move(move)    

    def kd_right(self, evt):
        if evt.ShiftDown():
            move = ('index', 1)
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

    def ku_e(self):
        self.presenter.export_waveforms()

    def ku_i(self):    
        self.presenter.guess_n()

#    def ku_z(self):
#        pubsub.Publisher().sendMessage("UNDO")

#    def ku_p(self):
#        pubsub.Publisher().sendMessage("NEXT")

    def ku_d(self):
        self.presenter.delete()

#----------------------------------------------------------------------------

class AudiogramInteractor(KeyInteractor):

    def ku_s(self):
        self.presenter.save()
