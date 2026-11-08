"""Recover explicit tag associations; no ancestor propagation or name merging."""
from collections import Counter

VERSION = 'content-tags-v1'
CATEGORIES = {'0': 'UNCATEGORIZED', '1': 'EVENT', '2': 'SONG', '3': 'SOURCE',
              '4': 'CREATOR', '5': 'META', '6': 'MEDIA', '7': 'GENERAL'}


def recover(tables, works, tagmap, workmap):
    tags = {r['id']: dict(r) for r in tables['otodb_tagwork']}
    associations, excluded, cross = {}, [], []
    for tid, tag in tags.items():
        target = tagmap.get(tid)
        tag['canonical_id'] = target
        tag['cross_category_alias'] = bool(target and tags[target]['category'] != tag['category'])
        if tag['cross_category_alias']:
            cross.append({'id': tid, 'target_id': target, 'from_category': tag['category'],
                          'to_category': tags[target]['category']})
    for row in tables['otodb_tagworkinstance']:
        tid, wid = tagmap.get(row['work_tag_id']), workmap.get(row['work_id'])
        original = tags.get(row['work_tag_id'])
        reason = ('unresolved_tag' if not tid else 'unavailable_work' if wid not in works
                  else 'cross_category_alias' if original['cross_category_alias']
                  else 'deprecated_tag' if tags[tid].get('deprecated') == 't' else None)
        if reason:
            excluded.append(dict(row, reason=reason, canonical_tag_id=tid, canonical_work_id=wid))
            continue
        key = wid, tid
        entry = associations.setdefault(key, {'work_id': wid, 'tag_id': tid,
            'category': tags[tid]['category'], 'source_records': []})
        entry['source_records'].append(dict(row))
    rows = sorted(associations.values(), key=lambda r: (int(r['work_id']), int(r['tag_id'])))
    for row in rows:
        row['source_records'].sort(key=lambda r: int(r['id']))
    parents = []
    for row in tables.get('otodb_tagworkparenthood', []):
        parent, child = tagmap.get(row['parent_id']), tagmap.get(row['tag_id'])
        parents.append(dict(row, canonical_parent_id=parent, canonical_tag_id=child,
                            status='unresolved' if not parent or not child else 'self_after_alias' if parent == child else 'explicit'))
    return {'tags': tags, 'work_tags': rows, 'tag_relations': parents,
            'tag_audit': {'version': VERSION, 'raw_tags_by_category': dict(Counter(t['category'] for t in tags.values())),
                'canonical_tags_by_category': dict(Counter(t['category'] for i,t in tags.items() if t['canonical_id']==i)),
                'raw_instances_by_category': dict(Counter(tags.get(r['work_tag_id'], {}).get('category', 'missing') for r in tables['otodb_tagworkinstance'])),
                'associations_by_category': dict(Counter(r['category'] for r in rows)),
                'deduplicated_instances': sum(len(r['source_records'])-1 for r in rows),
                'excluded_instances': excluded, 'exclusions_by_reason': dict(Counter(r['reason'] for r in excluded)),
                'cross_category_aliases': cross, 'parent_relations': len(parents),
                'categories': CATEGORIES, 'content_categories': ['2', '3'],
                'media_policy': 'retained, excluded from similarity pending semantic review'}}
