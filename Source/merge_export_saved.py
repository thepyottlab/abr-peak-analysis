import csv
import os
import re
import wx


ANALYZED_PATTERN = re.compile(r'^[^.].*-analyzed\.txt$', re.IGNORECASE)
THRESHOLD_PATTERN = re.compile(r'^Threshold \(dB SPL\):\s*([+-]?\d+(?:\.\d+)?)$', re.M)
FREQUENCY_PATTERN = re.compile(r'^Frequency \(kHz\):\s*([+-]?\d+(?:\.\d+)?)$', re.M)
THRESHOLD_ESTIMATION_PATTERN = re.compile(r'^Threshold estimation:\s*(.*)$', re.M)


def normalize_column_name(name):
    name = name.strip()
    name = re.sub(r'[()/]', '_', name)
    name = name.replace('%', 'pct')
    name = name.replace('-', '_')
    name = re.sub(r'\s+', '_', name)
    name = re.sub(r'_+', '_', name)
    return name


def find_analyzed_files(folder):
    if not os.path.isdir(folder):
        raise ValueError(f'Folder does not exist: {folder}')

    paths = []
    for root, _, files in os.walk(folder):
        for filename in files:
            if filename.startswith('.'):
                continue
            if ANALYZED_PATTERN.match(filename):
                paths.append(os.path.join(root, filename))
    return sorted(paths)


def parse_analyzed_file(path):
    with open(path, encoding='latin-1') as f:
        text = f.read()

    text = text.replace('\r\n', '\n').replace('\r', '\n')

    thr_match = THRESHOLD_PATTERN.search(text)
    if not thr_match:
        raise ValueError(f'Could not parse threshold from {path}')
    threshold = float(thr_match.group(1))

    freq_match = FREQUENCY_PATTERN.search(text)
    if not freq_match:
        raise ValueError(f'Could not parse frequency from {path}')
    frequency = float(freq_match.group(1))

    threshold_estimation = 'manual'
    threshold_est_match = THRESHOLD_ESTIMATION_PATTERN.search(text)
    if threshold_est_match:
        parsed_value = threshold_est_match.group(1).strip()
        if parsed_value and 'sigmoid' in parsed_value.lower():
            threshold_estimation = 'sigmoid'
        elif parsed_value.lower() == 'manual':
            threshold_estimation = 'manual'
        else:
            threshold_estimation = 'manual'

    lines = [line for line in text.split('\n') if line is not None]
    header_index = None
    for idx, line in enumerate(lines):
        if line.strip().startswith('Level'):
            header_index = idx
            break
    if header_index is None:
        raise ValueError(f'Could not find waveform table header in {path}')

    header_line = lines[header_index]
    column_names = [normalize_column_name(col) for col in header_line.split('\t')]
    rows = []

    for line in lines[header_index + 1:]:
        if not line.strip():
            continue
        values = line.split('\t')
        row = {}
        for idx, col in enumerate(column_names):
            value = values[idx].strip() if idx < len(values) else ''
            row[col] = value

        basename = os.path.basename(path)
        base_no_ext = os.path.splitext(basename)[0]
        source_id = re.sub(r'(-analyzed)$', '', base_no_ext, flags=re.IGNORECASE)

        row['SourceFilename'] = basename
        row['SourceID'] = source_id
        row['Frequency_kHz'] = frequency
        row['Stimulus'] = 'CLICK' if abs(frequency) < 1e-8 else 'FREQ'
        row['Threshold_dB_SPL'] = threshold
        row['ThresholdEstimation'] = threshold_estimation
        rows.append(row)

    return rows


def _make_fieldnames(rows):
    base_fields = [
        'SourceFilename',
        'SourceID',
        'Frequency_kHz',
        'Stimulus',
        'Threshold_dB_SPL',
        'ThresholdEstimation',
    ]

    extra_fields = []
    for row in rows:
        for key in row.keys():
            if key not in base_fields and key not in extra_fields:
                extra_fields.append(key)

    return base_fields + extra_fields


def _write_csv(rows, path):
    fieldnames = _make_fieldnames(rows)

    for row in rows:
        for field in fieldnames:
            if field not in row:
                row[field] = ''

    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def merge_analyzed_files(folder, output_filename=None):
    files = find_analyzed_files(folder)
    if not files:
        raise ValueError(f'No analyzed files matching "*-analyzed.txt" were found in {folder}')

    merged_rows = []
    for path in files:
        parsed_rows = parse_analyzed_file(path)
        merged_rows.extend(parsed_rows)

    if not merged_rows:
        raise ValueError(f'No waveform rows were parsed from analyzed files in {folder}')

    merged_rows.sort(key=lambda row: (
        row.get('SourceFilename', ''),
        float(row.get('Level') or float('nan')) if row.get('Level') not in (None, '') else float('nan')
    ))

    output_path = output_filename or os.path.join(folder, 'merged_analyzed_files.csv')
    _write_csv(merged_rows, output_path)
    return output_path, len(merged_rows), len(files)


def select_folder_dialog(parent=None):
    if wx is None:
        raise RuntimeError('wxPython is required for folder selection.')

    dialog = wx.DirDialog(parent, 'Choose a folder containing analyzed files:',
                          style=wx.DD_DIR_MUST_EXIST | wx.DD_CHANGE_DIR)
    try:
        if dialog.ShowModal() == wx.ID_OK:
            return dialog.GetPath()
        return None
    finally:
        dialog.Destroy()


def merge_analyzed_files_with_dialog(parent=None):
    folder = select_folder_dialog(parent)
    if not folder:
        return None
    return merge_analyzed_files(folder)


if __name__ == '__main__':
    if wx is None:
        raise RuntimeError('wxPython is required to run this script.')
    app = wx.App(False)
    result = merge_analyzed_files_with_dialog()
    if result:
        output_path, row_count, file_count = result
        print(f'Wrote {row_count} rows from {file_count} files to {output_path}')
