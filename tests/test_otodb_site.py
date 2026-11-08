import gzip
import json
from pathlib import Path
import tempfile
import unittest

from pipeline.sources.otodb import decode_copy, read_copy
from pipeline.build_site import assemble

TEMP_ROOT = Path(__file__).resolve().parents[1] / 'tmp'
TEMP_ROOT.mkdir(exist_ok=True)

class CopyReaderTests(unittest.TestCase):
    def test_copy_bytes_null_and_injection(self):
        self.assertIsNone(decode_copy(r'\N'))
        self.assertEqual(decode_copy(r'\\N'), r'\N')
        self.assertEqual(decode_copy(r'\344\270\255\xE6\x96\x87'), '中文')
        self.assertEqual(decode_copy(r'a\tb\nc\\d'), 'a\tb\nc\\d')
        with self.assertRaises(ValueError):
            decode_copy('bad\\')
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as tmp:
            p = Path(tmp) / 'input.gz'
            with gzip.open(p, 'wt', encoding='utf-8') as f:
                f.write("DROP TABLE anything;\nCOPY public.sample (id, text) FROM stdin;\n1\t<script>bad</script>\n\\.\n")
            self.assertEqual(list(read_copy(p, ['sample'])), [('sample', {'id': '1', 'text': '<script>bad</script>'})])

    def test_invalid_and_unterminated_copy(self):
        for text in ['COPY public.sample (id) FROM stdin;\n1\n',
                     'COPY public.sample (id, text) FROM stdin;\n1\n\\.\n',
                     'COPY public.sample FROM stdin;\n', 'SELECT 1;\n']:
            with self.subTest(text=text), tempfile.TemporaryDirectory(dir=TEMP_ROOT) as tmp:
                p = Path(tmp) / 'input.gz'
                with gzip.open(p, 'wt', encoding='utf-8') as f:
                    f.write(text)
                with self.assertRaises(ValueError):
                    list(read_copy(p, ['sample']))


class SiteDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dump = Path(__file__).resolve().parents[1] / 'data/raw/m1/otodb-snapshot.sql.gz'
        cls.graph = assemble(cls.dump, ['3580']) if cls.dump.exists() else None

    def test_real_snapshot_graph_invariants(self):
        if self.graph is None:
            self.skipTest('Local otoDB snapshot unavailable; not redistributed')
        graph = self.graph
        for node in graph['nodes']:
            self.assertNotIn('description', node)
            self.assertNotIn('uploader_id', node)
            self.assertNotIn('added_by_id', node)
        nodes = {n['id']: n for n in graph['nodes']}
        self.assertEqual(len(nodes), len(graph['nodes']))
        self.assertEqual(len({e['id'] for e in graph['edges']}), len(graph['edges']))
        for edge in graph['edges']:
            self.assertIn(edge['source'], nodes)
            self.assertIn(edge['target'], nodes)
            self.assertTrue(edge['evidence'])
            self.assertTrue(all(url.startswith('https://otodb.net/') for url in edge['evidence']))
            if edge['type'] == 'co_creation':
                self.assertEqual(edge['work_id'], 'work:3580')
                self.assertEqual(nodes[edge['source']]['type'], 'creator')
            if edge['type'] == 'collab_part':
                self.assertEqual(nodes[edge['target']]['type'], 'project')
        self.assertFalse(any(e['type'] == 'membership' for e in graph['edges']))
        self.assertFalse(any(e['source'] == 'creator:25871' and e['target'] == 'work:3580' for e in graph['edges']))
        self.assertEqual(sum(e['type'] == 'co_creation' for e in graph['edges']), 3)
        self.assertEqual(len(nodes['work:3580']['publications']), 5)
        self.assertTrue(any(e['source'] == 'work:3580' and e['target'] == 'work:3578' and e['type'] == 'collab_part' for e in graph['edges']))

    def test_reproducible_output_and_selection_limit(self):
        if self.graph is None:
            self.skipTest('Local otoDB snapshot unavailable; not redistributed')
        self.assertEqual(self.graph, assemble(self.dump, ['3580']))
        limited = assemble(self.dump, ['3580'], 1)
        self.assertEqual(limited['meta']['selected_works'], 1)
        self.assertGreater(limited['meta']['truncated_works'], 0)
        self.assertEqual(sum(e['type'] == 'co_creation' for e in limited['edges']), 3)


if __name__ == '__main__':
    unittest.main()
