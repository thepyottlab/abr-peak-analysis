import json
import os
import sqlite3
import time

import numpy

from config import DefaultValueHolder, expected_peak_count, MAX_PEAKS, peak_visibility_defaults
from datatype import ABRStimPolarity, Point, ThrSource, Th


SCHEMA_VERSION = 1


def analysis_path(model):
    filename = model.filename
    if model.stimPol == ABRStimPolarity.Condensation:
        filename += '-cond'
    if model.stimPol == ABRStimPolarity.Rarefaction:
        filename += '-rare'
    return filename + '-analyzed.sqlite'


def have_analysis(model):
    return os.path.isfile(analysis_path(model))


def save(model):
    path = analysis_path(model)

    overwrite = DefaultValueHolder('PhysiologyNotebook', 'overwriteOnSave')
    overwrite.SetVariables(value=False)
    overwrite.InitFromConfig()

    tmp_path = path + '.tmp'
    if os.path.exists(tmp_path):
        os.unlink(tmp_path)

    with sqlite3.connect(tmp_path) as db:
        db.execute('PRAGMA foreign_keys = ON')
        _create_schema(db)
        _save_model(db, model)

    if os.path.exists(path) and not overwrite.value:
        _archive_existing(path)
    os.replace(tmp_path, path)
    return 'Saved data to %s' % path


def restore(model):
    path = analysis_path(model)
    if not os.path.isfile(path):
        raise IOError("Analyzed data not found for '%s'" % model.filename)

    with sqlite3.connect(path) as db:
        db.row_factory = sqlite3.Row
        analysis = db.execute(
            'SELECT threshold FROM analysis WHERE id = 1'
        ).fetchone()
        if analysis is None:
            raise IOError('Could not parse %s' % path)

        peak_count_row = db.execute(
            'SELECT max(wave_label) AS peak_count FROM peaks'
        ).fetchone()
        peak_count = max(expected_peak_count(), peak_count_row['peak_count'] or 0)
        n = len(model.series)
        pind = numpy.full((n, peak_count), -1, dtype=int)
        nind = numpy.full((n, peak_count), -1, dtype=int)

        rows = db.execute('''
            SELECT l.level, p.wave_label, p.point_type, p.sample_index
            FROM peaks AS p
            JOIN levels AS l ON l.id = p.level_id
            ORDER BY l.position, p.wave_label, p.point_type
        ''')
        for row in rows:
            i = _level_index(model, row['level'])
            if i is None:
                continue
            j = int(row['wave_label']) - 1
            if row['point_type'] == 'peak':
                pind[i, j] = int(row['sample_index'])
            else:
                nind[i, j] = int(row['sample_index'])

    return "Loaded data from '%s'" % model.filename, pind, nind, analysis['threshold']


def filter_label(settings):
    if not settings or settings.get('ftype') == 'None':
        return 'none'
    low, high = settings.get('W', ('', ''))
    return '%s_%s_%s_%s' % (
        str(settings.get('ftype', '')).lower(),
        settings.get('N', ''),
        low,
        high,
    )


def current_filter_settings():
    filt = DefaultValueHolder('PhysiologyNotebook', 'filter')
    filt.SetVariables(ftype='Butterworth', fl=10000, fh=200, N=1)
    filt.InitFromConfig()
    return {'ftype': filt.ftype, 'W': (filt.fh, filt.fl), 'N': filt.N}


def _create_schema(db):
    db.executescript('''
        CREATE TABLE analysis (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            schema_version INTEGER NOT NULL,
            source_path TEXT NOT NULL,
            filename TEXT NOT NULL,
            frequency REAL,
            polarity TEXT NOT NULL,
            filter_label TEXT NOT NULL,
            filter_settings TEXT NOT NULL,
            threshold REAL,
            threshold_source TEXT NOT NULL,
            threshold_method TEXT NOT NULL,
            saved_at TEXT NOT NULL
        );

        CREATE TABLE levels (
            id INTEGER PRIMARY KEY,
            analysis_id INTEGER NOT NULL,
            position INTEGER NOT NULL,
            level REAL NOT NULL,
            sampling_rate REAL NOT NULL,
            FOREIGN KEY (analysis_id) REFERENCES analysis(id)
        );

        CREATE TABLE peaks (
            id INTEGER PRIMARY KEY,
            level_id INTEGER NOT NULL,
            wave_label INTEGER NOT NULL,
            point_type TEXT NOT NULL,
            sample_index INTEGER NOT NULL,
            latency REAL,
            amplitude REAL,
            FOREIGN KEY (level_id) REFERENCES levels(id)
        );

        CREATE TABLE waveform_points (
            level_id INTEGER NOT NULL,
            sample_index INTEGER NOT NULL,
            latency REAL NOT NULL,
            amplitude REAL NOT NULL,
            PRIMARY KEY (level_id, sample_index),
            FOREIGN KEY (level_id) REFERENCES levels(id)
        );
    ''')


