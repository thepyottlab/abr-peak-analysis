import csv
import os
import sqlite3
try:
    import wx
except ImportError:
    wx = None

from source_files import SOURCE_WILDCARD, find_source_files, is_source_file


SQLITE_PATTERN = '-analyzed.sqlite'

THRESHOLD_FIELDS = ['filename', 'frequency', 'estimation_method', 'threshold']
PEAK_FIELDS = ['filename', 'level', 'frequency', 'wave_label', 'p_amplitude', 'p_latency']
WAVEFORM_FIELDS = ['filename', 'level', 'frequency', 'filter', 'latency', 'amplitude']


def find_analyzed_files(folder):
    if not os.path.isdir(folder):
        raise ValueError(f'Folder does not exist: {folder}')

    paths = []
    for root, _, files in os.walk(folder):
        for filename in files:
            if filename.startswith('.'):
                continue
            if filename.lower().endswith(SQLITE_PATTERN):
                paths.append(os.path.join(root, filename))
    return sorted(paths)


def export_sqlite_files(paths, output_folder, thresholds=True, peaks=True, waveforms=True,
                        identifier=''):
    paths = sorted(set(paths))
    if not paths:
        raise ValueError('No SQLite analysis files selected.')
    if not any((thresholds, peaks, waveforms)):
        raise ValueError('Select at least one dataset to export.')
    if not os.path.isdir(output_folder):
        raise ValueError(f'Output folder does not exist: {output_folder}')

    written = {}
    if thresholds:
        rows = []
        for path in paths:
            rows.extend(threshold_rows(path))
        written['thresholds'] = _write_csv(
            output_folder, 'thresholds.csv', THRESHOLD_FIELDS, rows, identifier)
    if peaks:
        rows = []
        for path in paths:
            rows.extend(peak_rows(path))
        written['peaks'] = _write_csv(output_folder, 'peaks.csv', peak_fields(rows), rows, identifier)
    if waveforms:
        rows = []
        for path in paths:
            rows.extend(waveform_rows(path))
        written['waveforms'] = _write_csv(
            output_folder, 'waveforms.csv', WAVEFORM_FIELDS, rows, identifier)
    return written


def export_source_files(paths, output_folder, identifier=''):
    paths = sorted(set(p for p in paths if is_source_file(p)))
    if not paths:
        raise ValueError('No source data files selected.')
    if not os.path.isdir(output_folder):
        raise ValueError(f'Output folder does not exist: {output_folder}')

    rows = []
    for path in paths:
        rows.extend(source_waveform_rows(path))
    return {
        'waveforms': _write_csv(
            output_folder, 'waveforms.csv', WAVEFORM_FIELDS, rows, identifier)
    }


def export_model_waveforms(model, output_folder=None):
    source = getattr(model, 'filename', '')
    output_folder = output_folder or os.path.dirname(source) or os.getcwd()
    if not os.path.isdir(output_folder):
        raise ValueError(f'Output folder does not exist: {output_folder}')

    identifier = os.path.splitext(os.path.basename(source))[0]
    return _write_csv(
        output_folder, 'waveforms.csv', WAVEFORM_FIELDS,
        model_waveform_rows(model), identifier)


def model_waveform_rows(model):
    import analysis_sqlite

    filename = os.path.splitext(os.path.basename(getattr(model, 'filename', '')))[0]
    settings = getattr(model, 'filter_settings', None)
    filter_name = analysis_sqlite.filter_label(settings) if settings else 'none'
    rows = []
    for waveform in model.series:
        for latency, amplitude in zip(waveform.x, waveform.y):
            rows.append({
                'filename': filename,
                'level': waveform.level,
                'frequency': model.freq,
                'filter': filter_name,
                'latency': float(latency),
                'amplitude': float(amplitude),
            })
    return rows


def source_waveform_rows(path):
    model = _load_source_model(path)
    filename = os.path.splitext(os.path.basename(getattr(model, 'filename', path)))[0]
    rows = []
    for waveform in model.series:
        for latency, amplitude in zip(waveform.x, waveform.y):
            rows.append({
                'filename': filename,
                'level': waveform.level,
                'frequency': model.freq,
                'filter': 'none',
                'latency': float(latency),
                'amplitude': float(amplitude),
            })
    return rows


def _load_source_model(path):
    from datafile import loadabr
    from datatype import ABRStimPolarity
    return loadabr(path, filter=False, polarity=ABRStimPolarity.Avg,
                   noiseFloor=False, t_min=0, t_max=0)


def threshold_rows(path):
    with _connect(path) as db:
        rows = db.execute('''
            SELECT filename, frequency, threshold_method, threshold
            FROM analysis
            ORDER BY filename, frequency
        ''')
        return [{
            'filename': row['filename'],
            'frequency': row['frequency'],
            'estimation_method': row['threshold_method'],
            'threshold': row['threshold'],
        } for row in rows]


