"""Check that generated current-audit evidence still matches the published graph."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIST = ROOT / 'dist/otobirabeya-authors'
DEFAULT_ANALYSIS = ROOT / 'data/normalized/analysis'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inputs_graph_hash(document):
    for row in document.get('inputs') or []:
        if Path(row.get('file', '')).name == 'graph.json':
            return row.get('sha256')
    return None


def check(dist=DEFAULT_DIST, analysis=DEFAULT_ANALYSIS):
    dist, analysis = Path(dist), Path(analysis)
    graph_hash = digest(dist / 'graph.json')
    interaction_hash = digest(dist / 'interaction.json')
    content_hash = digest(dist / 'content-graph.json')
    checks = {}

    def load(name):
        path = analysis / name
        if not path.is_file():
            raise FileNotFoundError('Missing current evidence: ' + str(path))
        return json.loads(path.read_text(encoding='utf-8'))

    identity = load('identity-audit-current.json')
    checks['identity'] = inputs_graph_hash(identity) == graph_hash
    unified = load('unified-audit-current.json')
    checks['unified'] = inputs_graph_hash(unified) == graph_hash
    events = load('interaction-event-audit-current.json')
    checks['interaction_events'] = events.get('identity_graph_sha256') == graph_hash
    graph_audit = load('interaction-graph-audit-current.json')
    checks['interaction_graph'] = graph_audit.get('graph_sha256') == graph_hash and graph_audit.get('interaction_sha256') == interaction_hash
    release = load('release-validation.json')
    checks['release'] = release.get('input_sha256') == graph_hash and release.get('content_sha256') == content_hash
    stale = sorted(name for name, ok in checks.items() if not ok)
    if stale:
        raise ValueError('Stale current evidence: ' + ', '.join(stale))
    return {'passed': True, 'graph_sha256': graph_hash, 'interaction_sha256': interaction_hash,
            'content_sha256': content_hash, 'checks': checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist', type=Path, default=DEFAULT_DIST)
    parser.add_argument('--analysis', type=Path, default=DEFAULT_ANALYSIS)
    args = parser.parse_args()
    print(json.dumps(check(args.dist, args.analysis), ensure_ascii=True))


if __name__ == '__main__':
    main()
