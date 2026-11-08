"""Static content layer with lazy evidence shards, built before publication."""
import hashlib
import gzip
import json
from collections import defaultdict
from pathlib import Path
from pipeline.graph.content_similarity import compute


def write_bundle(dataset_path, graph, output):
    raw=Path(dataset_path).read_bytes();dataset=json.loads(raw)
    if 'work_tags' not in dataset:
        result={'meta':{'available':False,'reason':'normalized input has no work_tags'},'edges':[]}
        (output/'content-graph.json').write_text(json.dumps(result),encoding='utf-8')
        return result['meta']
    redirects=graph.get('meta',{}).get('identity',{}).get('redirects',{})
    creator_redirects={a.removeprefix('otodb:'):b.removeprefix('otodb:') for a,b in redirects.items() if a.startswith('otodb:') and b.startswith('otodb:')}
    if creator_redirects:
        grouped={}
        for r in dataset['participation']:
            cid=creator_redirects.get(r['work_tag_id'],r['work_tag_id']);key=(r['work_id'],cid)
            if key not in grouped:
                grouped[key]=dict(r,work_tag_id=cid,source_creator_ids=[r['work_tag_id']])
            else:
                row=grouped[key]
                row['creator_roles']=str(int(row.get('creator_roles') or 0)|int(r.get('creator_roles') or 0))
                row['source_creator_ids']=sorted(set(row['source_creator_ids']+[r['work_tag_id']]))
                for field in ['source_record_ids','source_work_ids']:
                    row[field]=sorted(set(row.get(field,[])+r.get(field,[])))
        dataset['participation']=list(grouped.values())
    result=compute(dataset,[n['otodb_id'] for n in graph['nodes'] if n.get('otodb_id')])
    result['meta'].pop('elapsed_seconds',None)
    result['meta']['available']=True
    result['meta']['input_sha256']=hashlib.sha256(raw).hexdigest()
    result['meta']['identity_redirects_sha256']=hashlib.sha256(json.dumps(redirects,sort_keys=True).encode()).hexdigest()
    credits={(r['work_id'],r['work_tag_id']):r for r in dataset['participation']}
    work_tags={(r['work_id'],r['tag_id']):r for r in dataset['work_tags']}
    participants=defaultdict(set);counts=defaultdict(lambda:defaultdict(int))
    for wid,aid in credits:participants[wid].add(aid)
    for wid,tid in work_tags:counts[wid][dataset['tags'][tid]['category']]+=1
    shards=defaultdict(lambda:{'edges':{},'work_evidence':{}});summaries=[]
    for edge in result['edges']:
        bucket=int(hashlib.sha256(edge['id'].encode()).hexdigest()[:8],16)%64
        filename=f'content-evidence-{bucket:02d}.json.gz'
        work_evidence={}
        for tag in edge['tags']:
            for side,aid in [('source',edge['source'].removeprefix('otodb:')),('target',edge['target'].removeprefix('otodb:'))]:
                for wid in tag[side+'_works']:
                    key=wid+':'+aid+':'+tag['tag_id']
                    work_evidence[key]={'work_id':wid,'author_id':aid,'tag_id':tag['tag_id'],
                        'title':dataset['works'][wid]['title'],'participant_count':len(participants[wid]),
                        'category_tag_count':counts[wid][edge['category']],
                        'participation':credits[wid,aid], 'tag_instances':work_tags[wid,tag['tag_id']]['source_records']}
        shards[bucket]['work_evidence'].update(work_evidence)
        shards[bucket]['edges'][edge['id']]={**edge,'work_evidence_keys':list(work_evidence)}
        summaries.append({k:v for k,v in edge.items() if k!='tags'}|{'weight':edge['similarity'],'evidence_file':filename})
    result['edges']=summaries
    result['meta']['edge_count']=len(summaries)
    for bucket,evidence in shards.items():
        payload=json.dumps(evidence,ensure_ascii=False,separators=(',',':')).encode('utf-8')
        (output/f'content-evidence-{bucket:02d}.json.gz').write_bytes(gzip.compress(payload,mtime=0))
    (output/'content-graph.json').write_text(json.dumps(result,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    return result['meta']
