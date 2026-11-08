"""Offline import of public OtomadSite following/followers JSON pages. No network/auth."""
import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

BASE = 'https://otomad.site'


def identifier(value):
    if not isinstance(value, str) or not value.isalnum() or not value.isascii():
        raise ValueError('Invalid upstream ID')
    return value


def import_pages(paths, endpoint, user_id, observed_on):
    datetime.strptime(observed_on, '%Y-%m-%d')
    identifier(user_id)
    if endpoint not in ('following', 'followers'):
        raise ValueError('Only public following/followers pages are supported')
    accounts, records, sources = {}, {}, []
    duplicates = 0
    for page_index, path in enumerate(paths):
        raw = Path(path).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        rows = json.loads(raw.decode('utf-8-sig'))
        if not isinstance(rows, list):
            raise ValueError('Expected a JSON array, not an API error or profile')
        sources.append({'sha256': digest, 'page_index': page_index,
                        'row_count': len(rows), 'endpoint': f'{BASE}/api/users/{endpoint}',
                        'requested_user_id': user_id, 'observed_on': observed_on,
                        'capture_method': 'user_supplied_browser_response'})
        for row in rows:
            rid = identifier(row['id'])
            follower, followee = identifier(row['followerId']), identifier(row['followeeId'])
            if (follower if endpoint == 'following' else followee) != user_id:
                raise ValueError('Response does not match requested user/direction')
            nested = row['followee' if endpoint == 'following' else 'follower']
            target = followee if endpoint == 'following' else follower
            if nested['id'] != target:
                raise ValueError('Nested account ID mismatch')
            account = {'id': target, 'platform': 'otomadsite',
                       'username': nested.get('username'), 'host': nested.get('host'),
                       'is_bot': nested.get('isBot'), 'creator_id': None}
            if target in accounts and 'username' in accounts[target] and accounts[target] != account:
                raise ValueError('Conflicting account snapshots; import separately')
            accounts[target] = account
            accounts.setdefault(user_id, {'id': user_id, 'platform': 'otomadsite',
                                         'creator_id': None})
            fact = {'id': rid, 'type': 'follows', 'source': follower, 'target': followee,
                    'upstream_created_at': row['createdAt']}
            datetime.fromisoformat(fact['upstream_created_at'].replace('Z', '+00:00'))
            if rid in records:
                if any(records[rid][k] != v for k, v in fact.items()):
                    raise ValueError('Conflicting relationship ID')
                duplicates += 1
            else:
                records[rid] = {**fact, 'observed_on': observed_on, 'evidence_sha256': []}
            if digest not in records[rid]['evidence_sha256']:
                records[rid]['evidence_sha256'].append(digest)
    return {'schema_version': 1, 'platform': 'otomadsite',
            'capture_method': 'user_supplied_browser_response',
            'authentication': 'not_independently_verified',
            'coverage': 'partial_pages_not_complete_follow_graph',
            'accounts': sorted(accounts.values(), key=lambda x: x['id']),
            'edges': sorted(records.values(), key=lambda x: x['id']),
            'sources': sources, 'duplicate_rows': duplicates}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pages', nargs='+', type=Path)
    parser.add_argument('--endpoint', choices=['following', 'followers'], required=True)
    parser.add_argument('--user-id', required=True)
    parser.add_argument('--observed-on', required=True, help='Date of observing the response, YYYY-MM-DD')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = import_pages(args.pages, args.endpoint, args.user_id, args.observed_on)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise FileExistsError('Output exists; choose a new path to preserve prior observations')
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f"Imported {len(result['edges'])} follows, {len(result['accounts'])} accounts; duplicates {result['duplicate_rows']}")


if __name__ == '__main__':
    main()
