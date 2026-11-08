"""Minimal local normalization pipeline. Python 3.11+, standard library only."""
import argparse
import itertools
import json
import re
from pathlib import Path


def decode_copy(value):
    if value == r'\N':
        return None
    def replace(match):
        token = match[1]
        if token.startswith('x'):
            return chr(int(token[1:], 16))
        if token[0] in '01234567':
            return chr(int(token, 8))
        return {'b': '\b', 'f': '\f', 'n': '\n', 'r': '\r', 't': '\t', 'v': '\v'}.get(token, token)
    return re.sub(r'\\(x[0-9a-fA-F]{1,2}|[0-7]{1,3}|.)', replace, value)


def normalize(raw, confirmed, supplement=None):
    tables = {name: [{k: decode_copy(v) for k, v in row.items()} for row in records]
              for name, records in raw['tables'].items()}
    data = {name: [] for name in ['creator', 'work', 'collab_project', 'organization',
                                  'participation', 'membership', 'sources', 'issues']}
    tags = {r['id']: r for r in tables['otodb_tagwork']}
    if len(tags) != len(tables['otodb_tagwork']):
        raise ValueError('Duplicate tag ID')
    work_ids = set()
    for row in tables['otodb_mediawork']:
        wid = 'otodb:work:' + row['id']
        if wid in work_ids:
            raise ValueError('Duplicate work ID')
        work_ids.add(wid)
        source = 'source:' + wid
        data['sources'].append({'id': source, 'url': 'https://otodb.net/work/' + row['id'],
                                'snapshot_sha256': raw['sha256']})
        data['work'].append({'id': wid, 'title': row['title'], 'source_ids': [source],
                             'classification': 'co_creation' if row['id'] in confirmed else 'pending',
                             'publications': []})
        if row.get('moved_to_id'):
            data['issues'].append({'entity': wid, 'reason': 'moved_work_requires_review'})
    works = {r['id']: r for r in data['work']}
    for row in tables['otodb_worksource']:
        wid = 'otodb:work:' + str(row['media_id'])
        if wid not in works:
            raise ValueError('Missing publication work: ' + wid)
        works[wid]['publications'].append({'id': 'otodb:publication:' + row['id'], 'url': row['url']})
    creators = {}
    roles = {1: 'audio', 2: 'visuals', 4: 'director', 8: 'music', 16: 'artwork'}
    for row in tables['otodb_tagworkinstance']:
        wid = 'otodb:work:' + row['work_id']
        if wid not in works or row['work_tag_id'] not in tags:
            raise ValueError('Missing participation reference')
        tag = tags[row['work_tag_id']]
        if tag['category'] != '4':
            continue
        cid = 'otodb:creator:' + tag['id']
        creators[cid] = {'id': cid, 'display_name': tag['name'], 'scope_status': 'undecided'}
        bits = int(row['creator_roles'] or 0)
        reason = ('creator_alias_requires_review' if tag.get('aliased_to_id') or tag.get('deprecated') == 't'
                  else 'sample_reference' if row['used_as_source'] == 't'
                  else 'unknown_role_bits' if bits < 0 or bits & ~63
                  else 'thanks_only' if bits == 32
                  else 'missing_roles' if not bits else None)
        if reason:
            data['issues'].append({'entity': cid, 'target_id': wid, 'reason': reason,
                                   'source_ids': ['source:' + wid]})
            continue
        data['participation'].append({'creator_id': cid, 'target_id': wid, 'target_type': 'work',
                                      'roles': [name for bit, name in roles.items() if bits & bit],
                                      'source_ids': ['source:' + wid]})
    data['creator'] = list(creators.values())
    for row in tables.get('otodb_workrelation', []):
        data['issues'].append({'entity': 'otodb:work:' + row['A_id'],
                               'target_id': 'otodb:work:' + row['B_id'],
                               'reason': 'upstream_work_relation_not_project_membership',
                               'upstream_relation': row['relation']})
    if supplement:
        for name in ['creator', 'collab_project', 'organization', 'participation', 'membership', 'sources']:
            data[name].extend(supplement.get(name, []))
    for name in data:
        data[name] = [json.loads(v) for v in sorted({json.dumps(r, ensure_ascii=False, sort_keys=True) for r in data[name]})]
    entities = {}
    for name in ['creator', 'work', 'collab_project', 'organization']:
        for row in data[name]:
            if row['id'] in entities:
                raise ValueError('Conflicting entity ID: ' + row['id'])
            entities[row['id']] = name
    sources = {r['id'] for r in data['sources']}
    if len(sources) != len(data['sources']):
        raise ValueError('Conflicting source ID')
    edges = []
    for name in ['participation', 'membership']:
        for row in data[name]:
            target = row.get('target_id', row.get('organization_id'))
            expected = 'organization' if name == 'membership' else row['target_type']
            if entities.get(row['creator_id']) != 'creator' or entities.get(target) != expected:
                raise ValueError('Invalid relation reference or target type')
            if not row.get('source_ids') or not set(row['source_ids']) <= sources:
                raise ValueError('Missing source evidence')
            if row.get('status') not in (None, 'verified', 'observed'):
                data['issues'].append({'entity': row['creator_id'], 'target_id': target, 'reason': 'pending_evidence'})
                continue
            edges.append({'source': row['creator_id'], 'target': target,
                          'type': 'membership' if name == 'membership' else ('collab_event' if expected == 'collab_project' else 'participation'),
                          'source_ids': row['source_ids']})
    for work in data['work']:
        if work['classification'] != 'co_creation':
            continue
        participants = sorted({e['source'] for e in edges if e['target'] == work['id'] and e['type'] == 'participation'})
        for a, b in itertools.combinations(participants, 2):
            edges.append({'source': a, 'target': b, 'type': 'co_creation', 'work_id': work['id'],
                          'source_ids': work['source_ids']})
    graph = {'nodes': [{'id': k, 'type': v} for k, v in sorted(entities.items())], 'edges': edges}
    return data, graph


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path, help='Local output of inspect_otodb.py')
    parser.add_argument('--confirmed-co-creation', action='append', default=[], help='Evidence-reviewed otoDB work ID; repeatable')
    parser.add_argument('--supplement', type=Path, help='Local JSON with sourced project/membership records')
    parser.add_argument('--output-dir', type=Path, default=Path('data/exports/m2'))
    args = parser.parse_args()
    raw = json.loads(args.input.read_text(encoding='utf-8'))
    supplement = json.loads(args.supplement.read_text(encoding='utf-8')) if args.supplement else None
    data, graph = normalize(raw, set(args.confirmed_co_creation), supplement)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for filename, result in [('normalized.json', data), ('graph.json', graph), ('issues.json', data['issues'])]:
        (args.output_dir / filename).write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf-8')
    print(f"Normalized {len(data['work'])} works; {len(graph['edges'])} edges; {len(data['issues'])} review issues")


if __name__ == '__main__':
    main()
