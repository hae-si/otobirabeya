"""Source-ID semantic audit samples from the immutable normalized snapshot."""
import argparse
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path


def audit(data):
    rows=data['work_tags'];by_category=defaultdict(list)
    for r in rows:by_category[r['category']].append(r)
    samples={}
    for category in ['2','3','6']:
        selected=sorted(by_category[category],key=lambda r:(int(r['tag_id']),int(r['work_id'])))
        picked=[];seen=set()
        for r in selected:
            if r['tag_id'] in seen:continue
            seen.add(r['tag_id'])
            picked.append({'tag':data['tags'][r['tag_id']], 'association':r,'work':data['works'][r['work_id']],
                           'participation':[p for p in data['participation'] if p['work_id']==r['work_id']]})
            if len(picked)==3:break
        samples[category]=picked
    return {'category_samples':samples,
      'sample_flags_by_category':{c:dict(Counter(s.get('used_as_source','missing') for r in rs for s in r['source_records'])) for c,rs in by_category.items()},
      'cross_category_alias_samples':data['tag_audit']['cross_category_aliases'][:8],
      'parent_samples':data['tag_relations'][:5],
      'duplicate_instance_samples':[r for r in rows if len(r['source_records'])>1][:5],
      'migration_samples':[w for w in data['works'].values() if w.get('migrated_from')][:5],
      'excluded_source_creator_samples':[r for r in data['audit']['excluded_credits'] if r['reason']=='source_reference'][:5],
      'excluded_thanks_samples':[r for r in data['audit']['excluded_credits'] if r['reason']=='thanks_only'][:5],
      'deprecated_tag_samples':[t for t in data['tags'].values() if t.get('deprecated')=='t'][:5],
      'interpretation':{'2':'song identities; sample flag retained as content, never production credit',
                        '3':'source identities from explicit category, not personal affiliation',
                        '6':'media identities retained, excluded from similarity; category is not a reviewed SOURCE synonym'},
      'limitations':['Samples are reproducible source checks, not certification of every tag or work',
                     'Cross-platform publications attach to canonical work; repeated URLs never auto-merge works']}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('dataset',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();raw=a.dataset.read_bytes();report=audit(json.loads(raw));report['input_sha256']=hashlib.sha256(raw).hexdigest();report['version']='content-source-audit-v1'
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({c:[{'tag_id':x['tag']['id'],'name':x['tag']['name'],'work_id':x['work']['id']} for x in rs] for c,rs in report['category_samples'].items()},ensure_ascii=False))


if __name__=='__main__':main()
