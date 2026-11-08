"""Identifier-only normalization sample; no upstream content copied."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCES = {
    'E04': 'https://otodb.net/work/3580',
    'E05': 'https://www.bilibili.com/video/BV1s1421t7aa/',
    'E06': 'https://soka.cafe/SCF',
    'E07': 'https://soka.cafe/index.php?title=八叶莲华会社&oldid=3285',
    'E08': 'https://otomad.wiki/音MAD社团',
}

def build():
    creators = [{'id': f'c{i}', 'scope_status': 'undecided', 'source_ids': [s]}
                for i, s in enumerate(['E04'] * 4 + ['E06'] * 2 + ['E07'] + ['E05'] * 2, 1)]
    works = [
        {'id': 'otodb:work:3580', 'source_ids': ['E04'], 'publication_urls': [
            'https://www.youtube.com/watch?v=pO27_mCMYBU',
            'https://www.nicovideo.jp/watch/sm45207926']},
        {'id': 'bilibili:BV1s1421t7aa', 'source_ids': ['E05'], 'status': 'pending_direct_review'},
    ]
    participation = [
        {'creator_id': f'c{i}', 'target_id': 'otodb:work:3580', 'target_type': 'work',
         'role': role, 'relation_type': 'co_creation', 'source_ids': ['E04'], 'status': 'observed'}
        for i, role in [(1, 'audio'), (2, 'visuals'), (3, 'artwork')]
    ]
    participation += [
        {'creator_id': f'c{i}', 'target_id': 'project:SCF', 'target_type': 'collab_project',
         'role': 'part', 'relation_type': 'collab_event', 'source_ids': ['E06'], 'status': 'pending_direct_review'}
        for i in [5, 6]]
    participation += [
        {'creator_id': f'c{i}', 'target_id': 'bilibili:BV1s1421t7aa', 'target_type': 'work',
         'role': 'tuning', 'relation_type': 'co_creation', 'source_ids': ['E05'], 'status': 'pending_direct_review'}
        for i in [8, 9]]
    return {'sources': [{'id': k, 'url': v, 'observed_at': '2026-10-28',
                         'evidence_level': 'direct' if k == 'E04' else ('unavailable' if k == 'E08' else 'search_index')}
                        for k, v in SOURCES.items()],
            'creator': creators, 'work': works,
            'collab_project': [{'id': 'project:SCF', 'source_ids': ['E06'], 'status': 'pending_direct_review'}],
            'organization': [{'id': 'organization:E07', 'source_ids': ['E07']}],
            'participation': participation,
            'membership': [{'creator_id': 'c7', 'organization_id': 'organization:E07',
                            'source_ids': ['E07'], 'role': 'president', 'start_date': None,
                            'end_date': None, 'status': 'pending_direct_review'}],
            'mention_candidate': [{'creator_id': 'c4', 'target_id': 'otodb:work:3580',
                                   'reason': 'thanks_only', 'source_ids': ['E04']}]}

def validate(data):
    ids = {row['id'] for name in ['creator', 'work', 'collab_project', 'organization'] for row in data[name]}
    assert len(ids) == sum(len(data[n]) for n in ['creator', 'work', 'collab_project', 'organization'])
    seen = set()
    for row in data['participation']:
        assert row['creator_id'] in ids and row['target_id'] in ids
        key = (row['creator_id'], row['target_id'], row['role'])
        assert key not in seen
        seen.add(key)
        assert row['creator_id'] != 'c4'
        if row['target_type'] == 'collab_project':
            assert row['relation_type'] == 'collab_event'
    for row in data['membership']:
        assert row['creator_id'] in ids and row['organization_id'] in ids
    for name in ['creator', 'work', 'collab_project', 'organization', 'participation', 'membership', 'mention_candidate']:
        for row in data[name]:
            assert row['source_ids'] and set(row['source_ids']) <= SOURCES.keys()
    assert len([w for w in data['work'] if w['id'] == 'otodb:work:3580']) == 1

if __name__ == '__main__':
    data = build()
    validate(data)
    output = ROOT / 'data/normalized/m1_sample.json'
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Validated identifier-only sample:', output)
