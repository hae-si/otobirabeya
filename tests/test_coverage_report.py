import unittest
from pipeline.sources.otomadsite_coverage import report, core_discovery


class CoverageTests(unittest.TestCase):
    def test_unknown_authors_and_directions_are_not_complete(self):
        dataset={'creators':{'a':{'name':'A'},'b':{'name':'B'}},'scopes':{'a':{'scope_status':'chinese_default'},'b':{'scope_status':'chinese'}}}
        social={'coverage':[{'user_id':'u','endpoint':'following','state':'visible_list_exhausted'}]}
        graph={'nodes':[{'otodb_id':'a','accounts':[{'id':'u','username':'u','host':None}]}]}
        r=report(dataset,social,graph)
        self.assertEqual(r['platform_presence_unknown'],1);self.assertEqual(r['direction_completion_ratio'],.5);self.assertFalse(r['known_accounts_95_percent_gate'])
    def test_no_accounts_is_not_success(self):
        r=report({'scopes':{},'creators':{}},{'coverage':[]},{'nodes':[]})
        self.assertIsNone(r['direction_completion_ratio']);self.assertFalse(r['known_accounts_95_percent_gate'])

    def test_core_discovery_excludes_other_accounts_and_deduplicates_authors(self):
        graph={'nodes':[{'id':'known','core':True,'accounts':[{'id':'a'},{'id':'b'}]},{'id':'new','core':True,'accounts':[{'id':'c'}]},{'id':'other','core':False,'accounts':[{'id':'d'}]}]}
        r=core_discovery({'a','b','c','d'},['known'],graph)
        self.assertEqual(r['observed_core_authors'],2);self.assertEqual(r['core_known_ratio'],.5)
        self.assertFalse(core_discovery({'a'},None,graph)['evaluable'])

    def test_small_core_sample_cannot_prove_saturation(self):
        graph={"nodes":[{"id":"known","core":True,"accounts":[{"id":"a"}]}]}
        r=core_discovery({"a"},["known"],graph)
        self.assertEqual(r["core_known_ratio"],1)
        self.assertFalse(r["enough_core_authors"])

    def test_only_platform_known_identity_counts_as_known(self):
        graph={"nodes":[{"id":str(i),"core":True,"accounts":[{"id":"a"+str(i)}]} for i in range(20)]}
        r=core_discovery({"a"+str(i) for i in range(20)},[str(i) for i in range(19)],graph)
        self.assertEqual(r["core_known_ratio"],.95)
        self.assertTrue(r["enough_core_authors"])
        self.assertEqual(r["new_core_authors"],1)
