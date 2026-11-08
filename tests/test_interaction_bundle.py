import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from pipeline.interaction_bundle import bundle, write_bundle


class InteractionBundleTests(unittest.TestCase):
    def fixture(self,p):
        def save(name,value): (p/name).write_text(json.dumps(value),encoding='utf-8')
        save('dataset.json',{'creators':{'1':{'name':'A'},'2':{'name':'B'}}})
        save('endpoint_probe.json',{})
        save('review.json',{'page_crosscheck_required':False,'dataset_sha256':hashlib.sha256((p/'dataset.json').read_bytes()).hexdigest(),
            'probe_sha256':hashlib.sha256((p/'endpoint_probe.json').read_bytes()).hexdigest(),'sort_policy':'like_sorted_available_top5',
            'comments':1,'pinned_comments':0,'unknown_accounts':1,'verified_creator_accounts':2})
        save('statistics.json',{'policy_accepted':True,'identity_supported_events':1})
        save('creator_verification.json',{str(n):{'creator_ids':[str(n)],'state':'otodb_creator_evidence','evidence':[{'work_url':'https://otodb.net/work/1','creator_roles':'2'}]} for n in [1,2]})
        save('video_observations.json',[{'aid':'10','bvid':'BVtest','title':'test','source_entries':[]}])
        save('comment_observations.json',[{'aid':'10','rpid':'5','message':'hello '*100,'mentions':[],'is_pinned':False,'like':5}])
        save('description_observations.json',[])
        (p/'comment_coverage.csv').write_text('aid,bvid\n10,BVtest\n')
        cols=['event_id','source_uid','target_uid','video_id','rpid','review_state','event_type','observed_at','response_sha256']
        with (p/'interaction_events.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=cols);w.writeheader()
            for ident,source,target in [('good','1','2'),('unknown','3','2'),('self','1','1')]:
                w.writerow(dict(zip(cols,[ident,source,target,'10','5','account_evidence_reviewed','video_comment','now','hash'])))
        return {'nodes':[],'meta':{}}

    def test_preview_excludes_unknown_and_self_and_limits_text(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'tmp') as root:
            p=Path(root);g=self.fixture(p);value=bundle(p,p,p/'dataset.json',g)
            self.assertEqual([e['event_id'] for e in value['events']],['good'])
            self.assertEqual(value['meta']['excluded_self_events'],1)
            self.assertLessEqual(len(value['events'][0]['excerpt']),182)
            self.assertEqual(g,{'nodes':[],'meta':{}})
            self.assertEqual(value['accounts']['3']['scope'],'all')
            self.assertEqual(value['accounts']['3']['identity_state'],'unknown')
            self.assertEqual(len(value['observed_events']),2)
            (p/'dataset.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'inputs changed'):bundle(p,p,p/'dataset.json',g)

    def test_site_bundle_preserves_both_event_lists_with_excerpts(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'tmp') as root:
            p=Path(root);g=self.fixture(p)
            local=bundle(p,p,p/'dataset.json',g)
            output=p/'interaction.json'
            write_bundle(p,p,p/'dataset.json',g,output)
            site=json.loads(output.read_bytes())
            for name in ('events','observed_events'):
                self.assertTrue(all('excerpt' in event for event in local[name]))
                self.assertEqual(site[name],local[name])

    def test_identity_merge_cannot_silently_change_approved_counts(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'tmp') as root:
            p=Path(root);g=self.fixture(p)
            g['meta']={'identity':{'redirects':{'otodb:2':'otodb:1'}}}
            with self.assertRaisesRegex(ValueError,'statistics mismatch'):bundle(p,p,p/'dataset.json',g)

    def test_peripheral_author_threshold_counts_comments_not_mentions_or_videos(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'tmp') as root:
            p=Path(root);g=self.fixture(p)
            comments=json.loads((p/'comment_observations.json').read_bytes())
            comments[0].update(speaker_uid='3',mentions=[{'target_uid':'3','name':'pending'},{'target_uid':'3','name':'pending'}])
            (p/'comment_observations.json').write_text(json.dumps(comments))
            v=bundle(p,p,p/'dataset.json',g)
            self.assertEqual(v['accounts']['3']['appearance_video_ids'],['10'])
            self.assertEqual(v['accounts']['3']['scope'],'all')
            videos=json.loads((p/'video_observations.json').read_bytes())
            videos.append({'aid':'20','bvid':'BVsecond','title':'second','source_entries':[]})
            (p/'video_observations.json').write_text(json.dumps(videos))
            (p/'description_observations.json').write_text(json.dumps([{'aid':'20','mentions':[{'target_uid':'3','name':'pending'}]}]))
            v=bundle(p,p,p/'dataset.json',g)
            self.assertEqual(v['accounts']['3']['appearance_video_ids'],['10','20'])
            self.assertEqual(v['accounts']['3']['scope'],'all')
            comments.append({**comments[0],'rpid':'6'})
            (p/'comment_observations.json').write_text(json.dumps(comments))
            v=bundle(p,p,p/'dataset.json',g)
            self.assertEqual(v['accounts']['3']['scope'],'peripheral')
            self.assertEqual(v['accounts']['3']['observed_comment_count'],2)
            self.assertEqual(v['accounts']['3']['identity_state'],'unknown')
            self.assertEqual(len(v['events']),1)
