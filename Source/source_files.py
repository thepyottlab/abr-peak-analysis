import os


SOURCE_WILDCARD = (
    'ABR files|ABR-*-*|VsEP files|VsEP-*-*|ANECS files|*.anx|'
    'Text files|*.txt|CSV files|*.csv|TSV files|*.tsv|All files|*'
)


def find_source_files(folder):
    if not os.path.isdir(folder):
        raise ValueError(f'Folder does not exist: {folder}')

    paths = []
    for root, _, files in os.walk(folder):
        for filename in files:
            path = os.path.join(root, filename)
            if is_source_file(path):
                paths.append(path)
    return sorted(paths)


def is_source_file(path):
    filename = os.path.basename(path)
    lower = filename.lower()
    if filename.startswith('.') or 'ch0avg' in lower or lower.endswith('.sqlite'):
        return False
    if '-analyzed.' in lower or not os.path.isfile(path):
        return False
    _, ext = os.path.splitext(filename)
    return (
        filename.startswith('ABR-') or
        filename.startswith('VsEP-') or
        ext == '' or
        ext.lower() in ('.anx', '.txt', '.csv', '.tsv')
    )
