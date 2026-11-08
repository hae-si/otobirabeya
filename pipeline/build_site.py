"""Build a local, offline otoDB explorer from a fixed public snapshot."""
import argparse
from collections import Counter, defaultdict
import hashlib
import gzip
import json
import re
from pathlib import Path
import shutil

from pipeline.sources.otodb import read_copy
from pipeline.normalize.creator_scope import classify, load_overrides

ROOT = Path(__file__).resolve().parents[1]
TABLES = ['otodb_mediawork', 'otodb_tagwork', 'otodb_tagworkinstance',
          'otodb_worksource', 'otodb_workrelation', 'otodb_tagworkcreatorconnection']
ROLE_NAMES = {1: '音声', 2: '映像', 4: '监督', 8: '音乐', 16: '绘画'}


def assemble(path, seeds, max_works=120):
    tables = {t: [] for t in TABLES}
    counts = Counter()
    for table, row in read_copy(path, TABLES):
        counts[table] += 1
        keys = {'otodb_mediawork': ['id', 'title', 'moved_to_id', 'status'],
                'otodb_tagwork': ['id', 'name', 'slug', 'category', 'aliased_to_id', 'deprecated'],
                'otodb_tagworkinstance': ['id', 'work_id', 'work_tag_id', 'creator_roles', 'used_as_source'],
                'otodb_worksource': ['id', 'media_id', 'url', 'published_date', 'platform', 'work_origin', 'is_pending', 'work_status'],
                'otodb_workrelation': ['id', 'A_id', 'B_id', 'relation'],
                'otodb_tagworkcreatorconnection': ['id', 'tag_id', 'site', 'content_id', 'dead']}[table]
        if not set(keys) <= row.keys():
            raise ValueError('Unsupported schema: ' + table)
        if table == 'otodb_tagwork' and row['category'] != '4':
            continue
        tables[table].append({k: row[k] for k in keys})
    works = {r['id']: r for r in tables['otodb_mediawork'] if r['status'] == '1' and not r['moved_to_id']}
    creators = {r['id']: r for r in tables['otodb_tagwork']}
    scopes = classify(creators, tables['otodb_tagworkcreatorconnection'], load_overrides(ROOT / 'data/manual/creator_scope.csv'))
    for name, records in tables.items():
        if len({r['id'] for r in records}) != len(records):
            raise ValueError('Duplicate ID in ' + name)
    if not seeds or not set(seeds) <= works.keys():
        raise ValueError('Seed work not present in snapshot')
    credits = [r for r in tables['otodb_tagworkinstance'] if r['work_tag_id'] in creators]
    seed_creators = {r['work_tag_id'] for r in credits if r['work_id'] in seeds and
                     r['used_as_source'] == 'f' and int(r['creator_roles'] or 0) & 31}
    candidates = set(seeds)
    candidates.update(r['work_id'] for r in credits if r['work_tag_id'] in seed_creators and r['used_as_source'] == 'f')
    parts = [r for r in tables['otodb_workrelation'] if r['relation'] == '2']
    parents = {r['B_id'] for r in parts if r['A_id'] in seeds}
    candidates.update(parents)
    candidates.update(r['A_id'] for r in parts if r['B_id'] in parents)
    unavailable_candidates = len(candidates - works.keys())
    candidates.intersection_update(works.keys())
    chosen = list(dict.fromkeys(seeds + sorted(candidates - set(seeds), key=int)))[:max_works]
    selected = set(chosen)
    project_ids = {r['B_id'] for r in parts if r['A_id'] in selected and r['B_id'] in selected}
    nodes = {}
    edges = []
    issues = []
    publications = defaultdict(list)
    for r in tables['otodb_worksource']:
        if r['media_id'] in selected and r['is_pending'] == 'f':
            publications[r['media_id']].append({'id': r['id'], 'url': r['url'], 'date': r['published_date'],
                                               'origin': '作者发布' if r['work_origin'] == '0' else '搬运' if r['work_origin'] == '1' else '来源类型未知',
                                               'availability': '可用（快照时）' if r['work_status'] == '0' else '已失效（快照时）' if r['work_status'] == '1' else '可用状态未知'})
    for wid in chosen:
        r = works[wid]
        nodes['work:' + wid] = {'id': 'work:' + wid, 'label': r['title'] or '作品 #' + wid,
                                'type': 'project' if wid in project_ids else 'work',
                                'url': 'https://otodb.net/work/' + wid,
                                'publications': sorted(publications[wid], key=lambda p: int(p['id'])),
                                'status': '上游合作总集标记' if wid in project_ids else '上游作品记录'}
        if r['moved_to_id']:
            issues.append({'target': 'work:' + wid, 'reason': '作品已移动，保留原ID，需复核'})
    excluded = Counter()
    for r in credits:
        if r['work_id'] not in selected:
            continue
        tag = creators[r['work_tag_id']]
        bits = int(r['creator_roles'] or 0)
        wid, cid = 'work:' + r['work_id'], 'creator:' + tag['id']
        reason = ('身份别名或弃用状态待复核' if tag['aliased_to_id'] or tag['deprecated'] == 't'
                  else '素材引用' if r['used_as_source'] == 't'
                  else '未知角色位' if bits < 0 or bits & ~63
                  else '仅致谢' if bits == 32 else '角色缺失' if not bits else None)
        if reason:
            excluded[reason] += 1
            issues.append({'creator_id': cid, 'target': wid, 'reason': reason,
                           'url': nodes[wid]['url'], 'upstream_record': r['id']})
            if reason != '角色缺失':
                continue
        nodes[cid] = {'id': cid, 'label': tag['name'], 'type': 'creator',
                      'url': 'https://otodb.net/tag/' + tag['slug'], 'scope': scopes[tag['id']]['label'],
                      'scope_verdict': scopes[tag['id']]}
        edges.append({'id': 'credit:' + r['id'], 'source': cid, 'target': wid,
                      'type': 'candidate' if reason else 'participation',
                      'roles': [label for bit, label in ROLE_NAMES.items() if bits & bit],
                      'evidence': [nodes[wid]['url']], 'record_id': r['id']})
    for r in parts:
        if r['A_id'] in selected and r['B_id'] in selected:
            edges.append({'id': 'part:' + r['id'], 'source': 'work:' + r['A_id'],
                          'target': 'work:' + r['B_id'], 'type': 'collab_part',
                          'evidence': ['https://otodb.net/work/' + r['A_id']], 'record_id': r['id']})
    confirmed = {'3580'} & selected
    for wid in sorted(confirmed):
        participants = sorted({e['source'] for e in edges if e['target'] == 'work:' + wid and e['type'] == 'participation'})
        from itertools import combinations
        for a, b in combinations(participants, 2):
            edges.append({'id': f'co:{wid}:{a}:{b}', 'source': a, 'target': b, 'type': 'co_creation',
                          'work_id': 'work:' + wid, 'evidence': ['https://otodb.net/work/' + wid]})
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        started = re.search(r'-- Started on (\d{4}-\d{2}-\d{2}) ', stream.read(4096))
    for e in edges:
        if e['source'] not in nodes or e['target'] not in nodes or not e['evidence']:
            raise ValueError('Invalid graph reference/evidence')
    return {'meta': {'source': 'otoDB', 'snapshot_sha256': digest, 'snapshot_date': started[1] if started else '未知日期',
                     'seed_work_ids': seeds, 'total_snapshot_works': counts['otodb_mediawork'],
                     'selected_works': len(selected), 'candidate_works': len(candidates),
                     'unavailable_candidates': unavailable_candidates,
                     'truncated_works': max(0, len(candidates) - len(selected)), 'excluded': dict(excluded),
                     'scope': '种子作品的共同作者与同合作总集单品；不是中文圈完整名册',
                     'license': '上游数据再发布许可未确认；本地调查原型',
                     'membership_count': 0, 'confirmed_co_creation_works': sorted(confirmed)},
            'nodes': sorted(nodes.values(), key=lambda n: n['id']),
            'edges': sorted(edges, key=lambda e: e['id']), 'issues': issues}


def main():
    from pipeline.author_site import main as current_main
    current_main()


if __name__ == '__main__':
    main()