def _save_model(db, model):
    settings = getattr(model, 'filter_settings', None) or current_filter_settings()
    db.execute('''
        INSERT INTO analysis (
            id, schema_version, source_path, filename, frequency, polarity,
            filter_label, filter_settings, threshold, threshold_source,
            threshold_method, saved_at
        ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        SCHEMA_VERSION,
        model.filename,
        os.path.splitext(os.path.basename(model.filename))[0],
        model.freq,
        _polarity_name(model.stimPol),
        filter_label(settings),
        json.dumps(settings, sort_keys=True),
        model.threshold,
        _threshold_source(model),
        _threshold_method(model),
        time.strftime('%Y-%m-%dT%H:%M:%S'),
    ))

    level_ids = {}
    for position, waveform in enumerate(model.series):
        cur = db.execute('''
            INSERT INTO levels (analysis_id, position, level, sampling_rate)
            VALUES (1, ?, ?, ?)
        ''', (position, waveform.level, waveform.fs))
        level_ids[waveform] = cur.lastrowid

    _save_peaks(db, model, level_ids)
    _save_waveform_points(db, model, level_ids)


def _save_peaks(db, model, level_ids):
    visible = DefaultValueHolder('PhysiologyNotebook', 'peakVisibility')
    visible.SetVariables(peak_visibility_defaults())
    visible.InitFromConfig()
    noise_floor = model.noiseFloor if getattr(model, 'useNoiseFloor', False) else 0

    rows = []
    for waveform in model.series:
        for point, value in getattr(waveform, 'points', {}).items():
            point_type, wave_label = point
            if wave_label < 1 or wave_label > MAX_PEAKS:
                continue
            key = ('p%d' if point_type == Point.PEAK else 'n%d') % wave_label
            if not getattr(visible, key):
                continue
            if value.index < 0 or value.index >= len(waveform.y):
                continue
            if waveform.threshold == Th.SUB:
                latency = None
                amplitude = None
            else:
                latency = float(waveform.x[value.index])
                amplitude = value.amplitude - noise_floor if point_type == Point.PEAK else value.amplitude
            rows.append((
                level_ids[waveform],
                int(wave_label),
                'peak' if point_type == Point.PEAK else 'trough',
                int(value.index),
                latency,
                None if amplitude is None else float(amplitude),
            ))

    db.executemany('''
        INSERT INTO peaks (
            level_id, wave_label, point_type, sample_index, latency, amplitude
        ) VALUES (?, ?, ?, ?, ?, ?)
    ''', rows)


def _save_waveform_points(db, model, level_ids):
    rows = []
    for waveform in model.series:
        level_id = level_ids[waveform]
        rows.extend(
            (level_id, i, float(latency), float(amplitude))
            for i, (latency, amplitude) in enumerate(zip(waveform.x, waveform.y))
        )

    db.executemany('''
        INSERT INTO waveform_points (
            level_id, sample_index, latency, amplitude
        ) VALUES (?, ?, ?, ?)
    ''', rows)


def _threshold_source(model):
    if model.threshold is None:
        return ''
    if model.thresholdSource is ThrSource.Manual:
        return 'manual'
    if model.thresholdSource is ThrSource.Auto:
        return 'automatic'
    return ''


def _threshold_method(model):
    if model.threshold is None:
        return ''
    if model.thresholdSource is ThrSource.Manual:
        return 'manual'
    return model.best_fit_type or ''


def _polarity_name(polarity):
    try:
        return polarity.name.lower()
    except AttributeError:
        return str(polarity)


def _archive_existing(path):
    base, fname = os.path.split(path)
    filetime = os.path.getmtime(path)
    filestring = time.strftime('%Y-%m-%d-%H-%M-%S-', time.gmtime(filetime))
    os.rename(path, os.path.join(base, filestring + fname))


def _level_index(model, level):
    for i, waveform in enumerate(model.series):
        if abs(float(waveform.level) - float(level)) < 1e-9:
            return i
    return None
