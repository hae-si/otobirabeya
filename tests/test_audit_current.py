import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.audit_current import check


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CurrentEvidenceTests(unittest.TestCase):
    def test_current_audits_must_match_published_artifacts(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            dist, analysis = root / 'dist', root / 'analysis'
            dist.mkdir(); analysis.mkdir()
            for name, payload in [('graph.json', b'graph'), ('interaction.json', b'interaction'), ('content-graph.json', b'content')]:
                (dist / name).write_bytes(payload)
            graph, interaction, content = sha(dist / 'graph.json'), sha(dist / 'interaction.json'), sha(dist / 'content-graph.json')
            docs = {
                'identity-audit-current.json': {'inputs': [{'file': 'dist/graph.json', 'sha256': graph}]},
                'unified-audit-current.json': {'inputs': [{'file': 'dist/graph.json', 'sha256': graph}]},
                'interaction-event-audit-current.json': {'identity_graph_sha256': graph},
                'interaction-graph-audit-current.json': {'graph_sha256': graph, 'interaction_sha256': interaction},
                'release-validation.json': {'input_sha256': graph, 'content_sha256': content},
            }
            for name, doc in docs.items():
                (analysis / name).write_text(json.dumps(doc), encoding='utf-8')
            self.assertTrue(check(dist, analysis)['passed'])
            docs['release-validation.json']['content_sha256'] = '0' * 64
            (analysis / 'release-validation.json').write_text(json.dumps(docs['release-validation.json']), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Stale current evidence'):
                check(dist, analysis)


if __name__ == '__main__':
    unittest.main()
