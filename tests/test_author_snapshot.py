import unittest
from pathlib import Path
from pipeline.author_site import assemble


class AuthorSnapshotTests(unittest.TestCase):
    def test_real_projection_scope_weights_and_evidence(self):
        path = Path(__file__).resolve().parents[1] / 'data/raw/m1/otodb-20261028-040005.sql.gz'
        if not path.exists():
            self.skipTest('Local snapshot not redistributed')
        data = assemble(path)
        nodes = {n['id']: n for n in data['nodes']}
        core = {n['id'] for n in data['nodes'] if n['chinese_scope']}
        self.assertEqual(len(core), data['meta']['chinese_scope_count'])
        self.assertTrue(all(n['type'] == 'creator' for n in nodes.values()))
        self.assertEqual(len({e['id'] for e in data['edges']}), len(data['edges']))
        related = set()
        for edge in data['edges']:
            self.assertIn(edge['source'], nodes)
            self.assertIn(edge['target'], nodes)
            self.assertTrue(edge['source'] in core or edge['target'] in core)
            related.update({edge['source'], edge['target']} - core)
            score = 0
            for event_id in edge['event_ids']:
                event = data['events'][event_id]
                self.assertEqual(event['n'], len(event['participants']))
                self.assertGreater(event['n'], 1)
                self.assertIn(edge['source'], event['participants'])
                self.assertIn(edge['target'], event['participants'])
                self.assertIn(event['root_work_id'], data['works'])
                score += 1 / (event['n'] - 1)
            self.assertAlmostEqual(score, edge['weights']['affiliation'], places=8)
        self.assertEqual(related, set(nodes) - core)
        self.assertEqual(len(nodes), len(data['nodes']))
