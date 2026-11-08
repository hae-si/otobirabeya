import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from pipeline.interaction_graph import integrate
from pipeline.audit_interaction_graph import audit


class InteractionGraphAuditTests(unittest.TestCase):
    def fixture(self,p):
        graph={'nodes':[{'id':cid,'core':True,'accounts':[{'id':cid}],'pagerank':.5,'community':'0','x':i,'y':i} for i,cid in enumerate(['a','b'])],
               'edges':[{'id':'ab','source':'a','target':'b','type':'follow','weight':1},{'id':'ba','source':'b','target':'a','type':'follow','weight':1}],
               'meta':{'algorithm':{'score':{'contributions':[{'name':'interaction','effectiveShare':.1}]}},
                       'layout':{'layerMasses':[{'name':'interaction','mass':1,'share':.1}],'interactionSpringCap':1}}}
        event={'event_id':'event','source_uid':'1','target_uid':'2','video_id':'v','rpid':'r','identity_state':'confirmed'}
        data={'meta':{'catalog_complete':True,'collection_audit':{'passed':True,'scope':'full_finite_catalog'},'event_audit':{'passed':True}},
              'accounts':{str(i):{'creator_id':cid,'label':cid,'identity_state':'confirmed','scope':'confirmed','appearance_video_ids':['v']} for i,cid in [(1,'a'),(2,'b')]},
              'events':[event],'observed_events':[event]}
        integrate(graph,data)
        data['meta']['event_audit']['observed_comment_counts_sha256']=hashlib.sha256(json.dumps({'1':0,'2':0},sort_keys=True).encode()).hexdigest()
        side=p/'interaction.json';side.write_text(json.dumps(data))
        graph['meta']['algorithm']['interaction_input_sha256']=hashlib.sha256(side.read_bytes()).hexdigest()
        path=p/'graph.json';path.write_text(json.dumps(graph))
        return graph,path,side

    def test_weight_or_follow_only_pagerank_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'tmp') as root:
            p=Path(root);g,path,side=self.fixture(p)
            result=audit(path,side);self.assertTrue(result['passed']);self.assertEqual(result['follow_only_pagerank_max_error'],0)
            g['interaction_edges'][0]['analysis_weight']=5;path.write_text(json.dumps(g))
            with self.assertRaisesRegex(ValueError,'weight mismatch'):audit(path,side)
            g,path,side=self.fixture(p);g['nodes'][0]['pagerank']=.7;path.write_text(json.dumps(g))
            with self.assertRaisesRegex(ValueError,'PageRank'):audit(path,side)

    def test_connected_account_must_have_a_community(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'tmp') as root:
            p=Path(root);g,path,side=self.fixture(p);g['nodes'][1]['community']=None;path.write_text(json.dumps(g))
            with self.assertRaisesRegex(ValueError,'missing community'):audit(path,side)

    def test_final_graph_requires_raw_event_audit(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'tmp') as root:
            p=Path(root);g,path,side=self.fixture(p)
            data=json.loads(side.read_bytes());del data['meta']['event_audit'];side.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'raw event audit'):audit(path,side)
