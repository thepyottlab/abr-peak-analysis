import re, os, string, sys
import configparser
import wx, wx.aui, wx.adv
import wx.lib.filebrowsebutton as filebrowse
#import wx.lib.pubsub as pubsub
import wx.html
import wx.grid
import webbrowser

from control import MatplotlibPanel, LazyTree, MPLAudiogram
from AudiogramPresenter import AudiogramPresenter
from WaveformPresenter import WaveformPresenter
from interactor import KeyInteractor, WaveformInteractor, AudiogramInteractor
from analysis_helpers import load_model
from source_files import SOURCE_WILDCARD, is_source_file

from config import DefaultValueHolder, MAX_PEAKS, expected_peak_count, peak_visibility_defaults
import filter_EPL_LabVIEW_ABRIO_File as peakio
from datatype import GetABRDataType, ABRDataType, ABRStimPolarity
from datafile import get_expt_id, get_stim_freq

from audiogram import load_audiogram

import warnings; warnings.simplefilter('ignore', DeprecationWarning)

def listdir(dir, match, incdirs=False):
    if incdirs:
        return [os.path.join(dir, f) for f in dircache.listdir(dir) if \
                match(f) or os.path.isdir(os.path.join(dir, f))]
    else:
        return [os.path.join(dir, f) for f in dircache.listdir(dir) if \
                match(f)]

#----------------------------------------------------------------------------

def loadmodel(fname, invert, polarity, useNoiseFloor):
    return load_model(fname, invert, polarity, useNoiseFloor)

#----------------------------------------------------------------------------

class PersistentFrame(wx.Frame):

    def __init__(self, name=None, parent=None, *args, **kwargs): 

        self.options = DefaultValueHolder('PhysiologyNotebook', name)
        self.options.SetVariables(width=600,height=800,x=0,y=0,maximized=0)
        self.options.InitFromConfig()

        size = (self.options.width, self.options.height)
        pos = (self.options.x, self.options.y)
        wx.Frame.__init__(self, parent, size=size, pos=pos, *args, **kwargs)
        if self.options.maximized:
            self.Maximize()
        self.Bind(wx.EVT_CLOSE, self.OnQuit)

    def OnQuit(self, evt):
        dlg = wx.MessageDialog(None, 'Are you sure you want to quit?',
              'Question', wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION)
        response = dlg.ShowModal()
        if response == wx.ID_YES:
            try:
                maximized = self.IsMaximized()
                #We want the pos and size of the unmaximized window
                self.Maximize(False)
                fpos = self.GetPosition()
                fsize = self.GetSize()
                self.options.SetVariables(width=fsize[0], height=fsize[1],
                        x=fpos[0], y=fpos[1], maximized=int(maximized))
                self.options.UpdateConfig()
            except Exception as e:
                print(f"An unexpected error occurred: {e}")
        
            self.Destroy()

#        evt.Skip()

#----------------------------------------------------------------------------

class PhysiologyNotebook(wx.aui.AuiNotebook):

    def __init__(self, parent, id=wx.ID_ANY, pos=wx.DefaultPosition,
            size=wx.DefaultSize, style=wx.aui.AUI_NB_DEFAULT_STYLE, **kwargs):

        wx.aui.AuiNotebook.__init__(self, parent, id, pos, size, style,
                **kwargs)

        self._resized = False

        dt = PhysiologyNbFileDropTarget(self)
        self.SetDropTarget(dt)
        self.Bind(wx.EVT_SIZE, self.OnSize)
        self.Bind(wx.EVT_IDLE, self.OnIdle)
        self.Bind(wx.aui.EVT_AUINOTEBOOK_PAGE_CLOSED, self.OnPageClosed)
        
    def __getitem__(self, index):
        ''' More pythonic way to get a specific page, also useful for iterating
            over all pages, e.g: for page in notebook: ... '''
        if index < self.GetPageCount():
            return self.GetPage(index)
        else:
            raise IndexError

    def is_audiogram_series(self, data):
        if len(data) < 2:
            return False
            
        expt_id = get_expt_id(data[0])
        for d in data:
            if GetABRDataType(d) != ABRDataType.CFTS:
                return False
            if get_expt_id(d) != expt_id:
                return False
            if get_stim_freq(d) <= 0:
                return False
                
        return True

    def load_normal(self, data, invert=False):
        showallpol = DefaultValueHolder('PhysiologyNotebook','showallpol')
        showallpol.SetVariables(value=False)
        showallpol.InitFromConfig()
        useNoiseFloor = DefaultValueHolder('PhysiologyNotebook','useNoiseFloor')
        useNoiseFloor.SetVariables(value=False)
        useNoiseFloor.InitFromConfig()

        wx.Cursor(wx.StockCursor(wx.CURSOR_WAIT))
        for d in data:
            dtype = GetABRDataType(d)
            if dtype == ABRDataType.Clinical or not showallpol.value:
                self.loadser(d, invert, ABRStimPolarity.Avg, useNoiseFloor.value)
            else:
                pol = [ABRStimPolarity.Avg, ABRStimPolarity.Condensation, ABRStimPolarity.Rarefaction]
                for p in pol:               
                    self.loadser(d, invert, p)
        wx.Cursor(wx.StockCursor(wx.CURSOR_DEFAULT))

    def load(self, data, invert=False):
        if self.is_audiogram_series(data):
            self.load_freq_series(data)
        else:
            self.load_normal(data, invert)
            
    def loadfiles(self, datafiles, invert=False):
        for df in datafiles:
            self.load([df], invert)
            
    def loadser(self, fname, invert=False, polarity=ABRStimPolarity.Avg, useNoiseFloor=False):
        try:
            model = loadmodel(fname, invert, polarity, useNoiseFloor)
            view = MatplotlibPanel(self, 'Time (msec)', 'Amplitude (uV)', 
                    figsize=(9,8))

            view.presenter = WaveformPresenter(model, view, WaveformInteractor())
            if model.dataType == ABRDataType.CFTS:
                name = '%s %.2f kHz' % (os.path.split(fname)[1], model.freq)
            else:
                name = '%s' % (os.path.split(fname)[1])
            
            if model.stimPol == ABRStimPolarity.Condensation:
                name = name + " (Cond)"
            if model.stimPol == ABRStimPolarity.Rarefaction:
                name = name + " (Rare)"
                
                
            self.AddPage(view, name, select=True)
            self.GetPage(self.GetSelection()).canvas.Resize()
            self.GetTopLevelParent().SetStatusText('Loaded file %s' % name) 
            
        except OSError as e:
#            print(format(e))           
            dlg = wx.MessageDialog(self, format(e), 'File Error', wx.OK | wx.ICON_ERROR)
            dlg.ShowModal()
            dlg.Destroy()
        except IOError as e:
            dlg = wx.MessageDialog(self, e.message, 'File Error',
                    wx.OK | wx.ICON_ERROR)
            dlg.ShowModal()
            dlg.Destroy()
            

    def load_freq_series(self, data):
        wx.Cursor(wx.StockCursor(wx.CURSOR_WAIT))
        try:
            model = load_audiogram(data)
            view = MPLAudiogram(self, 'Frequency (kHz)', 'Threshold (dB SPL)', 
                    figsize=(9,8))

            AudiogramPresenter(model, view, AudiogramInteractor())
            name = get_expt_id(data[0]) + ": audio"
                
            self.AddPage(view, name, select=True)
            self.GetTopLevelParent().SetStatusText('Loaded file %s' % name) 
        except IOError as e:
            dlg = wx.MessageDialog(self, e.message, 'File Error',
                    wx.OK | wx.ICON_ERROR)
            dlg.ShowModal()
            dlg.Destroy()
        wx.Cursor(wx.StockCursor(wx.CURSOR_DEFAULT))

    def OnSize(self, evt):
        self._resized = True
        
    def OnIdle(self, evt):
        if self._resized and self.PageCount > 0:
            self._resized = False
            for page in self:
                page.canvas.Resize()
#            w = self.GetPage(0)
#            w.canvas.Resize()

    def OnPageClosed(self, evt):
        pass
        
            
#----------------------------------------------------------------------------

class PhysiologyNbFileDropTarget(wx.FileDropTarget):

    def __init__(self, parent):
        wx.FileDropTarget.__init__(self)
        self.parent = parent

    def OnDropFiles(self, x, y, filenames):
        self.parent.load(filenames, self.invert)
        return True

    def OnEnter(self, x, y, meta):
        if meta == wx.DragCopy:
            self.invert = True
        else:
            self.invert = False
        return wx.DragMove    

#----------------------------------------------------------------------------

