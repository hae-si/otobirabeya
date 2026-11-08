"""Build the full Chinese-centered creator-only static explorer."""
import argparse
import csv
from collections import Counter, defaultdict
from urllib.parse import urlparse
import hashlib
import os
import tempfile
import json
from pathlib import Path
import shutil
import subprocess

from pipeline.graph.author_projection import project
from pipeline.config import otodb_snapshot,interaction_inputs

ROOT = Path(__file__).resolve().parents[1]

PLATFORM_HOSTS = {
    'bilibili.com': 'bilibili', 'b23.tv': 'bilibili', 'acfun.cn': 'acfun',
    'nicovideo.jp': 'niconico', 'nico.ms': 'niconico',
    'youtube.com': 'youtube', 'youtu.be': 'youtube',
    'soundcloud.com': 'soundcloud', 'twitter.com': 'twitter', 'x.com': 'twitter',
}


def platform_of(url):
    host = (urlparse(url or '').hostname or '').lower()
    for suffix, platform in PLATFORM_HOSTS.items():
        if host == suffix or host.endswith('.' + suffix):
            return platform
    return None


def primary_platform(counts):
    if not counts:
        return 'none'
    top = max(counts.values())
    winners = sorted(platform for platform, count in counts.items() if count == top)
    return winners[0] if len(winners) == 1 else 'tie'


def evidence_index(dataset):
    work_platforms = defaultdict(set)
    for publication in dataset.get('publications', []):
        platform = platform_of(publication.get('url'))
        if platform:
            work_platforms[publication['work_id']].add(platform)
    works_by_creator = defaultdict(set)
    for row in dataset.get('participation', []):
        works_by_creator[str(row['work_tag_id'])].add(row['work_id'])
    platform_counts = {}
    for creator_id, work_ids in works_by_creator.items():
        counts = Counter()
        for work_id in work_ids:
            for platform in work_platforms.get(work_id, ()):
                counts[platform] += 1
        if counts:
            platform_counts[creator_id] = dict(sorted(counts.items()))
    account_sites = defaultdict(set)
    for account in dataset.get('accounts', []):
        if account.get('content_id'):
            account_sites[str(account['tag_id'])].add(str(account['site']))
    return {'account_sites': {cid: sorted(sites) for cid, sites in account_sites.items()},
            'platform_counts': platform_counts}



