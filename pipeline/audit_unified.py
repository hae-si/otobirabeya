"""Cross-check final graph against source projection and sampled account facts."""
import argparse
from collections import Counter,deque
import hashlib
import json
from pathlib import Path
from pipeline.author_site import assemble
from pipeline.sources.otomadsite_audit import audit


def verify(dataset_path,social_path,graph_path):
    load=lambda p:json.loads(p.read_text(encoding='utf-8'))
    social,graph=load(social_path),load(graph_path)
    rechecked=audit(sorted({Path(r['directory']) for r in social['requests']}))
    def canonical(rows):
        return sorted(json.dumps({**r,'evidence':sorted(r['evidence'],key=lambda e:json.dumps(e,sort_keys=True))},sort_keys=True) for r in rows)
    if canonical(rechecked['edges'])!=canonical(social['edges']):raise ValueError('Social facts differ from raw responses')
    nodes={n['id']:n for n in graph['nodes']};edges={e['id']:e for e in graph['edges']}
    if len(nodes)!=len(graph['nodes']) or len(edges)!=len(graph['edges']):raise ValueError('Duplicate graph IDs')
    accounts={}
    for n in nodes.values():
        for a in n.get('accounts',[]):
            if a['id'] in accounts:raise ValueError('Account mapped to more than one graph node')
            accounts[a['id']]=n['id']
    if set(accounts)!={a['id'] for a in social['accounts']}:raise ValueError('Discovered account missing from graph')
    original=assemble(dataset_path)
    projection_records={r['id']:r for edge in graph['edges'] if edge['type']=='creation' for r in edge.get('source_projection',[])}
    projection_records.update({r['id']:r for r in graph['meta'].get('identity',{}).get('excluded_creation_self_edges',[])})
    for e in original['edges']:
        if e['id'] in projection_records:
            if projection_records[e['id']]!=e:raise ValueError('Original creation evidence changed during identity merge')
            continue
        actual=edges['creation:'+e['id']]
        if (actual['source'],actual['target'],actual['weight'],actual['event_ids'])!=('otodb:'+e['source'],'otodb:'+e['target'],e['weights']['affiliation'],e['event_ids']):raise ValueError('Creation projection mismatch')
    expected_pairs=set();pairs=set();self_follows=0;account_pairs=0
    for item in social['edges']:
        f=item['fact'];pair=(f['followerId'],f['followeeId'])
        if pair in pairs:continue
        pairs.add(pair);source,target=accounts[pair[0]],accounts[pair[1]]
        if source==target:self_follows+=1;continue
        expected_pairs.add((source,target));account_pairs+=1
    actual_follows=[e for e in graph['edges'] if e['type']=='follow']
    actual_pairs={(e['source'],e['target']) for e in actual_follows}
    if actual_pairs!=expected_pairs:raise ValueError('Follow direction or identity projection mismatch')
    if sum(len(e.get('account_edge_ids') or []) for e in actual_follows)!=account_pairs:raise ValueError('Follow aggregation account evidence mismatch')
    adjacency={n:set() for n in nodes}
    for e in edges.values():
        if e['source'] not in nodes or e['target'] not in nodes:raise ValueError('Orphan edge')
        adjacency[e['source']].add(e['target']);adjacency[e['target']].add(e['source'])
    distance={n:0 for n,v in nodes.items() if v.get('language_class')=='inferred_chinese'};queue=deque(distance)
    while queue:
        source=queue.popleft()
        for target in adjacency[source]:
            if target not in distance:distance[target]=distance[source]+1;queue.append(target)
    counts=Counter(distance.get(node,'unreachable') for node in accounts.values())
    outside=sorted(a for a,node in accounts.items() if distance.get(node,999)>3)
    return {'inputs':[{'file':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in [dataset_path,social_path,graph_path]],
            'raw_responses_verified':len(rechecked['requests']),'accounts':len(accounts),'nodes':len(nodes),'edges':len(edges),
            'creation_edges_verified':len(original['edges']),'follow_edges_verified':len(actual_pairs),'follow_account_edges_verified':account_pairs,'merged_self_follows_excluded':self_follows,
            'account_distance_from_chinese':dict(counts),'outside_three_hop_account_ids':outside,
            'state':'structural and provenance audit passed; not a semantic identity certification'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('dataset',type=Path);p.add_argument('social',type=Path);p.add_argument('graph',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();result=verify(a.dataset,a.social,a.graph);a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({k:v for k,v in result.items() if k!='inputs'}))
