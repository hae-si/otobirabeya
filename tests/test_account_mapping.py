import unittest
from pipeline.normalize.account_mapping import prepare


class MappingTests(unittest.TestCase):
    def setUp(self):
        self.dataset={'creators':{'a':{},'b':{}}}
        self.social={'accounts':[{'id':'u'},{'id':'unknown'}], 'mappings':[]}
        self.candidates=[{'user_id':'u','creator_ids':['a'],'state':'unique_explicit_platform_link'}]

    def test_unknown_account_retained(self):
        result=prepare(self.dataset,self.social,self.candidates)
        self.assertEqual(len(result),2)
        self.assertIsNone(next(r for r in result if r['account_id']=='unknown')['creator_id'])

    def test_conflict_not_merged(self):
        result=prepare(self.dataset,self.social,self.candidates+[{'user_id':'u','creator_ids':['b']}])
        row=next(r for r in result if r['account_id']=='u')
        self.assertEqual(row['state'],'conflict');self.assertIsNone(row['creator_id'])

    def test_independent_override_removes_upstream_mapping(self):
        row={'account_id':'u','decision':'independent','creator_id':'','display_name':'Test',
             'source_urls':'https://example.org/evidence','reason':'explicit correction','reviewed_at':'2026-10-28'}
        result=prepare(self.dataset,self.social,self.candidates,[row])
        self.assertIsNone(next(r for r in result if r['account_id']=='u')['creator_id'])

    def test_invalid_override_rejected(self):
        with self.assertRaises(ValueError):
            prepare(self.dataset,self.social,self.candidates,[{'account_id':'missing'}])
