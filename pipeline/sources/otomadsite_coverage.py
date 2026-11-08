"""Account/author coverage is independent from snowball saturation."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def report(dataset,social,graph):
    states={(r['user_id'],r['endpoint']):r['state'] for r in social['coverage']}
    nodes={n.get('otodb_id'):n for n in graph['nodes'] if n.get('otodb_id')}
    creators=[];directions=Counter()
    for cid,scope in sorted(dataset['scopes'].items()):
        if scope['scope_status'] not in {'chinese_default','chinese'}:continue
        accounts=[]
        for a in nodes.get(cid,{}).get('accounts',[]):
            if a.get('host') is not None:continue
            row={'id':a['id'],'username':a['username']}
            for endpoint in ['following','followers']:
                row[endpoint]=states.get((a['id'],endpoint),'not_sampled');directions[row[endpoint]]+=1
            accounts.append(row)
        creators.append({'creator_id':cid,'name':dataset['creators'][cid]['name'],'platform_presence':'discovered' if accounts else 'unknown','accounts':accounts})
    denominator=sum(directions.values())-directions['not_public_skipped']
    ratio=directions['visible_list_exhausted']/denominator if denominator else None
    return {'core_creators':len(creators),'with_discovered_local_account':sum(bool(r['accounts']) for r in creators),
            'platform_presence_unknown':sum(not r['accounts'] for r in creators),'directions':dict(directions),
            'direction_completion_ratio':ratio,'known_accounts_95_percent_gate':ratio is not None and ratio>=.95,
            'limitations':['unknown platform presence is not absence','identity links remain candidates','unobserved directions stay in conservative completion denominator','saturation requires three separate core-only batches; not implied by this report'],
            'creators':creators}


def core_discovery(neighbors,known_core_ids,graph):
    if known_core_ids is None or graph is None:
        return {'evaluable':False,'core_known_ratio':None,'reason':'missing pre-batch core identity snapshot or post-batch classification'}
    actors={n['id'] for n in graph['nodes'] if n.get('core') is True and any(a['id'] in neighbors for a in n.get('accounts',[]))}
    known=actors&set(known_core_ids)
    return {'evaluable':bool(actors),'core_known_ratio':len(known)/len(actors) if actors else None,
            'enough_core_authors':len(actors)>=20,'minimum_core_authors':20,'observed_core_authors':len(actors),'known_core_authors':len(known),'new_core_authors':len(actors-known),
            'excluded_account_count':len(neighbors)-sum(a['id'] in neighbors for n in graph['nodes'] if n.get('core') is True for a in n.get('accounts',[]))}


def saturation(manifest,root,project_root,graph=None):
    inputs=manifest['selection_inputs'];source=inputs[0]
    path=project_root/source['file']
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=source['sha256']:raise ValueError('Seed selection input changed')
    previous=json.loads(raw)
    before={a['id'] for a in previous['accounts']}
    previously_sampled={r['user_id'] for r in previous['coverage']}
    seeds=manifest['direct_otomadsite_connections'];neighbors=set()
    for line in (root/'requests.jsonl').read_text(encoding='utf-8').splitlines():
        r=json.loads(line)
        if r['status']!=200 or r['endpoint']=='users/show':continue
        raw=(root/r['file']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=r['sha256']:raise ValueError('Response changed')
        for row in json.loads(raw):neighbors.add(row['followeeId'] if r['endpoint'].endswith('following') else row['followerId'])
    progress=json.loads((root/'progress.json').read_text(encoding='utf-8'))
    completed={m['otomadsite_id'] for m in progress['mappings']}
    qualified=len({r.get('selection',{}).get('node_id') for r in seeds})>=4 and len({r['otomadsite_id'] for r in seeds})>=4 and not ({r['otomadsite_id'] for r in seeds}&previously_sampled) and all(r.get('selection',{}).get('core') is True and r['otomadsite_id'] in completed for r in seeds) and all(r['state'] in {'visible_list_exhausted','not_public_skipped'} for r in progress['coverage'])
    ratio=len(neighbors&before)/len(neighbors) if neighbors else None
    core_result=core_discovery(neighbors,manifest.get('known_core_node_ids'),graph)
    return {**core_result,'seeds':len(seeds),'qualified_core_batch':qualified,'observed_neighbor_accounts':len(neighbors),'new_accounts':len(neighbors-before),
            'all_account_known_ratio':ratio,'passes_90_percent':qualified and core_result['evaluable'] and core_result.get('enough_core_authors',False) and core_result['core_known_ratio']>=.9}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('dataset',type=Path);p.add_argument('social',type=Path);p.add_argument('graph',type=Path);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();paths=[args.dataset,args.social,args.graph]
    data=report(*(json.loads(v.read_text(encoding='utf-8')) for v in paths))
    data['inputs']=[{'file':str(v),'sha256':hashlib.sha256(v.read_bytes()).hexdigest()} for v in paths]
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in data.items() if k not in {'creators','inputs','limitations'}}))


if __name__=='__main__':main()