def assemble(path):
    from pipeline.normalize.snapshot import normalize_snapshot
    dataset = json.loads(path.read_text(encoding='utf-8')) if path.suffix == '.json' else normalize_snapshot(path)
    if dataset.get('schema_version') != 1:
        raise ValueError('Unsupported normalized schema version')
    creators, works, scopes = dataset['creators'], dataset['works'], dataset['scopes']
    tables = {'otodb_tagworkinstance': dataset['participation'], 'otodb_workrelation': dataset['relations']}
    anchors = {tid for tid, s in scopes.items() if s['scope_status'] in {'chinese_default', 'chinese'}}
    bilibili_creators = {a['tag_id'] for a in dataset.get('accounts',[]) if a['site'] == '3' and a['tag_id'] in creators}
    cooperation_tag_ids={tid for tid,t in dataset.get('tags',{}).items()
                         if (t.get('name') or '').strip() in {'合作','collaborative work','collaboration entry'}
                         or (t.get('slug') or '').strip() in {'collaborative_work','collaboration_entry'}}
    cooperation_works={row['work_id'] for row in dataset.get('work_tags',[]) if row['tag_id'] in cooperation_tag_ids}
    edges, events, excluded = project(creators, works, tables['otodb_tagworkinstance'], tables['otodb_workrelation'], anchors, cooperation_works)
    included = anchors | {tid for e in edges for tid in (e['source'], e['target'])}
    relevant_works = {wid for ev in events.values() for wid in ev['work_ids']} | {ev['root_work_id'] for ev in events.values()}
    evidence = evidence_index(dataset)
    nodes = []
    for tid in sorted(included, key=int):
        counts = evidence['platform_counts'].get(tid, {})
        nodes.append({'id': tid, 'label': creators[tid]['name'], 'type': 'creator', 'chinese_scope': tid in anchors,
                      'has_bilibili_account': tid in bilibili_creators, 'account_sites': evidence['account_sites'].get(tid, []),
                      'platform_counts': counts, 'primary_platform': primary_platform(counts),
                      'url': 'https://otodb.net/tag/' + creators[tid]['slug'], 'scope': scopes[tid]['label']})
    digest = dataset['meta']['snapshot_sha256']
    return {'meta': {'snapshot_sha256': digest, 'snapshot_date': dataset['meta']['snapshot_date'], 'chinese_scope_count': len(anchors),
                     'related_count': len(included - anchors), 'work_count': len(relevant_works), 'event_count': len(events),
                     'formula': 'sum(1/(all_recorded_participants-1))', 'rule_version': 'account-scope-v2',
                     'excluded': excluded, 'cooperation_work_count': len(cooperation_works), 'normalizer_version':dataset['meta']['normalizer_version'],
                     'quality_summary':{k:dataset['audit'][k] for k in ['creator_aliases_resolved','work_migrations_resolved','isolated_core_counts','chinese_only_isolated_count','peripheral_only_core_count']}}, 'nodes': nodes, 'edges': edges, 'events': events,
            'works': {wid: works[wid] for wid in sorted(relevant_works, key=int)}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    interactions=interaction_inputs()
    parser.add_argument('--dump', type=Path, default=otodb_snapshot())
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/otobirabeya-authors')
    parser.add_argument('--social-dataset', type=Path, help='Optional independent account/follows dataset')
    parser.add_argument('--dataset', type=Path, help='Build from an existing normalized dataset, without reading raw SQL')
    parser.add_argument('--interaction-review',type=Path,default=interactions['review'],help='Reviewed interaction directory; defaults to data_sources.json')
    parser.add_argument('--interaction-probe',type=Path,default=interactions['collection'],help='Matching collection directory; defaults to data_sources.json')
    parser.add_argument('--interaction-manifest',type=Path,default=interactions['manifest'],help='Frozen complete catalog; defaults to data_sources.json')
    args = parser.parse_args()
    publish_build(args)


def publish_build(args):
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".otobirabeya-build-", dir=output.parent) as directory:
        staged = argparse.Namespace(**vars(args))
        staged.output = Path(directory)
        build(staged)
        output.mkdir(parents=True, exist_ok=True)
        names=["app.js", "style.css", "THIRD_PARTY_NOTICES.md", "index.html", "graph.json"]
        if any(not (staged.output/name).is_file() for name in names):
            raise ValueError('Incomplete staged website')
        optional=[p.name for p in sorted(staged.output.glob('content-evidence-??.json.gz'))]
        optional.extend(name for name in ('chillroundf.ttf', 'chillroundf-ofl.txt') if (staged.output/name).is_file())
        if (staged.output/'content-graph.json').exists():optional.append('content-graph.json')
        if (staged.output/'interaction.json').exists():optional.append('interaction.json')
        names=optional+names
        backup=staged.output/'rollback';backup.mkdir()
        for name in names:
            if (output/name).exists():shutil.copy2(output/name,backup/name)
        changed=[]
        try:
            for name in names:
                os.replace(staged.output/name, output/name)
                changed.append(name)
        except OSError:
            try:
                for name in reversed(changed):
                    if (backup/name).exists():os.replace(backup/name,output/name)
                    else:(output/name).unlink()
            except OSError as recovery_error:
                recovery=Path(tempfile.mkdtemp(prefix='.otobirabeya-recovery-',dir=output.parent))
                shutil.copytree(backup,recovery/'originals',dirs_exist_ok=True)
                raise RuntimeError(f'Publication rollback failed; preserved originals: {recovery}') from recovery_error
            raise
        obsolete=output/'build-account-mappings.json'
        if obsolete.is_file():obsolete.unlink()


