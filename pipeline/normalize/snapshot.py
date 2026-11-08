"""Normalize immutable otoDB snapshots and emit reproducible quality/review reports."""
import argparse
from collections import Counter, defaultdict
import csv
import gzip
import hashlib
import json
from pathlib import Path
import re

from pipeline.sources.otodb import read_copy
from pipeline.config import otodb_snapshot
from pipeline.normalize.creator_scope import classify, load_overrides

ROOT = Path(__file__).resolve().parents[2]
TABLES = ['otodb_tagwork','otodb_mediawork','otodb_tagworkinstance','otodb_workrelation',
          'otodb_tagworkcreatorconnection','otodb_worksource','otodb_tagworkparenthood']


def resolve_chains(records, field):
    mapping, problems = {}, []
    for start in sorted(records, key=int):
        seen, current = [], start
        while True:
            if current not in records:
                problems.append({'id':start,'reason':'dangling_target','chain':seen+[current]});break
            if current in seen:
                problems.append({'id':start,'reason':'cycle','chain':seen+[current]});break
            seen.append(current)
            target = records[current].get(field)
            if not target:
                mapping[start] = current;break
            current = target
    return mapping, problems


def normalize_tables(tables, overrides=(), work_overrides=()):
    for name,records in tables.items():
        ids=[r['id'] for r in records if 'id' in r]
        if len(ids)!=len(set(ids)):raise ValueError('Duplicate upstream IDs in '+name)
    tags={r['id']:r for r in tables['otodb_tagwork']}
    rawworks={r['id']:r for r in tables['otodb_mediawork']}
    tagmap, tagproblems=resolve_chains(tags,'aliased_to_id')
    workmap, workproblems=resolve_chains(rawworks,'moved_to_id')
    creators={i:dict(t,aliases=[]) for i,t in tags.items() if t['category']=='4' and tagmap.get(i)==i}
    creator_map={i:target for i,target in tagmap.items() if tags[i]['category']=='4' and target in creators}
    cross_category=[i for i,t in tags.items() if t['category']=='4' and i in tagmap and i not in creator_map]
    for original,target in creator_map.items():
        if original!=target:creators[target]['aliases'].append({'id':original,'name':tags[original]['name']})
    works={i:{'id':i,'title':r['title'],'migrated_from':[]} for i,r in rawworks.items() if workmap.get(i)==i and r['status']=='1'}
    for original,target in workmap.items():
        if target in works and original!=target:works[target]['migrated_from'].append(original)
    accounts=[]
    for row in tables['otodb_tagworkcreatorconnection']:
        if row['tag_id'] in creator_map:
            accounts.append(dict(row,tag_id=creator_map[row['tag_id']],original_tag_id=row['tag_id']))
    remapped=[]; override_keys={}
    for row in overrides:
        original=row['creator_id'].removeprefix('otodb:creator:')
        if original not in creator_map:raise ValueError('Unresolved override creator '+original)
        value=dict(row,creator_id='otodb:creator:'+creator_map[original])
        key=value['creator_id'],value['method']
        if key in override_keys and override_keys[key]!=value:raise ValueError('Conflicting alias overrides: '+str(key))
        if key not in override_keys:remapped.append(value);override_keys[key]=value
    scopes=classify(creators,accounts,remapped)
    counts=Counter(); grouped={}; raw_by_creator=defaultdict(list); exclusions=[]
    for row in tables['otodb_tagworkinstance']:
        original=row['work_tag_id']
        if original not in tags or tags[original]['category']!='4':continue
        cid=creator_map.get(original);wid=workmap.get(row['work_id'])
        if cid:raw_by_creator[cid].append(row)
        if cid not in creators or creators[cid].get('deprecated')=='t':reason='unresolved_or_deprecated_creator'
        elif wid not in works:reason='unavailable_or_unresolved_work'
        else:reason=None
        bits=int(row['creator_roles'] or 0)
        if not reason:reason='unknown_role_bits' if bits<0 or bits&~63 else None
        if reason:
            counts[reason]+=1;exclusions.append({'record_id':row['id'],'creator_id':cid or original,'work_id':wid or row['work_id'],'reason':reason});continue
        if not bits:counts['missing_roles']+=1
        key=wid,cid
        value=grouped.setdefault(key,{'id':'normalized:'+wid+':'+cid,'work_id':wid,'work_tag_id':cid,
                                       'creator_roles':None,'used_as_source':'f','source_record_ids':[], 'source_work_ids':[]})
        value['source_record_ids'].append(row['id']);value['source_work_ids'].append(row['work_id'])
        if row['creator_roles'] is not None:value['creator_roles']=str(int(value['creator_roles'] or 0)|bits)
    credits=sorted(grouped.values(),key=lambda r:(int(r['work_id']),int(r['work_tag_id'])))
    for row in credits:
        row['source_record_ids']=sorted(set(row['source_record_ids']),key=int)
        row['source_work_ids']=sorted(set(row['source_work_ids']),key=int)
    relations=[]; relation_issues=[]; seen=set()
    for row in tables['otodb_workrelation']:
        a,b=workmap.get(row['A_id']),workmap.get(row['B_id'])
        if a not in works or b not in works:relation_issues.append({'id':row['id'],'reason':'unavailable_endpoint'});continue
        if a==b:relation_issues.append({'id':row['id'],'reason':'self_relation_after_migration'});continue
        key=a,b,row['relation']
        if key not in seen:relations.append(dict(row,A_id=a,B_id=b));seen.add(key)
    parents=defaultdict(set)
    for r in relations:
        if r['relation']=='2':parents[r['A_id']].add(r['B_id'])
    project_roots={v for values in parents.values() for v in values}
    by_work=defaultdict(list)
    for r in credits:by_work[r['work_id']].append(r)
    decisions={}
    for row in work_overrides:
        wid=workmap.get(row['work_id'])
        if wid not in works:raise ValueError('Unresolved work override '+row['work_id'])
        if row['classification'] not in {'co_creation_confirmed','collab_project','uncertain','not_collab'}:raise ValueError('Invalid work classification')
        if not row['source_urls'] or not row['reason'] or not row['reviewed_at']:raise ValueError('Work classification lacks evidence')
        if not all(u.startswith(('https://','http://')) for u in row['source_urls'].split('|')):raise ValueError('Work classification evidence must be public HTTP(S) URLs')
        if wid in decisions:raise ValueError('Conflicting work classifications '+wid)
        decisions[wid]=row
    classification_counts=Counter(); classification=[]
    for wid,w in works.items():
        explicit=sum(bool(int(r['creator_roles'] or 0)&31) for r in by_work[wid])
        state='collab_project_upstream' if wid in project_roots else 'collab_part_upstream' if wid in parents else 'co_creation_candidate' if explicit>=2 else 'unclassified'
        method='upstream_relation' if wid in project_roots or wid in parents else 'role_rule'
        if wid in decisions:state=decisions[wid]['classification'];method='human'
        w['classification']=state;w['classification_method']=method
        classification_counts[state]+=1
        classification.append({'work_id':wid,'classification':state,'method':method,'explicit_creators':explicit,
                               'source_url':'https://otodb.net/work/'+wid,'evidence':decisions.get(wid)})
    publications=[]
    for r in tables['otodb_worksource']:
        wid=workmap.get(r['media_id'])
        if wid in works and r['is_pending']=='f':publications.append({'id':r['id'],'work_id':wid,'url':r['url'],
            'published_date':r['published_date'],'original_work_id':r['media_id']})
    account_owners=defaultdict(set);url_works=defaultdict(set)
    for r in accounts:
        if r['content_id']:account_owners[r['site'],r['content_id']].add(r['tag_id'])
    for r in publications:url_works[r['url']].add(r['work_id'])
    from pipeline.graph.author_projection import project
    core={i for i,s in scopes.items() if s['scope_status'] in {'chinese_default','chinese'}}
    edges,events,_=project(creators,works,credits,relations,core)
    connected={i for e in edges for i in [e['source'],e['target']]}
    core_connected={i for e in edges if e['source'] in core and e['target'] in core for i in [e['source'],e['target']]}
    isolated=[]
    for cid in sorted(core-connected,key=int):
        accepted=[r for r in credits if r['work_tag_id']==cid]
        reason='no_creator_work_records' if not raw_by_creator[cid] else 'all_records_excluded' if not accepted else 'only_single_author_events'
        isolated.append({'creator_id':cid,'name':creators[cid]['name'],'reason':reason,
                         'raw_records':len(raw_by_creator[cid]),'accepted_records':len(accepted),
                         'source_url':'https://otodb.net/tag/'+creators[cid]['slug']})
    audit={'raw_counts':{k:len(v) for k,v in tables.items()},'canonical_creators':len(creators),'approved_canonical_works':len(works),
           'creator_aliases_resolved':sum(i!=t for i,t in creator_map.items()),'work_migrations_resolved':sum(i!=t for i,t in workmap.items()),
           'tag_chain_issues':tagproblems,'work_chain_issues':workproblems,'cross_category_creator_aliases':cross_category,
           'credit_flags':dict(counts),'excluded_credits':exclusions,'credit_rows_deduplicated':sum(len(r['source_record_ids'])-1 for r in credits),
           'relation_issues':relation_issues,'multi_parent_parts':[i for i,p in parents.items() if len(p)>1],
           'uncertain_events':[e['id'] for e in events.values() if e['uncertain_grouping']],
           'classification_counts':dict(classification_counts),'isolated_core_counts':dict(Counter(r['reason'] for r in isolated)),
           'isolated_core_authors':isolated,'core_count':len(core),'projection_edges':len(edges),'projection_events':len(events)}
    audit['shared_account_conflicts']=[{'site':site,'content_id':content,'creator_ids':sorted(ids,key=int)} for (site,content),ids in sorted(account_owners.items()) if len(ids)>1]
    audit['publication_url_conflicts']=[{'url':url,'work_ids':sorted(ids,key=int)} for url,ids in sorted(url_works.items()) if len(ids)>1]
    audit['chinese_only_isolated_count']=len(core-core_connected)
    audit['peripheral_only_core_count']=len((core&connected)-core_connected)
    from pipeline.normalize.content_tags import recover
    content = recover(tables, works, tagmap, workmap)
    return {'schema_version':1,**content,'creators':creators,'works':works,'participation':credits,'accounts':accounts,'publications':publications,
            'relations':relations,'scopes':scopes,'classifications':classification,'audit':audit}


