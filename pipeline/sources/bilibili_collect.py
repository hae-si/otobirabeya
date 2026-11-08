"""Single-worker collection of an immutable, finite public video catalog."""
import argparse
from contextlib import contextmanager
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
from .bilibili_pilot import Client
from .bilibili_probe import comment_rows,rows


@contextmanager
def exclusive(path):
    with path.open('a+b') as stream:
        stream.write(b'0');stream.flush();stream.seek(0)
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:yield
        finally:
            stream.seek(0)
            if os.name=='nt':msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(stream,fcntl.LOCK_UN)


def run(manifest,output,budget=None,interval=3,cache_from=None):
    seeds=json.loads(manifest.read_bytes());digest=hashlib.sha256(manifest.read_bytes()).hexdigest()
    if not 1<=len(seeds)<=6000:raise ValueError('Expected finite catalog of 1..6000 aliases')
    budget=budget or min(20000,len(seeds)*3+50)
    output.mkdir(parents=True,exist_ok=True)
    with exclusive(output/'collector.lock'):
        frozen=output/'manifest.sha256'
        if frozen.exists() and frozen.read_text()!=digest:raise ValueError('Manifest changed; cannot resume')
        frozen.write_text(digest)
        if cache_from and not (output/'requests.jsonl').exists():
            original=[json.loads(line) for line in (cache_from/'requests.jsonl').read_text(encoding='utf-8').splitlines()]
            imported=[r for r in original if r['endpoint'] in {'/x/web-interface/view','/x/v2/reply'}]
            (output/'requests.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in imported),encoding='utf-8')
        client=Client(output,budget,interval);requests_at_start=len(client.records);videos={};comments=[];coverage=[];metadata={};comment_attempts=set()
        if client.stopped and (output/'endpoint_probe.json').exists():
            prior=json.loads((output/'endpoint_probe.json').read_bytes())
            prior.update(access_stopped=True,complete_catalog_attempted=False,reason='access_stop',requests=len(client.records),probes=client.records)
            (output/'endpoint_probe.json').write_text(json.dumps(prior,ensure_ascii=False,indent=2),encoding='utf-8')
            (output/'progress.json').write_text(json.dumps({k:v for k,v in prior.items() if k!='probes'},indent=2),encoding='utf-8')
            return prior
        terminals={Client.key(r['endpoint'],r['params']):r for r in client.records if r['state']=='unavailable' and r['http_status']==200 and r.get('api_code') is not None}
        for record in client.cache.values():
            if record['endpoint']!='/x/web-interface/view':continue
            body=Path(record['raw_file']).read_bytes()
            if hashlib.sha256(body).hexdigest()!=record['sha256']:raise ValueError('Cache hash mismatch')
            value=json.loads(body)['data']
            if value.get('aid') and value.get('bvid'):
                metadata['aid:'+str(value['aid'])]=(value,record);metadata['bvid:'+value['bvid']]=(value,record)
        def fetch(endpoint,params):
            key=Client.key(endpoint,params)
            if key in terminals:return None,terminals[key]
            for attempt in range(3):
                value,record=client.request(endpoint,params)
                if not record or record['state'] in {'ok','access_stop'} or not (record['http_status']==0 or 500<=record['http_status']<600):break
            if record and record['state']=='unavailable' and record['http_status']==200 and record.get('api_code') is not None:terminals[key]=record
            return value,record
        def checkpoint(reason):
            report={'phase':'bounded_catalog_collection','probes':client.records,'access_stopped':client.stopped,
                    'manifest_sha256':digest,'requests':len(client.records),'request_budget':budget,'unique_videos':len(videos),'comments':len(comments),
                    'aliases_total':len(seeds),'aliases_processed':len(coverage),'complete_catalog_attempted':len(coverage)==len(seeds) and not client.stopped and all(r.get('comment_state')!='not_attempted' for r in coverage if r['state']=='ok'),
                    'reason':reason,'updated_at':datetime.now(timezone.utc).isoformat(),'sort_policy':'like_sorted_available_top5',
                    'page_crosscheck':'not_required_user_policy','creator_posts':'disabled_after_412','graph_admitted':False}
            for name,value in [('endpoint_probe.json',report),('video_observations.json',list(videos.values())),('comment_observations.json',comments),('seed_manifest.json',seeds)]:
                temp=output/(name+'.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(temp,output/name)
            rows(output/'seed_coverage.csv',coverage,['identity','state','aid','bvid','comment_state','api_code'])
            rows(output/'request_coverage.csv',client.records,['endpoint','observed_at','http_status','api_code','state','sha256','raw_file'])
            (output/'progress.json').write_text(json.dumps({k:v for k,v in report.items() if k!='probes'},indent=2),encoding='utf-8')
            return report
        reason='running'
        try:
            for seed in seeds:
                if client.stopped:reason='access_stop';break
                if len(client.records)-requests_at_start>=3 and all(r['http_status']==0 for r in client.records[-3:]):
                    reason='consecutive_transport_failures';break
                params={'bvid':seed['bvid']} if seed.get('bvid') else {'aid':str(seed['aid'])}
                identity=next(iter(params))+':'+next(iter(params.values()))
                video,record=metadata[identity] if identity in metadata else fetch('/x/web-interface/view',params)
                if record is None and video is None:reason='budget_exhausted' if len(client.records)>=budget else 'access_stop' if client.stopped else 'unavailable';break
                row={'identity':identity,'state':'unavailable','api_code':record.get('api_code') if record else None}
                if video and video.get('aid') and video.get('bvid') and (video.get('owner') or {}).get('mid'):
                    aid=str(video['aid']);row.update(state='ok',aid=aid,bvid=video['bvid'])
                    metadata['aid:'+aid]=(video,record);metadata['bvid:'+video['bvid']]=(video,record)
                    if aid not in videos:
                        videos[aid]={'aid':aid,'bvid':video['bvid'],'publisher_uid':str(video['owner']['mid']),
                                     'title':video.get('title'),'desc':video.get('desc'),'desc_v2':video.get('desc_v2'),
                                     'pubdate':video.get('pubdate'),'source_entries':[],
                                     'observed_at':record['observed_at'],'response_sha256':record['sha256']}
                    for entry in seed['source_entries']:
                        if entry not in videos[aid]['source_entries']:videos[aid]['source_entries'].append(entry)
                    if aid not in comment_attempts:
                        data,cr=fetch('/x/v2/reply',{'type':1,'oid':aid,'pn':1,'ps':20,'sort':1})
                        row['comment_state']=cr['state'] if cr else 'not_attempted'
                        if data:
                            comments.extend({**c,'aid':aid,'observed_at':cr['observed_at'],'response_sha256':cr['sha256']} for c in comment_rows(data))
                        comment_attempts.add(aid)
                    else:row['comment_state']='canonical_video_already_attempted'
                elif record and record['state']=='access_stop':row['state']='access_stop'
                coverage.append(row)
                if len(coverage)%20==0:checkpoint('running')
            else:reason='catalog_attempted'
        finally:result=checkpoint(reason)
        return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('manifest',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--cache-from',type=Path);p.add_argument('--budget',type=int);p.add_argument('--interval',type=float,default=3)
    a=p.parse_args();r=run(a.manifest,a.output,a.budget,a.interval,a.cache_from)
    print(json.dumps({k:v for k,v in r.items() if k!='probes'}))