def peak_rows(path):
    with _connect(path) as db:
        rows = db.execute('''
            SELECT a.filename, l.level, a.frequency, p.wave_label,
                   p.point_type, p.latency, p.amplitude
            FROM peaks AS p
            JOIN levels AS l ON l.id = p.level_id
            JOIN analysis AS a ON a.id = l.analysis_id
            ORDER BY a.filename, a.frequency, l.level, p.wave_label, p.point_type
        ''')
        result = {}
        for row in rows:
            data = dict(row)
            key = (data['filename'], data['level'], data['frequency'], data['wave_label'])
            point = result.setdefault(key, {
                'filename': data['filename'],
                'level': data['level'],
                'frequency': data['frequency'],
                'wave_label': data['wave_label'],
            })
            prefix = 'p' if data['point_type'] == 'peak' else 'n'
            latency = data['latency']
            amplitude = data['amplitude']
            if latency is None or latency < 0:
                latency = None
                amplitude = None
            point[f'{prefix}_amplitude'] = amplitude
            point[f'{prefix}_latency'] = latency
        return list(result.values())


def peak_fields(rows):
    fields = list(PEAK_FIELDS)
    if any('n_amplitude' in row or 'n_latency' in row for row in rows):
        fields.extend(['n_amplitude', 'n_latency'])
    return fields


def waveform_rows(path):
    with _connect(path) as db:
        rows = db.execute('''
            SELECT a.filename, l.level, a.frequency, a.filter_label AS filter,
                   w.latency, w.amplitude
            FROM waveform_points AS w
            JOIN levels AS l ON l.id = w.level_id
            JOIN analysis AS a ON a.id = l.analysis_id
            ORDER BY a.filename, a.frequency, l.level, w.sample_index
        ''')
        return [dict(row) for row in rows]


def _connect(path):
    if not os.path.isfile(path):
        raise ValueError(f'File does not exist: {path}')
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    try:
        db.execute('SELECT 1 FROM analysis LIMIT 1')
    except sqlite3.Error as e:
        db.close()
        raise ValueError(f'Not a valid analysis SQLite file: {path}') from e
    return db


def _write_csv(output_folder, filename, fields, rows, identifier=''):
    filename = _output_filename(identifier, filename)
    path = os.path.join(output_folder, filename)
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    return path, len(rows)


def _output_filename(identifier, filename):
    identifier = identifier.strip()
    if not identifier:
        return filename
    identifier = identifier.replace(os.sep, '_')
    if os.altsep:
        identifier = identifier.replace(os.altsep, '_')
    return '%s_%s' % (identifier, filename)


ExportDialogBase = wx.Dialog if wx is not None else object


