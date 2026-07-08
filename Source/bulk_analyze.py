import os

try:
    import wx
except ImportError:
    wx = None

import analysis_sqlite
from analysis_helpers import (
    guess_peaks,
    guess_troughs,
    load_model,
    visible_troughs_enabled,
)
from config import DefaultValueHolder
from datafile import POLARITY_UNSUPPORTED_MESSAGE, supports_stimulus_polarities
from datatype import ABRStimPolarity
from source_files import SOURCE_WILDCARD, find_source_files, is_source_file


def bulk_analyze_files(paths, thresholds=True, peaks=True, conflict_handler=None):
    paths = sorted(set(paths))
    if not paths:
        raise ValueError('No source data files selected.')

    result = {'saved': 0, 'skipped': 0, 'stopped': False, 'errors': []}
    apply_action = None

    for path in paths:
        try:
            polarities = _polarities_for(path)
        except Exception as e:
            result['errors'].append((path, str(e)))
            continue

        for polarity in polarities:
            try:
                model = load_model(path, polarity=polarity,
                                   useNoiseFloor=_use_noise_floor())
                conflicts = analysis_sqlite.selected_conflicts(
                    model, thresholds=thresholds, peaks=peaks)
                if conflicts:
                    action = apply_action
                    if action is None:
                        if conflict_handler is None:
                            action, apply_all = ('replace', False)
                        else:
                            action, apply_all = conflict_handler(
                                analysis_sqlite.analysis_path(model), conflicts)
                        if apply_all:
                            apply_action = action
                    if action == 'stop':
                        result['stopped'] = True
                        return result
                    if action == 'skip':
                        result['skipped'] += 1
                        continue

                if peaks:
                    guess_peaks(model)
                    if visible_troughs_enabled():
                        guess_troughs(model)
                if thresholds:
                    model.estimate_threshold()

                analysis_sqlite.save_selected(
                    model, thresholds=thresholds, peaks=peaks, waveforms=True)
                result['saved'] += 1
            except Exception as e:
                result['errors'].append((path, str(e)))

    return result


def _polarities_for(path):
    showallpol = DefaultValueHolder('PhysiologyNotebook', 'showallpol')
    showallpol.SetVariables(value=False)
    showallpol.InitFromConfig()
    if not showallpol.value:
        return [ABRStimPolarity.Avg]
    if not supports_stimulus_polarities(path):
        raise ValueError(POLARITY_UNSUPPORTED_MESSAGE)
    return [
        ABRStimPolarity.Condensation,
        ABRStimPolarity.Rarefaction,
    ]


def _use_noise_floor():
    use_noise_floor = DefaultValueHolder('PhysiologyNotebook', 'useNoiseFloor')
    use_noise_floor.SetVariables(value=False)
    use_noise_floor.InitFromConfig()
    return use_noise_floor.value


DialogBase = wx.Dialog if wx is not None else object


