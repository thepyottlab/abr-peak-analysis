import csv
import numpy as np
import os
import wx
from datetime import datetime


def select_file():
    dlg = wx.FileDialog(None, message="Select dataset",
                        wildcard="csv files (*.csv)|*.csv",
                        style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
    file_path = dlg.GetPath() if dlg.ShowModal() == wx.ID_OK else None
    dlg.Destroy()
    return file_path

#-------------------------------------------------------------------------------

class TSVTemplate(object):
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
            Recording date and time.
        levels : list of int
            Stimulus intensity levels in dB SPL.
        stimulus_frequency : str
            Stimulus mode from the Eclipse export.
        stimulus_waveform : str
            Stimulus mode from the Eclipse export.
        response_window : float
            Recording window duration in ms, derived from sample interval
            and sample count: sample_interval_ms * n_samples.
        response_fs : float
            Sampling rate in Hz, derived from sampling period:
            1 / (sample_interval_ms * 1e-3).
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
            self._header_line('[Eclipse ABR]', t),
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

def clean(value):
    return value.strip().strip('"')


def read_csv_file(file_path):
    try:
        print("Loading data...")
        with open(file_path, 'r', newline='') as f:
            lines = list(csv.reader(f))

        for header_i, line in enumerate(lines):
            headers = [h.strip() for h in line]
            if 'Date Time' in headers:
                break
        else:
            raise ValueError("Could not find Eclipse header row")

        headers = [h.replace(' ', '_') for h in headers]
        rows = [[clean(v) for v in line] for line in lines[header_i + 1:] if line]
        return headers, rows

    except FileNotFoundError:
        print(f"File not found: {file_path}")
        return None, None


def create_records_from_rows(headers, rows):
    print("Transforming Eclipse file into an ABR object...")

    sample_start_idx = headers.index('0')

    records = []
    for row in rows:
        kwargs = {headers[i]: row[i] for i in range(min(len(headers), len(row)))}
        record = Record(**kwargs)

        n_samples = int(to_numeric(record.Samples))
        record.raw_data.extend(row[i] for i in range(sample_start_idx,
                                                     sample_start_idx + n_samples))
        records.append(record)

    return records


def to_numeric(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return np.nan


def parse_datetime(value):
    for fmt in ('%m-%d-%Y %H:%M:%S', '%m/%d/%Y %I:%M %p'):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    raise ValueError(f"Could not parse Eclipse date/time: {value}")


def filename_part(value):
    return value.replace(': ', '-').replace(':', '-').replace('/', '-')

#-------------------------------------------------------------------------------

def main(file_path, output_folder=None):
    output_folder = output_folder or os.path.dirname(file_path)
    if not os.path.isdir(output_folder):
        raise ValueError(f"Output folder does not exist: {output_folder}")

    headers, rows = read_csv_file(file_path)
    if rows is None:
        return []

    records = create_records_from_rows(headers, rows)
    originalname = os.path.splitext(os.path.basename(file_path))[0]
    written = []

    for record in records:

        dt = parse_datetime(record.Date_Time)
        date_str = f"{dt.month}/{dt.day}/{dt.year} {dt.strftime('%I:%M %p')}"        
        time_str = dt.strftime('%I-%M-%S-%p')
        recordname = f"{originalname}_{time_str}_{filename_part(record.Tr_Name)}"
        print(f"Converting {recordname} to a .tsv ABR file")

        # Sampling rate from sampling period (ms)
        sample_interval = to_numeric(record.Sampl_Interval)  # ms
        response_fs     = 1 / (sample_interval * 1e-3)

        # Intensity level
        levels = [int(to_numeric(record.Set_Intensity))]

        # Raw data array (n_samples x n_levels)
        raw_array = np.full((len(record.raw_data), 1), np.nan)
        for row_i, val in enumerate(record.raw_data):
            raw_array[row_i, 0] = to_numeric(val)

        # Response window from sample count and sampling period (ms)
        response_window = sample_interval * int(to_numeric(record.Samples))

        # Fill in template and write file
        template = TSVTemplate(
            date=date_str,
            levels=levels,
            stimulus_frequency=record.Stim_Mode,
            stimulus_waveform=record.Stim_Mode,
            response_window=response_window,
            response_fs=response_fs,
            data=raw_array,
        )

        out_path = os.path.join(output_folder, recordname + '.tsv')
        template.write(out_path)
        written.append(out_path)

    print("Done! This window should close automatically")
    return written


def run():
    file_path = select_file()
    if file_path:
        main(file_path)


if __name__ == "__main__":
    app = wx.App(False)
    run()
    app.MainLoop()
