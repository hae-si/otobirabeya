import unittest
from pipeline.graph.author_projection import project


class ProjectionTests(unittest.TestCase):
    def test_full_denominator_and_unrelated_exclusion(self):
        creators = {str(i): {'name': 'synthetic'} for i in range(1, 6)}
        works = {'1': {'title': 'synthetic'}, '2': {'title': 'unrelated'}}
        credits = [{'work_id': w, 'work_tag_id': i, 'creator_roles': None, 'used_as_source': 'f'}
                   for w, ids in [('1', ['1', '2', '3']), ('2', ['4', '5'])] for i in ids]
        edges, events, _ = project(creators, works, credits, [], {'1'})
        self.assertEqual({(e['source'],e['target']) for e in edges}, {('1','2'),('1','3')})
        self.assertTrue(all(e['weights']['affiliation'] == .5 for e in edges))
        self.assertEqual(events['event:1']['n'], 3)
        self.assertNotIn('event:2', events)

    def test_project_dedup_and_role32_included(self):
        creators = {str(i): {} for i in range(1,5)}
        works = {str(i): {'title': 'synthetic'} for i in [10,11,12]}
        credits = [{'work_id': w,'work_tag_id': t,'creator_roles': role,'used_as_source':'f'}
                   for w,t,role in [('10','1','1'),('10','2',None),('11','1',None),('11','3',None),('12','2',None),('12','4','32')]]
        relations = [{'relation':'2','A_id':w,'B_id':'12'} for w in ['10','11']]
        edges, events, _ = project(creators, works, credits, relations, {'1','2'})
        self.assertEqual(len(events),1)
        self.assertEqual(events['event:12']['n'],4)
        self.assertEqual(next(e for e in edges if e['source']=='1' and e['target']=='2')['weights']['affiliation'],0.3333333333)
        self.assertEqual(len(edges),5)
        self.assertTrue(all('creation' not in e['weights'] for e in edges))
        self.assertIn('4',events['event:12']['participants'])
        self.assertEqual(events['event:12']['roles']['4'],32)

    def test_cooperation_tag_marks_event_and_keeps_pairs(self):
        creators={'1':{},'2':{},'3':{}}
        works={'1':{'title':'synthetic'}}
        credits=[{'work_id':'1','work_tag_id':i,'creator_roles':'3','used_as_source':'f'} for i in ['1','2','3']]
        edges,events,_=project(creators,works,credits,[],{'1'},cooperation_works={'1'})
        self.assertTrue(events['event:1']['cooperation'])
        self.assertEqual(len(edges),2)
        self.assertEqual(edges[0]['weights'],{'affiliation':.5,'project':0})
        self.assertNotIn('confirmed_work_ids',edges[0])
