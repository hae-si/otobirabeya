"""Prepare auditable account mapping candidates; raw evidence stays read-only."""
import csv
import hashlib
import json
from pathlib import Path

BASE=Path(__file__).resolve().parents[2]


def prepare(dataset, social, candidates, overrides=(), response_index=()):
    creators=dataset['creators']
    accounts={a['id']:a for a in social['accounts']}
    sources={}
    for root in response_index:
        for line in (root/'requests.jsonl').read_text(encoding='utf-8').splitlines():
            record=json.loads(line)
            raw=(root/record['file']).read_bytes()
            if hashlib.sha256(raw).hexdigest()!=record['sha256']:
                raise ValueError('Response evidence hash mismatch')
            if record['status']!=200:continue
            data=json.loads(raw)
            users=[data] if record['endpoint']=='users/show' else [x.get('follower') or x.get('followee') for x in data]
            for user in users:
                if user:sources.setdefault(user['id'],set()).add(record['sha256'])
    options={uid:set() for uid in accounts}
    basis={uid:[] for uid in accounts}
    for m in social['mappings']:
        if m.get('otodb_creator_id'):
            options[m['otomadsite_id']].add(m['otodb_creator_id'])
            basis[m['otomadsite_id']].append(m)
    for item in candidates:
        uid=item['user_id']
        if uid in options:
            options[uid].update(item['creator_ids']);basis[uid].append(item)
    manual={}
    for row in overrides:
        uid=row['account_id']
        if uid not in accounts or uid in manual:raise ValueError('Unknown or duplicate override account')
        if row['decision'] not in {'map','independent','unresolved'}:raise ValueError('Invalid mapping decision')
        if not row['reason'] or not row['reviewed_at'] or not row['source_urls'].startswith(('https://','http://')):raise ValueError('Missing review evidence')
        if row['decision']=='map' and row['creator_id'] not in creators:raise ValueError('Unknown creator')
        if row['decision']!='map' and row['creator_id']:raise ValueError('Non-map decision must not specify creator')
        manual[uid]=row
    result=[]
    for uid in sorted(accounts):
        ids=sorted(options[uid]);row=manual.get(uid)
        cid=(row['creator_id'] if row['decision']=='map' else None) if row else (ids[0] if len(ids)==1 and ids[0] in creators else None)
        state=row['decision'] if row else ('mapped_candidate' if cid else 'conflict' if len(ids)>1 else 'unresolved')
        result.append({'account_id':uid,'creator_id':cid,'state':state,'candidate_creator_ids':ids,'basis':basis[uid],
                       'response_sha256':sorted(sources.get(uid,set())),'manual':row})
    return result


def main():
    load=lambda p:json.loads((BASE/p).read_text(encoding='utf-8'))
    dataset=load('data/normalized/otodb/dataset.json')
    from pipeline.config import social_dataset
    social=json.loads(social_dataset().read_text(encoding='utf-8'))
    candidates=load('data/normalized/otomadsite/round2-identity-evidence.json')
    with (BASE/'data/manual/account_mappings.csv').open(encoding='utf-8-sig',newline='') as stream:overrides=list(csv.DictReader(stream))
    roots=sorted({(Path(r['directory']) if Path(r['directory']).is_absolute() else BASE/r['directory']).resolve() for r in social.get('requests',[])})
    from pipeline.normalize.profile_scope import extract, mapping_candidates
    profiles=extract(roots,[a['id'] for a in social['accounts']])
    uid_candidates=mapping_candidates(dataset,profiles)
    candidates+=uid_candidates
    (BASE/'data/normalized/otomadsite/profile-uid-comparison.json').write_text(json.dumps(uid_candidates,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    rows=prepare(dataset,social,candidates,overrides,roots)
    out=BASE/'data/normalized/otomadsite';(out/'account-mapping-review.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    safe=[{'user_id':r['account_id'],'creator_ids':[r['creator_id']],'state':'unique_explicit_platform_link','evidence':r} for r in rows if r['creator_id']]
    (out/'account-mapping-resolved.json').write_text(json.dumps(safe,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (out/'account-mapping-overrides.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    from collections import Counter
    print(json.dumps(dict(Counter(r['state'] for r in rows))))


if __name__=='__main__':main()
