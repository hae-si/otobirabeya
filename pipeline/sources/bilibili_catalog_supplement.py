"""Freeze the selected full catalog plus already-reviewed otoDB sample provenance."""
import argparse
import hashlib
import json
from pathlib import Path


def freeze(base,prior,output):
    originals=json.loads(base.read_bytes());earlier=json.loads(prior.read_bytes())
    def key(row):return 'bvid:'+row['bvid'] if row.get('bvid') else 'aid:'+str(row['aid'])
    seeds={key(row):row for row in originals};entries=0
    for row in earlier:
        sources=[s for s in row['source_entries'] if s['family']=='otodb']
        if not sources:continue
        current=seeds.setdefault(key(row),{k:v for k,v in row.items() if k!='source_entries'}|{'source_entries':[]})
        for source in sources:
            if source not in current['source_entries']:current['source_entries'].append(source);entries+=1
    output.mkdir(parents=True,exist_ok=False)
    manifest=output/'manifest.json';manifest.write_text(json.dumps(list(seeds.values()),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    audit={'base_sha256':hashlib.sha256(base.read_bytes()).hexdigest(),'prior_sha256':hashlib.sha256(prior.read_bytes()).hexdigest(),
           'manifest_sha256':hashlib.sha256(manifest.read_bytes()).hexdigest(),'base_aliases':len(originals),'final_aliases':len(seeds),
           'otodb_source_entries_retained':entries,'new_scope':'selected full catalogs plus the two existing otoDB structural samples; no new importance ranking'}
    (output/'catalog_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return audit


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['base','prior','output']:p.add_argument(name,type=Path)
    a=p.parse_args();print(json.dumps(freeze(a.base,a.prior,a.output)))
