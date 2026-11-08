"""Extract explicit Bilibili profile links from hash-verified cached responses."""
import hashlib
import html
import json
import re
from urllib.parse import urlsplit


def bilibili_links(user):
    values = [('description', user.get('description') or '')]
    values += [(f'fields[{i}].value', f.get('value') or '') for i, f in enumerate(user.get('fields') or [])]
    values += [(f'verifiedLinks[{i}]', v) for i, v in enumerate(user.get('verifiedLinks') or []) if isinstance(v, str)]
    found = set()
    for field, text in values:
        for url in re.findall(r'https?://[^\s<>"\'\]]+', html.unescape(text)):
            parts = urlsplit(url)
            host = (parts.hostname or '').lower()
            pattern = r'/([1-9][0-9]*)/?' if host == 'space.bilibili.com' else r'/space/([1-9][0-9]*)/?' if host in {'m.bilibili.com', 'www.bilibili.com', 'bilibili.com'} else None
            match = re.fullmatch(pattern, parts.path) if pattern else None
            if match:
                found.add((match[1], field, url))
    return [{'uid': uid, 'field': field, 'url': url, 'canonical_url': f'https://space.bilibili.com/{uid}'} for uid, field, url in sorted(found)]


def extract(roots, account_ids):
    records = {uid: {} for uid in account_ids}
    for root in roots:
        for line in (root / 'requests.jsonl').read_text(encoding='utf-8').splitlines():
            r = json.loads(line)
            if r['status'] != 200:
                continue
            raw = (root / r['file']).read_bytes()
            if hashlib.sha256(raw).hexdigest() != r['sha256']:
                raise ValueError('Profile response hash mismatch')
            data = json.loads(raw)
            users = [data] if r['endpoint'] == 'users/show' else [x.get('follower') or x.get('followee') for x in data]
            for user in users:
                if not user or user['id'] not in records:
                    continue
                for link in bilibili_links(user):
                    evidence = {**link, 'response_sha256': r['sha256'], 'response_file': str(root / r['file']), 'endpoint': r['endpoint']}
                    records[user['id']][json.dumps(evidence, sort_keys=True)] = evidence
    return {uid: {'rule': 'explicit_bilibili_profile_link', 'core': bool(items), 'evidence': [items[k] for k in sorted(items)]} for uid, items in sorted(records.items())}


def mapping_candidates(dataset, profiles):
    owners = {}
    for account in dataset['accounts']:
        if account['site'] == '3' and account['dead'] == 'f' and account['tag_id'] in dataset['creators']:
            uid = account['content_id']
            if uid.isdigit():
                owners.setdefault(uid, set()).add(account['tag_id'])
    result = []
    for account_id, profile in sorted(profiles.items()):
        links = profile['evidence']
        if not links:
            continue
        ids = sorted({cid for link in links for cid in owners.get(link['uid'], set())})
        result.append({'user_id': account_id, 'creator_ids': ids,
                       'state': 'unique_explicit_platform_link' if len(ids) == 1 else 'conflict' if ids else 'no_otodb_uid_match',
                       'basis': 'exact_bilibili_uid', 'evidence': links})
    return result
