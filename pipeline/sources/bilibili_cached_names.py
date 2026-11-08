"""Collect public UID names from existing raw responses; prepare exact-name merges."""
import hashlib
import json
from pathlib import Path
import subprocess
from pipeline.config import interaction_inputs

def main():
    source=interaction_inputs()['collection'];out=Path('data/normalized/bilibili/account-names-20261031');out.mkdir(exist_ok=False)
    report=json.loads((source/'endpoint_probe.json').read_bytes());names={}
    for r in report['probes']:
        raw=Path(r['raw_file']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=r['sha256']:raise ValueError('Raw hash mismatch')
        if r['state']!='ok':continue
        data=json.loads(raw)['data'];actors=[]
        if r['endpoint'].endswith('/view'):actors.append(data.get('owner') or {})
        if r['endpoint'].endswith('/reply'):
            rows=list(data.get('replies') or [])+list(data.get('hots') or [])
            pin=(data.get('upper') or {}).get('top') or (data.get('top') or {}).get('upper')
            if pin:rows.append(pin)
            actors.extend(c.get('member') or {} for c in rows if isinstance(c,dict))
        for a in actors:
            uid=str(a.get('mid',''));name=a.get('uname') or a.get('name')
            if uid.isdigit() and int(uid)>0 and isinstance(name,str) and name:
                if uid not in names or names[uid]['observed_at']<r['observed_at']:
                    names[uid]={'name':name,'observed_at':r['observed_at'],'response_sha256':r['sha256']}
    graph=json.loads(Path('dist/otobirabeya-authors/graph.json').read_bytes());renamed=0;missing=[]
    for n in graph['nodes']:
        if n['label'].startswith('UID '):
            found={names[u]['name'] for u in n.get('bilibili_uids',[]) if u in names}
            if len(found)==1:n['label']=found.pop();renamed+=1
            else:missing.append(n['id'])
    (out/'uid_names.json').write_text(json.dumps(names,ensure_ascii=False),encoding='utf-8')
    (out/'named_graph_input.json').write_text(json.dumps(graph,ensure_ascii=False),encoding='utf-8')
    code="const fs=require('fs'),{mergeExactNames}=require('./web/exact-name-identity.cjs');const g=JSON.parse(fs.readFileSync(process.argv[1]));fs.writeFileSync(process.argv[2],JSON.stringify(mergeExactNames(g.nodes).meta));"
    subprocess.run(['node','-e',code,str(out/'named_graph_input.json'),str(out/'exact_name_merges.json')],check=True)
    (out/'result.json').write_text(json.dumps({'cached_uid_names':len(names),'renamed_nodes':renamed,'missing_nodes':missing,'network_requests':0,'publication':'pending projection/content recomputation; candidates only'},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'renamed_nodes':renamed,'missing':len(missing),'output':str(out)}))

if __name__=='__main__':main()
