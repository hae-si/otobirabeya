import copy
import unittest
from pipeline.sources.otomadsite_seeds import select


class SeedSelectionTests(unittest.TestCase):
    def fixture(self):
        nodes=[];accounts=[]
        for i in range(8):
            uid=str(i);a={'id':uid,'username':'u'+uid,'host':None,'isBot':False};accounts.append(a)
            nodes.append({'id':'node:'+uid,'core':True,'otodb_id':uid if i%2 else None,'community':i%3,'accounts':[a]})
        return {'accounts':accounts,'edges':[],'coverage':[{'user_id':'0'}]},{'nodes':nodes}
    def test_reproducible_strata_and_no_input_mutation(self):
        s,g=self.fixture();before=copy.deepcopy((s,g));a=select(s,g)
        self.assertEqual(a,select(s,g));self.assertEqual((s,g),before)
        self.assertEqual(len(a),4);self.assertEqual(len({r['selection']['stratum'] for r in a}),4)
    def test_sampled_failed_remote_and_bot_are_skipped(self):
        s,g=self.fixture();g['nodes'][1]['accounts'][0]['host']='remote.example';g['nodes'][2]['accounts'][0]['isBot']=True
        result=select(s,g,excluded={'3'})
        self.assertTrue(all(r['otomadsite_id'] not in {'0','1','2','3'} for r in result))

    def test_non_core_never_selected_even_with_mapping(self):
        s,g=self.fixture()
        for n in g["nodes"]:n["core"]=False
        self.assertEqual(select(s,g),[])
        g["nodes"][1]["core"]=True
        self.assertEqual([r["otomadsite_id"] for r in select(s,g)],["1"])

    def test_second_account_is_not_a_new_seed_author(self):
        s,g=self.fixture()
        g["nodes"][1]["accounts"].append({"id":"0","username":"already_sampled","host":None})
        result=select(s,g)
        self.assertNotIn("node:1",{r["selection"]["node_id"] for r in result})
        self.assertEqual(len(result),len({r["selection"]["node_id"] for r in result}))
