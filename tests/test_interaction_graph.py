import copy
import math
import unittest
from pipeline.interaction_graph import integrate


class InteractionGraphTests(unittest.TestCase):
    def test_mapped_pending_alias_is_not_a_duplicate_or_an_analysis_weight_boost(self):
        graph={'nodes':[{'id':'otodb:1','chinese_scope':True,'has_bilibili_account':True},{'id':'otodb:2','chinese_scope':True,'has_bilibili_account':True}],'meta':{}}
        def account(cid,state,scope,aids):return {'creator_id':cid,'label':cid,'identity_state':state,'scope':scope,'appearance_video_ids':aids}
        actors={'a':account('otodb:1','confirmed','confirmed',['1']),
                'alias':account('otodb:1','unknown','all',['2']),
                'b':account('otodb:2','confirmed','confirmed',['1','2'])}
        events=[{'event_id':'known','source_uid':'a','target_uid':'b','video_id':'1','rpid':'1','identity_state':'confirmed'},
                {'event_id':'pending','source_uid':'alias','target_uid':'b','video_id':'2','rpid':'2','identity_state':'unknown'}]
        edge=integrate(graph,{'accounts':actors,'observed_events':events,'events':[],'meta':{}})[0]
        self.assertEqual(len(graph['nodes']),2)
        self.assertAlmostEqual(edge['weight'],2);self.assertAlmostEqual(edge['analysis_weight'],1)
        self.assertEqual(edge['analysis_event_ids'],['known']);self.assertEqual(edge['analysis_video_count'],1)

    def test_direction_video_saturation_and_singletons_excluded_from_analysis(self):
        graph={'nodes':[{'id':'otodb:1','chinese_scope':True,'has_bilibili_account':True}],'meta':{}}
        accounts={'a':{'creator_id':'otodb:1','label':'A','identity_state':'confirmed','scope':'confirmed','appearance_video_ids':['1']},
                  'b':{'creator_id':'bilibili:2','label':'B','identity_state':'unknown','scope':'related','appearance_video_ids':['1','2']},
                  'c':{'creator_id':'bilibili:3','label':'C','identity_state':'unknown','scope':'all','appearance_video_ids':['1']}}
        events=[{'event_id':str(i),'source_uid':s,'target_uid':t,'video_id':v,'rpid':r,'identity_state':'unknown'} for i,(s,t,v,r) in enumerate([
            ('a','b','1','10'),('a','b','1','10'),('a','b','1','11'),('a','b','2','12'),('b','a','1','13'),('c','a','1','14')])]
        edges=integrate(graph,{'accounts':accounts,'observed_events':events,'events':[],'meta':{}})
        forward=next(e for e in edges if e['source']=='otodb:1' and e['target']=='bilibili:2')
        self.assertAlmostEqual(forward['weight'],2);self.assertEqual(forward['observation_unit_count'],3)
        self.assertTrue(forward['analysis_enabled']);self.assertEqual(len(edges),2)
        self.assertNotIn('bilibili:3',{n['id'] for n in graph['nodes']})
        self.assertIsNone(accounts['c']['node_id'])
        self.assertTrue(next(n for n in graph['nodes'] if n['id']=='bilibili:2')['has_bilibili_account'])
        self.assertEqual(next(n for n in graph['nodes'] if n['id']=='bilibili:2')['identity_state'],'unknown')

    def test_selected_publisher_is_core_without_fabricating_production_roles(self):
        graph={'nodes':[{'id':'a','chinese_scope':True,'has_bilibili_account':True}],'meta':{}}
        accounts={'a':{'creator_id':'a','label':'A','identity_state':'confirmed','scope':'confirmed','appearance_video_ids':[]},
                  'p':{'creator_id':'bilibili:2','label':'P','identity_state':'unknown','scope':'core','appearance_video_ids':[],
                       'selected_work_publisher':True,'selected_publications':[{'aid':'1'}]}}
        events=[{'event_id':'1','source_uid':'a','target_uid':'p','video_id':'1','rpid':'2','identity_state':'unknown'}]
        edges=integrate(graph,{'accounts':accounts,'events':[],'observed_events':events,'meta':{}})
        node=next(n for n in graph['nodes'] if n['id']=='bilibili:2')
        self.assertTrue(node['chinese_scope']);self.assertTrue(node['has_bilibili_account']);self.assertEqual(node['identity_state'],'unknown')
        self.assertTrue(edges[0]['analysis_enabled']);self.assertEqual(accounts['p']['appearance_video_ids'],[])
    def test_selected_publisher_without_any_interaction_event_is_not_a_node(self):
        graph={'nodes':[],'meta':{}}
        accounts={'p':{'creator_id':'bilibili:9','label':'P','identity_state':'unknown','scope':'core',
                       'selected_work_publisher':True,'selected_publications':[{'aid':'1'}],
                       'appearance_video_ids':[]}}
        edges=integrate(graph,{'accounts':accounts,'observed_events':[],'events':[],'meta':{}})
        self.assertEqual(edges,[]);self.assertEqual(graph['nodes'],[])
        self.assertIsNone(accounts['p']['node_id'])
        self.assertEqual(accounts['p']['graph_excluded_reason'],'no_interaction_events')
