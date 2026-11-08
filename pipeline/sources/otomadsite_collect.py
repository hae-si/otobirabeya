"""Bounded anonymous collection from explicit otoDB OtomadSite links; no credentials."""
import hashlib
import os
import json
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(os.environ.get('OTOMADSITE_OUTPUT', 'data/raw/otomadsite/snowball-20261028'))
UA = 'otobirabeya-research/0.1 (public social graph feasibility; Python urllib; no authentication)'


def main():
    request_cap=int(os.environ.get('OTOMADSITE_REQUEST_CAP','180'))
    if not 1<=request_cap<=180:raise ValueError('Request cap must be between 1 and 180')
    ROOT.mkdir(parents=True, exist_ok=True)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    index = ROOT / 'requests.jsonl'
    cached = {}
    if index.exists():
        for line in index.read_text(encoding='utf-8').splitlines():
            record = json.loads(line)
            if record['status'] == 200:
                cached[record['key']] = record
    calls = 0

    def request(endpoint, body):
        nonlocal calls
        key = hashlib.sha256(json.dumps([endpoint, body], sort_keys=True).encode()).hexdigest()
        if key in cached:
            record = cached[key]
            raw = (ROOT / record['file']).read_bytes()
            assert hashlib.sha256(raw).hexdigest() == record['sha256']
            return json.loads(raw)
        if calls >= request_cap:
            raise RuntimeError('Global request cap reached; resume only after review')
        if calls:
            time.sleep(2)
        calls += 1
        req = urllib.request.Request('https://otomad.site/api/' + endpoint,
                                     data=json.dumps(body).encode(), method='POST',
                                     headers={'Content-Type': 'application/json', 'User-Agent': UA})
        try:
            response = opener.open(req, timeout=30)
        except urllib.error.HTTPError as error:
            response = error
        raw = response.read(4 * 1024 * 1024 + 1)
        if len(raw) > 4 * 1024 * 1024:
            raise RuntimeError('Response exceeds size cap')
        filename = key + '.json'
        record = {'key': key, 'endpoint': endpoint, 'request': body,
                  'observed_at': datetime.now(timezone.utc).isoformat(),
                  'status': response.code, 'content_type': response.headers.get('Content-Type'),
                  'cf_ray': response.headers.get('CF-Ray'), 'user_agent': UA,
                  'file': filename, 'sha256': hashlib.sha256(raw).hexdigest()}
        if (ROOT / filename).exists():
            filename = key + '-' + str(time.time_ns()) + '.json'
            record['file'] = filename
        (ROOT / filename).write_bytes(raw)
        with index.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(record) + '\n')
        print(json.dumps({'endpoint': endpoint, 'status': response.code, 'call': calls}), flush=True)
        if response.code != 200:
            raise RuntimeError(f'HTTP {response.code}; inspect saved response, no automatic retries')
        data = json.loads(raw)
        cached[key] = record
        return data

    source = json.loads(Path(os.environ.get('OTOMADSITE_SEEDS', 'data/normalized/otomadsite/otodb-seed-candidates-20261028.json')).read_text(encoding='utf-8'))
    mappings, edges, discovered, coverage = [], {}, {}, []
    for link in source['direct_otomadsite_connections']:
        url = urlparse(link['content_id'])
        if link['dead'] != 'f' or url.hostname != 'otomad.site' or not url.path.startswith('/@'):
            continue
        username = url.path[2:]
        if '/' in username or '@' in username:
            continue
        known_id = link.get('otomadsite_id')
        user = request('users/show', {'userId': known_id} if known_id else {'username': username})
        if user.get('host') is not None or (user.get('id') != known_id if known_id else user.get('username', '').lower() != username.lower()):
            raise ValueError('Local account resolution mismatch')
        uid = user['id']
        mappings.append({'otodb_creator_id': None if link['tag_id'].startswith('user-provided:') else link['tag_id'], 'otodb_connection_id': None if link['id'].startswith('user-provided:') else link['id'],
                         'user_provided_name': link.get('display_name'),
                         'otomadsite_id': uid, 'username': user['username'],
                         'evidence_url': link['content_id'], 'mapping_basis': link.get('mapping_basis', 'explicit_otodb_link'),
                         'reciprocal_link_verified': False})
        for endpoint, visibility in [('following', 'followingVisibility'), ('followers', 'followersVisibility')]:
            if user.get(visibility) != 'public':
                coverage.append({'user_id': uid, 'endpoint': endpoint, 'state': 'not_public_skipped'})
                continue
            cursor, seen, complete = None, set(), False
            for page in range(20):
                body = {'userId': uid, 'limit': 20}
                if cursor:
                    body['untilId'] = cursor
                rows = request('users/' + endpoint, body)
                if not isinstance(rows, list):
                    raise ValueError('Expected relationship array')
                if not rows:
                    complete = True
                    break
                for row in rows:
                    if row['followerId' if endpoint == 'following' else 'followeeId'] != uid:
                        raise ValueError('Relationship direction mismatch')
                    edges[row['id']] = {k: row[k] for k in ['id', 'createdAt', 'followerId', 'followeeId']}
                    other = row.get('followee' if endpoint == 'following' else 'follower', {})
                    if other:
                        discovered[other['id']] = {k: other.get(k) for k in ['id', 'username', 'host', 'isBot']}
                next_cursor = rows[-1]['id']
                if next_cursor in seen:
                    raise ValueError('Non-advancing cursor')
                seen.add(next_cursor)
                cursor = next_cursor
            coverage.append({'user_id': uid, 'endpoint': endpoint, 'state': 'visible_list_exhausted' if complete else 'page_cap', 'last_cursor': cursor})
        result = {'snapshot_sha256': source['snapshot_sha256'], 'mappings': mappings,
                  'edges': sorted(edges.values(), key=lambda r: r['id']),
                  'discovered_accounts': sorted(discovered.values(), key=lambda r: r['id']),
                  'coverage': coverage, 'expansion': 'unmapped accounts queued, not recursively collected',
                  'limits': {'max_requests': request_cap, 'max_pages_per_list': 20, 'page_size': 20, 'interval_seconds': 2}}
        (ROOT / 'progress.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Collection finished; inspect progress.json and requests.jsonl', flush=True)


if __name__ == '__main__':
    main()
