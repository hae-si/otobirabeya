"""Independently verify finite catalog coverage and raw observation lineage."""
import argparse
import csv
from collections import Counter
import hashlib
import json
from pathlib import Path


UNAVAILABLE_VIEW={-404,62002,62004,62012}
UNAVAILABLE_REPLY={12002,12003,12061}


def audit(manifest,collection,require_complete=True):
    seeds=json.loads(manifest.read_bytes());report=json.loads((collection/'endpoint_probe.json').read_bytes())
    digest=hashlib.sha256(manifest.read_bytes()).hexdigest()
    if report['manifest_sha256']!=digest:raise ValueError('Collection manifest mismatch')
    if require_complete and (not report.get('complete_catalog_attempted') or report.get('access_stopped')):
        raise ValueError('Finite catalog not complete or access stopped')
    videos=json.loads((collection/'video_observations.json').read_bytes())
    comments=json.loads((collection/'comment_observations.json').read_bytes())
    with (collection/'seed_coverage.csv').open(encoding='utf-8-sig',newline='') as f:coverage=list(csv.DictReader(f))
    identity=lambda row:'bvid:'+row['bvid'] if row.get('bvid') else 'aid:'+str(row['aid'])
    expected={identity(row):row for row in seeds}
    if len(expected)!=len(seeds):raise ValueError('Duplicate manifest identity')
    if len({row['identity'] for row in coverage})!=len(coverage):raise ValueError('Duplicate coverage identity')
    if require_complete and {r['identity'] for r in coverage}!=set(expected):raise ValueError('Missing catalog coverage')
    if len(coverage)!=report['aliases_processed']:raise ValueError('Coverage count mismatch')
    bodies={};by_hash={};by_request={}
    for record in report['probes']:
        raw=Path(record['raw_file']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=record['sha256']:raise ValueError('Raw response hash mismatch')
        if record['http_status']==200 and record.get('api_code') is not None:
            if json.loads(raw).get('code')!=record['api_code']:raise ValueError('Recorded API code differs from raw response')
        if require_complete and (record['state']=='access_stop' or record['http_status'] in {401,403,412,429} or record.get('api_code') in {-101,-403,-352,-412,-509,-799}):
            raise ValueError('Access-stop record present in full catalog evidence')
        key=(record['endpoint'],json.dumps(record['params'],sort_keys=True))
        by_request.setdefault(key,[]).append(record)
        if record['state']=='ok':
            data=json.loads(raw)
            if record['http_status']!=200 or data.get('code')!=0 or not isinstance(data.get('data'),dict):
                raise ValueError('Success record inconsistent with raw body')
            by_hash.setdefault(record['sha256'],[]).append((record,data['data']));bodies[key]=(record,data['data'])
    by_aid={v['aid']:v for v in videos};by_bvid={v['bvid']:v for v in videos}
    if len(by_aid)!=len(videos) or len(by_bvid)!=len(videos):raise ValueError('Duplicate canonical video')
    sources={aid:set() for aid in by_aid};unavailable=Counter();incomplete=[]
    for row in coverage:
        if row['identity'] not in expected:raise ValueError('Unexpected covered identity')
        seed=expected[row['identity']]
        if row['state']=='ok':
            v=by_bvid.get(seed['bvid']) if seed.get('bvid') else by_aid.get(str(seed['aid']))
            if not v or row['aid']!=v['aid'] or row['bvid']!=v['bvid']:raise ValueError('Video alias identity mismatch')
            sources[v['aid']].update(json.dumps(e,sort_keys=True,ensure_ascii=False) for e in seed['source_entries'])
        else:
            params={'bvid':seed['bvid']} if seed.get('bvid') else {'aid':str(seed['aid'])}
            rs=by_request.get(('/x/web-interface/view',json.dumps(params,sort_keys=True)),[])
            terminal=[r for r in rs if r['http_status']==200 and r['api_code'] in UNAVAILABLE_VIEW and r['state']=='unavailable']
            if not terminal:incomplete.append({'identity':row['identity'],'reason':'no_verified_terminal_video_response'})
            else:unavailable[str(terminal[-1]['api_code'])]+=1
    for v in videos:
        if {json.dumps(e,sort_keys=True,ensure_ascii=False) for e in v['source_entries']}!=sources[v['aid']]:
            raise ValueError('Cross-catalog source provenance mismatch')
        record,data=next(((r,d) for r,d in by_hash.get(v['response_sha256'],[]) if r['endpoint']=='/x/web-interface/view' and r['observed_at']==v['observed_at']),(None,None))
        if not record or record['endpoint']!='/x/web-interface/view':raise ValueError('Missing video raw lineage')
        for actual,raw_value in [(v['aid'],str(data.get('aid'))),(v['bvid'],data.get('bvid')),
                                 (v['publisher_uid'],str((data.get('owner') or {}).get('mid'))),
                                 (v.get('title'),data.get('title')),(v.get('desc'),data.get('desc')),(v.get('desc_v2'),data.get('desc_v2'))]:
            if actual!=raw_value:raise ValueError('Video field differs from source response')
    raw_comments={};reply_absence=Counter();nonmonotonic=[]
    for aid in by_aid:
        params={'type':1,'oid':aid,'pn':1,'ps':20,'sort':1};key=('/x/v2/reply',json.dumps(params,sort_keys=True))
        if key not in bodies:
            terminal=[r for r in by_request.get(key,[]) if r['http_status']==200 and r['api_code'] in UNAVAILABLE_REPLY and r['state']=='unavailable']
            if terminal:reply_absence[str(terminal[-1]['api_code'])]+=1
            else:incomplete.append({'aid':aid,'reason':'comment_response_missing_or_unclassified_failure'})
            continue
        record,data=bodies[key];pin=(data.get('upper') or {}).get('top') or (data.get('top') or {}).get('upper')
        selected=[];seen=set()
        if isinstance(pin,dict) and pin.get('rpid'):selected.append((pin,True));seen.add(str(pin['rpid']))
        count=0;likes=[]
        returned=[c for c in data.get('replies') or [] if isinstance(c,dict) and c.get('rpid') and str(c['rpid']) not in seen]
        raw_likes=[c.get('like') for c in returned]
        if all(isinstance(n,(int,float)) for n in raw_likes) and raw_likes!=sorted(raw_likes,reverse=True):nonmonotonic.append(aid)
        returned.sort(key=lambda c:c.get('like') if isinstance(c.get('like'),(int,float)) else float('-inf'),reverse=True)
        for c in returned:
            if not isinstance(c,dict) or not c.get('rpid') or str(c['rpid']) in seen:continue
            if count==5:break
            selected.append((c,False));seen.add(str(c['rpid']));count+=1;likes.append(c.get('like'))
        for c,pinned in selected:raw_comments[(aid,str(c['rpid']))]=(c,pinned,record)
    observed={(c['aid'],c['rpid']):c for c in comments}
    if len(observed)!=len(comments) or set(observed)!=set(raw_comments):raise ValueError('Comment selection or deduplication differs from raw data')
    for key,c in observed.items():
        raw,pinned,record=raw_comments[key]
        if c['speaker_uid']!=str((raw.get('member') or {}).get('mid','')) or c['message']!=(raw.get('content') or {}).get('message',''):
            raise ValueError('Comment speaker or text differs from actual speaker')
        if c['is_pinned']!=pinned or c['response_sha256']!=record['sha256'] or c.get('like')!=raw.get('like') or c['observed_at']!=record['observed_at']:
            raise ValueError('Comment pin, ranking metadata or lineage mismatch')
        content=raw.get('content') or {}
        for m in c.get('mentions',[]):
            if c['message'][m['start']:m['end']]!='@'+m['name']:raise ValueError('Mention span mismatch')
            ids={str((content.get(field) or {})[m['name']]) for field in ['at_name_to_mid','at_name_to_mid_str'] if m['name'] in (content.get(field) or {})}
            if ids!={m['target_uid']}:raise ValueError('Mention UID ambiguous or not supported by raw mapping')
    if require_complete and incomplete:raise ValueError('Unresolved catalog coverage: '+json.dumps(incomplete[:5]))
    return {'scope':'full_finite_catalog' if require_complete else 'partial_preflight_not_completion',
            'manifest_sha256':digest,'probe_sha256':hashlib.sha256((collection/'endpoint_probe.json').read_bytes()).hexdigest(),
            'aliases_expected':len(seeds),'aliases_checked':len(coverage),'videos':len(videos),'comments':len(comments),
            'raw_response_records_verified':len(report['probes']),'video_unavailable_by_api_code':dict(unavailable),
            'comment_unavailable_by_api_code':dict(reply_absence),'unresolved':incomplete,
            'observed_nonmonotonic_like_sequences':nonmonotonic,'passed':not incomplete if require_complete else True}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['manifest','collection','output']:p.add_argument(name,type=Path)
    p.add_argument('--allow-incomplete',action='store_true')
    a=p.parse_args();result=audit(a.manifest,a.collection,not a.allow_incomplete)
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
