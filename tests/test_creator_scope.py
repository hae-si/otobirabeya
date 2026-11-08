import unittest
from pipeline.normalize.creator_scope import classify


class ScopeTests(unittest.TestCase):
    def setUp(self):
        self.creators = {str(i): {'name': 'synthetic', 'slug': 'synthetic'} for i in range(1, 5)}
        self.connections = [{'id': str(i), 'tag_id': tid, 'site': site, 'content_id': 'synthetic', 'dead': dead}
                            for i, (tid, site, dead) in enumerate([('1','3','f'),('2','3','f'),('2','1','f'),('3','1','f'),('4','3','t')], 1)]

    def test_platform_rule_and_dead(self):
        r = classify(self.creators, self.connections)
        self.assertEqual([r[str(i)]['scope_status'] for i in range(1, 5)], ['chinese_default', 'chinese_default', 'undecided', 'undecided'])
        self.connections.append({'id':'6','tag_id':'1','site':'2','content_id':'synthetic','dead':'f'})
        self.assertEqual(classify(self.creators, self.connections)['1']['scope_status'], 'chinese_default')

    def test_override_priority_and_persistence(self):
        base = {'creator_id':'otodb:creator:2','reason':'synthetic evidence','reviewed_at':'2026-10-28','source_urls':'https://example.org/evidence'}
        overrides = [dict(base, method='human',scope_status='non_chinese'), dict(base,method='model',scope_status='chinese')]
        r = classify(self.creators, self.connections, overrides)
        self.assertEqual(r['2']['scope_status'], 'non_chinese')
        self.assertEqual(r['2']['method'], 'human')
        self.assertEqual(classify(self.creators, [], overrides)['2']['scope_status'], 'non_chinese')
        self.creators['1']['aliased_to_id']='2'
        self.assertEqual(classify(self.creators, self.connections)['1']['scope_status'], 'undecided')