def normalize_snapshot(path):
    tables={t:[] for t in TABLES}
    for table,row in read_copy(path,TABLES):tables[table].append(row)
    with (ROOT/'data/manual/work_classifications.csv').open(encoding='utf-8-sig',newline='') as stream:work_overrides=list(csv.DictReader(stream))
    data=normalize_tables(tables,load_overrides(ROOT/'data/manual/creator_scope.csv'),work_overrides)
    with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    with gzip.open(path,'rt',encoding='utf-8') as stream:date=re.search(r'-- Started on (\d{4}-\d{2}-\d{2})',stream.read(4096))
    data['meta']={'snapshot_sha256':digest,'snapshot_date':date[1] if date else '未知','normalizer_version':'snapshot-v2-content-tags',
                  'upstream_schema_commit':'61ef9df2cfdadb79966bf15c058cfa18518febda',
                  'overlays_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'data/manual/creator_scope.csv',ROOT/'data/manual/work_classifications.csv']}}
    return data


def write_dataset(data,output,previous=None):
    output.mkdir(parents=True,exist_ok=True)
    for filename,value in [('dataset.json',data),('audit.json',data['audit'])]:
        (output/filename).write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
    lines=['# otoDB 数据审计（自动生成）','', '来源快照 SHA256：'+data['meta']['snapshot_sha256'],'',
           '| 指标 | 数量 |','| --- | --- |']
    for key in ['canonical_creators','approved_canonical_works','creator_aliases_resolved','work_migrations_resolved','credit_rows_deduplicated','core_count','projection_edges','projection_events','chinese_only_isolated_count','peripheral_only_core_count']:
        lines.append(f"| {key} | {data['audit'][key]} |")
    for key in ['credit_flags','classification_counts','isolated_core_counts']:
        lines.extend(['','## '+key,'','```json',json.dumps(data['audit'][key],ensure_ascii=False,indent=2),'```'])
    lines.extend(['','异常完整记录见 audit.json；清单是待核验任务，不代表已经人工确认。原始SQL未修改。'])
    (output/'AUDIT_REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    from pipeline.graph.author_projection import project
    core={i for i,s in data['scopes'].items() if s['scope_status'] in {'chinese_default','chinese'}}
    edges,events,_=project(data['creators'],data['works'],data['participation'],data['relations'],core)
    review=[]
    for e in sorted(edges,key=lambda e:-e['weights']['affiliation'])[:30]:
        review.append({'kind':'strong_edge','id':e['id'],'priority_value':e['weights']['affiliation'],'reason':'check repeated events and identity mapping',
                       'source_urls':'|'.join('https://otodb.net/work/'+events[k]['root_work_id'] for k in e['event_ids'])})
    for e in sorted(events.values(),key=lambda e:-e['n'])[:20]:review.append({'kind':'large_event','id':e['id'],'priority_value':e['n'],'reason':'check participant completeness and project grouping','source_urls':'https://otodb.net/work/'+e['root_work_id']})
    core_works={r['work_id'] for r in data['participation'] if r['work_tag_id'] in core}
    for c in sorted((c for c in data['classifications'] if c['classification']=='co_creation_candidate' and c['work_id'] in core_works),key=lambda c:-c['explicit_creators'])[:30]:
        review.append({'kind':'classification_candidate','id':c['work_id'],'priority_value':c['explicit_creators'],'reason':'roles support participation; verify single work vs segmented collab','source_urls':c['source_url']})
    with (output/'review_queue.csv').open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=['kind','id','priority_value','reason','source_urls']);writer.writeheader();writer.writerows(review)
    if previous:
        diff={'previous_meta':previous['meta'],'current_meta':data['meta'],'collections':{}}
        diff['comparable_rules']=all(previous['meta'].get(k)==data['meta'].get(k) for k in ['normalizer_version','overlays_sha256'])
        for name in ['creators','works','scopes']:
            a,b=previous[name],data[name]
            diff['collections'][name]={'added':sorted(set(b)-set(a),key=int),'removed':sorted(set(a)-set(b),key=int),
                                       'changed':sorted((i for i in set(a)&set(b) if a[i]!=b[i]),key=int)}
        (output/'snapshot_diff.json').write_text(json.dumps(diff,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dump',type=Path,default=otodb_snapshot())
    parser.add_argument('--output',type=Path,default=ROOT/'data/normalized/otodb')
    parser.add_argument('--compare',type=Path,help='Previous normalized dataset.json, normalized with the same rules')
    args=parser.parse_args();data=normalize_snapshot(args.dump)
    previous=json.loads(args.compare.read_text(encoding='utf-8')) if args.compare else None
    write_dataset(data,args.output,previous)
    summary={k:v for k,v in data['audit'].items() if not isinstance(v,list)}
    print(json.dumps(summary,ensure_ascii=True))


if __name__=='__main__':main()
