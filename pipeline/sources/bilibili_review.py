"""Offline review of immutable cached responses against an otoDB snapshot."""
import argparse
import hashlib
import json
from pathlib import Path
from .bilibili_probe import comment_rows, rows, description_mentions


def review(probe_dir, dataset_path, output, identity_graph=None):
    report = json.loads((probe_dir/'endpoint_probe.json').read_bytes())
    accepted_policy = report.get('sort_policy') == 'like_sorted_available_top5' and report.get('page_crosscheck') == 'not_required_user_policy'
    videos = json.loads((probe_dir/'video_observations.json').read_bytes())
    dataset = json.loads(dataset_path.read_bytes())
    identity=json.loads(identity_graph.read_bytes()) if identity_graph else None
    redirects={}
    comments = []
    video_ids={v['aid'] for v in videos};metadata_records={};reply_records={}
    for probe in report['probes']:
        raw = Path(probe['raw_file']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != probe['sha256']:
            raise ValueError('Cached response hash mismatch')
        if probe['endpoint'].endswith('/reply'):reply_records[str(probe['params']['oid'])]=probe
        if probe['state']=='ok' and probe['endpoint'].endswith('/view'):
            metadata_records[str(json.loads(raw)['data'].get('aid'))]=probe
        if probe['state'] == 'ok' and probe['endpoint'].endswith('/reply') and str(probe['params']['oid']) in video_ids:
            for c in comment_rows(json.loads(raw)['data']):
                comments.append({**c, 'aid': str(probe['params']['oid']),
                                 'observed_at': probe['observed_at'], 'response_sha256': probe['sha256']})
    comments = list({(c['aid'], c['rpid']): c for c in comments}.values())
    accounts = {}
    for a in dataset['accounts']:
        if a['site'] == '3' and ('creators' not in dataset or a['tag_id'] in dataset['creators']):
            accounts.setdefault(str(a['content_id']), set()).add(a['tag_id'])
    evidence = {}
    for p in dataset['participation']:
        bits = int(p.get('creator_roles') or 0)
        if p['used_as_source'] == 'f' and bits & 31 and not bits & ~63:
            evidence.setdefault(p['work_tag_id'], []).append({**p,
                'work_url': 'https://otodb.net/work/'+p['work_id']})
    uids = {v['publisher_uid'] for v in videos}
    uids.update(c['speaker_uid'] for c in comments)
    uids.update(m['target_uid'] for c in comments for m in c['mentions'])
    uids.update(m['target_uid'] for v in videos for m in description_mentions(v))
    uids={u for u in uids if u.isdigit() and int(u)>0}
    if identity is not None:
        from pipeline.normalize.interaction_identity import resolve_interaction_identities
        candidates={cid for uid in uids for cid in accounts.get(uid,set()) if cid in dataset['creators']}
        redirects=resolve_interaction_identities(identity,dataset,candidates)
    canonical_evidence={}
    for cid,credits in evidence.items():canonical_evidence.setdefault(redirects.get('otodb:'+cid,'otodb:'+cid),[]).extend(credits)
    def evidence_key(p):
        try:return (0,int(p.get('work_id')),int(p.get('work_tag_id')),str(p.get('id','')))
        except (TypeError,ValueError):return (1,str(p.get('work_id','')),str(p.get('work_tag_id','')),str(p.get('id','')))
    for credits in canonical_evidence.values():credits.sort(key=evidence_key)
    verification = {}
    for uid in sorted(uids):
        ids = accounts.get(uid, set())
        canonical_ids=sorted({redirects.get('otodb:'+cid,'otodb:'+cid) for cid in ids})
        eligible = [p for cid in canonical_ids for p in canonical_evidence.get(cid, [])]
        state = 'otodb_creator_evidence' if len(canonical_ids) == 1 and eligible else 'unknown'
        verification[uid] = {'account_id': uid, 'state': state, 'creator_ids': sorted(ids),
                             'canonical_creator_ids':canonical_ids,'mapping_state':'resolved' if len(canonical_ids)==1 else 'unknown',
                             'evidence': eligible if state != 'unknown' else [],
                             'basis': 'otodb_account_uid_and_explicit_production_credit',
                             'own_upload_checked': False}
    owners = {v['aid']: v['publisher_uid'] for v in videos}
    def self_event(source,target):
        return source==target or all(len(verification[u]['canonical_creator_ids'])==1 for u in [source,target]) and verification[source]['canonical_creator_ids']==verification[target]['canonical_creator_ids']
    events = {}
    for c in comments:
        if c['speaker_uid'] not in verification:continue
        targets = [('comment_mention', m['target_uid']) for m in c['mentions']]
        if not c['is_pinned']:
            targets.append(('video_comment', owners[c['aid']]))
        for kind, target in targets:
            if target not in verification:continue
            key = f"bilibili:{c['aid']}:{c['rpid']}:{kind}:{c['speaker_uid']}:{target}"
            both = all(verification[u]['state'] == 'otodb_creator_evidence' for u in [c['speaker_uid'], target])
            events[key] = {'event_id': key, 'event_type': kind, 'source_uid': c['speaker_uid'],
                           'target_uid': target, 'video_id': c['aid'], 'rpid': c['rpid'],
                           'self_event': self_event(c['speaker_uid'],target),
                           'identity_state': 'otodb_supported' if both else 'unknown',
                           'review_state': 'account_evidence_reviewed' if accepted_policy else 'offline_checked_page_unverified',
                           'observed_at': c['observed_at'], 'response_sha256': c['response_sha256']}
    descriptions=[]
    for v in videos:
        mentions=description_mentions(v)
        descriptions.append({'aid':v['aid'],'mentions':mentions,'desc':v.get('desc'),'desc_v2':v.get('desc_v2')})
        for m in mentions:
            source=v['publisher_uid'];target=m['target_uid']
            if source not in verification or target not in verification:continue
            key=f"bilibili:{v['aid']}:description_mention:{source}:{target}"
            both=all(verification[u]['state']=='otodb_creator_evidence' for u in [source,target])
            record=metadata_records.get(v['aid'],{})
            events[key]={'event_id':key,'event_type':'description_mention','source_uid':source,'target_uid':target,
                         'video_id':v['aid'],'rpid':'','self_event':self_event(source,target),
                         'identity_state':'otodb_supported' if both else 'unknown',
                         'review_state':'account_evidence_reviewed' if accepted_policy else 'offline_checked_page_unverified',
                         'observed_at':v.get('observed_at',record.get('observed_at')),
                         'response_sha256':v.get('response_sha256',record.get('sha256'))}
    output.mkdir(parents=True, exist_ok=False)
    result = {'network_requests': 0, 'videos': len(videos), 'comments': len(comments),
              'pinned_comments': sum(c['is_pinned'] for c in comments),
              'comments_without_valid_speaker_uid':sum(c['speaker_uid'] not in verification for c in comments),
              'mention_occurrences': sum(len(c['mentions']) for c in comments),
              'description_mention_occurrences':sum(len(d['mentions']) for d in descriptions),
              'events': len(events), 'identity_supported_events': sum(e['identity_state']=='otodb_supported' for e in events.values()),
              'unique_event_comments': len({(e['video_id'], e['rpid']) for e in events.values() if e['rpid']}),
              'verified_creator_accounts': sum(v['state']!='unknown' for v in verification.values()),
              'unknown_accounts': sum(v['state']=='unknown' for v in verification.values()),
              'dataset_sha256': hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
              'identity_redirects_sha256':hashlib.sha256(json.dumps(redirects,sort_keys=True).encode()).hexdigest(),
              'probe_sha256': hashlib.sha256((probe_dir/'endpoint_probe.json').read_bytes()).hexdigest(),
              't14_admitted': accepted_policy, 'graph_admitted': False,
              'adapter_scope': 'public_metadata_like_sorted_comments_otodb_creator_evidence',
              'sort_policy': report.get('sort_policy','observed_like_sorted_subset'),
              'ranking_origin':'local_like_sort_of_returned_top_level_subset',
              'page_crosscheck_required': not accepted_policy,
              'decision': 'Identity-supported subset available for local statistics; creator-post API disabled' if accepted_policy else 'Continue offline only; page comparison and hot ordering unverified; public posts access stopped'}
    for name, data in [('review.json',result),('comment_observations.json',comments),('description_observations.json',descriptions),('creator_verification.json',verification)]:
        (output/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    columns = ['event_id','event_type','source_uid','target_uid','video_id','rpid','self_event','identity_state','review_state','observed_at','response_sha256']
    rows(output/'interaction_events.csv',events.values(),columns)
    rows(output/'creator_verification.csv',
         [{**v, 'creator_ids': json.dumps(v['creator_ids']), 'evidence': json.dumps(v['evidence'],ensure_ascii=False)} for v in verification.values()],
         ['account_id','state','creator_ids','basis','own_upload_checked','evidence'])
    supported=[e for e in events.values() if e['identity_state']=='otodb_supported' and not e['self_event']]
    stats={'scope':'selected_videos_only','policy_accepted':accepted_policy,
           'videos':len(videos),'observed_comments':len(comments),'candidate_events':len(events),
           'identity_supported_events':len(supported),
           'identity_supported_unique_comments':len({(e['video_id'],e['rpid']) for e in supported if e['rpid']}),
           'source_accounts':len({e['source_uid'] for e in supported}),
           'target_accounts':len({e['target_uid'] for e in supported}),
           'unknown_accounts':result['unknown_accounts'],'graph_admitted':False}
    coverage=[]
    for v in videos:
        observed=[c for c in comments if c['aid']==v['aid'] and not c['is_pinned']]
        likes=[c['like'] for c in observed]
        reply=reply_records.get(v['aid'],{});available=reply.get('state')=='ok'
        coverage.append({'aid':v['aid'],'bvid':v['bvid'],'observed_top_level_comments':len(observed),
                         'target_limit':5,'limit_filled':len(observed)==5,
                         'observed_likes_descending':bool(likes) and all(isinstance(x,(int,float)) for x in likes) and likes==sorted(likes,reverse=True),
                         'coverage':'available_subset' if available else 'unavailable',
                         'comment_state':reply.get('state','not_attempted'),'api_code':reply.get('api_code'),
                         'response_sha256':reply.get('sha256'),'sort_parameter':1})
    rows(output/'comment_coverage.csv',coverage,['aid','bvid','observed_top_level_comments','target_limit','limit_filled','observed_likes_descending','coverage','comment_state','api_code','response_sha256','sort_parameter'])
    (output/'statistics.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (output/'pilot_audit.md').write_text(
        '# 视频互动离线复核\n\n'
        f"{result['videos']}部视频，{result['comments']}条评论，{result['mention_occurrences']}次评论结构化提及、{result['description_mention_occurrences']}次简介提及，"
        f"{result['events']}个分项事件，涉及{result['unique_event_comments']}条原评论。\n\n"
        '逐条核对提及原文位置、响应UID、真实说话人及去重键；所有事件保留原件哈希。'
        '制作证据仅接受otoDB明确制作角色且非素材引用，账号与作品证据不等于本人公开投稿核验。'+
        ('按评论点赞排序口径复核账号及事件证据。图谱接入要求目录完整且通过独立审计。' if accepted_policy else '采样口径未获接受，不准入图谱。')+
        '观察子集不是网页热评前五；unknown不等于非作者。准入状态见review.json。\n',encoding='utf-8')
    return result


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['probe_dir','dataset','output']: parser.add_argument(name,type=Path)
    parser.add_argument('--identity-graph',type=Path)
    args=parser.parse_args()
    print(json.dumps(review(args.probe_dir,args.dataset,args.output,args.identity_graph),ensure_ascii=False))
