import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from pipeline.normalize.snapshot import normalize_tables, resolve_chains


def fixture():
    tables={t:[] for t in ['otodb_tagwork','otodb_mediawork','otodb_tagworkinstance','otodb_workrelation','otodb_tagworkcreatorconnection','otodb_worksource']}
    tables['otodb_tagwork']=[{'id':str(i),'name':'synthetic-'+str(i),'slug':'synthetic-'+str(i),'category':'4',
                             'aliased_to_id':'2' if i==1 else None,'deprecated':'f'} for i in range(1,7)]
    tables['otodb_mediawork']=[{'id':i,'title':'synthetic-work','status':'1','moved_to_id':target} for i,target in [('10','11'),('11',None),('12',None)]]
    tables['otodb_tagworkcreatorconnection']=[{'id':str(i),'tag_id':str(i),'site':'3','content_id':'synthetic-account','dead':'f'} for i in [1,4,5,6]]
    tables['otodb_tagworkinstance']=[{'id':str(i),'work_id':w,'work_tag_id':c,'creator_roles':bits,'used_as_source':'f'}
                                    for i,(w,c,bits) in enumerate([('10','1','1'),('11','2','2'),('11','3','2'),('12','4',None),('11','5','32')],1)]
    return tables


class NormalizationTests(unittest.TestCase):
    def test_explicit_alias_migration_merge_and_isolates(self):
        data=normalize_tables(fixture())
        self.assertNotIn('1',data['creators'])
        self.assertNotIn('10',data['works'])
        credit=next(r for r in data['participation'] if r['work_tag_id']=='2')
        self.assertEqual(credit['creator_roles'],'3')
        self.assertEqual(credit['source_work_ids'],['10','11'])
        self.assertEqual(credit['source_record_ids'],['1','2'])
        self.assertEqual(data['scopes']['2']['scope_status'],'chinese_default')
        self.assertEqual(data['audit']['isolated_core_counts'],{'only_single_author_events':1,'no_creator_work_records':1})
        self.assertEqual(data['works']['11']['classification'],'co_creation_candidate')

    def test_cycles_and_dangling_are_not_merged(self):
        mapping,issues=resolve_chains({'1':{'target':'2'},'2':{'target':'1'},'3':{'target':'4'},'5':{'target':None}},'target')
        self.assertEqual(mapping,{'5':'5'})
        self.assertEqual({r['reason'] for r in issues},{'cycle','dangling_target'})

    def test_manual_classification_survives_normalization(self):
        override={'work_id':'10','classification':'co_creation_confirmed','source_urls':'https://example.org/synthetic-evidence',
                  'reason':'synthetic test only','reviewed_at':'2026-10-28'}
        data=normalize_tables(fixture(),work_overrides=[override])
        self.assertEqual(data['works']['11']['classification'],'co_creation_confirmed')
        self.assertEqual(data['works']['11']['classification_method'],'human')
        self.assertEqual(next(c for c in data['classifications'] if c['work_id']=='11')['evidence'],override)

    def test_conflicting_alias_overrides_rejected(self):
        base={'method':'human','source_urls':'https://example.org','reason':'synthetic','reviewed_at':'2026-10-28'}
        rows=[dict(base,creator_id='otodb:creator:1',scope_status='chinese'),dict(base,creator_id='otodb:creator:2',scope_status='non_chinese')]
        with self.assertRaises(ValueError):normalize_tables(fixture(),overrides=rows)

    def test_shared_accounts_and_urls_are_flagged_not_merged(self):
        tables=fixture()
        tables['otodb_worksource']=[{'id':str(i),'media_id':wid,'url':'https://example.org/synthetic-shared-url',
                                    'is_pending':'f','published_date':None} for i,wid in [(1,'11'),(2,'12')]]
        data=normalize_tables(tables)
        self.assertTrue(data['audit']['shared_account_conflicts'])
        self.assertEqual(data['audit']['publication_url_conflicts'][0]['work_ids'],['11','12'])
        self.assertIn('4',data['creators'])
        self.assertIn('2',data['creators'])
        self.assertIn('11',data['works'])
        self.assertIn('12',data['works'])

    def test_manual_project_classification_reaches_projection(self):
        from pipeline.graph.author_projection import project
        override={'work_id':'11','classification':'collab_project','source_urls':'https://example.org/synthetic',
                  'reason':'synthetic project evidence','reviewed_at':'2026-10-28'}
        data=normalize_tables(fixture(),work_overrides=[override])
        edges,events,_=project(data['creators'],data['works'],data['participation'],data['relations'],{'2'})
        self.assertEqual(events['event:11']['type'],'project')
        self.assertEqual(edges[0]['weights']['project'],0.5)
        self.assertEqual(len(edges),2)

    def test_web_projection_reads_normalized_json_without_raw(self):
        from pipeline.author_site import assemble
        data=normalize_tables(fixture())
        data['meta']={'snapshot_sha256':'synthetic','snapshot_date':'2026-10-28','normalizer_version':'synthetic-test'}
        root=Path(__file__).resolve().parents[1]/'tmp';root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as directory:
            path=Path(directory)/'dataset.json';path.write_text(json.dumps(data),encoding='utf-8')
            with patch('pipeline.normalize.snapshot.normalize_snapshot',side_effect=AssertionError('Must not read raw snapshot')):
                result=assemble(path)
        self.assertEqual(result['meta']['snapshot_sha256'],'synthetic')
        self.assertEqual(result['meta']['chinese_scope_count'],4)
