import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from pipeline.audit_package import audit_package


class PackageAuditTests(unittest.TestCase):
    def candidate(self, root, interaction=None):
        shard = 'content-evidence-00.json.gz'
        data = {
            'graph.json': {},
            'content-graph.json': {'edges': [{'id': 'edge', 'evidence_file': shard}]},
            'interaction.json': interaction or {'events': [], 'observed_events': []},
        }
        version = hashlib.sha256()
        for name, value in data.items():
            raw = json.dumps(value).encode()
            (root / name).write_bytes(raw)
            version.update(name.encode() + raw)
        evidence = {'edges': {'edge': {'work_evidence_keys': ['work']}}, 'work_evidence': {'work': {}}}
        raw = gzip.compress(json.dumps(evidence).encode())
        (root / shard).write_bytes(raw)
        version.update(shard.encode() + raw)
        assets = {}
        for name in ('app.js', 'style.css', 'THIRD_PARTY_NOTICES.md'):
            raw = name.encode()
            (root / name).write_bytes(raw)
            assets[name] = hashlib.sha256(raw).hexdigest()[:12]
        (root / 'index.html').write_text(
            f'<html data-data-version="{version.hexdigest()[:16]}">'
            f'<link href="style.css?v={assets["style.css"]}">'
            f'<script src="app.js?v={assets["app.js"]}"></script>',
            encoding='utf-8',
        )

    def test_exact_bundle_rejects_extras_and_stale_assets(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / 'tmp') as directory:
            root = Path(directory)
            self.candidate(root)
            self.assertEqual(len(audit_package(root)['files']), 8)
            extra = root / 'raw.json'
            extra.touch()
            with self.assertRaisesRegex(ValueError, 'unexpected'):
                audit_package(root)
            extra.unlink()
            (root / 'app.js').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'asset version'):
                audit_package(root)

    def test_candidate_keeps_excerpts_and_rejects_incomplete_evidence(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / 'tmp') as directory:
            root = Path(directory)
            self.candidate(root, {'events': [], 'observed_events': [{'excerpt': 'local text'}]})
            self.assertEqual(len(audit_package(root)['files']), 8)
            (root / 'content-evidence-00.json.gz').unlink()
            with self.assertRaisesRegex(ValueError, 'evidence files'):
                audit_package(root)