def build(args):
    review=getattr(args,'interaction_review',None);probe=getattr(args,'interaction_probe',None)
    manifest=getattr(args,'interaction_manifest',None);collection_audit=None
    if bool(review)!=bool(probe):raise ValueError('Both interaction review and probe directories required')
    if review:
        if not manifest:raise ValueError('Frozen interaction catalog manifest required')
        from pipeline.audit_interaction_collection import audit as audit_collection
        collection_audit=audit_collection(manifest,probe)
    if args.dataset:
        dataset_path=args.dataset
    else:
        from pipeline.normalize.snapshot import normalize_snapshot, write_dataset
        normalized=normalize_snapshot(args.dump)
        write_dataset(normalized,ROOT/'data/normalized/otodb')
        dataset_path=ROOT/'data/normalized/otodb/dataset.json'
    data = assemble(dataset_path)
    additional = ROOT/'config/additional_relations.json'
    normalized_data=json.loads(dataset_path.read_text(encoding='utf-8'))
    evidence=evidence_index(normalized_data)
    included={n['id'] for n in data['nodes']}
    review=getattr(args,'interaction_review',None);probe=getattr(args,'interaction_probe',None)
    if bool(review)!=bool(probe):raise ValueError('Both interaction review and probe directories required')
    if review:
        verification=json.loads((review/'creator_verification.json').read_bytes())
        for record in verification.values():
            if len(record.get('canonical_creator_ids',['otodb:'+cid for cid in record['creator_ids']]))!=1:continue
            for cid in record['creator_ids']:
                if cid in included:continue
                creator=normalized_data['creators'][cid]
                counts=evidence['platform_counts'].get(cid,{})
                data['nodes'].append({'id':cid,'label':creator['name'],'type':'creator','chinese_scope':False,'has_bilibili_account':False,
                    'account_sites':evidence['account_sites'].get(cid,[]),'platform_counts':counts,'primary_platform':primary_platform(counts),
                    'scope':normalized_data['scopes'][cid]['label'],'url':'https://otodb.net/tag/'+creator['slug'],
                    'inclusion_basis':'mapped_interaction_identity_endpoint'})
                included.add(cid)
    for row in json.loads(additional.read_text(encoding='utf-8')):
        for endpoint in (row['source'],row['target']):
            if not endpoint.startswith('otodb:'):
                continue
            cid=endpoint.removeprefix('otodb:')
            if cid in included:
                continue
            creator=normalized_data['creators'].get(cid)
            if creator is None:
                raise ValueError('Unknown additional endpoint: '+endpoint)
            counts=evidence['platform_counts'].get(cid,{})
            data['nodes'].append({'id':cid,'label':creator['name'],'type':'creator','chinese_scope':False,'has_bilibili_account':False,'account_sites':evidence['account_sites'].get(cid,[]),'platform_counts':counts,'primary_platform':primary_platform(counts),'scope':normalized_data['scopes'][cid]['label'],'url':'https://otodb.net/tag/'+creator['slug'],'inclusion_basis':'explicit_additional_endpoint'})
            included.add(cid)
    args.output.mkdir(parents=True, exist_ok=True)
    graph_file = args.output / 'graph.json'
    graph_file.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    subprocess.run(['node', str(ROOT / 'web/layout.cjs'), str(graph_file)], check=True)
    data = json.loads(graph_file.read_text(encoding='utf-8'))
    bundler = ROOT / 'web/node_modules/esbuild/bin/esbuild'
    notices = ['# Third-party notices\n\nGephi Lite is an interaction reference; its application source is not included.\n']
    packages = ROOT / 'web/node_modules'
    for folder in sorted(packages.iterdir()):
        candidates = sorted(folder.iterdir()) if folder.name.startswith('@') else [folder]
        for package in candidates:
            manifest = package / 'package.json'
            if not manifest.is_file():
                continue
            info = json.loads(manifest.read_text(encoding='utf-8'))
            notices.append(f"\n## {info.get('name')} {info.get('version')} — {info.get('license')}\n")
            for license_file in package.iterdir():
                if license_file.is_file() and license_file.name.lower().startswith(('license', 'licence', 'copying')):
                    notices.append(license_file.read_text(encoding='utf-8'))
    (args.output / 'THIRD_PARTY_NOTICES.md').write_text('\n'.join(notices), encoding='utf-8')
    from pipeline.config import social_dataset
    social = args.social_dataset or social_dataset()
    if not social.exists():raise FileNotFoundError(social)
    if social.exists():
        from pipeline.normalize.profile_scope import extract
        social_data=json.loads(social.read_text(encoding='utf-8'))
        roots=sorted({(Path(r['directory']) if Path(r['directory']).is_absolute() else ROOT/r['directory']).resolve() for r in social_data.get('requests',[])})
        profile_scope=extract(roots, [a['id'] for a in social_data['accounts']])
        (args.output/'profile-scope.json').write_text(json.dumps(profile_scope,ensure_ascii=False),encoding='utf-8')
        subprocess.run(['node', str(ROOT/'web/social-build.cjs'), str(social), str(args.output/'social-graph.json')], check=True)
    else:
        (args.output/'profile-scope.json').write_text('{}',encoding='utf-8')
        (args.output/'social-graph.json').write_text(json.dumps({'nodes':[],'edges':[]}),encoding='utf-8')
    identity = ROOT/'data/normalized/otomadsite/round2-identity-evidence.json'
    if not identity.exists():
        identity = args.output/'empty-identity.json'
        identity.write_text('[]',encoding='utf-8')
    from pipeline.normalize.account_mapping import prepare
    from pipeline.normalize.profile_scope import mapping_candidates
    overrides = args.output/'build-account-mappings.json'
    if social.exists():
        normalized_data=json.loads(dataset_path.read_text(encoding='utf-8'))
        candidates=json.loads(identity.read_text(encoding='utf-8'))+mapping_candidates(normalized_data,profile_scope)
        with (ROOT/'data/manual/account_mappings.csv').open(encoding='utf-8-sig',newline='') as stream:
            manual=list(csv.DictReader(stream))
        rows=prepare(normalized_data,social_data,candidates,manual,roots)
        overrides.write_text(json.dumps(rows,ensure_ascii=False),encoding='utf-8')
    else:
        overrides.write_text('[]',encoding='utf-8')
    subprocess.run(['node',str(ROOT/'web/unified-build.cjs'),str(args.output),str(dataset_path),str(identity)]+([str(overrides)] if overrides.exists() else []),check=True)
    final=json.loads((args.output/'unified-graph.json').read_text(encoding='utf-8'))
    ids={n['id'] for n in final['nodes']}
    if len(ids)!=len(final['nodes']) or any(e['source'] not in ids or e['target'] not in ids for e in final['edges']):
        raise ValueError('Invalid unified graph references')
    redirects=final['meta'].get('identity',{}).get('redirects',{})
    if not all(redirects.get('otodb:'+n['id'],'otodb:'+n['id']) in ids for n in data['nodes']):
        raise ValueError('Missing projected creator')
    if sum(len(e.get('source_projection',[e])) for e in final['edges'] if e['type']=='creation')+len(final['meta'].get('identity',{}).get('excluded_creation_self_edges',[]))!=len(data['edges']):
        raise ValueError('Missing projected creation edges')
    inputs=[dataset_path,ROOT/'data/manual/account_mappings.csv']
    if social.exists():inputs.append(social)
    if identity.name!='empty-identity.json':inputs.append(identity)
    final['meta']['input_hashes']=[{'file':str(p), 'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in inputs]
    final['meta']['mapping_sha256']=hashlib.sha256(overrides.read_bytes()).hexdigest()
    final['meta']['sampled_accounts']=len({r['user_id'] for r in social_data['coverage']}) if social.exists() else 0
    final['meta']['social_coverage']=dict(Counter(r['state'] for r in social_data['coverage'])) if social.exists() else {}
    final['meta']['otodb_snapshot_date']=data['meta']['snapshot_date']
    observations=sorted({ev['observed_at'] for edge in social_data.get('edges',[]) for ev in edge.get('evidence',[]) if ev.get('observed_at')})
    final['meta']['social_observation_range']=[observations[0],observations[-1]] if observations else None
    from pipeline.normalize.organizations import read_records
    organization_inputs=[ROOT/'data/manual/organizations.csv',ROOT/'data/manual/memberships.csv']
    final['organization_data']=read_records(*organization_inputs,json.loads(dataset_path.read_text(encoding='utf-8'))['creators'])
    final['meta']['input_hashes'] += [{'file':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in organization_inputs]
    graph_file.write_text(json.dumps(final,ensure_ascii=False),encoding='utf-8')
    validated=subprocess.run(['node', '-e', "const fs=require('fs'),{readAdditional}=require('./web/additional-relations.cjs');const g=JSON.parse(fs.readFileSync(process.argv[1]));process.stdout.write(JSON.stringify(readAdditional(process.argv[2],g.nodes)));",str(graph_file),str(additional)],cwd=ROOT,check=True,stdout=subprocess.PIPE)
    final['additional_edges']=json.loads(validated.stdout)
    final['meta']['input_hashes'].append({'file':str(additional),'sha256':hashlib.sha256(additional.read_bytes()).hexdigest()})
    for item in final['meta']['input_hashes']:
        path=Path(item['file'])
        if not path.is_absolute():path=ROOT/path
        try:item['file']=str(path.resolve().relative_to(ROOT))
        except ValueError:item['file']=str(path)
    from pipeline.content_bundle import write_bundle
    final['meta']['content']=write_bundle(dataset_path,final,args.output)
    graph_file.write_text(json.dumps(final,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    review=getattr(args,'interaction_review',None);probe=getattr(args,'interaction_probe',None)
    if bool(review)!=bool(probe):raise ValueError('Both interaction review and probe directories required')
    if review:
        from pipeline.interaction_bundle import write_bundle as write_interactions
        from pipeline.interaction_graph import integrate as integrate_interactions
        from pipeline.audit_interaction_events import audit as audit_events
        event_audit=audit_events(probe,dataset_path,review,graph_file)
        current=json.loads(graph_file.read_bytes())
        observations=write_interactions(review,probe,dataset_path,current,args.output/'interaction.json')
        if not observations['meta'].get('catalog_complete') or json.loads((probe/'endpoint_probe.json').read_bytes()).get('access_stopped'):
            raise ValueError('Complete bounded catalog required before fourth-layer publication; retain current website')
        integrate_interactions(current,observations)
        apply_cached_display_names(current,observations)
        observations['meta']['collection_audit']=collection_audit
        observations['meta']['event_audit']=event_audit
        current['meta']['interaction']['collection_audit']=collection_audit
        current['meta']['interaction']['event_audit']=event_audit
        (args.output/'interaction.json').write_text(json.dumps(observations,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
        graph_file.write_text(json.dumps(current,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    else:
        (args.output/'interaction.json').write_text(json.dumps({'schema_version':1,'meta':{'available':False},'events':[]}),encoding='utf-8')
    subprocess.run(['node',str(ROOT/'web/apply-content-analysis.cjs'),str(args.output)],check=True)
    current=json.loads(graph_file.read_bytes())
    sanitize_absolute_paths(current)
    graph_file.write_text(json.dumps(current,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    if review:
        from pipeline.audit_interaction_graph import audit as audit_graph
        audit_graph(graph_file,args.output/'interaction.json')
    write_frontend(args.output)
    for name in ['profile-scope.json','social-graph.json','unified-graph.json','empty-identity.json','social.html','unified.html','standalone.html','social.js','unified.js','graph-data.js']:
        obsolete=args.output/name
        if obsolete.exists():obsolete.unlink()
    print(json.dumps(data['meta'], ensure_ascii=True))




def sanitize_absolute_paths(value):
    if isinstance(value, dict):
        for key, item in list(value.items()):
            if key in {'response_file', 'raw_file', 'source_file'} and isinstance(item, str):
                try:
                    value[key] = Path(item).resolve().relative_to(ROOT).as_posix()
                except ValueError:
                    pass
            else:
                sanitize_absolute_paths(item)
    elif isinstance(value, list):
        for item in value:
            sanitize_absolute_paths(item)


def apply_cached_display_names(graph, interactions):
    config = json.loads((ROOT/'config/data_sources.json').read_bytes())
    value = config.get('bilibili_names')
    if not value:
        return
    path = (ROOT/value).resolve()
    if Path(value).is_absolute() or not path.is_relative_to(ROOT/'data/normalized'):
        raise ValueError('Bilibili name cache must be inside data/normalized')
    raw = path.read_bytes()
    names = json.loads(raw)

    def label_for(label, uids):
        if label not in {'UID '+uid for uid in uids}:
            return None
        matches = {names[uid]['name'] for uid in uids if uid in names and names[uid].get('name')}
        return next(iter(matches)) if len(matches) == 1 else None

    for node in graph['nodes']:
        label = label_for(node['label'], node.get('bilibili_uids', []))
        if label:
            node['display_label'] = label
    for uid, account in interactions['accounts'].items():
        label = label_for(account['label'], [uid])
        if label:
            account['display_label'] = label
    provenance = {'file': Path(value).as_posix(), 'sha256': hashlib.sha256(raw).hexdigest()}
    graph['meta']['bilibili_display_names'] = provenance
    interactions['meta']['bilibili_display_names'] = provenance


def write_frontend(output):
    bundler=ROOT/'web/node_modules/esbuild/bin/esbuild'
    subprocess.run(['node',str(bundler),str(ROOT/'web/app.js'),'--bundle','--format=iife','--legal-comments=inline','--outfile='+str(output/'app.js')],check=True)
    css=(ROOT/'web/style.css').read_text(encoding='utf-8')
    for name in ('chillroundf.ttf', 'chillroundf-ofl.txt'):
        shutil.copyfile(ROOT/'web'/name,output/name)
    font_hash=hashlib.sha256((output/'chillroundf.ttf').read_bytes()).hexdigest()[:12]
    css=css.replace('"chillroundf.ttf"','"chillroundf.ttf?v='+font_hash+'"')
    (output/'style.css').write_text(css,encoding='utf-8',newline='\n')
    html=(ROOT/'web/index.html').read_text(encoding='utf-8')
    data_digest=hashlib.sha256()
    data_files = [output / name for name in ('graph.json', 'content-graph.json', 'interaction.json')]
    data_files.extend(sorted(output.glob('content-evidence-??.json.gz')))
    for path in data_files:
        if path.is_file():
            data_digest.update(path.name.encode())
            data_digest.update(path.read_bytes())
    html=html.replace('<html ','<html data-data-version="'+data_digest.hexdigest()[:16]+'" ',1)
    for name in ['app.js','style.css']:
        digest=hashlib.sha256((output/name).read_bytes()).hexdigest()[:12]
        html=html.replace('"'+name+'"','"'+name+'?v='+digest+'"')
    (output/'index.html').write_text(html,encoding='utf-8',newline='\n')


if __name__ == '__main__':
    main()
