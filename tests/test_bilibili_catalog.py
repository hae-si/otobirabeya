import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import urlparse,parse_qs
from pipeline.sources.bilibili_catalog import freeze
from pipeline.sources.bilibili_collect import run
from pipeline.audit_interaction_collection import audit


class CatalogTests(unittest.TestCase):
    def test_closed_comment_area_is_terminal_only_with_matching_raw_code(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'tmp') as root:
            p=Path(root);manifest=p/'manifest.json';manifest.write_text(json.dumps([{'aid':'1','source_entries':[]}]))
            def response(cmd,**kwargs):
                payload={'code':12061,'message':'UP主已关闭评论区'} if urlparse(cmd[-1]).path.endswith('/reply') else {'code':0,'data':{'aid':1,'bvid':'BV1ApYzz2ENu','owner':{'mid':10}}}
                Path(cmd[cmd.index('-o')+1]).write_text(json.dumps(payload))
                return SimpleNamespace(stdout='200',returncode=0)
            with patch('pipeline.sources.bilibili_pilot.subprocess.run',side_effect=response),patch('pipeline.sources.bilibili_pilot.time.sleep'):
                run(manifest,p/'out')
            self.assertEqual(audit(manifest,p/'out')['comment_unavailable_by_api_code'],{'12061':1})
            report=p/'out/endpoint_probe.json';data=json.loads(report.read_bytes());data['probes'][-1]['api_code']=12003;report.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'differs from raw'):audit(manifest,p/'out')

    def test_catalog_only_extracts_video_component_and_valid_bilibili_ids(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'tmp') as root:
            p=Path(root);viewer=p/'viewer.json';author=p/'author.html'
            viewer.write_text(json.dumps({'list':[{'data':[{'aid':'av12','platform':'bilibili','title':'a'},{'aid':'12','platform':'other'},{'aid':'missing'}]}]}))
            props=json.dumps({'videos':[1,[[0,{'url':[0,'https://www.bilibili.com/video/BV1ApYzz2ENu'],'title':[0,'b']}]]]})
            author.write_text('<a href="https://www.bilibili.com/video/BVoutside">x</a><astro-island component-url="VideoResults.x.js" props=\''+props+'\'></astro-island>')
            result=freeze([('test',viewer)],author,p/'out')
            self.assertEqual(result['manifest_aliases'],2)
            self.assertEqual(len(result['rejected']),2)

    def test_collection_resolves_aliases_and_resumes_terminal_unavailability(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'tmp') as root:
            p=Path(root);manifest=p/'manifest.json'
            manifest.write_text(json.dumps([{'aid':'1','source_entries':[{'family':'viewer'}]},
                {'bvid':'BV1ApYzz2ENu','source_entries':[{'family':'author'}]}, {'aid':'2','source_entries':[]}]))
            def response(cmd,**kwargs):
                params=parse_qs(urlparse(cmd[-1]).query);path=urlparse(cmd[-1]).path
                if path.endswith('/reply'):payload={'code':0,'data':{'replies':[{'rpid':1,'member':{'mid':20},'content':{'message':'x'}}]}}
                elif params.get('aid')==['2']:payload={'code':62012}
                else:payload={'code':0,'data':{'aid':1,'bvid':'BV1ApYzz2ENu','owner':{'mid':10}}}
                Path(cmd[cmd.index('-o')+1]).write_text(json.dumps(payload))
                return SimpleNamespace(stdout='200',returncode=0)
            with patch('pipeline.sources.bilibili_pilot.subprocess.run',side_effect=response) as mock,patch('pipeline.sources.bilibili_pilot.time.sleep'):
                result=run(manifest,p/'out');self.assertEqual(mock.call_count,3)
                resumed=run(manifest,p/'out',budget=3);self.assertEqual(mock.call_count,3)
            self.assertTrue(result['complete_catalog_attempted']);self.assertEqual(resumed['unique_videos'],1)
            videos=json.loads((p/'out/video_observations.json').read_bytes());self.assertEqual(len(videos[0]['source_entries']),2)
            self.assertEqual(resumed['comments'],1)
            checked=audit(manifest,p/'out');self.assertTrue(checked['passed']);self.assertEqual(checked['comments'],1)
            comment_path=p/'out/comment_observations.json';original_comments=comment_path.read_bytes()
            edited=json.loads(original_comments);edited[0]['speaker_uid']='10';comment_path.write_text(json.dumps(edited))
            with self.assertRaisesRegex(ValueError,'actual speaker'):audit(manifest,p/'out')
            comment_path.write_bytes(original_comments)
            before=(p/'out/video_observations.json').read_bytes()
            records=[json.loads(line) for line in (p/'out/requests.jsonl').read_text().splitlines()]
            with (p/'out/requests.jsonl').open('a') as f:f.write(json.dumps({**records[-1],'state':'access_stop','http_status':412})+'\n')
            with patch('pipeline.sources.bilibili_pilot.subprocess.run') as mock:
                stopped=run(manifest,p/'out');mock.assert_not_called()
            self.assertTrue(stopped['access_stopped']);self.assertFalse(stopped['complete_catalog_attempted'])
            self.assertEqual((p/'out/video_observations.json').read_bytes(),before)
