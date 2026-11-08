import unittest
from pipeline.normalize.profile_scope import bilibili_links, mapping_candidates


class ProfileScopeTests(unittest.TestCase):
    def test_mobile_profile(self):
        links = bilibili_links({'fields': [{'value': 'https://m.bilibili.com/space/1786556'}]})
        self.assertEqual(links[0]['uid'], '1786556')

    def test_html_and_description(self):
        links = bilibili_links({'description': '主页 https://space.bilibili.com/123?x=1', 'fields': [{'value': '<a href="https://space.bilibili.com/456">B站</a>'}]})
        self.assertEqual({x['uid'] for x in links}, {'123', '456'})

    def test_not_video_or_fake_domain_or_label(self):
        for value in ['https://www.bilibili.com/video/BV1abc', 'https://space.bilibili.com.evil.org/123', 'Bilibili', 'https://space.bilibili.com/0']:
            self.assertEqual(bilibili_links({'description': value}), [])

    def test_verified_link(self):
        self.assertEqual(bilibili_links({'verifiedLinks': ['https://space.bilibili.com/123']})[0]['uid'], '123')

    def test_uid_comparison_conflicts_and_missing(self):
        dataset={'creators': {'a': {}, 'b': {}}, 'accounts': [
            {'site':'3','dead':'f','content_id':'123','tag_id': cid} for cid in ['a','b']]}
        rows=mapping_candidates(dataset, {'u':{'evidence':[{'uid':'123'}]},'v':{'evidence':[{'uid':'999'}]}})
        self.assertEqual(rows[0]['state'],'conflict')
        self.assertEqual(rows[1]['state'],'no_otodb_uid_match')
