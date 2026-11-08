"""Deterministic, bounded seed selection from observed coverage, never names."""
import argparse
import hashlib
import json
from pathlib import Path


def select(social, graph, excluded=(), count=4):
    if not 1<=count<=4:raise ValueError('Select between one and four bounded seeds')
    sampled={r['user_id'] for r in social['coverage']}
    degree={a['id']:0 for a in social['accounts']}
    for edge in social['edges']:
        for key in ['followerId','followeeId']:degree[edge['fact'][key]]+=1
    candidates=[]
    for node in graph['nodes']:
        if node.get('core') is not True or any(a['id'] in sampled for a in node.get('accounts',[])):continue
        for account in node.get('accounts',[]):
            uid=account['id']
            if uid in sampled or uid in excluded or account.get('host') is not None or account.get('isBot') is True:continue
            candidates.append({'account':account,'node':node,'degree':degree[uid]})
    chosen=[]
    for mapped,high in [(True,True),(False,True),(True,False),(False,False),(None,True),(None,False)]:
        pool=[r for r in candidates if (mapped is None or bool(r['node'].get('otodb_id'))==mapped) and r not in chosen and r['node']['id'] not in {x['node']['id'] for x in chosen}]
        if not pool:continue
        groups={r['node'].get('community') for r in chosen}
        pool.sort(key=lambda r:(r['node'].get('community') in groups,-r['degree'] if high else r['degree'],r['account']['id']))
        row=pool[0];chosen.append(row)
        row['stratum']=('mapped' if row['node'].get('otodb_id') else 'independent')+('_higher_degree' if high else '_lower_degree')
        if len(chosen)>=count:break
    return [{'id':'user-provided:bounded:'+r['account']['id'],'tag_id':'user-provided:bounded:'+r['account']['id'],
             'otomadsite_id':r['account']['id'],'content_id':'https://otomad.site/@'+r['account']['username'],'dead':'f',
             'mapping_basis':'known_public_id_no_creator_assertion','selection':{'core':True,'node_id':r['node']['id'],'stratum':r['stratum'],'observed_degree':r['degree'],'community':r['node'].get('community')}} for r in chosen]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('social',type=Path);parser.add_argument('graph',type=Path);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--require-otodb',action='store_true',help='Restrict this batch to core nodes with otoDB creator mappings')
    parser.add_argument('--raw-root',type=Path,default=Path('data/raw/otomadsite'))
    args=parser.parse_args()
    if args.output.exists():raise FileExistsError('Use a fresh seed manifest')
    excluded=set()
    for index in args.raw_root.glob('*/requests.jsonl'):
        for line in index.read_text(encoding='utf-8').splitlines():
            r=json.loads(line)
            if r['endpoint']=='users/show' and r['status']==404 and r['request'].get('userId'):excluded.add(r['request']['userId'])
    load=lambda p:json.loads(p.read_text(encoding='utf-8'))
    social,graph=load(args.social),load(args.graph)
    inputs=[{'file':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in [args.social,args.graph]]
    known_core_node_ids=sorted(n['id'] for n in graph['nodes'] if n.get('core') is True and n.get('accounts'))
    if args.require_otodb:graph={**graph,'nodes':[n for n in graph['nodes'] if n.get('otodb_id')]}
    result={'known_core_node_ids':known_core_node_ids,'policy':{'core_only':True,'require_otodb':args.require_otodb},'snapshot_sha256':next((v.get('snapshot_sha256') for v in social.get('mappings',[]) if v.get('snapshot_sha256')),None),
            'selection_inputs':inputs,'excluded_failed_ids':sorted(excluded),'direct_otomadsite_connections':select(social,graph,excluded)}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'seeds':len(result['direct_otomadsite_connections']),'excluded_failed_ids':len(excluded)}))


if __name__=='__main__':main()
