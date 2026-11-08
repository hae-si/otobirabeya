"""Independently reconstruct reviewed event directions from immutable API bodies."""
import argparse
import csv
import hashlib
import json
from pathlib import Path


def mentions(content):
    text=content.get('message') or ''; mappings={}; candidates=[]
    for field in ['at_name_to_mid','at_name_to_mid_str']:
        for name,uid in (content.get(field) or {}).items():
            if name and str(uid).isdigit() and int(uid)>0:
                mappings.setdefault(name,set()).add(str(uid))
    for name,uids in mappings.items():
        start=0
        while True:
            pos=text.find('@'+name,start)
            if pos<0:break
            end=pos+len(name)+1;start=pos+1
            if end==len(text) or not (text[end].isalnum() or text[end]=='_'):
                candidates.append((pos,end,name,uids))
    result=[];cursor=0
    for pos,end,name,uids in sorted(candidates,key=lambda x:(x[0],-x[1],x[2])):
        if pos<cursor:continue
        cursor=end
        if len(uids)==1:result.append((pos,end,name,next(iter(uids))))
    return result


def audit(collection,dataset_path,review_dir,identity_graph):
    read=lambda p:json.loads(p.read_bytes())
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    report=read(collection/'endpoint_probe.json');review=read(review_dir/'review.json')
    if review['probe_sha256']!=digest(collection/'endpoint_probe.json') or review['dataset_sha256']!=digest(dataset_path):
        raise ValueError('Review input hash mismatch')
    videos={};comments={};replies={};selected_aids={v['aid'] for v in read(collection/'video_observations.json')}
    for record in report['probes']:
        raw=Path(record['raw_file']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=record['sha256']:raise ValueError('Raw hash mismatch')
        if record['endpoint']=='/x/v2/reply':replies[str(record['params']['oid'])]=record
        if record['state']!='ok':continue
        payload=json.loads(raw)
        if payload.get('code')!=0:raise ValueError('Success body mismatch')
        data=payload['data']
        if record['endpoint']=='/x/web-interface/view' and str(data['aid']) in selected_aids:videos[str(data['aid'])]=(data,record)
        if record['endpoint']=='/x/v2/reply' and str(record['params']['oid']) in selected_aids:
            aid=str(record['params']['oid']);seen=set()
            pin=(data.get('upper') or {}).get('top') or (data.get('top') or {}).get('upper')
            selected=[]
            if isinstance(pin,dict) and pin.get('rpid'):selected.append((pin,True,1,1));seen.add(str(pin['rpid']))
            candidates=[(i,c) for i,c in enumerate(data.get('replies') or [],1) if isinstance(c,dict) and c.get('rpid')]
            candidates.sort(key=lambda pair:pair[1].get('like') if isinstance(pair[1].get('like'),(int,float)) else float('-inf'),reverse=True)
            rank=0
            for index,c in candidates:
                if str(c['rpid']) in seen:continue
                if rank==5:break
                rank+=1;seen.add(str(c['rpid']));selected.append((c,False,rank,index))
            for c,pinned,rank,index in selected:comments[(aid,str(c['rpid']))]=(c,pinned,rank,index,record)
    observed=read(review_dir/'comment_observations.json')
    if set(videos)!=selected_aids:raise ValueError('Missing selected video metadata')
    if len(observed)!=len(comments) or {(c['aid'],c['rpid']) for c in observed}!=set(comments):raise ValueError('Reviewed comment selection mismatch')
    for c in observed:
        raw,pin,rank,index,record=comments[(c['aid'],c['rpid'])]
        expected_mentions=mentions(raw.get('content') or {})
        actual_mentions=[(m['start'],m['end'],m['name'],m['target_uid']) for m in c['mentions']]
        if actual_mentions!=expected_mentions:raise ValueError('Reviewed mentions differ from raw mappings and text')
        if c['ranking_origin']!=('pinned' if pin else 'local_like_sort_of_returned_top_level_subset'):raise ValueError('Reviewed ranking origin mismatch')
        if (c['speaker_uid'],c['message'],c['is_pinned'],c['rank'],c['response_rank'],c['response_sha256'],c['observed_at'])!=(str((raw.get('member') or {}).get('mid','')),(raw.get('content') or {}).get('message',''),pin,rank,index,record['sha256'],record['observed_at']):
            raise ValueError('Reviewed speaker, ranking or lineage mismatch')
    expected={}
    valid=lambda u:str(u).isdigit() and int(u)>0
    def add(aid,rpid,kind,source,target,record):
        source=str(source);target=str(target)
        if valid(source) and valid(target):expected[(aid,rpid,kind,source,target)]=record
    for aid,(v,record) in videos.items():
        for segment in v.get('desc_v2') or []:
            if isinstance(segment,dict) and segment.get('type')==2:add(aid,'','description_mention',v['owner']['mid'],segment.get('biz_id',''),record)
    for (aid,rpid),(c,pin,rank,index,record) in comments.items():
        source=str((c.get('member') or {}).get('mid',''))
        if not pin:add(aid,rpid,'video_comment',source,videos[aid][0]['owner']['mid'],record)
        for _,_,_,target in mentions(c.get('content') or {}):add(aid,rpid,'comment_mention',source,target,record)
    with (review_dir/'interaction_events.csv').open(encoding='utf-8-sig',newline='') as f:events=list(csv.DictReader(f))
    key=lambda e:(e['video_id'],e['rpid'],e['event_type'],e['source_uid'],e['target_uid'])
    if len(events)!=len(expected) or {key(e) for e in events}!=set(expected):raise ValueError('Event directions or deduplication differ from raw evidence')
    dataset=read(dataset_path);verification=read(review_dir/'creator_verification.json');accounts={};credits={}
    for a in dataset['accounts']:
        if a['site']=='3' and a['tag_id'] in dataset['creators']:accounts.setdefault(str(a['content_id']),set()).add(a['tag_id'])
    from pipeline.normalize.interaction_identity import resolve_interaction_identities
    redirects=resolve_interaction_identities(read(identity_graph),dataset,{cid for uid in verification for cid in accounts.get(uid,set())})
    for p in dataset['participation']:
        bits=int(p.get('creator_roles') or 0)
        if p['used_as_source']=='f' and bits&31 and not bits&~63:
            cid=redirects.get('otodb:'+p['work_tag_id'],'otodb:'+p['work_tag_id'])
            credits.setdefault(cid,[]).append({**p,'work_url':'https://otodb.net/work/'+p['work_id']})
    required_uids={u for k in expected for u in k[3:]}
    required_uids.update(str(v['owner']['mid']) for v,_ in videos.values() if valid(v['owner']['mid']))
    required_uids.update(str((c.get('member') or {}).get('mid','')) for c,*_ in comments.values() if valid((c.get('member') or {}).get('mid','')))
    required_uids.update(uid for c,*_ in comments.values() for _,_,_,uid in mentions(c.get('content') or {}))
    required_uids.update(str(s['biz_id']) for v,_ in videos.values() for s in v.get('desc_v2') or [] if isinstance(s,dict) and s.get('type')==2 and valid(s.get('biz_id','')))
    if set(verification)!=required_uids:raise ValueError('Verification account coverage mismatch')
    for uid,v in verification.items():
        ids=sorted(accounts.get(uid,set()));canonical=sorted({redirects.get('otodb:'+cid,'otodb:'+cid) for cid in ids})
        eligible=[p for cid in canonical for p in credits.get(cid,[])] if len(canonical)==1 else []
        if v['creator_ids']!=ids or v['canonical_creator_ids']!=canonical or v['mapping_state']!=('resolved' if len(canonical)==1 else 'unknown') or v['state']!=('otodb_creator_evidence' if eligible else 'unknown') or v['evidence']!=eligible:
            raise ValueError('Account mapping or production qualification mismatch')
    supported=[]
    for e in events:
        record=expected[key(e)];source=verification[e['source_uid']];target=verification[e['target_uid']]
        self_event=e['source_uid']==e['target_uid'] or len(source['canonical_creator_ids'])==len(target['canonical_creator_ids'])==1 and source['canonical_creator_ids']==target['canonical_creator_ids']
        both=source['state']==target['state']=='otodb_creator_evidence'
        if e['self_event']!=str(self_event) or e['identity_state']!=('otodb_supported' if both else 'unknown') or e['response_sha256']!=record['sha256'] or e['observed_at']!=record['observed_at']:
            raise ValueError('Event identity, self or lineage mismatch')
        if both and not self_event:supported.append(e)
    stats=read(review_dir/'statistics.json')
    if stats['identity_supported_events']!=len(supported) or stats['identity_supported_unique_comments']!=len({(e['video_id'],e['rpid']) for e in supported if e['rpid']}) or stats['observed_comments']!=len(comments):raise ValueError('Statistics denominator mismatch')
    with (review_dir/'comment_coverage.csv').open(encoding='utf-8-sig',newline='') as f:coverage=list(csv.DictReader(f))
    if len(coverage)!=len(videos) or {c['aid'] for c in coverage}!=set(videos):raise ValueError('Comment coverage video set mismatch')
    for c in coverage:
        record=replies.get(c['aid'],{});count=sum(aid==c['aid'] and not pin for (aid,_),(_,pin,*_) in comments.items())
        if c['coverage']!=('available_subset' if record.get('state')=='ok' else 'unavailable') or c['comment_state']!=record.get('state','not_attempted') or c['api_code']!=str(record.get('api_code') if record.get('api_code') is not None else '') or c['response_sha256']!=(record.get('sha256') or '') or int(c['observed_top_level_comments'])!=count:
            raise ValueError('Comment coverage status or lineage mismatch')
    comment_counts={uid:0 for uid in verification}
    for c,*_ in comments.values():
        uid=str((c.get('member') or {}).get('mid',''))
        if uid in comment_counts:comment_counts[uid]+=1
    counts_hash=hashlib.sha256(json.dumps(comment_counts,sort_keys=True).encode()).hexdigest()
    return {'passed':True,'network_requests':0,'events_checked':len(events),'comments_checked':len(comments),'accounts_checked':len(verification),'supported_nonself_events':len(supported),'observed_comment_counts_sha256':counts_hash,'probe_sha256':digest(collection/'endpoint_probe.json'),'dataset_sha256':digest(dataset_path),'events_sha256':digest(review_dir/'interaction_events.csv'),'identity_graph_sha256':digest(identity_graph)}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['collection','dataset','review','identity_graph','output']:p.add_argument(name,type=Path)
    a=p.parse_args();result=audit(a.collection,a.dataset,a.review,a.identity_graph)
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
