"""Verify saved request evidence and merge sampled follows without network calls."""
import hashlib
import json
from collections import Counter
from pathlib import Path


def audit(roots):
    edges, accounts, mappings, evidence, coverage = {}, {}, {}, [], []
    status = Counter()
    for root in roots:
        root = Path(root)
        pages = {}
        cursors, completed, failed = {}, set(), set()
        for line in (root / 'requests.jsonl').read_text(encoding='utf-8').splitlines():
            request = json.loads(line)
            raw = (root / request['file']).read_bytes()
            if hashlib.sha256(raw).hexdigest() != request['sha256']:
                raise ValueError('Response hash mismatch')
            status[str(request['status'])] += 1
            evidence.append({**request, 'directory': str(root)})
            if request['status'] != 200:
                if request['endpoint'] in {'users/following','users/followers'}:
                    failed.add((request['endpoint'],request['request']['userId']))
                continue
            data = json.loads(raw)
            if request['endpoint'] == 'users/show':
                uid = data['id']
                accounts[uid] = {k: data.get(k) for k in ['id', 'username', 'host', 'isBot']}
                continue
            body = request['request']
            pagekey = (request['endpoint'], body['userId'])
            if pagekey in completed or body.get('untilId') != cursors.get(pagekey):
                raise ValueError('Broken pagination cursor chain')
            seen = pages.setdefault(pagekey, set())
            if not isinstance(data, list):
                raise ValueError('Expected array')
            for row in data:
                direction = 'followerId' if request['endpoint'].endswith('following') else 'followeeId'
                if row[direction] != body['userId'] or row['id'] in seen:
                    raise ValueError('Direction mismatch or overlapping pages')
                seen.add(row['id'])
                fact = {k: row[k] for k in ['id', 'createdAt', 'followerId', 'followeeId']}
                if row['id'] in edges and edges[row['id']]['fact'] != fact:
                    raise ValueError('Conflicting follow record')
                item = edges.setdefault(row['id'], {'fact': fact, 'evidence': []})
                item['evidence'].append({'response_sha256': request['sha256'],
                                         'observed_at': request['observed_at'],
                                         'endpoint': request['endpoint']})
                for field in ['follower', 'followee']:
                    user = row.get(field)
                    if user:
                        if user['id'] != row[field+'Id']:
                            raise ValueError('Nested account mismatch')
                        accounts[user['id']] = {k: user.get(k) for k in ['id', 'username', 'host', 'isBot']}
            if data:cursors[pagekey]=data[-1]['id']
            else:completed.add(pagekey)
        progress_path=root/'progress.json'
        progress = json.loads(progress_path.read_text(encoding='utf-8')) if progress_path.exists() else {'mappings':[],'coverage':[]}
        for mapping in progress['mappings']:
            uid = mapping['otomadsite_id']
            if uid in mappings and mappings[uid]['otodb_creator_id'] != mapping['otodb_creator_id']:
                raise ValueError('Conflicting creator mapping')
            mappings[uid] = mapping
        reported={("users/"+c['endpoint'],c['user_id']):c for c in progress['coverage']}
        for key,c in reported.items():
            if c['state']=='visible_list_exhausted' and key not in completed:
                raise ValueError('Exhausted coverage lacks terminal empty page')
        for key in pages.keys() | failed:
            reported[key]={'user_id':key[1],'endpoint':key[0].split('/')[-1],
                           'state':'request_failed' if key in failed else 'visible_list_exhausted' if key in completed else reported.get(key,{}).get('state','partial_interrupted'),
                           'last_cursor':cursors.get(key)}
        coverage.extend(reported.values())
    return {'schema_version': 1, 'accounts': sorted(accounts.values(), key=lambda x: x['id']),
            'edges': sorted(edges.values(), key=lambda x: x['fact']['id']),
            'mappings': list(mappings.values()), 'coverage': coverage,
            'requests': evidence, 'http_status_counts': dict(status),
            'limitations': ['bounded snowball sample', 'no inference of friendship',
                            'visible lists only; no full-history guarantee',
                            'creator mappings based on public links, not real identity']}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('roots', nargs='+', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.roots)
    if args.output.exists():
        raise FileExistsError('Choose a fresh output path')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k: len(result[k]) for k in ['accounts', 'edges', 'mappings', 'requests']}))
