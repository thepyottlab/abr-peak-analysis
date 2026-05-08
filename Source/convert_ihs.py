import numpy as np
from datetime import datetime
import os
import wx


def select_file():
    dlg = wx.FileDialog(None, message="Select dataset",
                        wildcard="txt files (*.txt)|*.txt",
                        style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
    file_path = dlg.GetPath() if dlg.ShowModal() == wx.ID_OK else None
    dlg.Destroy()
    return file_path

#-------------------------------------------------------------------------------

class EPLTemplate(object):
    """Represents the structure of a CUSTOM ABR file.

    Header lines carry trailing tabs equal to (n_levels - 1) so every row
    has the same column width as the data section.

    Output format:
        [CUSTOM ABR]<tabs>
        Date=<date><tabs>
        Levels=<l1>;<l2>;...;<ln>;<tabs>
        [Params]<tabs>
        Stimulus.Frequency (kHz)=<freq><tabs>
        Stimulus.Waveform=<waveform><tabs>
        Response.Window (ms)=<window><tabs>
        Response.Fs (Hz)=<fs><tabs>
        [DATA]<tabs>
        <l1>\\t<l2>\\t...\\t<ln>
        <v1>\\t<v2>\\t...\\t<vn>
        ...
    """

    def __init__(self, date, levels, stimulus_frequency, stimulus_waveform,
                 response_window, response_fs, data):
        """
        Parameters
        ----------
        date : str
            Recording date and time, e.g. '1/29/2025 11:41 AM'.
        levels : list of int
            Stimulus intensity levels in dB SPL, sorted ascending.
        stimulus_frequency : float
            Stimulus frequency in kHz (0.0 for clicks).
        stimulus_waveform : str
            'FREQ' for tone pips, 'CLICK' for clicks.
        response_window : float
            Recording window duration in ms, derived from sampling period
            and sweep count: sample_interval_us * n_sweeps / 1000.
        response_fs : float
            Sampling rate in Hz, derived from sampling period:
            1 / (sample_interval_us * 1e-6).
        data : np.ndarray
            Shape (n_samples, n_levels). Columns must match order of levels.
        """
        self.date              = date
        self.levels            = levels
        self.stimulus_frequency = stimulus_frequency
        self.stimulus_waveform  = stimulus_waveform
        self.response_window   = response_window
        self.response_fs       = response_fs
        self.data              = data

    def _header_line(self, content, n_tabs):
        return content + '\t' * n_tabs

    def to_tsv(self):
        t = len(self.levels) - 1  # trailing tabs = data columns - 1
        levels_str = ';'.join(str(l) for l in self.levels) + ';'

        lines = [
            self._header_line('[CUSTOM ABR]', t),
            self._header_line(f'Date={self.date}', t),
            self._header_line(f'Levels={levels_str}', t),
            self._header_line('[Params]', t),
            self._header_line(f'Stimulus.Frequency (kHz)={self.stimulus_frequency}', t),
            self._header_line(f'Stimulus.Waveform={self.stimulus_waveform}', t),
            self._header_line(f'Response.Window (ms)={self.response_window}', t),
            self._header_line(f'Response.Fs (Hz)={self.response_fs}', t),
            self._header_line('[DATA]', t),
            '\t'.join(str(l) for l in self.levels),
        ]
        for row in self.data:
            lines.append('\t'.join('' if np.isnan(v) else str(v) for v in row))

        return '\n'.join(lines) + '\n'

    def write(self, filepath):
        with open(filepath, 'w', newline='') as f:
            f.write(self.to_tsv())

#-------------------------------------------------------------------------------

class Record(object):

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.raw_data = []

#-------------------------------------------------------------------------------

def read_txt_file(file_path):
    try:
        print("Loading data...")
        with open(file_path, 'r') as f:
            first_line = f.readline()
            separator = '|' if '|' in first_line else '\t'
            f.seek(0)
            lines = [line.strip().split(separator) for line in f]

        max_fields = max(len(line) for line in lines)
        padded_lines = [line + [None] * (max_fields - len(line)) for line in lines]

        headers = padded_lines[0]
        for i, h in enumerate(headers):
            if h is None or h.strip() == '':
                headers[i] = f'Unnamed {i + 1}'

        return headers, padded_lines[1:]

    except FileNotFoundError:
        print(f"File not found: {file_path}")
        return None, None


def process_records(headers, rows, stim_freq_replace=('--', ' -- '),
                    stim_freq_value='0'):
    print("Formatting data...")

    headers = [h.replace('.', '_') for h in headers]
    if 'Intesity' in headers:
        headers[headers.index('Intesity')] = 'Intensity'

    stim_idx = headers.index('StimFreq')
    id_idx   = headers.index('SystemID')
    int_idx  = headers.index('Intensity')

    seen = {}
    for row in rows:
        if row[stim_idx] in stim_freq_replace:
            row[stim_idx] = stim_freq_value
        key = (row[id_idx], row[stim_idx], row[int_idx])
        seen[key] = row

    return headers, list(seen.values())


def create_records_from_rows(headers, rows):
    print("Transforming IHS file into an ABR object...")

    named_idx   = [i for i, h in enumerate(headers) if not h.startswith('Unnamed')]
    unnamed_idx = [i for i, h in enumerate(headers) if h.startswith('Unnamed')]
    named_hdrs  = [headers[i] for i in named_idx]

    records = []
    for row in rows:
        kwargs = {named_hdrs[j]: row[named_idx[j]] for j in range(len(named_idx))}
        record = Record(**kwargs)

        raw_val = kwargs.get('Raw Data (uV):')
        if raw_val is not None and raw_val != '':
            record.raw_data.append(raw_val)
        record.raw_data.extend(row[i] for i in unnamed_idx)

        records.append(record)

    return records


def group_records(records):
    grouped = {}
    for record in records:
        system_id = getattr(record, 'SystemID', None)
        stim_freq = getattr(record, 'StimFreq', None)
        if system_id and stim_freq:
            grouped.setdefault(system_id, {}).setdefault(stim_freq, []).append(record)
    return grouped


def to_numeric(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return np.nan

#-------------------------------------------------------------------------------

def main(file_path):
    headers, rows = read_txt_file(file_path)
    if rows is None:
        return

    headers, rows = process_records(headers, rows)
    records = create_records_from_rows(headers, rows)
    grouped = group_records(records)

    for system_id, stim_freq_dict in grouped.items():
        for stim_freq, rec_list in stim_freq_dict.items():

            rec_list.sort(key=lambda r: to_numeric(r.Intensity))

            # Date and time
            dt = datetime.strptime(
                f'{rec_list[0].Rec_Date} {rec_list[0].Rec_Time}',
                '%Y-%m-%d %H:%M:%S')
            date_str = dt.strftime('%-m/%-d/%Y %I:%M %p')

            # Frequency and waveform type
            if stim_freq == '0':
                frequency_khz     = 0.0
                stimulus_waveform = 'CLICK'
                frequency_name    = 'CLICK'
            else:
                frequency_khz     = to_numeric(stim_freq) / 1000
                stimulus_waveform = 'FREQ'
                frequency_name    = str(frequency_khz)

            recordname = f"{rec_list[0].SystemID} {frequency_name}"
            print(f"Converting {recordname} to an Eaton-Peabody file")

            # Sampling rate from sampling period (µs); response window from
            # period and sweep count
            sweeps          = max(to_numeric(r.Sweeps) for r in rec_list)
            sample_interval = to_numeric(rec_list[0].SamplingRate)  # µs
            response_fs     = 1 / (sample_interval * 1e-6)
            response_window = sample_interval * sweeps / 1000       # ms

            # Intensity levels
            levels = [int(to_numeric(r.Intensity)) for r in rec_list]

            # Raw data array (n_samples x n_levels)
            raw_columns = [r.raw_data for r in rec_list]
            n_rows = max(len(col) for col in raw_columns)
            raw_array = np.full((n_rows, len(raw_columns)), np.nan)
            for col_i, col in enumerate(raw_columns):
                for row_i, val in enumerate(col):
                    raw_array[row_i, col_i] = to_numeric(val)

            if np.all(np.isnan(raw_array[-1])):
                raw_array = raw_array[:-1]

            data_length = len(raw_array) // 2
            raw_array   = raw_array[data_length:]

            template = EPLTemplate(
                date=date_str,
                levels=levels,
                stimulus_frequency=frequency_khz,
                stimulus_waveform=stimulus_waveform,
                response_window=response_window,
                response_fs=response_fs,
                data=raw_array,
            )

            out_path = os.path.join(os.path.dirname(file_path),
                                    recordname + '.tsv')
            template.write(out_path)

    print("Done! This window should close automatically")


def run():
    file_path = select_file()
    if file_path:
        main(file_path)


if __name__ == "__main__":
    app = wx.App(False)
    run()
    app.MainLoop()