import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from pipeline.sources.bilibili_pilot import Client, run
from pipeline.sources.bilibili_probe import comment_rows, description_mentions


class PilotTests(unittest.TestCase):
    def test_captcha_word_in_valid_video_content_is_not_an_access_challenge(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'tmp') as root:
            def response(cmd,**kwargs):
                Path(cmd[cmd.index('-o')+1]).write_text(json.dumps({'code':0,'data':{'aid':1,'title':'captcha music'}}))
                return SimpleNamespace(stdout='200',returncode=0)
            with patch('pipeline.sources.bilibili_pilot.subprocess.run',side_effect=response),patch('pipeline.sources.bilibili_pilot.time.sleep'):
                client=Client(Path(root));data,_=client.request('/x/web-interface/view',{'aid':'1'})
            self.assertEqual(data['aid'],1);self.assertFalse(client.stopped)

    def test_actual_returned_comments_are_locally_like_sorted_with_response_rank(self):
        comments=[{'rpid':n,'member':{'mid':n},'like':likes,'content':{}} for n,likes in [(1,3),(2,9),(3,7),(4,8),(5,1),(6,10)]]
        got=comment_rows({'replies':comments})
        self.assertEqual([c['like'] for c in got],[10,9,8,7,3])
        self.assertEqual([c['response_rank'] for c in got],[6,2,4,3,1])
        self.assertEqual([c['rank'] for c in got],[1,2,3,4,5])
    def test_description_requires_structured_uid_not_text_or_bv(self):
        got=description_mentions({'desc_v2':[{'type':1,'raw_text':'@someone BV123','biz_id':0},
            {'type':2,'raw_text':'creator','biz_id':20},{'type':2,'raw_text':'invalid','biz_id':0}]})
        self.assertEqual(len(got),1)
        self.assertEqual(got[0]['target_uid'],'20')
        self.assertEqual(got[0]['segment_index'],1)

    def test_pin_does_not_consume_like_sorted_budget_or_use_hots(self):
        def c(n): return {'rpid':n,'member':{'mid':n},'content':{}}
        got=comment_rows({'upper':{'top':c(1)},'replies':[c(n) for n in range(1,8)],'hots':[c(99)]})
        self.assertEqual([r['rpid'] for r in got],['1','2','3','4','5','6'])
        self.assertEqual([r['rank'] for r in got[1:]],[1,2,3,4,5])

    def test_resume_uses_hash_checked_cache_and_retains_access_stop(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'tmp') as root:
            output=Path(root)
            def response(cmd,**kwargs):
                path=Path(cmd[cmd.index('-o')+1])
                blocked='oid=' in cmd[-1]
                path.write_text('blocked' if blocked else json.dumps({'code':0,'data':{'aid':1}}))
                return SimpleNamespace(stdout='412' if blocked else '200',returncode=0)
            with patch('pipeline.sources.bilibili_pilot.subprocess.run',side_effect=response) as mock, patch('pipeline.sources.bilibili_pilot.time.sleep'):
                client=Client(output)
                client.request('/x/web-interface/view',{'aid':'1'})
                client.request('/x/v2/reply',{'oid':'1'})
                resumed=Client(output)
                self.assertEqual(resumed.request('/x/web-interface/view',{'aid':'1'})[0]['aid'],1)
                self.assertIsNone(resumed.request('/x/web-interface/view',{'aid':'2'})[0])
                self.assertEqual(mock.call_count,2)
                with self.assertRaises(ValueError): resumed.request('/x/space/wbi/arc/search',{'mid':'1'})
                Path(client.records[0]['raw_file']).write_text('{}')
                with self.assertRaisesRegex(ValueError,'hash mismatch'): resumed.request('/x/web-interface/view',{'aid':'1'})

    def test_resume_rejects_changed_manifest(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'tmp') as root:
            p=Path(root); manifest=p/'manifest.json';manifest.write_text('[]')
            run(manifest,p/'out')
            manifest.write_text('[{}]')
            with self.assertRaisesRegex(ValueError,'Manifest changed'): run(manifest,p/'out')
