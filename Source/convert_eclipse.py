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


def split_datetime(value):
    parts = value.split(None, 1)
    if len(parts) == 2:
        return parts
    raise ValueError(f"Could not parse Eclipse date/time: {value}")


def parse_time(value):
    for fmt in ('%H:%M:%S', '%H:%M', '%I:%M:%S %p', '%I:%M %p'):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    raise ValueError(f"Could not parse Eclipse time: {value}")


def filename_part(value):
    return value.replace(': ', '-').replace(':', '-').replace('/', '-')

#-------------------------------------------------------------------------------

TEMPLATE_FIELDS = ['ID', 'Eclipse ID', 'Channel', 'Timestamp', 'Label']


def channel_labels(file_path):
    headers, rows = read_csv_file(file_path)
    if rows is None:
        return []
    idx = headers.index('Tr_Name')
    return sorted(set(row[idx] for row in rows if idx < len(row) and row[idx]))


def template_timestamps(file_path):
    headers, rows = read_csv_file(file_path)
    if rows is None:
        return []
    records = create_records_from_rows(headers, rows)
    return sorted(set(record_timestamp(record) for record in records))


def template_timestamp_rows(file_path):
    headers, rows = read_csv_file(file_path)
    if rows is None:
        return []
    records = create_records_from_rows(headers, rows)
    return sorted(set((record.Tr_Name, record_timestamp(record))
                      for record in records))


def read_template_csv(path):
    with open(path, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or any(c not in reader.fieldnames for c in TEMPLATE_FIELDS):
            raise ValueError('Template CSV must contain columns: %s' %
                             ', '.join(TEMPLATE_FIELDS))
        return [_template_row(row) for row in reader]


def write_template_csv(path, rows):
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=TEMPLATE_FIELDS)
        writer.writeheader()
        writer.writerows(non_empty_template_rows(rows))


def non_empty_template_rows(rows):
    return [row for row in (_template_row(row) for row in rows)
            if any(row.values())]


def normalize_template_rows(rows, available_channels=None):
    available_channels = (set(available_channels)
                          if available_channels is not None else None)
    result = []
    for row_i, row in enumerate(rows, start=1):
        row = _template_row(row)
        if not any(row.values()):
            continue
        if not row['Eclipse ID']:
            raise ValueError(f'Template row {row_i}: Eclipse ID is required.')
        if not row['Timestamp']:
            raise ValueError(f'Template row {row_i}: Timestamp is required.')
        if not row['Channel']:
            raise ValueError(f'Template row {row_i}: Channel is required.')
        if (available_channels is not None and
                row['Channel'] not in available_channels):
            raise ValueError(
                f'Template row {row_i}: Channel "{row["Channel"]}" '
                'was not found in selected files.'
            )
        row['Timestamp'] = normalize_template_timestamp(row['Timestamp'], row_i)
        result.append(row)
    if not result:
        raise ValueError('Add at least one template row.')
    return result


def _template_row(row):
    return {field: str(row.get(field, '') or '').strip()
            for field in TEMPLATE_FIELDS}


def normalize_template_timestamp(value, row_i):
    try:
        return datetime.strptime(value.strip(), '%H:%M:%S').strftime('%H:%M:%S')
    except ValueError as e:
        raise ValueError(
            f'Template row {row_i}: Timestamp must be HH:MM:SS.'
        ) from e


def record_datetime_parts(record):
    date_part, time_part = split_datetime(record.Date_Time)
    time = parse_time(time_part)
    return f"{date_part.replace('-', '/')} {time.strftime('%I:%M %p')}", time


def record_timestamp(record):
    return record_datetime_parts(record)[1].strftime('%H:%M:%S')


def eclipse_id_matches(filename_stem, eclipse_id):
    stem = filename_stem.lower()
    eclipse_id = eclipse_id.strip()
    if eclipse_id.lower() in stem:
        return True
    if eclipse_id.isdigit():
        return normalize_numeric_id(eclipse_id) in stem
    return False


def normalize_numeric_id(value):
    value = value.lstrip('0')
    return value if value else '0'


def template_record_name(row):
    parts = [row['ID'], row['Eclipse ID'], row['Timestamp'],
             row['Label'], row['Channel']]
    return '_'.join(filename_part(part) for part in parts if part)


def unique_path(path):
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    i = 2
    while True:
        candidate = f'{stem}_{i}{ext}'
        if not os.path.exists(candidate):
            return candidate
        i += 1


def write_record(record, out_path):
    date_str, _ = record_datetime_parts(record)

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

    template.write(out_path)


def template_written_files(file_path, output_folder, records, template_rows):
    filename_stem = os.path.splitext(os.path.basename(file_path))[0]
    rows = [row for row in template_rows
            if eclipse_id_matches(filename_stem, row['Eclipse ID'])]
    written = []
    for record in records:
        timestamp = record_timestamp(record)
        for row in rows:
            if (row['Timestamp'] != timestamp or
                    row['Channel'] != getattr(record, 'Tr_Name', None)):
                continue
            out_path = os.path.join(output_folder,
                                    template_record_name(row) + '.tsv')
            out_path = unique_path(out_path)
            write_record(record, out_path)
            written.append(out_path)
    return written


def main(file_path, output_folder=None, channel_labels=None, template_rows=None,
         available_channels=None):
    output_folder = output_folder or os.path.dirname(file_path)
    if not os.path.isdir(output_folder):
        raise ValueError(f"Output folder does not exist: {output_folder}")

    headers, rows = read_csv_file(file_path)
    if rows is None:
        return []

    records = create_records_from_rows(headers, rows)
    if template_rows is not None:
        return template_written_files(
            file_path, output_folder, records,
            normalize_template_rows(template_rows, available_channels),
        )

    if channel_labels is not None:
        channel_labels = set(channel_labels)
        records = [r for r in records
                   if getattr(r, 'Tr_Name', None) in channel_labels]

    originalname = os.path.splitext(os.path.basename(file_path))[0]
    written = []

    for record in records:

        _, time = record_datetime_parts(record)
        time_str = time.strftime('%H-%M-%S')
        recordname = f"{originalname}_{time_str}_{filename_part(record.Tr_Name)}"
        print(f"Converting {recordname} to a .tsv ABR file")

        out_path = os.path.join(output_folder, recordname + '.tsv')
        write_record(record, out_path)
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
