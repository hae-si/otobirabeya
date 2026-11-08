"""Bridge to the shared JS identity policy; never maintain a second name matcher."""
import json
from pathlib import Path
import subprocess


def resolve_interaction_identities(graph,dataset,creator_ids):
    value={'nodes':[{k:n.get(k) for k in ['id','label','otodb_id']} for n in graph['nodes']],
           'redirects':graph.get('meta',{}).get('identity',{}).get('redirects',{}),
           'accounts':dataset.get('accounts',[]),
           'creators':[{'id':cid,'name':dataset['creators'][cid]['name']} for cid in sorted(creator_ids)]}
    result=subprocess.run(['node',str(Path(__file__).resolve().parents[2]/'web/interaction-identity.cjs')],
                          input=json.dumps(value,ensure_ascii=False),capture_output=True,text=True,encoding='utf-8',check=True)
    return json.loads(result.stdout)
