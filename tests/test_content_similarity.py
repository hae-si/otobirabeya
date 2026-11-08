import unittest
from pipeline.graph.content_similarity import compute


def fixture(shared=False, large=False):
    people=['a','b']+(['c'+str(i) for i in range(50)] if large else [])
    works={'1':{},'2':{},'3':{}}
    participation=[dict(work_id='1' if shared or a=='a' else '2',work_tag_id=a,
                        creator_roles='1',used_as_source='f',source_record_ids=[a]) for a in people]
    return {'creators':{a:{} for a in people+['isolated']},'works':works,'participation':participation,
            'tags':{'10':{'name':'song'},'11':{'name':'source'}},
            'work_tags':[{'work_id':w,'tag_id':'10','category':'2','source_records':[]} for w in ['1','2']]}


class ContentTests(unittest.TestCase):
    def test_different_works_and_single_tag_warning(self):
        d=fixture();r=compute(d)
        e=r['edges'][0]
        self.assertAlmostEqual(e['similarity'],1)
        self.assertEqual(e['tags'][0]['same_works'],[])
        self.assertEqual(e['distinct_work_tag_support'],1)
        self.assertIn('single_shared_tag',e['confidence_flags'])
        self.assertEqual(len(d['creators']),3)

    def test_large_same_work_explicitly_warns(self):
        r=compute(fixture(shared=True,large=True),author_ids=['a','b'])
        self.assertIn('same_work_only',r['edges'][0]['confidence_flags'])
        self.assertEqual(r['edges'][0]['distinct_work_tag_support'],0)

    def test_source_reference_not_participant(self):
        d=fixture();d['participation'][0]['used_as_source']='t'
        self.assertEqual(compute(d)['edges'],[])

    def test_idf_units_distinct_and_deterministic(self):
        d=fixture()
        d['participation'].append(dict(work_id='3',work_tag_id='isolated',creator_roles='1',used_as_source='f'))
        d['works']['4']={}
        a=compute(d);b=compute(d,idf_unit='authors')
        self.assertNotEqual(a['edges'][0]['tags'][0]['idf'],b['edges'][0]['tags'][0]['idf'])
        self.assertEqual(a['edges'],compute(d)['edges'])

    def test_no_content_and_zero_idf(self):
        d=fixture();d['work_tags']=[]
        self.assertEqual(compute(d)['edges'],[])
        d=fixture();d['work_tags'].append(dict(work_id='3',tag_id='10',category='2'))
        self.assertEqual(compute(d)['edges'],[])

    def test_high_frequency_no_silent_truncation_and_topk_union(self):
        d=fixture(shared=True,large=True);r=compute(d,top_k=10)
        self.assertEqual(r['meta']['coverage']['2']['candidate_pairs'],52*51//2)
        self.assertFalse(r['meta']['truncated'])
        self.assertLessEqual(len(r['edges']),52*10)
