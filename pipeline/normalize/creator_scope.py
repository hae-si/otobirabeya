"""Project-owned scope overlay; account presence is a heuristic, not nationality."""
import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from pipeline.sources.otodb import read_copy

ROOT = Path(__file__).resolve().parents[2]
RULE_VERSION = 'account-scope-v2'
LABELS = {'chinese_default': '中文作者（账号规则默认）', 'pending_model': '双平台账号，待模型判断',
          'undecided': '中文圈归属未判定', 'chinese': '中文作者（补充判定）', 'non_chinese': '非中文作者（补充判定）'}


def load_overrides(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        required = {'creator_id', 'scope_status', 'method', 'source_urls', 'reason', 'reviewed_at'}
        if not required <= set(reader.fieldnames or []):
            raise ValueError('Scope CSV missing required headers')
        result = list(reader)
    seen = set()
    for row in result:
        key = row['creator_id'], row['method']
        if key in seen:
            raise ValueError('Duplicate creator/method override: ' + str(key))
        seen.add(key)
        if row['method'] not in {'human', 'model'} or row['scope_status'] not in {'chinese', 'non_chinese', 'undecided'}:
            raise ValueError('Invalid override method/status')
        if not row['reason'].strip() or not row['reviewed_at'].strip() or not row['source_urls'].strip():
            raise ValueError('Override requires evidence, reason and review date')
        if not all(u.startswith(('https://', 'http://')) for u in row['source_urls'].split('|')):
            raise ValueError('Override evidence must be public HTTP(S) URLs')
    return result


def classify(creators, connections, overrides=()):
    accounts = defaultdict(list)
    for row in connections:
        if row['tag_id'] in creators and row['dead'] == 'f' and row['content_id']:
            accounts[row['tag_id']].append(row)
    overrides_by_id = defaultdict(list)
    for row in overrides:
        key = row['creator_id'].removeprefix('otodb:creator:')
        if key not in creators or row['creator_id'] != 'otodb:creator:' + key:
            raise ValueError('Override creator ID not found: ' + row['creator_id'])
        overrides_by_id[key].append(row)
    result = {}
    for tid, tag in sorted(creators.items(), key=lambda item: int(item[0])):
        links = sorted(accounts[tid], key=lambda r: int(r['id']))
        sites = {r['site'] for r in links}
        status = 'chinese_default' if '3' in sites else 'undecided'
        reason = ('both_bilibili_and_niconico' if status == 'pending_model' else
                  'has_bilibili_account' if status == 'chinese_default' else
                  'no_active_account_records' if not links else 'no_bilibili_account_record')
        if tag.get('aliased_to_id') or tag.get('deprecated') == 't':
            status = 'undecided'
            reason = 'alias_or_deprecated_identity_requires_review'
        verdict = {'creator_id': 'otodb:creator:' + tid, 'display_name': tag['name'],
                   'scope_status': status, 'method': 'rule', 'rule_version': RULE_VERSION,
                   'reason': reason,
                   'source_urls': ['https://otodb.net/tag/' + tag['slug']],
                   'accounts': [{'record_id': r['id'], 'site': r['site'], 'account_id': r['content_id']} for r in links]}
        if overrides_by_id[tid]:
            chosen = max(overrides_by_id[tid], key=lambda r: {'model': 1, 'human': 2}[r['method']])
            verdict.update({k: chosen[k] for k in ['scope_status', 'method', 'reason', 'reviewed_at']})
            verdict['source_urls'] = chosen['source_urls'].split('|')
        verdict['label'] = LABELS[verdict['scope_status']]
        result[tid] = verdict
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dump', type=Path, default=ROOT / 'data/raw/m1/otodb-snapshot.sql.gz')
    parser.add_argument('--overrides', type=Path, default=ROOT / 'data/manual/creator_scope.csv')
    parser.add_argument('--output', type=Path, default=ROOT / 'data/normalized/scope')
    args = parser.parse_args()
    creators, connections = {}, []
    for table, row in read_copy(args.dump, ['otodb_tagwork', 'otodb_tagworkcreatorconnection']):
        if table == 'otodb_tagwork' and row['category'] == '4':
            creators[row['id']] = row
        elif table == 'otodb_tagworkcreatorconnection':
            connections.append(row)
    verdicts = list(classify(creators, connections, load_overrides(args.overrides)).values())
    with args.dump.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    meta = {'snapshot_sha256': digest, 'rule_version': RULE_VERSION,
            'counts': dict(Counter(r['scope_status'] for r in verdicts))}
    args.output.mkdir(parents=True, exist_ok=True)
    for filename, records in [('creator_scope.json', verdicts), ('model_review_queue.json', [r for r in verdicts if r['scope_status'] == 'pending_model']),
                              ('undecided_queue.json', [r for r in verdicts if r['scope_status'] == 'undecided'])]:
        (args.output / filename).write_text(json.dumps({'meta': meta, 'records': records}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    undecided = [r for r in verdicts if r['scope_status'] == 'undecided']
    combinations = Counter(tuple(sorted({a['site'] for a in r['accounts']}, key=int)) for r in undecided)
    statistics = {'meta': meta, 'undecided_reasons': dict(Counter(r['reason'] for r in undecided)),
                  'undecided_account_combinations': [{'site_codes': list(sites), 'creators': count} for sites, count in combinations.most_common()],
                  'site_codes': {'0':'website','1':'Niconico','2':'YouTube','3':'Bilibili','4':'Twitter','5':'Bluesky','6':'SoundCloud'}}
    (args.output / 'scope_statistics.json').write_text(json.dumps(statistics, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(meta, ensure_ascii=True))


if __name__ == '__main__':
    main()
