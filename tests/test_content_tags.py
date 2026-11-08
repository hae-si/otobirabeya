import unittest
from pipeline.normalize.content_tags import recover


class ContentTagTests(unittest.TestCase):
    def tables(self):
        return {'otodb_tagwork': [dict(id=str(i), category=c, name='same name',
                    aliased_to_id=None, deprecated='t' if i==6 else 'f')
                    for i,c in [(1,'2'),(2,'2'),(3,'3'),(4,'2'),(5,'4'),(6,'3')]],
                'otodb_tagworkinstance': [dict(id=str(i), work_id=w, work_tag_id=t,
                    used_as_source='t', creator_roles=None)
                    for i,w,t in [(1,'10','1'),(2,'11','2'),(3,'11','3'),(4,'11','4'),(5,'11','6'),(6,'99','2')]],
                'otodb_tagworkparenthood': [dict(id='1', parent_id='1', tag_id='3', primary='t')]}

    def test_alias_migration_dedup_and_samples_retained(self):
        r=recover(self.tables(), {'11':{}}, {'1':'2','2':'2','3':'3','4':'3','5':'5','6':'6'}, {'10':'11','11':'11'})
        song=next(x for x in r['work_tags'] if x['tag_id']=='2')
        self.assertEqual([x['id'] for x in song['source_records']], ['1','2'])
        self.assertEqual(song['source_records'][0]['used_as_source'], 't')
        self.assertEqual(r['tag_audit']['deduplicated_instances'], 1)
        self.assertEqual(r['tag_audit']['exclusions_by_reason'], {'cross_category_alias':1,'deprecated_tag':1,'unavailable_work':1})
        self.assertEqual(r['tag_relations'][0]['canonical_parent_id'], '2')

    def test_same_name_different_categories_do_not_merge(self):
        r=recover(self.tables(), {'11':{}}, {str(i):str(i) for i in range(1,7)}, {'11':'11'})
        self.assertEqual({x['tag_id'] for x in r['work_tags']}, {'2','3','4'})

    def test_unresolved_and_creator_tags_remain_distinct(self):
        t=self.tables()
        t['otodb_tagworkinstance'].append(dict(id='7',work_id='11',work_tag_id='5',used_as_source='t',creator_roles='1'))
        r=recover(t, {'11':{}}, {'5':'5'}, {'11':'11'})
        self.assertEqual(len(r['work_tags']),1)
        self.assertEqual(r['work_tags'][0]['category'],'4')
        self.assertEqual(r['tag_audit']['exclusions_by_reason']['unresolved_tag'],6)
