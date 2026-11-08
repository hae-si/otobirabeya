import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from pipeline.sources.otomadsite_audit import audit


class SamplingAuditTests(unittest.TestCase):
    def capture(self, root, pages, progress=None):
        records=[]
        for i,(body,data) in enumerate(pages):
            raw=json.dumps(data).encode();name=f'{i}.json';(root/name).write_bytes(raw)
            records.append({'endpoint':'users/following','request':{'userId':'a',**body},'status':200,'file':name,'sha256':hashlib.sha256(raw).hexdigest(),'observed_at':'2026-10-29T00:00:00Z'})
        (root/'requests.jsonl').write_text('\n'.join(json.dumps(r) for r in records),encoding='utf-8')
        if progress is not None:(root/'progress.json').write_text(json.dumps(progress),encoding='utf-8')
        return audit([root])

    def row(self):
        return {'id':'r1','createdAt':'2026-01-01','followerId':'a','followeeId':'b','followee':{'id':'b','username':'b'}}

    def test_interrupted_without_progress_is_partial(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'tmp') as d:
            r=self.capture(Path(d),[({},[self.row()])])
            self.assertEqual(r['coverage'][0]['state'],'partial_interrupted')

    def test_empty_terminal_page_proves_exhaustion(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'tmp') as d:
            r=self.capture(Path(d),[({},[self.row()]),({'untilId':'r1'},[])])
            self.assertEqual(r['coverage'][0]['state'],'visible_list_exhausted')

    def test_bad_cursor_rejected(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'tmp') as d:
            with self.assertRaisesRegex(ValueError,'cursor'):
                self.capture(Path(d),[({},[self.row()]),({'untilId':'wrong'},[])])

    def test_false_completion_and_nested_id_rejected(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'tmp') as d:
            with self.assertRaisesRegex(ValueError,'terminal'):
                self.capture(Path(d),[({},[self.row()])],{'mappings':[],'coverage':[{'user_id':'a','endpoint':'following','state':'visible_list_exhausted'}]})
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'tmp') as d:
            row=self.row();row['followee']['id']='wrong'
            with self.assertRaisesRegex(ValueError,'Nested'):
                self.capture(Path(d),[({},[row])])
