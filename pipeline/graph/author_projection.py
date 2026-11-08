"""Evidence-preserving Newman projection of creator affiliations."""
from collections import defaultdict
from itertools import combinations


def project(creators, works, credits, relations, anchors, cooperation_works=()):
    usable = {tid for tid, t in creators.items() if not t.get('aliased_to_id') and t.get('deprecated') != 't'}
    by_work = defaultdict(dict)
    excluded = defaultdict(int)
    for row in credits:
        tid, wid = row['work_tag_id'], row['work_id']
        if tid not in usable or wid not in works:
            continue
        bits = int(row['creator_roles'] or 0)
        if row['used_as_source'] != 'f' or bits < 0 or bits & ~63:
            excluded['source_thanks_or_unknown_role'] += 1
            continue
        by_work[wid][tid] = bits
    parents = defaultdict(set)
    for r in relations:
        if r['relation'] == '2' and r['A_id'] in works and r['B_id'] in works:
            parents[r['A_id']].add(r['B_id'])
    roots = {}
    ambiguous = set()
    for wid in works:
        current, visited = wid, set()
        while current in parents:
            if current in visited or len(parents[current]) != 1:
                ambiguous.update(visited | {current})
                current = wid
                break
            visited.add(current)
            current = next(iter(parents[current]))
        roots[wid] = current
    events = {}
    project_roots = {v for ps in parents.values() for v in ps} | {wid for wid,w in works.items() if w.get('classification')=='collab_project'}
    cooperation_works=set(cooperation_works)
    for wid, participants in by_work.items():
        root = roots[wid]
        key = 'event:' + root
        event = events.setdefault(key, {'id': key, 'root_work_id': root, 'title': works[root]['title'] or '#' + root,
                                        'type': 'project' if root in project_roots else 'work',
                                        'cooperation': False,
                                        'participants': {}, 'roles': {}, 'work_ids': [], 'uncertain_grouping': False})
        event['work_ids'].append(wid)
        event['cooperation'] |= wid in cooperation_works
        event['uncertain_grouping'] |= wid in ambiguous
        for tid, bits in participants.items():
            event['participants'].setdefault(tid, []).append(wid)
            event['roles'][tid] = event['roles'].get(tid, 0) | bits
    edges = {}
    retained_events = {}
    for key, event in sorted(events.items()):
        people = set(event['participants'])
        if not people & anchors or len(people) < 2:
            continue
        event['n'] = len(people)
        event['unknown_role_count'] = sum(all(by_work[w][tid] == 0 for w in ws) for tid, ws in event['participants'].items())
        event['work_ids'].sort(key=int)
        for ws in event['participants'].values():
            ws.sort(key=int)
        retained_events[key] = event
        pairs = set()
        for a in people & anchors:
            for b in people - {a}:
                pairs.add(tuple(sorted((a, b), key=int)))
        for a, b in sorted(pairs, key=lambda p: (int(p[0]), int(p[1]))):
            edge = edges.setdefault((a, b), {'id': a + ':' + b, 'source': a, 'target': b,
                                              'weights': {'affiliation': 0.0, 'project': 0.0},
                                              'event_ids': [], 'cooperation_event_ids': [], 'collaboration_event_ids': []})
            contribution = 1 / (event['n'] - 1)
            edge['weights']['affiliation'] += contribution
            if event['type'] == 'project':
                edge['weights']['project'] += contribution
            edge['event_ids'].append(key)
            (edge['cooperation_event_ids'] if event['cooperation'] else edge['collaboration_event_ids']).append(key)
    for edge in edges.values():
        edge['weights'] = {k: round(v, 10) for k, v in edge['weights'].items()}
    return list(edges.values()), retained_events, dict(excluded)
