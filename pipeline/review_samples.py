"""Recompute selected high-impact scores from raw record lineage; no semantic auto-approval."""
import argparse
import hashlib
import json
from pathlib import Path
from pipeline.sources.otodb import read_copy
from pipeline.normalize.snapshot import resolve_chains
from pipeline.graph.author_projection import project

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,default=ROOT/'data/normalized/otodb/dataset.json')
    parser.add_argument('--dump',type=Path,default=ROOT/'data/raw/m1/otodb-20261028-040005.sql.gz')
    args=parser.parse_args();data=json.loads(args.dataset.read_text(encoding='utf-8'))
    with args.dump.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    if digest!=data['meta']['snapshot_sha256']:raise ValueError('Dataset/raw snapshot mismatch')
    raw={t:[] for t in ['otodb_tagwork','otodb_mediawork','otodb_tagworkinstance']}
    for t,r in read_copy(args.dump,raw):raw[t].append(r)
    tagmap,_=resolve_chains({r['id']:r for r in raw['otodb_tagwork']},'aliased_to_id')
    workmap,_=resolve_chains({r['id']:r for r in raw['otodb_mediawork']},'moved_to_id')
    records={r['id']:r for r in raw['otodb_tagworkinstance']}
    for credit in data['participation']:
        for rid in credit['source_record_ids']:
            row=records[rid]
            if tagmap.get(row['work_tag_id'])!=credit['work_tag_id'] or workmap.get(row['work_id'])!=credit['work_id']:
                raise ValueError('Broken credit lineage: '+rid)
    core={i for i,s in data['scopes'].items() if s['scope_status'] in {'chinese_default','chinese'}}
    edges,events,_=project(data['creators'],data['works'],data['participation'],data['relations'],core)
    selected_edges=sorted(edges,key=lambda e:-e['weights']['affiliation'])[:3]
    selected_events={e['id'] for e in sorted(events.values(),key=lambda e:-e['n'])[:3]}
    selected_events.update(k for e in selected_edges for k in e['event_ids'])
    checks=[]
    for eid in sorted(selected_events):
        event=events[eid];work_ids=set(event['work_ids']);people=set();source_ids=[]
        for credit in data['participation']:
            if credit['work_id'] not in work_ids:continue
            for rid in credit['source_record_ids']:
                row=records[rid];people.add(tagmap[row['work_tag_id']]);source_ids.append(rid)
        if people!=set(event['participants']) or len(people)!=event['n']:raise ValueError('Participant count mismatch: '+eid)
        checks.append({'event_id':eid,'participants_recomputed':len(people),'source_record_ids':source_ids,
                       'source_url':'https://otodb.net/work/'+event['root_work_id'],'status':'raw_record_count_verified',
                       'semantic_classification':'pending_separate_review'})
    edge_checks=[]
    for edge in selected_edges:
        score=sum(1/(events[k]['n']-1) for k in edge['event_ids'])
        if abs(score-edge['weights']['affiliation'])>1e-8:raise ValueError('Score mismatch')
        edge_checks.append({'edge_id':edge['id'],'score':score,'event_ids':edge['event_ids'],'status':'numeric_and_lineage_verified'})
    result={'snapshot_sha256':digest,'all_retained_credit_lineage':'verified','event_checks':checks,'edge_checks':edge_checks,
            'limit':'No page text or external participant completeness was verified; no candidates auto-approved.'}
    path=args.dataset.parent/'sample_checks.json';path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'Verified all credit lineage, {len(edge_checks)} high-weight edges and {len(checks)} event participant counts')


if __name__=='__main__':main()