class BulkAnalyzeDialog(DialogBase):

    def __init__(self, parent, default_folder):
        if wx is None:
            raise RuntimeError('wxPython is required for bulk analysis.')
        wx.Dialog.__init__(self, parent, title='Bulk Analyze/Filter', size=(700, 420))
        self.paths = []
        self.default_folder = default_folder if os.path.isdir(default_folder) else os.getcwd()

        sizer = wx.BoxSizer(wx.VERTICAL)

        options = wx.StaticBoxSizer(wx.StaticBox(self, wx.ID_ANY, 'Datasets'), wx.HORIZONTAL)
        self.thresholds = wx.CheckBox(self, wx.ID_ANY, 'Thresholds')
        self.peaks = wx.CheckBox(self, wx.ID_ANY, 'Peaks')
        self.waveforms = wx.CheckBox(self, wx.ID_ANY, 'Waveforms')
        for cb in (self.thresholds, self.peaks, self.waveforms):
            cb.SetValue(True)
            options.Add(cb, 0, wx.ALL, 5)
        self.waveforms.Disable()
        sizer.Add(options, 0, wx.EXPAND | wx.ALL, 5)

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        add_folder = wx.Button(self, wx.ID_ANY, 'Add Folder')
        add_files = wx.Button(self, wx.ID_ANY, 'Add Files')
        clear = wx.Button(self, wx.ID_ANY, 'Clear')
        buttons.Add(add_folder, 0, wx.ALL, 5)
        buttons.Add(add_files, 0, wx.ALL, 5)
        buttons.Add(clear, 0, wx.ALL, 5)
        sizer.Add(buttons, 0, wx.ALL, 0)

        self.list = wx.ListCtrl(self, wx.ID_ANY, style=wx.LC_REPORT)
        self.list.InsertColumn(0, 'File')
        self.list.InsertColumn(1, 'Folder')
        self.list.SetColumnWidth(0, 240)
        self.list.SetColumnWidth(1, 420)
        sizer.Add(self.list, 1, wx.EXPAND | wx.ALL, 5)

        actions = wx.StdDialogButtonSizer()
        analyze = wx.Button(self, wx.ID_OK, 'Analyze')
        cancel = wx.Button(self, wx.ID_CANCEL)
        actions.AddButton(analyze)
        actions.AddButton(cancel)
        actions.Realize()
        sizer.Add(actions, 0, wx.EXPAND | wx.ALL, 5)

        self.SetSizer(sizer)
        add_folder.Bind(wx.EVT_BUTTON, self.on_add_folder)
        add_files.Bind(wx.EVT_BUTTON, self.on_add_files)
        clear.Bind(wx.EVT_BUTTON, self.on_clear)
        analyze.Bind(wx.EVT_BUTTON, self.on_analyze)

    def on_add_folder(self, evt):
        dlg = wx.DirDialog(self, 'Choose a folder containing source data files:',
                           defaultPath=self.default_folder,
                           style=wx.DD_DIR_MUST_EXIST | wx.DD_CHANGE_DIR)
        try:
            if dlg.ShowModal() == wx.ID_OK:
                folder = dlg.GetPath()
                self.add_paths(find_source_files(folder))
                self.default_folder = folder
        finally:
            dlg.Destroy()

    def on_add_files(self, evt):
        dlg = wx.FileDialog(
            self,
            'Choose source data files:',
            wildcard=SOURCE_WILDCARD,
            style=wx.FD_OPEN | wx.FD_MULTIPLE | wx.FD_FILE_MUST_EXIST,
        )
        try:
            if dlg.ShowModal() == wx.ID_OK:
                self.add_paths(dlg.GetPaths())
                if dlg.GetPaths():
                    self.default_folder = os.path.dirname(dlg.GetPaths()[0])
        finally:
            dlg.Destroy()

    def on_clear(self, evt):
        self.paths = []
        self.refresh_list()

    def on_analyze(self, evt):
        busy = False
        try:
            wx.BeginBusyCursor()
            busy = True
            result = bulk_analyze_files(
                self.paths,
                thresholds=self.thresholds.GetValue(),
                peaks=self.peaks.GetValue(),
                conflict_handler=self.ask_conflict,
            )
        except Exception as e:
            wx.MessageBox(str(e), 'Bulk Analyze Error', wx.OK | wx.ICON_ERROR)
            return
        finally:
            if busy:
                wx.EndBusyCursor()

        wx.MessageBox(_summary_text(result), 'Bulk Analyze Complete',
                      wx.OK | wx.ICON_INFORMATION)
        self.EndModal(wx.ID_OK)

    def ask_conflict(self, path, conflicts):
        dlg = ConflictDialog(self, path, conflicts)
        try:
            if dlg.ShowModal() == wx.ID_OK:
                return dlg.choice, dlg.apply_all.GetValue()
            return 'stop', False
        finally:
            dlg.Destroy()

    def add_paths(self, paths):
        self.paths = sorted(set(self.paths + [p for p in paths if is_source_file(p)]))
        self.refresh_list()

    def refresh_list(self):
        self.list.DeleteAllItems()
        for path in self.paths:
            idx = self.list.InsertItem(self.list.GetItemCount(), os.path.basename(path))
            self.list.SetItem(idx, 1, os.path.dirname(path))


class ConflictDialog(DialogBase):

    def __init__(self, parent, path, conflicts):
        wx.Dialog.__init__(self, parent, title='Bulk Analyze Conflict')
        self.choice = 'stop'

        data = ' and '.join(conflicts)
        filename = os.path.basename(path)
        message = (
            '%s already has %s data.\n\n'
            'Choose how Bulk Analyze/Filter should proceed.'
        ) % (filename, data)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(wx.StaticText(self, wx.ID_ANY, message), 0, wx.ALL, 10)
        self.apply_all = wx.CheckBox(self, wx.ID_ANY, 'Apply to All')
        sizer.Add(self.apply_all, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        for label, action in (('Stop', 'stop'), ('Skip', 'skip'), ('Replace', 'replace')):
            button = wx.Button(self, wx.ID_ANY, label)
            button.Bind(wx.EVT_BUTTON, lambda evt, a=action: self._choose(a))
            buttons.Add(button, 0, wx.ALL, 5)
        sizer.Add(buttons, 0, wx.ALIGN_RIGHT | wx.ALL, 5)
        self.SetSizerAndFit(sizer)

    def _choose(self, action):
        self.choice = action
        self.EndModal(wx.ID_OK)


def _summary_text(result):
    lines = [
        'Saved: %d' % result['saved'],
        'Skipped: %d' % result['skipped'],
    ]
    if result['stopped']:
        lines.append('Stopped before all files were processed.')
    if result['errors']:
        lines.append('Errors: %d' % len(result['errors']))
        for path, error in result['errors'][:5]:
            lines.append('%s: %s' % (os.path.basename(path), error))
    return '\n'.join(lines)


def analyze_with_dialog(parent=None, default_folder='.'):
    if wx is None:
        raise RuntimeError('wxPython is required for bulk analysis.')
    dialog = BulkAnalyzeDialog(parent, default_folder)
    try:
        return dialog.ShowModal() == wx.ID_OK
    finally:
        dialog.Destroy()
