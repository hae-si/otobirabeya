"""Resumable, bounded public metadata/comment pilot; restricted creator-post API disabled."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time
from urllib.parse import urlencode
from .bilibili_probe import STOP_HTTP, STOP_CODES, comment_rows, rows


class Client:
    def __init__(self, output, budget=200, interval=3):
        if not 1 <= budget <= 20000: raise ValueError('budget must be 1..20000')
        self.output=output; self.budget=budget; self.interval=max(2,interval)
        output.mkdir(parents=True,exist_ok=True); (output/'raw').mkdir(exist_ok=True)
        self.path=output/'requests.jsonl'
        self.records=[json.loads(line) for line in self.path.read_text(encoding='utf-8').splitlines()] if self.path.exists() else []
        self.stopped=any(r['state']=='access_stop' for r in self.records)
        self.cache={self.key(r['endpoint'],r['params']):r for r in self.records if r['state']=='ok'}
        self.last_request=0

    @staticmethod
    def key(endpoint,params): return json.dumps([endpoint,params],sort_keys=True)

    def request(self,endpoint,params):
        if endpoint not in {'/x/web-interface/view','/x/v2/reply'}:
            raise ValueError('Only metadata and traditional comments enabled')
        key=self.key(endpoint,params)
        if key in self.cache:
            record=self.cache[key];body=Path(record['raw_file']).read_bytes()
            if hashlib.sha256(body).hexdigest()!=record['sha256']: raise ValueError('Cache hash mismatch')
            return json.loads(body)['data'],record
        if self.stopped or len(self.records)>=self.budget: return None,None
        time.sleep(max(0,self.interval-(time.monotonic()-self.last_request)))
        target=(self.output/'raw'/f'{len(self.records)+1:03d}.body').resolve()
        if target.exists(): raise ValueError('Unjournaled raw response exists; preserve for review')
        at=datetime.now(timezone.utc).isoformat()
        result=subprocess.run(['curl.exe','-q','-sS','--max-time','25','--max-redirs','0','-o',str(target),'-w','%{http_code}',
                               'https://api.bilibili.com'+endpoint+'?'+urlencode(params)],capture_output=True,text=True)
        self.last_request=time.monotonic()
        body=target.read_bytes() if target.exists() else b''
        if not target.exists(): target.write_bytes(body)
        try: payload=json.loads(body)
        except (ValueError,UnicodeDecodeError): payload={}
        if not isinstance(payload,dict): payload={}
        code=payload.get('code');status=int(result.stdout.strip()) if result.stdout.strip().isdigit() else 0
        ok=result.returncode==0 and status==200 and code==0 and isinstance(payload.get('data'),dict)
        self.stopped=status in STOP_HTTP or code in STOP_CODES or (not ok and 'captcha' in body[:2000].decode('utf-8',errors='ignore').lower())
        record={'endpoint':endpoint,'params':params,'observed_at':at,'http_status':status,'api_code':code,
                'sha256':hashlib.sha256(body).hexdigest(),'raw_file':str(target),
                'state':'access_stop' if self.stopped else 'ok' if ok else 'unavailable',
                'transport_exit_code':result.returncode,
                'page_crosscheck':'not_required_user_policy'}
        with self.path.open('a',encoding='utf-8') as f: f.write(json.dumps(record,ensure_ascii=False)+'\n')
        self.records.append(record)
        if ok: self.cache[key]=record
        return (payload['data'] if ok else None),record


def run(manifest,output,budget=200,interval=3):
    if budget>200:raise ValueError('Pilot budget must not exceed 200')
    seeds=json.loads(manifest.read_bytes())
    if len(seeds)>20: raise ValueError('Pilot manifest limited to 20 aliases / 10 unique videos')
    digest=hashlib.sha256(manifest.read_bytes()).hexdigest()
    output.mkdir(parents=True,exist_ok=True)
    frozen=output/'manifest.sha256'
    if frozen.exists() and frozen.read_text()!=digest: raise ValueError('Manifest changed; cannot resume')
    frozen.write_text(digest)
    client=Client(output,budget,interval);videos={};comments=[]
    for seed in seeds:
        video,record=client.request('/x/web-interface/view',{'bvid':seed['bvid']} if seed.get('bvid') else {'aid':str(seed['aid'])})
        if not video: continue
        if not video.get('aid') or not video.get('bvid') or not (video.get('owner') or {}).get('mid'): continue
        aid=str(video['aid'])
        if aid in videos:
            for entry in seed['source_entries']:
                if entry not in videos[aid]['source_entries']: videos[aid]['source_entries'].append(entry)
            continue
        if len(videos)>=10: break
        videos[aid]={'aid':aid,'bvid':video['bvid'],'publisher_uid':str(video['owner']['mid']),
                     'title':video.get('title'),'desc':video.get('desc'),'desc_v2':video.get('desc_v2'),
                     'pubdate':video.get('pubdate'),'source_entries':list(seed['source_entries']),
                     'observed_at':record['observed_at'],'response_sha256':record['sha256']}
        data,record=client.request('/x/v2/reply',{'type':1,'oid':aid,'pn':1,'ps':20,'sort':1})
        if data:
            comments.extend({**c,'aid':aid,'observed_at':record['observed_at'],'response_sha256':record['sha256']} for c in comment_rows(data))
    report={'phase':'T15_limited_pilot','probes':client.records,'access_stopped':client.stopped,
            'manifest_sha256':digest,'requests':len(client.records),'unique_videos':len(videos),
            'comments':len(comments),'sort_policy':'like_sorted_available_top5','page_crosscheck':'not_required_user_policy',
            'creator_posts':'disabled_after_412','graph_admitted':False}
    for name,value in [('endpoint_probe.json',report),('video_observations.json',list(videos.values())),('comment_observations.json',comments),('seed_manifest.json',seeds)]:
        (output/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (output/'video_observations.jsonl').write_text(''.join(json.dumps(v,ensure_ascii=False)+'\n' for v in videos.values()),encoding='utf-8')
    rows(output/'seed_manifest.csv',[{**s,'source_entries':json.dumps(s['source_entries'],ensure_ascii=False)} for s in seeds],
         ['aid','bvid','video_role','reason','source_entries'])
    rows(output/'request_coverage.csv',client.records,['endpoint','observed_at','http_status','api_code','state','sha256','raw_file'])
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('manifest',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();r=run(a.manifest,a.output)
    print(json.dumps({k:v for k,v in r.items() if k!='probes'}))
