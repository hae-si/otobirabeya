import json
import gzip
import tempfile
import unittest
from pathlib import Path
from pipeline.content_bundle import write_bundle


class ContentBundleTests(unittest.TestCase):
    def test_same_name_creator_aliases_pool_features_and_preserve_credit_evidence(self):
        d={'creators':{'1':{},'2':{},'3':{}},'works':{'10':{'title':'a'},'11':{'title':'b'},'12':{'title':'untagged'}},
           'tags':{'7':{'name':'song','category':'2'}},
           'participation':[dict(work_id=w,work_tag_id=a,creator_roles='1',used_as_source='f',source_record_ids=[a]) for w,a in [('10','1'),('10','2'),('11','3')]],
           'work_tags':[dict(work_id=w,tag_id='7',category='2',source_records=[{'id':w}]) for w in ['10','11']]}
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'tmp') as root:
            out=Path(root);p=out/'dataset.json';p.write_text(json.dumps(d));before=p.read_bytes()
            write_bundle(p,{'nodes':[{'otodb_id':'1'},{'otodb_id':'3'}],'meta':{'identity':{'redirects':{'otodb:2':'otodb:1'}}}},out)
            edges=json.loads((out/'content-graph.json').read_text())['edges'];self.assertEqual(len(edges),1)
            self.assertEqual({edges[0]['source'],edges[0]['target']},{'otodb:1','otodb:3'})
            shard=json.loads(gzip.decompress((out/edges[0]['evidence_file']).read_bytes()))
            evidence=next(r for r in shard['work_evidence'].values() if r['author_id']=='1')
            self.assertEqual(evidence['participant_count'],1)
            self.assertEqual(evidence['participation']['source_record_ids'],['1','2'])
            self.assertEqual(evidence['participation']['source_creator_ids'],['1','2'])
            self.assertEqual(p.read_bytes(),before)

    def test_lazy_shards_keep_upstream_credit_and_tag_evidence(self):
        d={'creators':{'1':{},'2':{}},'works':{'10':{'title':'a'},'11':{'title':'b'},'12':{'title':'untagged'}},
           'tags':{'3':{'name':'song','category':'2'}},
           'participation':[dict(work_id=w,work_tag_id=a,creator_roles='1',used_as_source='f',source_record_ids=[a]) for w,a in [('10','1'),('11','2')]],
           'work_tags':[dict(work_id=w,tag_id='3',category='2',source_records=[{'id':w,'used_as_source':'t'}]) for w in ['10','11']]}
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'tmp') as root:
            out=Path(root);p=out/'dataset.json';p.write_text(json.dumps(d))
            meta=write_bundle(p,{'nodes':[{'otodb_id':'1'},{'otodb_id':'2'},{'id':'unmapped'}]},out)
            edges=json.loads((out/'content-graph.json').read_text())['edges']
            self.assertEqual(len(edges),1);self.assertTrue(meta['available'])
            self.assertNotIn('tags',edges[0])
            compressed=(out/edges[0]['evidence_file']).read_bytes()
            shard=json.loads(gzip.decompress(compressed))
            self.assertEqual(compressed,gzip.compress(gzip.decompress(compressed),mtime=0))
            evidence=shard['edges'][edges[0]['id']]
            self.assertEqual(len(evidence['work_evidence_keys']),2)
            work=shard['work_evidence'][evidence['work_evidence_keys'][0]]
            self.assertEqual(work['participant_count'],1)
            self.assertEqual(work['tag_instances'][0]['used_as_source'],'t')

    def test_old_dataset_explicitly_unavailable(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'tmp') as root:
            out=Path(root);p=out/'dataset.json';p.write_text('{}')
            self.assertFalse(write_bundle(p,{'nodes':[]},out)['available'])
