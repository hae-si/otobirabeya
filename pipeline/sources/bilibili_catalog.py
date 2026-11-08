"""Freeze explicitly selected public pick catalogs; no voter data or guessed video IDs."""
import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re


def unwrap(value):
    if isinstance(value,list) and len(value)==2 and isinstance(value[0],int):
        tag,data=value
        if tag==0:return {k:unwrap(v) for k,v in data.items()} if isinstance(data,dict) else data
        if tag==1:return [unwrap(v) for v in data]
        return data
    return value


class AuthorCatalog(HTMLParser):
    def __init__(self):super().__init__();self.videos=[];self.components=0
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='astro-island' and 'VideoResults.' in attrs.get('component-url',''):
            self.components+=1
            values=unwrap(json.loads(attrs['props'])['videos'])
            self.videos.extend({k:r.get(k) for k in ['url','title','author_uid','author_name']} for r in values)


def freeze(viewer_sources,author_path,output):
    seeds={};rejected=[];inputs=[];counts={}
    def add(identity,source,title):
        key=next(iter(identity))+':'+str(next(iter(identity.values())))
        row=seeds.setdefault(key,{**identity,'video_role':'original','reason':'complete_selected_pick_catalog','source_entries':[]})
        row['source_entries'].append({**source,'listed_title':title})
    for edition,path in viewer_sources:
        data=json.loads(path.read_bytes());entries=[r for g in data['list'] for r in g['data']]
        counts['viewer:'+edition]=len(entries)
        for index,item in enumerate(entries):
            value=str(item.get('aid',''))
            source={'family':'viewer_pick','edition':edition,'url':'https://otm.ink/viewpick/result/'+edition,'entry_index':index}
            match=re.fullmatch(r'(?:av)?([1-9][0-9]*)',value)
            if item.get('platform') not in {None,'bilibili'} or not match:
                rejected.append({**source,'source_id':value,'reason':'non_bilibili' if item.get('platform') not in {None,'bilibili'} else 'invalid_video_id'});continue
            add({'aid':match[1]},source,item.get('title',''))
        inputs.append({'edition':edition,'family':'viewer_pick','sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'file':str(path)})
    parser=AuthorCatalog();parser.feed(author_path.read_text(encoding='utf-8'))
    if parser.components!=1:raise ValueError('Expected exactly one VideoResults catalog')
    counts['author:2025']=len(parser.videos)
    for index,item in enumerate(parser.videos):
        source={'family':'author_pick','edition':'2025','url':'https://otopick.lachrymal.net/results/2025/','entry_index':index}
        match=re.fullmatch(r'https://www\.bilibili\.com/video/(BV[0-9A-Za-z]{10})/?',item.get('url') or '')
        if not match:rejected.append({**source,'source_id':item.get('url'),'reason':'invalid_video_url'});continue
        add({'bvid':match[1]},source,item.get('title',''))
    inputs.append({'edition':'2025','family':'author_pick','sha256':hashlib.sha256(author_path.read_bytes()).hexdigest(),'file':str(author_path)})
    output.mkdir(parents=True,exist_ok=False)
    manifest=list(seeds.values())
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    report={'counts':counts,'manifest_aliases':len(manifest),'source_entries':sum(len(s['source_entries']) for s in manifest),
            'rejected':rejected,'inputs':inputs,'manifest_sha256':hashlib.sha256((output/'manifest.json').read_bytes()).hexdigest(),
            'canonical_video_dedup':'after_successful_BV_aid_metadata_resolution','request_budget':len(manifest)*3+50,
            'scope':'viewer2025_annual_viewer2026h_author2025_complete_catalogs'}
    (output/'catalog_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source_dir',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();r=freeze([(e,a.source_dir/('viewpick-'+e+'.json')) for e in ['2025','2026h']],a.source_dir/'authorpick-2025.html',a.output)
    print(json.dumps({k:v for k,v in r.items() if k not in {'inputs','rejected'}}))
