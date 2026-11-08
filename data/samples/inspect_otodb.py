"""Read a local pg_dump COPY text stream; never execute SQL or fetch data."""
import argparse
import gzip
import hashlib
import json
import re
from pathlib import Path

def rows(path):
    table = None
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        for line in stream:
            if table:
                if line.rstrip('\n') == '\\.':
                    table = None
                    continue
                values = line.rstrip('\n').split('\t')
                if len(values) != len(columns):
                    raise ValueError('COPY column count mismatch: ' + table)
                yield table, dict(zip(columns, values))
            else:
                match = re.match(r'COPY public\.(\w+) \((.*?)\) FROM stdin;', line)
                if match:
                    table = match[1]
                    columns = [c.strip('"') for c in match[2].split(', ')]

def inspect(path, work_id):
    selected = {k: [] for k in ['otodb_mediawork', 'otodb_tagworkinstance', 'otodb_worksource', 'otodb_workrelation']}
    for table, row in rows(path):
        keep = ((table == 'otodb_mediawork' and row['id'] == work_id)
                or (table == 'otodb_tagworkinstance' and row['work_id'] == work_id)
                or (table == 'otodb_worksource' and row['media_id'] == work_id)
                or (table == 'otodb_workrelation' and work_id in (row['A_id'], row['B_id'])))
        if keep:
            selected[table].append(row)
    tag_ids = {r['work_tag_id'] for r in selected['otodb_tagworkinstance']}
    selected['otodb_tagwork'] = [r for t, r in rows(path) if t == 'otodb_tagwork' and r['id'] in tag_ids]
    assert len(selected['otodb_mediawork']) == 1
    assert {r['id'] for r in selected['otodb_tagwork']} == tag_ids
    return {'sha256': hashlib.file_digest(path.open('rb'), 'sha256').hexdigest(),
            'work_id': work_id, 'encoding': 'raw COPY text; \\N means NULL', 'tables': selected}

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('dump', type=Path)
    parser.add_argument('--work-id', default='3580')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = inspect(args.dump, args.work_id)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print({k: len(v) for k, v in result['tables'].items()})
