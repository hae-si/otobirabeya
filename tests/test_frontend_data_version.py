from pathlib import Path
import re
import tempfile
import unittest
from pipeline.author_site import write_frontend


class FrontendDataVersionTests(unittest.TestCase):
    def test_data_change_invalidates_urls_even_when_javascript_is_unchanged(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'tmp') as root:
            p=Path(root);(p/'graph.json').write_text('{"nodes":[]}')
            write_frontend(p)
            first=(p/'index.html').read_text(encoding='utf-8');script=(p/'app.js').read_bytes()
            (p/'graph.json').write_text('{"nodes":[{"id":"new"}]}')
            write_frontend(p)
            second=(p/'index.html').read_text(encoding='utf-8')
            version=lambda html:re.search(r'data-data-version="([a-f0-9]+)"',html)[1]
            self.assertNotEqual(version(first),version(second))
            self.assertEqual(script,(p/'app.js').read_bytes())
            self.assertIn('dataVersion',script.decode())
            (p/'content-evidence-00.json.gz').write_bytes(b'shard evidence')
            write_frontend(p)
            third=(p/'index.html').read_text(encoding='utf-8')
            self.assertNotEqual(version(second),version(third))
