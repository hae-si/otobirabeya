import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re

from pipeline.audit_current import DEFAULT_ANALYSIS, DEFAULT_DIST, check


DATA_FILES = ('graph.json', 'content-graph.json', 'interaction.json')
SITE_FILES = set(DATA_FILES) | {'index.html', 'app.js', 'style.css', 'THIRD_PARTY_NOTICES.md'}
FONT_FILES = {'chillroundf.ttf', 'chillroundf-ofl.txt'}
SHARD_NAME = re.compile(r'content-evidence-(?:[0-5][0-9]|6[0-3])\.json\.gz')


def audit_package(dist):
    root = Path(dist)
    paths = {p.name: p for p in root.iterdir()}
    if any(p.is_symlink() or not p.is_file() for p in paths.values()):
        raise ValueError('Package must contain only regular files')
    missing = SITE_FILES - paths.keys()
    unexpected = {name for name in paths.keys() - SITE_FILES - FONT_FILES if not SHARD_NAME.fullmatch(name)}
    if missing or unexpected:
        raise ValueError(f'Package files mismatch: missing={sorted(missing)}, unexpected={sorted(unexpected)}')

    index = json.loads(paths['content-graph.json'].read_bytes())
    expected = {}
    ids = set()
    for edge in index['edges']:
        name, edge_id = edge['evidence_file'], edge['id']
        if not SHARD_NAME.fullmatch(name) or edge_id in ids:
            raise ValueError('Invalid or duplicate content evidence reference')
        ids.add(edge_id)
        expected.setdefault(name, set()).add(edge_id)
    if expected.keys() != paths.keys() - SITE_FILES - FONT_FILES:
        raise ValueError('Package evidence files do not match the content index')
    for name, edge_ids in expected.items():
        with gzip.open(paths[name], 'rt', encoding='utf-8') as stream:
            shard = json.load(stream)
        if shard['edges'].keys() != edge_ids:
            raise ValueError(f'Package evidence edges do not match the index: {name}')
        if any(key not in shard['work_evidence']
               for edge in shard['edges'].values() for key in edge['work_evidence_keys']):
            raise ValueError(f'Package evidence has missing work records: {name}')

    html = paths['index.html'].read_text(encoding='utf-8')
    css = paths['style.css'].read_text(encoding='utf-8')
    if FONT_FILES & paths.keys() or 'chillroundf.ttf' in css:
        if not FONT_FILES <= paths.keys():
            raise ValueError('Package is missing the font or its licence')
        font_hash = hashlib.sha256(paths['chillroundf.ttf'].read_bytes()).hexdigest()[:12]
        if f'"chillroundf.ttf?v={font_hash}"' not in css:
            raise ValueError('Stylesheet font version does not match the package')
    data_version = hashlib.sha256()
    for name in (*DATA_FILES, *sorted(expected)):
        data_version.update(name.encode())
        data_version.update(paths[name].read_bytes())
    if re.findall(r'data-data-version="([^"]+)"', html) != [data_version.hexdigest()[:16]]:
        raise ValueError('HTML data version does not match the package')

    files = []
    for name, path in sorted(paths.items()):
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        if name in {'app.js', 'style.css'} and f'"{name}?v={sha[:12]}"' not in html:
            raise ValueError(f'HTML asset version does not match {name}')
        files.append({'file': name, 'bytes': path.stat().st_size, 'sha256': sha})
    return {'files': files}


def main():
    parser = argparse.ArgumentParser(description='Verify the exact static candidate directory and produce its SHA256 manifest')
    parser.add_argument('--dist', type=Path, default=DEFAULT_DIST)
    parser.add_argument('--analysis', type=Path, default=DEFAULT_ANALYSIS)
    parser.add_argument('--manifest', type=Path)
    args = parser.parse_args()
    if args.manifest and args.manifest.resolve().is_relative_to(args.dist.resolve()):
        parser.error('--manifest must be outside the candidate directory')
    result = audit_package(args.dist)
    check(args.dist, args.analysis)
    manifest = json.dumps(result, indent=2) + '\n'
    if args.manifest:
        args.manifest.write_text(manifest, encoding='utf-8')
    else:
        print(manifest, end='')


if __name__ == '__main__':
    main()