class ConvertFilesDialog(wx.Dialog):
    TEMPLATE_INITIAL_ROWS = 100
    TEMPLATE_TRAILING_ROWS = 20
    TEMPLATE_UNDO_LIMIT_BYTES = 100 * 1024 * 1024

    def __init__(self, parent, title, wildcard, default_folder,
                 convert_file, source_name, show_eclipse_options=False,
                 channel_loader=None, template_reader=None,
                 template_writer=None, template_fields=None,
                 timestamp_loader=None, eclipse_id_matcher=None):
        wx.Dialog.__init__(self, parent, title=title,
                           size=(820, 720 if show_eclipse_options else 420))
        self.paths = []
        self.default_folder = default_folder if os.path.isdir(default_folder) else os.getcwd()
        self.convert_file = convert_file
        self.source_name = source_name
        self.show_eclipse_options = show_eclipse_options
        self.channel_loader = channel_loader
        self.template_reader = template_reader
        self.template_writer = template_writer
        self.template_fields = template_fields or []
        self.timestamp_loader = timestamp_loader
        self.eclipse_id_matcher = eclipse_id_matcher
        self.channel_choices = []
        self.timestamps_by_path = {}
        self.template_undo = []
        self.template_redo = []
        self.template_undo_bytes = 0
        self.template_redo_bytes = 0
        self.suppress_template_undo = False
        self.converted = False

        sizer = wx.BoxSizer(wx.VERTICAL)

        if show_eclipse_options:
            self.mode = wx.RadioBox(
                self, wx.ID_ANY, 'Conversion Mode',
                choices=['Convert All', 'Convert from Template'],
                majorDimension=2,
                style=wx.RA_SPECIFY_COLS,
            )
            sizer.Add(self.mode, 0, wx.EXPAND | wx.ALL, 5)
        else:
            self.mode = None

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        add_files = wx.Button(self, wx.ID_ANY, 'Add Files')
        clear = wx.Button(self, wx.ID_ANY, 'Clear')
        buttons.Add(add_files, 0, wx.ALL, 5)
        buttons.Add(clear, 0, wx.ALL, 5)
        sizer.Add(buttons, 0, wx.ALL, 0)

        self.list = wx.ListCtrl(self, wx.ID_ANY, style=wx.LC_REPORT)
        self.list.InsertColumn(0, 'File')
        self.list.InsertColumn(1, 'Folder')
        self.list.SetColumnWidth(0, 240)
        self.list.SetColumnWidth(1, 420)
        sizer.Add(self.list, 1, wx.EXPAND | wx.ALL, 5)

        if show_eclipse_options:
            self.channels_panel = wx.Panel(self, wx.ID_ANY)
            channels = wx.StaticBoxSizer(
                wx.StaticBox(self.channels_panel, wx.ID_ANY, 'Select Channels'),
                wx.VERTICAL)
            channel_buttons = wx.BoxSizer(wx.HORIZONTAL)
            self.channel_all = wx.Button(self.channels_panel, wx.ID_ANY, 'All')
            self.channel_none = wx.Button(self.channels_panel, wx.ID_ANY, 'None')
            channel_buttons.Add(self.channel_all, 0, wx.ALL, 5)
            channel_buttons.Add(self.channel_none, 0, wx.ALL, 5)
            channels.Add(channel_buttons, 0, wx.ALL, 0)
            self.channel_list = wx.CheckListBox(
                self.channels_panel, wx.ID_ANY, choices=[], size=(-1, 100))
            self.channel_list.Disable()
            self.channel_all.Disable()
            self.channel_none.Disable()
            channels.Add(self.channel_list, 1, wx.EXPAND | wx.ALL, 5)
            self.channels_panel.SetSizer(channels)
            sizer.Add(self.channels_panel, 0, wx.EXPAND | wx.ALL, 5)

            self.template_panel = wx.Panel(self, wx.ID_ANY)
            template = wx.StaticBoxSizer(
                wx.StaticBox(self.template_panel, wx.ID_ANY, 'Template'),
                wx.VERTICAL)
            template_buttons = wx.BoxSizer(wx.HORIZONTAL)
            self.template_clear = wx.Button(self.template_panel, wx.ID_ANY, 'Clear All')
            self.template_import = wx.Button(self.template_panel, wx.ID_ANY, 'Import Template')
            self.template_export = wx.Button(self.template_panel, wx.ID_ANY, 'Export Template')
            for button in (self.template_clear, self.template_import,
                           self.template_export):
                template_buttons.Add(button, 0, wx.ALL, 5)
            template.Add(template_buttons, 0, wx.ALL, 0)

            self.template_grid = wx.grid.Grid(self.template_panel, wx.ID_ANY,
                                              size=(-1, 280))
            self.template_grid.CreateGrid(self.TEMPLATE_INITIAL_ROWS,
                                          len(self.template_fields))
            for col, label in enumerate(self.template_fields):
                self.template_grid.SetColLabelValue(col, label)
                self.template_grid.SetColSize(col, 150)
            self.fit_template_columns()
            self.set_template_channel_editors()
            self.template_grid.Bind(wx.EVT_KEY_DOWN, self.on_template_key_down)
            self.template_grid.Bind(wx.grid.EVT_GRID_CELL_CHANGING,
                                    self.on_template_cell_changing)
            self.template_grid.Bind(wx.grid.EVT_GRID_CELL_CHANGED,
                                    self.on_template_cell_changed)
            self.template_grid.Bind(wx.EVT_SIZE, self.on_template_grid_size)
            self.template_grid.Bind(wx.grid.EVT_GRID_SELECT_CELL,
                                    self.on_template_select_cell)
            self.template_grid.Bind(wx.grid.EVT_GRID_CELL_LEFT_DCLICK,
                                    self.on_template_cell_left_dclick)
            template.Add(self.template_grid, 1, wx.EXPAND | wx.ALL, 5)
            self.template_panel.SetSizer(template)
            self.template_panel.Hide()
            sizer.Add(self.template_panel, 0, wx.EXPAND | wx.ALL, 5)
        else:
            self.channels_panel = None
            self.channel_list = None
            self.channel_all = None
            self.channel_none = None
            self.template_panel = None
            self.template_grid = None

        out = wx.StaticBoxSizer(wx.StaticBox(self, wx.ID_ANY, 'Output Folder'), wx.HORIZONTAL)
        self.output = wx.TextCtrl(self, wx.ID_ANY, self.default_folder)
        browse = wx.Button(self, wx.ID_ANY, 'Browse')
        out.Add(self.output, 1, wx.EXPAND | wx.ALL, 5)
        out.Add(browse, 0, wx.ALL, 5)
        sizer.Add(out, 0, wx.EXPAND | wx.ALL, 5)

        actions = wx.BoxSizer(wx.HORIZONTAL)
        convert = wx.Button(self, wx.ID_ANY, 'Convert')
        cancel = wx.Button(self, wx.ID_CANCEL)
        actions.AddStretchSpacer()
        actions.Add(convert, 0, wx.ALL, 5)
        actions.Add(cancel, 0, wx.ALL, 5)
        sizer.Add(actions, 0, wx.EXPAND | wx.ALL, 5)

        self.SetSizer(sizer)
        self.wildcard = wildcard
        add_files.Bind(wx.EVT_BUTTON, self.on_add_files)
        clear.Bind(wx.EVT_BUTTON, self.on_clear)
        browse.Bind(wx.EVT_BUTTON, self.on_browse_output)
        convert.Bind(wx.EVT_BUTTON, self.on_convert)
        if self.mode is not None:
            self.mode.Bind(wx.EVT_RADIOBOX, self.on_mode)
        if self.channel_list is not None:
            self.channel_all.Bind(wx.EVT_BUTTON, self.on_select_all_channels)
            self.channel_none.Bind(wx.EVT_BUTTON, self.on_select_no_channels)
            self.template_clear.Bind(wx.EVT_BUTTON, self.on_template_clear)
            self.template_import.Bind(wx.EVT_BUTTON, self.on_template_import)
            self.template_export.Bind(wx.EVT_BUTTON, self.on_template_export)

    def on_add_files(self, evt):
        dlg = wx.FileDialog(
            self,
            'Choose files to convert:',
            defaultDir=self.default_folder,
            wildcard=self.wildcard,
            style=wx.FD_OPEN | wx.FD_MULTIPLE | wx.FD_FILE_MUST_EXIST,
        )
        try:
            if dlg.ShowModal() == wx.ID_OK:
                paths = dlg.GetPaths()
                self.add_paths(paths)
                if paths:
                    self.default_folder = os.path.dirname(paths[0])
                    self.output.SetValue(self.default_folder)
        finally:
            dlg.Destroy()

    def on_clear(self, evt):
        self.paths = []
        self.refresh_list()

    def on_browse_output(self, evt):
        current = self.output.GetValue()
        default = current if os.path.isdir(current) else self.default_folder
        dlg = wx.DirDialog(self, 'Choose an output folder:',
                           defaultPath=default,
                           style=wx.DD_DIR_MUST_EXIST | wx.DD_CHANGE_DIR)
        try:
            if dlg.ShowModal() == wx.ID_OK:
                self.output.SetValue(dlg.GetPath())
        finally:
            dlg.Destroy()

    def on_mode(self, evt):
        template_mode = self.template_mode()
        if self.channels_panel is not None:
            self.channels_panel.Show(not template_mode)
        if self.template_panel is not None:
            self.template_panel.Show(template_mode)
        self.Layout()
        if template_mode:
            wx.CallAfter(self.fit_template_columns)

    def on_select_all_channels(self, evt):
        self.check_all_channels(True)

    def on_select_no_channels(self, evt):
        self.check_all_channels(False)

    def on_template_import(self, evt):
        dlg = wx.FileDialog(
            self,
            'Import template:',
            wildcard='CSV template files (*.csv)|*.csv|All files|*',
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        )
        try:
            if dlg.ShowModal() == wx.ID_OK:
                self.push_template_undo()
                self.set_template_rows(self.template_reader(dlg.GetPath()))
        except Exception as e:
            wx.MessageBox(str(e), 'Conversion Error', wx.OK | wx.ICON_ERROR)
        finally:
            dlg.Destroy()

    def on_template_export(self, evt):
        dlg = wx.FileDialog(
            self,
            'Export template:',
            defaultFile='template.csv',
            wildcard='CSV template files (*.csv)|*.csv|All files|*',
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        )
        try:
            if dlg.ShowModal() == wx.ID_OK:
                self.template_writer(dlg.GetPath(), self.template_rows())
        except Exception as e:
            wx.MessageBox(str(e), 'Conversion Error', wx.OK | wx.ICON_ERROR)
        finally:
            dlg.Destroy()

    def on_template_clear(self, evt):
        self.push_template_undo()
        self.clear_template_grid()

    def on_convert(self, evt):
        if not self.paths:
            wx.MessageBox('No files selected.', 'Conversion Error',
                          wx.OK | wx.ICON_ERROR)
            return
        if (self.channel_list is not None and not self.template_mode() and
                not self.selected_channel_labels()):
            wx.MessageBox('Select at least one channel to convert.',
                          'Conversion Error', wx.OK | wx.ICON_ERROR)
            return
        if not os.path.isdir(self.output.GetValue()):
            wx.MessageBox('Output folder does not exist.', 'Conversion Error',
                          wx.OK | wx.ICON_ERROR)
            return
        self.convert_selected()

    def add_paths(self, paths):
        self.paths = sorted(set(self.paths + [p for p in paths if os.path.isfile(p)]))
        self.refresh_list()

    def refresh_list(self):
        self.list.DeleteAllItems()
        for path in self.paths:
            idx = self.list.InsertItem(self.list.GetItemCount(), os.path.basename(path))
            self.list.SetItem(idx, 1, os.path.dirname(path))
        self.refresh_channels()

    def refresh_channels(self):
        if self.channel_list is None:
            return

        old_labels = set(self.channel_list.GetString(i)
                         for i in range(self.channel_list.GetCount()))
        old_checked = set(self.selected_channel_labels())
        labels = []
        timestamps = {}
        try:
            for path in self.paths:
                labels.extend(self.channel_loader(path))
                if self.timestamp_loader is not None:
                    timestamps[path] = self.timestamp_loader(path)
        except Exception as e:
            wx.MessageBox(str(e), 'Conversion Error', wx.OK | wx.ICON_ERROR)
            labels = []
            timestamps = {}

        labels = sorted(set(labels))
        self.channel_choices = labels
        self.timestamps_by_path = timestamps
        self.channel_list.Clear()
        for label in labels:
            self.channel_list.Append(label)
        for i, label in enumerate(labels):
            self.channel_list.Check(i, label in old_checked or label not in old_labels)

        enabled = bool(labels)
        self.channel_list.Enable(enabled)
        self.channel_all.Enable(enabled)
        self.channel_none.Enable(enabled)
        self.set_template_channel_editors()
        self.refresh_template_timestamp_editors()

    def check_all_channels(self, checked):
        for i in range(self.channel_list.GetCount()):
            self.channel_list.Check(i, checked)

    def template_mode(self):
        return self.mode is not None and self.mode.GetSelection() == 1

    def template_rows(self, include_blank=False):
        if self.template_grid is None:
            return None
        rows = []
        for row in range(self.template_grid.GetNumberRows()):
            data = {
                field: self.template_grid.GetCellValue(row, col).strip()
                for col, field in enumerate(self.template_fields)
            }
            if include_blank or any(data.values()):
                rows.append(data)
        return rows

    def set_template_rows(self, rows):
        grid = self.template_grid
        if grid.GetNumberRows():
            grid.DeleteRows(0, grid.GetNumberRows())
        rows = rows or []
        row_count = max(self.TEMPLATE_INITIAL_ROWS,
                        len(rows) + self.TEMPLATE_TRAILING_ROWS)
        grid.AppendRows(row_count)
        for row_i, row in enumerate(rows):
            for col, field in enumerate(self.template_fields):
                grid.SetCellValue(row_i, col, row.get(field, ''))
        self.set_template_channel_editors()
        self.refresh_template_timestamp_editors()
        self.ensure_template_trailing_rows()
        self.fit_template_columns()

    def clear_template_grid(self):
        grid = self.template_grid
        if grid.GetNumberRows():
            grid.DeleteRows(0, grid.GetNumberRows())
        grid.AppendRows(self.TEMPLATE_INITIAL_ROWS)
        self.set_template_channel_editors()
        self.refresh_template_timestamp_editors()
        self.fit_template_columns()

    def template_snapshot(self):
        grid = self.template_grid
        return [
            [grid.GetCellValue(row, col)
             for col in range(grid.GetNumberCols())]
            for row in range(grid.GetNumberRows())
        ]

    def template_snapshot_size(self, snapshot):
        return sum(len(value.encode('utf-8')) + 8
                   for row in snapshot for value in row)

    def clear_template_redo(self):
        self.template_redo = []
        self.template_redo_bytes = 0

    def push_template_history(self, history, bytes_attr, snapshot, trim=True):
        if history and history[-1][1] == snapshot:
            return
        size = self.template_snapshot_size(snapshot)
        history.append((size, snapshot))
        setattr(self, bytes_attr, getattr(self, bytes_attr) + size)
        if trim:
            self.trim_template_history()

    def trim_template_history(self):
        while (self.template_undo_bytes + self.template_redo_bytes >
               self.TEMPLATE_UNDO_LIMIT_BYTES):
            if self.template_undo:
                old_size, _ = self.template_undo.pop(0)
                self.template_undo_bytes -= old_size
            elif self.template_redo:
                old_size, _ = self.template_redo.pop(0)
                self.template_redo_bytes -= old_size
            else:
                return

    def push_template_undo(self, clear_redo=True, trim=True):
        if self.suppress_template_undo or self.template_grid is None:
            return
        if clear_redo:
            self.clear_template_redo()
        snapshot = self.template_snapshot()
        self.push_template_history(
            self.template_undo, 'template_undo_bytes', snapshot, trim=trim)

    def undo_template(self):
        if not self.template_undo:
            return
        self.push_template_history(
            self.template_redo, 'template_redo_bytes',
            self.template_snapshot(), trim=False)
        size, snapshot = self.template_undo.pop()
        self.template_undo_bytes -= size
        self.restore_template_snapshot(snapshot)
        self.trim_template_history()

    def redo_template(self):
        if not self.template_redo:
            return
        self.push_template_undo(clear_redo=False, trim=False)
        size, snapshot = self.template_redo.pop()
        self.template_redo_bytes -= size
        self.restore_template_snapshot(snapshot)
        self.trim_template_history()

    def restore_template_snapshot(self, snapshot):
        grid = self.template_grid
        self.suppress_template_undo = True
        try:
            if grid.GetNumberRows():
                grid.DeleteRows(0, grid.GetNumberRows())
            grid.AppendRows(max(self.TEMPLATE_INITIAL_ROWS, len(snapshot)))
            for row_i, row in enumerate(snapshot):
                for col_i, value in enumerate(row[:grid.GetNumberCols()]):
                    grid.SetCellValue(row_i, col_i, value)
            self.set_template_channel_editors()
            self.refresh_template_timestamp_editors()
            self.ensure_template_trailing_rows()
            self.fit_template_columns()
            grid.ForceRefresh()
        finally:
            self.suppress_template_undo = False

    def on_template_grid_size(self, evt):
        self.fit_template_columns()
        evt.Skip()

    def fit_template_columns(self):
        grid = self.template_grid
        if grid is None:
            return
        cols = grid.GetNumberCols()
        if not cols:
            return
        width = grid.GetGridWindow().GetClientSize().GetWidth()
        if width <= 0:
            width = grid.GetClientSize().GetWidth() - grid.GetRowLabelSize()
        width = max(width, cols)
        col_width = max(1, width // cols)
        for col in range(cols - 1):
            grid.SetColSize(col, col_width)
        grid.SetColSize(cols - 1, max(1, width - col_width * (cols - 1)))

    def template_channel_col(self):
        try:
            return self.template_fields.index('Channel')
        except ValueError:
            return None

    def template_timestamp_col(self):
        try:
            return self.template_fields.index('Timestamp')
        except ValueError:
            return None

    def template_eclipse_id_col(self):
        try:
            return self.template_fields.index('Eclipse ID')
        except ValueError:
            return None

    def set_template_channel_editors(self, start_row=0):
        if self.template_grid is None:
            return
        channel_col = self.template_channel_col()
        if channel_col is None:
            return
        for row in range(start_row, self.template_grid.GetNumberRows()):
            editor = wx.grid.GridCellChoiceEditor(self.channel_choices, True)
            self.template_grid.SetCellEditor(row, channel_col, editor)

    def set_template_timestamp_editor(self, row):
        timestamp_col = self.template_timestamp_col()
        if timestamp_col is None or row < 0:
            return
        editor = wx.grid.GridCellChoiceEditor(
            self.timestamp_choices_for_row(row), True)
        self.template_grid.SetCellEditor(row, timestamp_col, editor)

    def refresh_template_timestamp_editors(self):
        if self.template_grid is None:
            return
        for row in range(self.template_grid.GetNumberRows()):
            self.set_template_timestamp_editor(row)

    def timestamp_choices_for_row(self, row):
        eclipse_col = self.template_eclipse_id_col()
        if eclipse_col is None:
            return []
        eclipse_id = self.template_grid.GetCellValue(row, eclipse_col).strip()
        if not eclipse_id:
            return []
        channel_col = self.template_channel_col()
        channel = ''
        if channel_col is not None:
            channel = self.template_grid.GetCellValue(row, channel_col).strip()
        choices = []
        for path, timestamp_rows in self.timestamps_by_path.items():
            stem = os.path.splitext(os.path.basename(path))[0]
            if (self.eclipse_id_matcher is None or
                    self.eclipse_id_matcher(stem, eclipse_id)):
                choices.extend(timestamp for row_channel, timestamp in timestamp_rows
                               if not channel or row_channel == channel)
        return sorted(set(choices))

    def template_row_blank(self, row):
        return not any(
            self.template_grid.GetCellValue(row, col).strip()
            for col in range(self.template_grid.GetNumberCols())
        )

    def ensure_template_rows(self, count):
        if self.template_grid is None:
            return
        current = self.template_grid.GetNumberRows()
        if count > current:
            self.template_grid.AppendRows(count - current)
            self.set_template_channel_editors(current)
            for row in range(current, self.template_grid.GetNumberRows()):
                self.set_template_timestamp_editor(row)

    def ensure_template_trailing_rows(self):
        if self.template_grid is None:
            return
        self.ensure_template_rows(self.TEMPLATE_INITIAL_ROWS)
        trailing = 0
        for row in reversed(range(self.template_grid.GetNumberRows())):
            if not self.template_row_blank(row):
                break
            trailing += 1
        if trailing < self.TEMPLATE_TRAILING_ROWS:
            self.ensure_template_rows(
                self.template_grid.GetNumberRows() +
                self.TEMPLATE_TRAILING_ROWS - trailing)

    def on_template_cell_changing(self, evt):
        self.push_template_undo()
        evt.Skip()

    def on_template_cell_changed(self, evt):
        if evt.GetCol() in (self.template_eclipse_id_col(),
                            self.template_channel_col()):
            self.set_template_timestamp_editor(evt.GetRow())
        self.ensure_template_trailing_rows()
        evt.Skip()

    def on_template_select_cell(self, evt):
        self.set_template_timestamp_editor(evt.GetRow())
        evt.Skip()

    def on_template_cell_left_dclick(self, evt):
        self.set_template_timestamp_editor(evt.GetRow())
        evt.Skip()

    def on_template_key_down(self, evt):
        key = evt.GetKeyCode()
        shortcut = evt.CmdDown() or evt.ControlDown()
        if (shortcut and
                ((key in (ord('Z'), ord('z')) and evt.ShiftDown()) or
                 key in (ord('Y'), ord('y')))):
            self.redo_template()
            return
        if key in (ord('Z'), ord('z')) and shortcut:
            self.undo_template()
            return
        if key in (ord('V'), ord('v')) and shortcut:
            self.paste_template_clipboard()
            return
        if key in (wx.WXK_DELETE, wx.WXK_BACK):
            cells = self.selected_template_cells()
            if not cells:
                cells = [(self.template_grid.GetGridCursorRow(),
                          self.template_grid.GetGridCursorCol())]
            self.push_template_undo()
            self.set_template_cells(cells, '')
            return
        evt.Skip()

    def paste_template_clipboard(self):
        text = self.template_clipboard_text()
        values = self.clipboard_grid_values(text)
        if not values:
            return

        if len(values) == 1 and len(values[0]) == 1:
            cells = self.selected_template_cells()
            if len(cells) > 1:
                self.push_template_undo()
                self.set_template_cells(cells, values[0][0])
                return

        start_row, start_col = self.template_paste_anchor()
        self.push_template_undo()
        self.ensure_template_rows(start_row + len(values))
        for row_i, row_values in enumerate(values):
            for col_i, value in enumerate(row_values):
                col = start_col + col_i
                if col < self.template_grid.GetNumberCols():
                    self.template_grid.SetCellValue(start_row + row_i,
                                                    col, value)
        self.refresh_template_timestamp_editors()
        self.ensure_template_trailing_rows()
        self.template_grid.ForceRefresh()

    def template_clipboard_text(self):
        data = wx.TextDataObject()
        if not wx.TheClipboard.Open():
            return ''
        try:
            if wx.TheClipboard.GetData(data):
                return data.GetText()
            return ''
        finally:
            wx.TheClipboard.Close()

    def clipboard_grid_values(self, text):
        if text == '':
            return []
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        lines = text.split('\n')
        if lines and lines[-1] == '':
            lines.pop()
        return [line.split('\t') for line in lines]

    def template_coord(self, coord):
        try:
            return coord.GetRow(), coord.GetCol()
        except AttributeError:
            return coord[0], coord[1]

    def selected_template_cells(self):
        grid = self.template_grid
        cells = set()
        for top_left, bottom_right in zip(grid.GetSelectionBlockTopLeft(),
                                          grid.GetSelectionBlockBottomRight()):
            top, left = self.template_coord(top_left)
            bottom, right = self.template_coord(bottom_right)
            for row in range(top, bottom + 1):
                for col in range(left, right + 1):
                    cells.add((row, col))
        for coord in grid.GetSelectedCells():
            cells.add(self.template_coord(coord))
        for row in grid.GetSelectedRows():
            for col in range(grid.GetNumberCols()):
                cells.add((row, col))
        for col in grid.GetSelectedCols():
            for row in range(grid.GetNumberRows()):
                cells.add((row, col))
        return sorted(cells)

    def set_template_cells(self, cells, value):
        max_row = max(row for row, _ in cells)
        self.ensure_template_rows(max_row + 1)
        for row, col in cells:
            if col < self.template_grid.GetNumberCols():
                self.template_grid.SetCellValue(row, col, value)
        self.refresh_template_timestamp_editors()
        self.ensure_template_trailing_rows()
        self.template_grid.ForceRefresh()

    def template_paste_anchor(self):
        grid = self.template_grid
        blocks = grid.GetSelectionBlockTopLeft()
        if blocks:
            return self.template_coord(blocks[0])
        cells = grid.GetSelectedCells()
        if cells:
            return self.template_coord(cells[0])
        rows = grid.GetSelectedRows()
        if rows:
            return rows[0], 0
        cols = grid.GetSelectedCols()
        if cols:
            return max(grid.GetGridCursorRow(), 0), cols[0]
        return max(grid.GetGridCursorRow(), 0), max(grid.GetGridCursorCol(), 0)

    def convert_selected(self):
        parent = self.GetParent()
        output_folder = self.output.GetValue()
        template_rows = (self.template_rows(include_blank=True)
                         if self.template_mode() else None)
        channel_labels = None if template_rows is not None else self.selected_channel_labels()
        if parent is not None:
            parent.SetStatusText('Running %s to .tsv converter...' % self.source_name)

        busy = False
        try:
            wx.BeginBusyCursor()
            busy = True
            written = []
            for path in self.paths:
                if template_rows is not None:
                    written.extend(self.convert_file(
                        path, output_folder, template_rows=template_rows,
                        available_channels=self.channel_choices) or [])
                elif channel_labels is None:
                    written.extend(self.convert_file(path, output_folder) or [])
                else:
                    written.extend(self.convert_file(
                        path, output_folder, channel_labels=channel_labels) or [])
            if template_rows is not None and not written:
                if parent is not None:
                    parent.SetStatusText('No matching template recordings found.')
                wx.MessageBox('No matching template recordings found.',
                              'Conversion Error', wx.OK | wx.ICON_ERROR)
                return
            if channel_labels is not None and not written:
                if parent is not None:
                    parent.SetStatusText('No matching %s channels found.' %
                                         self.source_name)
                wx.MessageBox(
                    "No matching channels found in selected files. "
                    "Example channel name: 'R: A2-Cz'.",
                    'Conversion Error', wx.OK | wx.ICON_ERROR)
                return
            if parent is not None:
                parent.OnRefresh()
                parent.SetStatusText('Converted %s files successfully. '
                                     'Please drag and drop files to canvas.' %
                                     self.source_name)
            noun = 'file' if len(written) == 1 else 'files'
            wx.MessageBox('%d TSV %s written to:\n%s' %
                          (len(written), noun, output_folder),
                          self.GetTitle() + ' Complete',
                          wx.OK | wx.ICON_INFORMATION)
            self.converted = True
            self.on_clear(None)
        except Exception as e:
            if parent is not None:
                parent.SetStatusText('Could not parse %s file. '
                                     'Most likely not a valid %s export file.' %
                                     (self.source_name, self.source_name))
            dlg = wx.MessageDialog(self, str(e), 'Conversion Error',
                                   wx.OK | wx.ICON_ERROR)
            dlg.ShowModal()
            dlg.Destroy()
        finally:
            if busy:
                wx.EndBusyCursor()

    def selected_channel_labels(self):
        if self.channel_list is None:
            return None
        return [self.channel_list.GetString(i)
                for i in range(self.channel_list.GetCount())
                if self.channel_list.IsChecked(i)]

#----------------------------------------------------------------------------

class PhysiologyFrame(PersistentFrame):

    def __init__(self, name="InteractiveFrame", parent=None, splash=False, 
            *args, **kwargs):

        if splash:
            splash = PhysiologySplashScreen(duration=1000)
            splash.Show()

        PersistentFrame.__init__(self, name, parent, *args, **kwargs)

        #Initialize menu
        menubar = wx.MenuBar()
        file = wx.Menu()
        ID_SET_DIR = wx.NewId()
        ID_SET_OPTIONS = wx.NewId()
        ID_CLOSE_TAB = wx.NewId()
        ID_CLOSE_ALL_BUT = wx.NewId()
        ID_CLOSE_ALL_TABS = wx.NewId()
        ID_REFRESH = wx.NewId()
        ID_SAVE = wx.NewId()
        file.Append(ID_SET_DIR, 'Open &Directory\tCtrl+D', 'Open Directory') 
        file.Append(wx.ID_OPEN, 'Open &File\tCtrl+F', 'Open File')
        file.Append(ID_SAVE, '&Save\tCtrl+S', 'Save current analysis')
        file.Append(ID_REFRESH, '&Refresh\tCtrl+R', 'Refresh')
        file.AppendSeparator()
        file.Append(ID_SET_OPTIONS, '&Options\tCtrl+O', 'Options')
        file.AppendSeparator()
        file.Append(ID_CLOSE_TAB, 'Close &tab\tCtrl+W', 'Close tab')
        file.Append(ID_CLOSE_ALL_BUT, 'Close all &but active tab\tCtrl+B', 'Close all but')
        file.Append(ID_CLOSE_ALL_TABS, 'Close &all tabs\tCtrl+A', 'Close all tabs')
        file.AppendSeparator()
        file.Append(wx.ID_EXIT, '&Quit\tCtrl+Q', 'Quit Application')
        menubar.Append(file, '&File')

        ID_CONVERT_IHS = wx.NewId()
        ID_CONVERT_ECLIPSE = wx.NewId()

        tools = wx.Menu()
        ID_EXPORT = wx.NewId()
        ID_BULK_ANALYZE = wx.NewId()
        tools.Append(ID_CONVERT_IHS, 'Convert &IHS Data', 'Convert IHS Data')
        tools.Append(ID_CONVERT_ECLIPSE, 'Convert &Eclipse Data', 'Convert Eclipse Data')
        tools.AppendSeparator()
        tools.Append(ID_BULK_ANALYZE, '&Bulk Analyze/Filter', 'Analyze and filter files in bulk')
        tools.Append(ID_EXPORT, '&Export', 'Export analyzed SQLite files to CSV')
        menubar.Append(tools, '&Tools')

        help = wx.Menu()
        ID_DISPLAY_HELP = wx.NewId()
        help.Append(ID_DISPLAY_HELP, '&Help\tCtrl+H', 'Help')
        help.AppendSeparator()
        help.Append(wx.ID_ABOUT, '&About\tCtrl+A', 'About')
        menubar.Append(help, '&Help')
        self.SetMenuBar(menubar)

        #Menu events
        self.Bind(wx.EVT_MENU, self.OnSetDir, id=ID_SET_DIR)
        self.Bind(wx.EVT_MENU, self.OnSetOptions, id=ID_SET_OPTIONS)
        self.Bind(wx.EVT_MENU, self.OnOpenFile, id=wx.ID_OPEN)
        self.Bind(wx.EVT_MENU, self.OnSave, id=ID_SAVE)
        self.Bind(wx.EVT_MENU, self.OnQuit, id=wx.ID_EXIT)
        self.Bind(wx.EVT_MENU, self.OnAbout, id=wx.ID_ABOUT)
        self.Bind(wx.EVT_MENU, self.OnRefresh, id=ID_REFRESH)
        self.Bind(wx.EVT_MENU, self.OnCloseTab, id=ID_CLOSE_TAB)
        self.Bind(wx.EVT_MENU, self.OnCloseAllBut, id=ID_CLOSE_ALL_BUT)
        self.Bind(wx.EVT_MENU, self.OnCloseAllTabs, id=ID_CLOSE_ALL_TABS)
        self.Bind(wx.EVT_MENU, self.OnConvertIHS, id=ID_CONVERT_IHS)
        self.Bind(wx.EVT_MENU, self.OnConvertEclipse, id=ID_CONVERT_ECLIPSE)
        self.Bind(wx.EVT_MENU, self.OnBulkAnalyze, id=ID_BULK_ANALYZE)
        self.Bind(wx.EVT_MENU, self.OnExport, id=ID_EXPORT)
        self.Bind(wx.EVT_MENU, self.OnDisplayHelp, id=ID_DISPLAY_HELP)

        #Initialize manager and panels
        self.__mgr = wx.aui.AuiManager()
        self.__mgr.SetManagedWindow(self)

        self.__nb = PhysiologyNotebook(self)

        # self.help = wx.html.HtmlHelpController(style=
        #         wx.html.HF_CONTENTS |
        #         wx.html.HF_PRINT |
        #         wx.html.HF_MERGE_BOOKS
        #         )
        # self.help.AddBook('help/help.chm')
        # self.helpPath = os.path.join(os.path.dirname(__file__), 'help', 'ABR Peak Analysis.pdf')
        self.helpPath = os.path.join(os.path.dirname(__file__), 'help', 'index.htm')
        # self.help.AddBook(self.helpPath)

        self.foptions = DefaultValueHolder("PhysiologyNotebook", "file")
        self.foptions.SetVariables(startdir=".")
        self.foptions.InitFromConfig()
        rootpath = self.foptions.startdir
        if not os.path.isdir(rootpath):
            rootpath = '.'
        os.chdir(rootpath)
#        rootpath = os.getcwd()

        self.__filetree = LazyTree(self, io=peakio, root=rootpath,
                                   open_callback=self.__nb.load)

        self.__mgr.AddPane(self.__nb, wx.aui.AuiPaneInfo().
                Name('notebook').Center().CloseButton(False).
                MaximizeButton(True))
        self.__mgr.AddPane(self.__filetree, wx.aui.AuiPaneInfo().
                Name('files').Left().CloseButton(False).MaximizeButton(False).
                BestSize((200,400)))

        self.__mgr.Update()

        self.CreateStatusBar()
        self.SetStatusText('Please drag and drop files to canvas')
        self.Show()

    def OnRefresh(self, evt=None):
        self.__filetree.root = self.__filetree.root
        self.SetStatusText('File tree refreshed.'
                               'Please drag and drop files to canvas.')
        
    def OnDisplayHelp(self, evt):
        # self.help.DisplayContents()
        # os.startfile(self.helpPath)
        file_url = f"file://{self.helpPath}"
        webbrowser.open(file_url)

    def OnCloseTab(self, evt):
        self.__nb.DeletePage(self.__nb.GetSelection())

    def OnCloseAllBut(self, evt):
        for k in reversed(range(self.__nb.PageCount)):
            if k != self.__nb.GetSelection():
                self.__nb.DeletePage(k)

    def OnCloseAllTabs(self, evt):
        for k in reversed(range(self.__nb.PageCount)):
            self.__nb.DeletePage(k)

    def ConvertFiles(self, title, wildcard, convert_file, source_name,
                     channel_loader=None, template_reader=None,
                     template_writer=None, template_fields=None,
                     timestamp_loader=None, eclipse_id_matcher=None):
        dialog = ConvertFilesDialog(self, title, wildcard, self.__filetree.root,
                                    convert_file, source_name,
                                    source_name == 'Eclipse',
                                    channel_loader=channel_loader,
                                    template_reader=template_reader,
                                    template_writer=template_writer,
                                    template_fields=template_fields,
                                    timestamp_loader=timestamp_loader,
                                    eclipse_id_matcher=eclipse_id_matcher)
        try:
            dialog.ShowModal()
            return dialog.converted
        finally:
            dialog.Destroy()

    def OnConvertIHS(self, evt):
        import convert_ihs
        self.ConvertFiles('Convert IHS', 'TXT files (*.txt)|*.txt',
                          convert_ihs.main, 'IHS')

    def OnConvertEclipse(self, evt):
        import convert_eclipse
        self.ConvertFiles('Convert Eclipse Data', 'CSV files (*.csv)|*.csv',
                          convert_eclipse.main, 'Eclipse',
                          channel_loader=convert_eclipse.channel_labels,
                          template_reader=convert_eclipse.read_template_csv,
                          template_writer=convert_eclipse.write_template_csv,
                          template_fields=convert_eclipse.TEMPLATE_FIELDS,
                          timestamp_loader=convert_eclipse.template_timestamp_rows,
                          eclipse_id_matcher=convert_eclipse.eclipse_id_matches)

    def OnExport(self, evt):
        import merge_export_saved

        if merge_export_saved.export_with_dialog(self, self.__filetree.root):
            self.SetStatusText('Export complete.')

    def OnBulkAnalyze(self, evt):
        import bulk_analyze

        if bulk_analyze.analyze_with_dialog(self, self.__filetree.root):
            self.OnRefresh()
            self.SetStatusText('Bulk analyze/filter complete.')

    def OnAbout(self, evt):
        info = wx.adv.AboutDialogInfo()
        info.Name = "ABR Peak Analysis"
        info.Version = "1.11.1"
        info.Copyright = "(C) 2007 Speech and Hearing Bioscience and Technology"
#        info.WebSite = "http://web.mit.edu/shbt"
        info.Developers = ["Brad Buran"]
        wx.adv.AboutBox(info)

    def OnSetOptions(self, evt):
        dlg = PhysiologyOptions(self, wx.ID_ANY, "Options")
        dlg.CenterOnScreen()
        val = dlg.ShowModal()
        if val == wx.ID_OK:
            self.foptions.SetVariables(startdir=dlg.file.startdir)
            if self.__filetree.root != dlg.file.startdir:
                self.__filetree.root = dlg.file.startdir
            for page in self.__nb:
                if hasattr(page, 'presenter'):
                    page.presenter._plotupdate = True
        dlg.Destroy()

#        evt.Skip()
#
#        Skip() was causing Spyder/Python to fire two events: dialogs would
#        appear twice every time each menu option was selected. I've removed
#        it throughout. KEH 9/4/2013

    def OnSetDir(self, evt):
        dlg = wx.DirDialog(self, "Choose a directory:",
                defaultPath=self.__filetree.root, 
                style=wx.DD_DIR_MUST_EXIST | wx.DD_CHANGE_DIR)
        if dlg.ShowModal() == wx.ID_OK:
            newfolder = dlg.GetPath()
            self.__filetree.root = newfolder
            self.foptions.SetVariables(startdir=newfolder)
#            self.foptions.startdir = newfolder
            self.foptions.UpdateConfig()
        dlg.Destroy()
#        evt.Skip()

    def OnOpenFile(self, evt):
        dlg = wx.FileDialog(self, "Choose a file:", wildcard=SOURCE_WILDCARD,
                style=wx.FD_OPEN | wx.FD_MULTIPLE | wx.FD_CHANGE_DIR | wx.FD_FILE_MUST_EXIST)
        if dlg.ShowModal() == wx.ID_OK:
            paths = [p for p in dlg.GetPaths() if is_source_file(p)]
            if paths:
                self.__nb.loadfiles(paths)
            else:
                self.SetStatusText('No valid source files selected.')
        dlg.Destroy()    
#        evt.Skip()

    def OnSave(self, evt):
        if self.__nb.GetPageCount() == 0:
            self.SetStatusText('No active tab to save.')
            return

        page = self.__nb.GetPage(self.__nb.GetSelection())
        if hasattr(page, 'presenter') and hasattr(page.presenter, 'save'):
            page.presenter.save()
        else:
            self.SetStatusText('Active tab cannot be saved.')
#        evt.Skip()

#----------------------------------------------------------------------------

class PhysiologyOptions(wx.Dialog):

    @staticmethod
    def _option_defaults():
        return {
            'filter': {'ftype': 'Butterworth', 'fl': 10000, 'fh': 200, 'N': 1},
            'file': {'startdir': '.'},
            'iofilter': {'method': 'database'},
            'showallpol': {'value': False},
            'minlatency': {'value': float(1.5)},
            'baselinewin': {'value': float(0.3)},
            'useNoiseFloor': {'value': False},
            'overwriteOnSave': {'value': False},
            'autoRestore': {'value': True},
            'timeRangeMin': {'value': float(0)},
            'timeRangeMax': {'value': ''},
            'expectedPeaks': {'value': 5},
            'peakVisibility': peak_visibility_defaults(),
            'plotting': {'addGridlines': True},
        }

    @staticmethod
    def _optional_float(value, default):
        return default if value == '' else float(value)

    def _configured_option(self, name):
        option = DefaultValueHolder('PhysiologyNotebook', name)
        option.SetVariables(self.defaults[name])
        option.InitFromConfig()
        return option

    def __init__(self, parent, id, title, size=wx.DefaultSize,
            pos=wx.DefaultPosition, style=wx.DEFAULT_DIALOG_STYLE):

        self.defaults = self._option_defaults()
        self.filter = self._configured_option('filter')
        self.file = self._configured_option('file')
        self.iofilter = self._configured_option('iofilter')
        self.showallpol = self._configured_option('showallpol')
        self.minlatency = self._configured_option('minlatency')
        self.baselinewin = self._configured_option('baselinewin')
        self.useNoiseFloor = self._configured_option('useNoiseFloor')
        self.overwriteOnSave = self._configured_option('overwriteOnSave')
        self.autoRestore = self._configured_option('autoRestore')
        self.timeRangeMin = self._configured_option('timeRangeMin')
        self.timeRangeMax = self._configured_option('timeRangeMax')
        self.expectedPeaks = self._configured_option('expectedPeaks')
        self.peakVisibility = self._configured_option('peakVisibility')
        self.plotting = self._configured_option('plotting')

        filter = self.filter
        file = self.file
        minlatency = self.minlatency
        showallpol = self.showallpol
        baselinewin = self.baselinewin

        ftypes = ['None', 'Bessel', 'Butterworth']
        wx.Dialog.__init__(self)
        self.SetExtraStyle(wx.DIALOG_EX_CONTEXTHELP)
        self.Create(parent, id, title)

        sizer = wx.BoxSizer(wx.VERTICAL)
        
        #Default directory
        dbox = wx.StaticBox(self, wx.ID_ANY, "Default Directory")
        dsizer = wx.StaticBoxSizer(dbox, wx.VERTICAL)
        self.dbb = filebrowse.DirBrowseButton(self, wx.ID_ANY, size=(550,-1),
                startDirectory=file.startdir)
        self.dbb.SetValue(file.startdir)
        dsizer.Add(self.dbb, 0, wx.EXPAND|wx.ALL, 5)

        #Filter options
        fbox = wx.StaticBox(self, wx.ID_ANY, "Filtering")
        fsizer = wx.StaticBoxSizer(fbox, wx.VERTICAL)
        box = wx.BoxSizer(wx.HORIZONTAL)

        #Filter type
        label = wx.StaticText(self, wx.ID_ANY, "Filter type:")
        box.Add(label, 0, wx.ALL, 5)
        self.ftype = wx.Choice(self, wx.ID_ANY, choices=ftypes)
        self.ftype.SetSelection(self.ftype.FindString(filter.ftype))
        box.Add(self.ftype, 0, wx.EXPAND|wx.ALL, 5)

        self.ftype.Bind(wx.EVT_CHOICE, self.ftype_choice)

        #Highpass
        label = wx.StaticText(self, wx.ID_ANY, "Highpass cutoff (Hz):")
        box.Add(label, 0, wx.ALL, 5)
        self.fh = wx.TextCtrl(self, wx.ID_ANY, str(filter.fh),
            size=(75,-1), validator=FrequencyValidator())
        box.Add(self.fh, 0, wx.ALL, 5)

        #Lowpass
        label = wx.StaticText(self, wx.ID_ANY, "Lowpass cutoff (Hz):")
        box.Add(label, 0, wx.ALL, 5)
        self.fl = wx.TextCtrl(self, wx.ID_ANY, str(filter.fl),
            size=(75,-1), validator=FrequencyValidator())
        box.Add(self.fl, 0, wx.ALL, 5)
        fsizer.Add(box, 0, wx.GROW|wx.ALL, 5)

        #Order
        label = wx.StaticText(self, wx.ID_ANY, "Order:")
        box.Add(label, 0, wx.ALL, 5)
        self.ford = wx.TextCtrl(self, wx.ID_ANY, str(filter.N),
                                size=(75, -1), validator=FrequencyValidator())
        box.Add(self.ford, 0, wx.ALL, 5)

        #Roll-off info
        self.ford_info = wx.StaticText(self, wx.ID_ANY, self._get_rolloff_label(filter.N, filter.ftype))
        box.Add(self.ford_info, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        self.ford.Bind(wx.EVT_TEXT, self.OnOrderChanged)

        self._set_filter_enabled(filter.ftype)

        # Custom Tmin
        wbox = wx.StaticBox(self, wx.ID_ANY, "Waveform Window")
        wsizer = wx.StaticBoxSizer(wbox, wx.HORIZONTAL)
        label = wx.StaticText(self, wx.ID_ANY, "Start (ms):")
        wsizer.Add(label, 0, wx.ALL, 5)
        self.tminb = wx.TextCtrl(self, wx.ID_ANY, str(self.timeRangeMin.value),
                                 size=(75, -1), validator=MinLatencyValidator())
        wsizer.Add(self.tminb, 0, wx.ALL, 5)

        # Custom Tmax
        label = wx.StaticText(self, wx.ID_ANY, "End (ms):")
        wsizer.Add(label, 0, wx.ALL, 5)
        self.tmaxb = wx.TextCtrl(self, wx.ID_ANY, str(self.timeRangeMax.value),
                                 size=(75, -1), validator=MinLatencyValidator())
        wsizer.Add(self.tmaxb, 0, wx.ALL, 5)

        #stim polarity
        pbox = wx.StaticBox(self, wx.ID_ANY, "Analysis")
        psizer = wx.StaticBoxSizer(pbox, wx.HORIZONTAL)
        label = wx.StaticText(self, wx.ID_ANY, "Analyze each stimulus polarity:")
        psizer.Add(label, 0, wx.ALL, 5)
        self.cb = wx.CheckBox(self, wx.ID_ANY)
        self.cb.SetValue(showallpol.value)
        self.cb.Bind(wx.EVT_CHOICE, self.OnStimPolCheck)
        psizer.Add(self.cb, 0, wx.ALL, 5)

        #min latency
        label = wx.StaticText(self, wx.ID_ANY, "Min latency (ms):")
        psizer.Add(label, 0, wx.ALL, 5)
        self.mlb = wx.TextCtrl(self, wx.ID_ANY, str(minlatency.value),
            size=(75,-1), validator=MinLatencyValidator())
        psizer.Add(self.mlb, 0, wx.ALL, 5)

        # baseline window
        label = wx.StaticText(self, wx.ID_ANY, "Baseline window (ms):")
        psizer.Add(label, 0, wx.ALL, 5)
        self.blw = wx.TextCtrl(self, wx.ID_ANY, str(baselinewin.value),
            size=(75,-1), validator=MinLatencyValidator())
        psizer.Add(self.blw, 0, wx.ALL, 5)

        # Saving
        obox = wx.StaticBox(self, wx.ID_ANY, "Saving")
        osizer = wx.StaticBoxSizer(obox, wx.HORIZONTAL)

        # Use noise floor
        label = wx.StaticText(self, wx.ID_ANY, "Do noise floor analysis:")
        osizer.Add(label, 0, wx.ALL, 5)
        self.nfcb = wx.CheckBox(self, wx.ID_ANY)
        self.nfcb.SetValue(self.useNoiseFloor.value)
        self.nfcb.Bind(wx.EVT_CHOICE, self.OnUseNoiseFloorCheck)
        osizer.Add(self.nfcb, 0, wx.ALL, 5)

        # Overwrite on save
        label = wx.StaticText(self, wx.ID_ANY, "Overwrite on save:")
        osizer.Add(label, 0, wx.ALL, 5)
        self.owcb = wx.CheckBox(self, wx.ID_ANY)
        self.owcb.SetValue(self.overwriteOnSave.value)
        self.owcb.Bind(wx.EVT_CHOICE, self.OnOverwriteOnSaveCheck)
        osizer.Add(self.owcb, 0, wx.ALL, 5)

        # Auto restore previous analysis
        label = wx.StaticText(self, wx.ID_ANY, "Auto restore analysis:")
        osizer.Add(label, 0, wx.ALL, 5)
        self.arcb = wx.CheckBox(self, wx.ID_ANY)
        self.arcb.SetValue(self.autoRestore.value)
        self.arcb.Bind(wx.EVT_CHOICE, self.OnAutoRestoreCheck)
        osizer.Add(self.arcb, 0, wx.ALL, 5)

        # Plotting
        gbox = wx.StaticBox(self, wx.ID_ANY, "Plotting")
        gsizer = wx.StaticBoxSizer(gbox, wx.HORIZONTAL)
        label = wx.StaticText(self, wx.ID_ANY, "Add gridlines:")
        gsizer.Add(label, 0, wx.ALL, 5)
        self.gridcb = wx.CheckBox(self, wx.ID_ANY)
        self.gridcb.SetValue(self.plotting.addGridlines)
        gsizer.Add(self.gridcb, 0, wx.ALL, 5)

        # Peak display filtering
        vbox = wx.StaticBox(self, wx.ID_ANY, "Peak Display")
        vsizer = wx.StaticBoxSizer(vbox, wx.VERTICAL)

        expected_row = wx.BoxSizer(wx.HORIZONTAL)
        label = wx.StaticText(self, wx.ID_ANY, "Expected number of peaks:")
        expected_row.Add(label, 0, wx.ALL, 5)
        self.expectedPeakChoice = wx.Choice(self, wx.ID_ANY,
                                            choices=[str(i) for i in range(1, MAX_PEAKS + 1)])
        self.expectedPeakChoice.SetSelection(expected_peak_count() - 1)
        expected_row.Add(self.expectedPeakChoice, 0, wx.ALL, 5)
        vsizer.Add(expected_row, 0, wx.ALL, 5)

        peak_row = wx.BoxSizer(wx.HORIZONTAL)
        label = wx.StaticText(self, wx.ID_ANY, "Show peaks:")
        peak_row.Add(label, 0, wx.ALL, 5)
        self.pcbs = []
        for k, roman in enumerate(['I', 'II', 'III', 'IV', 'V', 'VI']):
            cb = wx.CheckBox(self, wx.ID_ANY, roman)
            cb.SetValue(getattr(self.peakVisibility, 'p%d' % (k + 1)))
            peak_row.Add(cb, 0, wx.ALL, 5)
            self.pcbs.append(cb)
        vsizer.Add(peak_row, 0, wx.ALL, 5)

        valley_row = wx.BoxSizer(wx.HORIZONTAL)
        label = wx.StaticText(self, wx.ID_ANY, "Show valleys:")
        valley_row.Add(label, 0, wx.ALL, 5)
        self.ncbs = []
        for k, roman in enumerate(['I', 'II', 'III', 'IV', 'V', 'VI']):
            cb = wx.CheckBox(self, wx.ID_ANY, roman)
            cb.SetValue(getattr(self.peakVisibility, 'n%d' % (k + 1)))
            valley_row.Add(cb, 0, wx.ALL, 5)
            self.ncbs.append(cb)
        vsizer.Add(valley_row, 0, wx.ALL, 5)

        line = wx.StaticLine(self, wx.ID_ANY, size=(25,-1), style=wx.LI_HORIZONTAL)

        sizer.Add(dsizer, 0, wx.EXPAND|wx.ALL, 5)
        sizer.Add(fsizer, 0, wx.EXPAND|wx.ALL, 5)
        sizer.Add(wsizer, 0, wx.EXPAND|wx.ALL, 5)
        sizer.Add(psizer, 0, wx.EXPAND|wx.ALL, 5)
        sizer.Add(osizer, 0, wx.EXPAND|wx.ALL, 5)
        sizer.Add(gsizer, 0, wx.EXPAND|wx.ALL, 5)
        sizer.Add(vsizer, 0, wx.EXPAND|wx.ALL, 5)
        sizer.Add(line, 0, wx.GROW, wx.RIGHT|wx.TOP, 5)

        #Buttons
        btnsizer = wx.BoxSizer(wx.HORIZONTAL)
        self.ok = wx.Button(self, wx.ID_OK)
        self.ok.SetDefault()
        btnsizer.Add(self.ok, 0, wx.ALL, 5)

        self.cancel = wx.Button(self, wx.ID_CANCEL)
        btnsizer.Add(self.cancel, 0, wx.ALL, 5)

        btnsizer.AddStretchSpacer()
        self.reset = wx.Button(self, wx.ID_ANY, "Restore Defaults")
        btnsizer.Add(self.reset, 0, wx.ALL, 5)

#        sizer.Add(btnsizer, 0, wx.ALIGN_CENTER_VERTICAL|wx.ALL, 5)
        sizer.Add(btnsizer, 0, wx.EXPAND|wx.ALL, 5)
        self.SetSizer(sizer)
        sizer.Fit(self)

        self.reset.Bind(wx.EVT_BUTTON, self.OnResetDefaults)
        self.ok.Bind(wx.EVT_BUTTON, self.OnOk)

    def _set_filter_enabled(self, ftype):
        enabled = ftype != 'None'
        self.fh.Enable(enabled)
        self.fl.Enable(enabled)
        self.ford.Enable(enabled)

    def OnResetDefaults(self, evt):
        if wx.MessageBox(
                "Restore all settings to defaults?",
                "Restore Defaults",
                wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION,
                self) != wx.YES:
            return

        defaults = self.defaults
        self.dbb.SetValue(defaults['file']['startdir'])

        filter = defaults['filter']
        self.ftype.SetStringSelection(filter['ftype'])
        self.fl.SetValue(str(filter['fl']))
        self.fh.SetValue(str(filter['fh']))
        self.ford.SetValue(str(filter['N']))
        self._set_filter_enabled(filter['ftype'])
        self.ford_info.SetLabel(self._get_rolloff_label(filter['N'], filter['ftype']))

        self.tminb.SetValue(str(defaults['timeRangeMin']['value']))
        self.tmaxb.SetValue(str(defaults['timeRangeMax']['value']))
        self.cb.SetValue(defaults['showallpol']['value'])
        self.mlb.SetValue(str(defaults['minlatency']['value']))
        self.blw.SetValue(str(defaults['baselinewin']['value']))
        self.nfcb.SetValue(defaults['useNoiseFloor']['value'])
        self.owcb.SetValue(defaults['overwriteOnSave']['value'])
        self.arcb.SetValue(defaults['autoRestore']['value'])
        self.gridcb.SetValue(defaults['plotting']['addGridlines'])
        self.expectedPeakChoice.SetSelection(defaults['expectedPeaks']['value'] - 1)

        visibility = defaults['peakVisibility']
        for prefix, cbs in (('p', self.pcbs), ('n', self.ncbs)):
            for i, cb in enumerate(cbs):
                cb.SetValue(visibility['%s%d' % (prefix, i + 1)])

        if hasattr(self, 'dbb_color'):
            self.dbb.SetBackgroundColour(self.dbb_color)
        if hasattr(self, 'txtctrl_color'):
            self.fl.SetBackgroundColour(self.txtctrl_color)
            self.fh.SetBackgroundColour(self.txtctrl_color)
        self.Refresh()

    def OnStimPolCheck(self, evt):
        self.showallpol = self.cb.GetValue()

    def OnUseNoiseFloorCheck(self, evt):
        self.useNoiseFloor = self.nfcb.GetValue()

    def OnOverwriteOnSaveCheck(self, evt):
        self.overwriteOnSave = self.owcb.GetValue()

    def OnAutoRestoreCheck(self, evt):
        self.useNoiseFloor = self.arcb.GetValue()

    def OnOk(self, evt):
        if self.Validate():
            self.EndModal(wx.ID_OK)
            self.file.SetVariables(startdir=self.dbb.GetValue())
            self.file.UpdateConfig()
            self.filter.SetVariables(ftype=self.ftype.GetString(self.ftype.GetSelection()),
                    fl=int(self.fl.GetValue()), fh=int(self.fh.GetValue()), N=int(self.ford.GetValue()))
            self.filter.UpdateConfig()
            self.showallpol.SetVariables(value=self.cb.GetValue())
            self.showallpol.UpdateConfig()
            self.minlatency.SetVariables(value=float(self.mlb.GetValue()))
            self.minlatency.UpdateConfig()
            self.baselinewin.SetVariables(value=float(self.blw.GetValue()))
            self.baselinewin.UpdateConfig()
            self.timeRangeMin.SetVariables(
                value=self._optional_float(self.tminb.GetValue(), 0.0))
            self.timeRangeMin.UpdateConfig()
            self.timeRangeMax.SetVariables(
                value=self._optional_float(self.tmaxb.GetValue(), ''))
            self.timeRangeMax.UpdateConfig()
            self.useNoiseFloor.SetVariables(value=self.nfcb.GetValue())
            self.useNoiseFloor.UpdateConfig()
            self.overwriteOnSave.SetVariables(value=self.owcb.GetValue())
            self.overwriteOnSave.UpdateConfig()
            self.autoRestore.SetVariables(value=self.arcb.GetValue())
            self.autoRestore.UpdateConfig()
            self.plotting.SetVariables(addGridlines=self.gridcb.GetValue())
            self.plotting.UpdateConfig()
            self.expectedPeaks.SetVariables(value=int(self.expectedPeakChoice.GetStringSelection()))
            self.expectedPeaks.UpdateConfig()
            self.peakVisibility.SetVariables({
                '%s%d' % (prefix, i + 1): cb.GetValue()
                for prefix, cbs in (('p', self.pcbs), ('n', self.ncbs))
                for i, cb in enumerate(cbs)
            })
            self.peakVisibility.UpdateConfig()


    def Validate(self):
        msg = []
        flag = False

        if not hasattr(self, 'dbb_color'):
            self.dbb_color = self.dbb.GetBackgroundColour()
        if not hasattr(self, 'txtctrl_color'):
            self.txtctrl_color = self.fl.GetBackgroundColour()

        if not os.path.exists(self.dbb.GetValue()):
            msg.append("Directory does not exist")
            flag = True
            self.dbb.SetBackgroundColour("Pink")
        else:    
            self.dbb.SetBackgroundColour(self.dbb_color)

        fl = self.fl.GetValue()
        fh = self.fh.GetValue()
        ftype = self.ftype.GetString(self.ftype.GetSelection())

        if ftype != 'None' and fl == '':
            msg.append("Must specify a value for the lowpass frequency")
            self.fl.SetBackgroundColour("Pink")
            flag = True
        else:    
            self.fl.SetBackgroundColour(self.txtctrl_color)
        if ftype != 'None' and fh == '':
            msg.append("Must specify a value for the highpass frequency")
            self.fh.SetBackgroundColour("Pink")
            flag = True
        else:    
            self.fh.SetBackgroundColour(self.txtctrl_color)

        if fl != '' and fh != '' and ftype != 'None':
            if not int(self.fl.GetValue()) > int(self.fh.GetValue()):
                msg.append("Lowpass freq must be greater than highpass freq")
                flag = True
                self.fl.SetBackgroundColour("Pink")
                self.fh.SetBackgroundColour("Pink")
            else:    
                self.fl.SetBackgroundColour(self.txtctrl_color)
                self.fh.SetBackgroundColour(self.txtctrl_color)
        
#        minlatency = self.mlb.GetValue()

        if flag:
            self.Refresh()
            wx.MessageBox("\n".join(msg), "Error")

        return not flag    

    def ftype_choice(self, evt):
        ftype = evt.GetString()
        self._set_filter_enabled(ftype)
        self.ford_info.SetLabel(self._get_rolloff_label(self.ford.GetValue(), ftype))

    def _get_rolloff_label(self, N, ftype=None):
        if ftype == 'None':
            return "(0 dB/oct effective)"
        try:
            rolloff = int(N) * 12
            return f"({rolloff} dB/oct effective)"
        except (ValueError, TypeError):
            return ""

    def OnOrderChanged(self, evt):
        ftype = self.ftype.GetString(self.ftype.GetSelection())
        self.ford_info.SetLabel(self._get_rolloff_label(self.ford.GetValue(), ftype))

#----------------------------------------------------------------------------

class PhysiologyValidator(wx.PyValidator):

    def __init__(self):
        wx.PyValidator.__init__(self)

    def Clone(self):
        return PhysiologyValidator()

    def TransferToWindow(self):
        return True

    def TransferFromWindow(self):
        return True

#----------------------------------------------------------------------------
class FrequencyValidator(PhysiologyValidator):

    def __init__(self):
        PhysiologyValidator.__init__(self)
        self.Bind(wx.EVT_CHAR, self.OnChar)

    def Validate(self, win):
        tc = self.GetWindow()
        val = tc.GetValue()
        
        for x in val:
            if x not in string.digits:
                return False
        return True

    def Clone(self):
        return FrequencyValidator()

    def OnChar(self, evt):
        key = evt.GetKeyCode()
        
        if key < wx.WXK_SPACE or key == wx.WXK_DELETE or key > 255:
            evt.Skip()
            return

        if chr(key) in string.digits:
            evt.Skip()
            return

        return

#----------------------------------------------------------------------------

class FileValidator(PhysiologyValidator):

    def __init__(self):
        wx.PyValidator.__init__(self)

    def Clone(self):
        return FileValidator()

    def Validate(self, win):
        tc = self.GetWindow()
        val = tc.GetValue()
        return os.path.exists(val)

#----------------------------------------------------------------------------
class MinLatencyValidator(PhysiologyValidator):

    def __init__(self):
        PhysiologyValidator.__init__(self)
        self.Bind(wx.EVT_CHAR, self.OnChar)

    def Validate(self, win):
        tc = self.GetWindow()
        val = tc.GetValue()
        
#        for x in val:
#            if x not in string.digits:
#                return False
        return True

    def Clone(self):
        return MinLatencyValidator()

    def OnChar(self, evt):
        key = evt.GetKeyCode()
        evt.Skip()
        
        
#        if key < wx.WXK_SPACE or key == wx.WXK_DELETE or key > 255:
#            evt.Skip()
#            return
#
#        if chr(key) in string.digits:
#            evt.Skip()
#            return

        return

#----------------------------------------------------------------------------

class PhysiologySplashScreen(wx.adv.SplashScreen):

    def __init__(self, parent=None, duration=3000):
        # splash_bitmap = os.path.join(os.path.split(sys.argv[0])[0], "splash.png")
        splash_bitmap = os.path.join(os.path.dirname(__file__), "splash.png")
        bitmap = wx.Image(name=splash_bitmap).ConvertToBitmap()
        style = wx.adv.SPLASH_CENTRE_ON_SCREEN | wx.adv.SPLASH_TIMEOUT
        wx.adv.SplashScreen.__init__(self, bitmap, style, duration, parent)
        self.Bind(wx.EVT_CLOSE, self.OnExit)

    def OnExit(self, evt):
        self.Hide()
        evt.Skip()

#----------------------------------------------------------------------------

class AutomaticFrame(PersistentFrame):

    def __init__(self, runs, name="AutomaticFrame", parent=None,
            params=None, *args, **kwargs):

        PersistentFrame.__init__(self, name, parent, *args, **kwargs)

        #Initialize menu
        menubar = wx.MenuBar()
        file = wx.Menu()
        file.Append(wx.ID_EXIT, '&Quit\tCtrl+Q', 'Quit Application')
        menubar.Append(file, '&File')
        self.SetMenuBar(menubar)

        #Menu events
        self.Bind(wx.EVT_MENU, self.OnQuit, id=wx.ID_EXIT)
        self.Bind(wx.EVT_CLOSE, self.OnQuit)

        self.view = MatplotlibPanel(self, 'Time (msec)', 'Amplitude (uV)', 
                figsize=(9,8))
#        pubsub.Publisher().subscribe(self.next, "DATA SAVED")
#        pubsub.Publisher().subscribe(self.next, "NEXT")
#        pubsub.Publisher().subscribe(self.undo, "UNDO")

        self.CreateStatusBar()

        self.runs = runs
        self.current = -1
        self.params = params

        self.next()
        self.Show()

    def next(self, evt=None):
        self.view.subplot.cla()
        self.current += 1
        if self.current >= len(self.runs):
            self.SetStatusText('No more runs to analyze')
        else:
            model = loadmodel(self.runs[self.current]['data'],
                    self.params.invert)
            self.presenter = WaveformPresenter(None, self.view,
                    WaveformInteractor())
            self.presenter.load(model, self.params)
            self.SetStatusText('Loaded %r - %.2f kHz' % (model.location,
                model.freq)) 

    def undo(self, evt=None):
        if self.current > 0:
            self.current -= 2
            self.next()
