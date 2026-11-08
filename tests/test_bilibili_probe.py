import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from pipeline.sources.bilibili_probe import run, comment_rows, structured_mentions
from pipeline.sources.bilibili_review import review
import hashlib


class ProbeTests(unittest.TestCase):
    def test_mentions_require_literal_span_and_unambiguous_uid(self):
        content={'message':'@甲、@甲乙 @bad @甲', 'at_name_to_mid':{'甲':1,'甲乙':2,'bad':3,'absent':4},
                 'at_name_to_mid_str':{'bad':'9'}, 'members':[{'mid':'5','uname':'other'}]}
        got=structured_mentions(content)
        self.assertEqual([m['target_uid'] for m in got],['1','2','1'])
        for m in got:
            self.assertEqual(content['message'][m['start']:m['end']], '@'+m['name'])

    def test_offline_review_direction_evidence_and_hash_guard(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'tmp') as root:
            p=Path(root);raw=p/'raw.json'
            c={'rpid':1,'member':{'mid':20},'content':{'message':'@target','at_name_to_mid':{'target':30}}}
            raw.write_text(json.dumps({'data':{'upper':{'top':c},'replies':[c,dict(c,rpid=2)]}}))
            probe={'raw_file':str(raw),'sha256':hashlib.sha256(raw.read_bytes()).hexdigest(),
                   'endpoint':'/x/v2/reply','params':{'oid':10},'state':'ok','observed_at':'test'}
            (p/'endpoint_probe.json').write_text(json.dumps({'probes':[probe],'sort_policy':'like_sorted_available_top5','page_crosscheck':'not_required_user_policy'}))
            (p/'video_observations.json').write_text(json.dumps([{'aid':'10','bvid':'BVfixture','publisher_uid':'99','desc_v2':[{'type':2,'raw_text':'target','biz_id':30}]}]))
            dataset={'accounts':[{'site':'3','content_id':'20','tag_id':'a'},{'site':'3','content_id':'30','tag_id':'b'}],
                     'participation':[{'work_tag_id':'a','work_id':'w','used_as_source':'f','creator_roles':'2'},
                                      {'work_tag_id':'b','work_id':'w','used_as_source':'t','creator_roles':'2'}]}
            ds=p/'dataset.json';ds.write_text(json.dumps(dataset))
            result=review(p,ds,p/'out')
            self.assertEqual(result['events'],4)
            self.assertEqual(result['unique_event_comments'],2)
            self.assertEqual(result['verified_creator_accounts'],1)
            self.assertFalse(result['graph_admitted'])
            self.assertTrue(result['t14_admitted'])
            self.assertFalse(result['page_crosscheck_required'])
            dataset['accounts'][1]['tag_id']='a'
            ds.write_text(json.dumps(dataset))
            review(p,ds,p/'self-out')
            stats=json.loads((p/'self-out/statistics.json').read_bytes())
            self.assertEqual(stats['identity_supported_events'],0)
            raw.write_text('{}')
            with self.assertRaisesRegex(ValueError,'hash mismatch'): review(p,ds,p/'out2')

    def test_pinned_speaker_and_duplicate_comment_are_preserved(self):
        c={'rpid':1,'member':{'mid':20},'content':{'message':'test'}}
        rows=comment_rows({'upper':{'mid':99,'top':c},'replies':[c,dict(c,rpid=2)]})
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]['speaker_uid'],'20')
        self.assertTrue(rows[0]['is_pinned'])
        self.assertEqual(rows[1]['sort_status'],'observed_like_sorted_subset')

    def test_access_rejection_stops_all_further_requests(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/"tmp") as root:
            p=Path(root);manifest=p/'seeds.json'
            manifest.write_text(json.dumps([{'bvid':'BV1ApYzz2ENu','source_entries':[]},{'aid':'2','source_entries':[]}]))
            def reject(cmd,**kwargs):
                Path(cmd[cmd.index('-o')+1]).write_text('blocked')
                return SimpleNamespace(stdout='412')
            with patch('pipeline.sources.bilibili_probe.subprocess.run',side_effect=reject) as mock:
                result=run(manifest,p/'out')
            self.assertEqual(mock.call_count,1)
            self.assertTrue(result['access_stopped'])
            self.assertFalse(result['t14_admitted'])
            self.assertEqual(json.loads((p/'out/video_observations.json').read_text()),[])
