import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from pipeline.sources.bilibili_review import review
from pipeline.audit_interaction_events import audit,mentions


class EventAuditTests(unittest.TestCase):
    def test_literal_longest_mentions_and_ambiguity(self):
        content={'message':'@A-li @A abc@Afoo @A', 'at_name_to_mid':{'A':'1','A-li':'2'},'at_name_to_mid_str':{'A':'3'}}
        self.assertEqual(mentions(content),[(0,5,'A-li','2')])

    def test_raw_audit_rejects_reversed_event_and_rank_tampering(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'tmp') as root:
            p=Path(root);collection=p/'collection';collection.mkdir()
            write=lambda path,value:path.write_text(json.dumps(value),encoding='utf-8')
            records=[]
            for endpoint,params,data in [('/x/web-interface/view',{'bvid':'BVtest'},{'aid':1,'bvid':'BVtest','owner':{'mid':10},'desc':'','desc_v2':[]}),('/x/v2/reply',{'oid':'1'},{'replies':[{'rpid':2,'member':{'mid':20},'like':9,'content':{'message':'@owner','at_name_to_mid':{'owner':10}}}]})]:
                raw=p/(str(len(records))+'.body');write(raw,{'code':0,'data':data})
                records.append({'endpoint':endpoint,'params':params,'state':'ok','raw_file':str(raw),'sha256':hashlib.sha256(raw.read_bytes()).hexdigest(),'observed_at':'2026-10-30'})
            write(collection/'endpoint_probe.json',{'probes':records,'sort_policy':'like_sorted_available_top5','page_crosscheck':'not_required_user_policy'})
            write(collection/'video_observations.json',[{'aid':'1','bvid':'BVtest','publisher_uid':'10','desc':'','desc_v2':[]}])
            dataset=p/'dataset.json';write(dataset,{'accounts':[],'creators':{},'participation':[]})
            graph=p/'graph.json';write(graph,{'nodes':[]})
            out=p/'review';review(collection,dataset,out,graph)
            self.assertEqual(audit(collection,dataset,out,graph)['events_checked'],2)
            coverage=out/'comment_coverage.csv';original_coverage=coverage.read_bytes()
            coverage.write_bytes(original_coverage.replace(b'available_subset',b'unavailable'))
            with self.assertRaisesRegex(ValueError,'coverage status'):audit(collection,dataset,out,graph)
            coverage.write_bytes(original_coverage)
            events=out/'interaction_events.csv';original=events.read_bytes()
            events.write_bytes(original.replace(b',20,10,',b',10,20,'))
            with self.assertRaisesRegex(ValueError,'directions'):audit(collection,dataset,out,graph)
            events.write_bytes(original)
            comments=out/'comment_observations.json';value=json.loads(comments.read_bytes());value[0]['response_rank']=99;write(comments,value)
            with self.assertRaisesRegex(ValueError,'ranking'):audit(collection,dataset,out,graph)