class ExportDialog(ExportDialogBase):

    def __init__(self, parent, default_folder):
        if wx is None:
            raise RuntimeError('wxPython is required for export.')
        wx.Dialog.__init__(self, parent, title='Export', size=(700, 540))
        self.paths = []
        self.output_folder = default_folder if os.path.isdir(default_folder) else os.getcwd()

        sizer = wx.BoxSizer(wx.VERTICAL)

        self.mode = wx.RadioBox(
            self, wx.ID_ANY, 'Export Mode',
            choices=['Analyzed Data', 'Source Data'],
            majorDimension=2,
            style=wx.RA_SPECIFY_COLS,
        )
        sizer.Add(self.mode, 0, wx.EXPAND | wx.ALL, 5)

        options = wx.StaticBoxSizer(wx.StaticBox(self, wx.ID_ANY, 'Datasets'), wx.HORIZONTAL)
        self.thresholds = wx.CheckBox(self, wx.ID_ANY, 'Thresholds')
        self.peaks = wx.CheckBox(self, wx.ID_ANY, 'Peaks')
        self.waveforms = wx.CheckBox(self, wx.ID_ANY, 'Waveforms')
        for cb in (self.thresholds, self.peaks, self.waveforms):
            cb.SetValue(True)
            options.Add(cb, 0, wx.ALL, 5)
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

        ident = wx.StaticBoxSizer(wx.StaticBox(self, wx.ID_ANY, 'Output Identifier'), wx.HORIZONTAL)
        self.identifier = wx.TextCtrl(self, wx.ID_ANY, '')
        ident.Add(self.identifier, 1, wx.EXPAND | wx.ALL, 5)
        sizer.Add(ident, 0, wx.EXPAND | wx.ALL, 5)

        out = wx.StaticBoxSizer(wx.StaticBox(self, wx.ID_ANY, 'Output Folder'), wx.HORIZONTAL)
        self.output = wx.TextCtrl(self, wx.ID_ANY, self.output_folder)
        browse = wx.Button(self, wx.ID_ANY, 'Browse')
        out.Add(self.output, 1, wx.EXPAND | wx.ALL, 5)
        out.Add(browse, 0, wx.ALL, 5)
        sizer.Add(out, 0, wx.EXPAND | wx.ALL, 5)

        actions = wx.StdDialogButtonSizer()
        export = wx.Button(self, wx.ID_OK, 'Export')
        cancel = wx.Button(self, wx.ID_CANCEL)
        actions.AddButton(export)
        actions.AddButton(cancel)
        actions.Realize()
        sizer.Add(actions, 0, wx.EXPAND | wx.ALL, 5)

        self.SetSizer(sizer)
        self.mode.Bind(wx.EVT_RADIOBOX, self.on_mode)
        add_folder.Bind(wx.EVT_BUTTON, self.on_add_folder)
        add_files.Bind(wx.EVT_BUTTON, self.on_add_files)
        clear.Bind(wx.EVT_BUTTON, self.on_clear)
        browse.Bind(wx.EVT_BUTTON, self.on_browse_output)
        export.Bind(wx.EVT_BUTTON, self.on_export)
        self.update_dataset_options()

    def on_add_folder(self, evt):
        if self.is_source_mode():
            message = 'Choose a folder containing source data files:'
        else:
            message = 'Choose a folder containing SQLite analysis files:'
        dlg = wx.DirDialog(self, message,
                           defaultPath=self.output_folder,
                           style=wx.DD_DIR_MUST_EXIST | wx.DD_CHANGE_DIR)
        try:
            if dlg.ShowModal() == wx.ID_OK:
                folder = dlg.GetPath()
                if self.is_source_mode():
                    self.add_paths(find_source_files(folder))
                else:
                    self.add_paths(find_analyzed_files(folder))
                self.output.SetValue(folder)
        finally:
            dlg.Destroy()

    def on_add_files(self, evt):
        if self.is_source_mode():
            message = 'Choose source data files:'
            wildcard = SOURCE_WILDCARD
        else:
            message = 'Choose SQLite analysis files:'
            wildcard = 'SQLite analysis files|*-analyzed.sqlite|SQLite files|*.sqlite'
        dlg = wx.FileDialog(
            self,
            message,
            wildcard=wildcard,
            style=wx.FD_OPEN | wx.FD_MULTIPLE | wx.FD_FILE_MUST_EXIST,
        )
        try:
            if dlg.ShowModal() == wx.ID_OK:
                self.add_paths(dlg.GetPaths())
                if dlg.GetPaths():
                    self.output.SetValue(os.path.dirname(dlg.GetPaths()[0]))
        finally:
            dlg.Destroy()

    def on_clear(self, evt):
        self.paths = []
        self.refresh_list()

    def on_mode(self, evt):
        self.paths = []
        self.refresh_list()
        self.update_dataset_options()

    def on_browse_output(self, evt):
        dlg = wx.DirDialog(self, 'Choose an output folder:',
                           defaultPath=self.output.GetValue(),
                           style=wx.DD_DIR_MUST_EXIST | wx.DD_CHANGE_DIR)
        try:
            if dlg.ShowModal() == wx.ID_OK:
                self.output.SetValue(dlg.GetPath())
        finally:
            dlg.Destroy()

    def on_export(self, evt):
        try:
            if self.is_source_mode():
                written = export_source_files(
                    self.paths,
                    self.output.GetValue(),
                    identifier=self.identifier.GetValue(),
                )
            else:
                written = export_sqlite_files(
                    self.paths,
                    self.output.GetValue(),
                    thresholds=self.thresholds.GetValue(),
                    peaks=self.peaks.GetValue(),
                    waveforms=self.waveforms.GetValue(),
                    identifier=self.identifier.GetValue(),
                )
        except Exception as e:
            wx.MessageBox(str(e), 'Export Error', wx.OK | wx.ICON_ERROR)
            return

        lines = [f'{os.path.basename(path)}: {count} rows'
                 for _, (path, count) in sorted(written.items())]
        wx.MessageBox('\n'.join(lines), 'Export Complete', wx.OK | wx.ICON_INFORMATION)
        self.EndModal(wx.ID_OK)

    def add_paths(self, paths):
        if self.is_source_mode():
            selected = [p for p in paths if is_source_file(p)]
        else:
            selected = [p for p in paths if p.lower().endswith('.sqlite')]
        self.paths = sorted(set(self.paths + selected))
        self.refresh_list()

    def refresh_list(self):
        self.list.DeleteAllItems()
        for path in self.paths:
            idx = self.list.InsertItem(self.list.GetItemCount(), os.path.basename(path))
            self.list.SetItem(idx, 1, os.path.dirname(path))

    def is_source_mode(self):
        return self.mode.GetSelection() == 1

    def update_dataset_options(self):
        source = self.is_source_mode()
        self.thresholds.Show(not source)
        self.peaks.Show(not source)
        self.thresholds.SetValue(not source)
        self.peaks.SetValue(not source)
        self.waveforms.SetValue(True)
        self.waveforms.Enable(not source)
        self.Layout()


def export_with_dialog(parent=None, default_folder='.'):
    if wx is None:
        raise RuntimeError('wxPython is required for export.')
    dialog = ExportDialog(parent, default_folder)
    try:
        return dialog.ShowModal() == wx.ID_OK
    finally:
        dialog.Destroy()


def merge_analyzed_files(folder, output_filename=None):
    output_folder = os.path.dirname(output_filename) if output_filename else folder
    return export_sqlite_files(find_analyzed_files(folder), output_folder)


if __name__ == '__main__':
    if wx is None:
        raise RuntimeError('wxPython is required for export.')
    app = wx.App(False)
    export_with_dialog(default_folder=os.getcwd())
