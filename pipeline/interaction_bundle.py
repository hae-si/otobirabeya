"""Build the evidence sidecar consumed by the fourth graph layer and event views."""
import argparse
import csv
import hashlib
import json
from pathlib import Path


def bundle(review, probe, dataset_path, graph):
    paths=[review/n for n in ['review.json','statistics.json','interaction_events.csv','creator_verification.json','comment_observations.json','description_observations.json','comment_coverage.csv']]
    paths += [probe/'endpoint_probe.json',probe/'video_observations.json',dataset_path]
    audit=json.loads(paths[0].read_bytes());summary=json.loads(paths[1].read_bytes())
    if audit.get('page_crosscheck_required') is not False or not summary.get('policy_accepted'):
        raise ValueError('Interaction review policy not accepted')
    if hashlib.sha256(dataset_path.read_bytes()).hexdigest()!=audit['dataset_sha256'] or hashlib.sha256((probe/'endpoint_probe.json').read_bytes()).hexdigest()!=audit['probe_sha256']:
        raise ValueError('Interaction review inputs changed')
    dataset=json.loads(dataset_path.read_bytes());verification=json.loads((review/'creator_verification.json').read_bytes())
    videos=json.loads((probe/'video_observations.json').read_bytes())
    collection=json.loads((probe/'endpoint_probe.json').read_bytes())
    if (probe/'seed_coverage.csv').exists():paths.append(probe/'seed_coverage.csv')
    comments={(c['aid'],c['rpid']):c for c in json.loads((review/'comment_observations.json').read_bytes())}
    descriptions=json.loads((review/'description_observations.json').read_bytes())
    appearances={}
    video_ids={v['aid'] for v in videos}
    def observe(uid,aid):
        if aid not in video_ids:raise ValueError('Unknown appearance video')
        if uid and uid.isdigit() and int(uid)>0:appearances.setdefault(uid,set()).add(aid)
    for c in comments.values():
        observe(c.get('speaker_uid'),c['aid'])
        for mention in c.get('mentions',[]):observe(mention['target_uid'],c['aid'])
    for d in descriptions:
        for mention in d['mentions']:observe(mention['target_uid'],d['aid'])
    redirects=graph.get('meta',{}).get('identity',{}).get('redirects',{})
    nodes={n['id']:n for n in graph['nodes']}
    accounts={}
    for uid,v in verification.items():
        ids=v['creator_ids'];canonical_ids=v.get('canonical_creator_ids',['otodb:'+cid for cid in ids]);known=v['state']=='otodb_creator_evidence' and len(canonical_ids)==1 and bool(v['evidence'])
        if not known: continue
        cid=ids[0];canonical=redirects.get(canonical_ids[0],canonical_ids[0])
        accounts[uid]={'uid':uid,'creator_id':canonical,'label':nodes.get(canonical,{}).get('label',dataset['creators'][cid]['name']),
                       'mapping_state':'resolved',
                       'identity_state':'confirmed','scope':'confirmed','appearance_video_ids':sorted(appearances.get(uid,set())),
                       'node_id':canonical if canonical in nodes else None,
                       'evidence':[{'work_url':e['work_url'],'creator_roles':e['creator_roles'],'source_record_ids':e.get('source_record_ids',[])} for e in v['evidence']]}
    with (review/'interaction_events.csv').open(encoding='utf-8-sig',newline='') as f: events=list(csv.DictReader(f))
    if len({e['event_id'] for e in events})!=len(events): raise ValueError('Duplicate interaction event IDs')
    preview=[];self_count=0
    by_video={v['aid']:v for v in videos}
    for e in events:
        if e['video_id'] not in by_video: raise ValueError('Unknown interaction video')
        source=accounts.get(e['source_uid']);target=accounts.get(e['target_uid'])
        identity=source is not None and target is not None
        self_event=e['source_uid']==e['target_uid'] or (identity and source['creator_id']==target['creator_id'])
        if self_event:self_count+=1
        if not identity or self_event or e['review_state']!='account_evidence_reviewed':continue
        if e['event_type'] not in {'video_comment','comment_mention','description_mention'}:raise ValueError('Unknown event type')
        c=comments.get((e['video_id'],e['rpid'])) if e['rpid'] else None
        if e['rpid'] and not c:raise ValueError('Missing comment evidence')
        original=c['message'] if c else by_video[e['video_id']].get('desc','')
        target_name=target['label'];pos=original.find('@'+target_name)
        if c:
            m=next((m for m in c.get('mentions',[]) if m['target_uid']==e['target_uid']),None)
            if m:pos=m['start']
        start=max(0,pos-45) if pos>=0 else 0
        preview.append({k:e[k] for k in ['event_id','event_type','source_uid','target_uid','video_id','rpid','observed_at','response_sha256']} |
                       {'is_pinned':bool(c and c['is_pinned']),'like':c.get('like') if c else None,
                        'sample_rank':c.get('rank') if c else None,'response_rank':c.get('response_rank') if c else None,
                        'excerpt':('…' if start else '')+original[start:start+180]+('…' if len(original)>start+180 else '')})
    if len(preview)!=summary['identity_supported_events']:raise ValueError('Reviewed statistics mismatch after identity projection')
    labels={}
    for c in comments.values():
        for m in c.get('mentions',[]):labels.setdefault(m['target_uid'],m['name'])
    for d in descriptions:
        for m in d['mentions']:labels.setdefault(m['target_uid'],m['name'])
    all_uids=set(verification)|set(appearances)|{e[k] for e in events for k in ['source_uid','target_uid']}
    for uid in sorted(all_uids):
        if uid not in accounts:
            aids=sorted(appearances.get(uid,set()))
            verification_row=verification.get(uid,{})
            ids=verification_row.get('creator_ids',[])
            canonical_ids=verification_row.get('canonical_creator_ids',['otodb:'+cid for cid in ids])
            mapped=len(canonical_ids)==1
            canonical=redirects.get(canonical_ids[0],canonical_ids[0]) if mapped else redirects.get('bilibili:'+uid,'bilibili:'+uid)
            label=nodes.get(canonical,{}).get('label',dataset['creators'][ids[0]]['name']) if mapped else nodes.get(canonical,{}).get('label',labels.get(uid,'UID '+uid))
            accounts[uid]={'uid':uid,'creator_id':canonical,'label':label,
                           'mapping_state':'resolved' if mapped else 'unknown',
                           'node_id':canonical if canonical in nodes else None,'evidence':[],'identity_state':'unknown',
                           'scope':'related' if len(aids)>=2 else 'all','appearance_video_ids':aids}
    observed=[];self_count=0
    confirmed={e['event_id']:e for e in preview}
    for e in events:
        if e['source_uid']==e['target_uid'] or accounts[e['source_uid']]['creator_id']==accounts[e['target_uid']]['creator_id']:
            self_count+=1;continue
        if e['event_id'] in confirmed:observed.append({**confirmed[e['event_id']],'identity_state':'confirmed'});continue
        c=comments.get((e['video_id'],e['rpid'])) if e['rpid'] else None
        text=c['message'] if c else by_video[e['video_id']].get('desc','')
        observed.append({k:e[k] for k in ['event_id','event_type','source_uid','target_uid','video_id','rpid','observed_at','response_sha256']} |
                        {'is_pinned':bool(c and c['is_pinned']),'like':c.get('like') if c else None,
                         'sample_rank':c.get('rank') if c else None,'response_rank':c.get('response_rank') if c else None,
                         'excerpt':text[:180]+('…' if len(text)>180 else ''),'identity_state':'unknown'})
    with (review/'comment_coverage.csv').open(encoding='utf-8-sig',newline='') as f:coverage=list(csv.DictReader(f))
    selected_publications={}
    comment_ids={}
    for comment in comments.values():
        if comment.get('speaker_uid'):comment_ids.setdefault(comment['speaker_uid'],set()).add((comment['aid'],comment['rpid']))
    for video in videos:
        if any(s.get('family') in {'viewer_pick','author_pick'} for s in video['source_entries']):
            selected_publications.setdefault(video['publisher_uid'],[]).append({'aid':video['aid'],'bvid':video['bvid'],'title':video['title'],'source_entries':video['source_entries']})
    for uid,account in accounts.items():
        account['observed_comment_count']=len(comment_ids.get(uid,set()))
        if account['identity_state']=='unknown':account['scope']='peripheral' if account['observed_comment_count']>=2 else 'all'
        account['selected_publications']=selected_publications.get(uid,[])
        account['selected_work_publisher']=bool(account['selected_publications'])
        if account['selected_work_publisher']:
            account['appearance_scope']=account['scope']
            account['scope']='core'
    return {'schema_version':1,'meta':{'available':True,'scope':'selected_videos_only','sort_policy':audit['sort_policy'],
            'videos':len(videos),'observed_comments':audit['comments'],'pinned_comments':audit['pinned_comments'],
            'candidate_events':len(events),'confirmed_events':len(preview),'excluded_self_events':self_count,
            'unknown_accounts':audit['unknown_accounts'],'evidence_accounts':audit['verified_creator_accounts'],
            'selected_publisher_accounts':len(selected_publications),
            'unknown_core_publisher_accounts':sum(a['identity_state']=='unknown' and a['scope']=='core' for a in accounts.values()),
            'unknown_related_accounts':sum(a['scope']=='related' for a in accounts.values()),
            'unknown_peripheral_accounts':sum(a['scope']=='peripheral' for a in accounts.values()),
            'unknown_all_only_accounts':sum(a['scope']=='all' for a in accounts.values()),
            'appearance_policy':'distinct_videos_retained_as_evidence_only',
            'author_scope_policy':'selected_work_publishers_core_other_unknown_at_least_2_observed_comments_peripheral',
            'ranking_origin':audit.get('ranking_origin','legacy_response_order'),
            'catalog_complete':collection.get('complete_catalog_attempted',False),
            'catalog_aliases_total':collection.get('aliases_total'),
            'catalog_aliases_processed':collection.get('aliases_processed'),
            'input_hashes':[{'file':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths],
            'graph_changed':False},'accounts':accounts,'videos':[{**{k:v[k] for k in ['aid','bvid','title','source_entries']},'publisher_uid':v.get('publisher_uid','')} for v in videos],
            'coverage':coverage,'events':preview,'observed_events':observed}


def write_bundle(review,probe,dataset,graph,output):
    value=bundle(review,probe,dataset,graph)
    output.write_text(json.dumps(value,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    return value


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['review','probe','dataset','graph','output']:p.add_argument(name,type=Path)
    a=p.parse_args();r=write_bundle(a.review,a.probe,a.dataset,json.loads(a.graph.read_bytes()),a.output)
    print(json.dumps(r['meta'],ensure_ascii=False))
