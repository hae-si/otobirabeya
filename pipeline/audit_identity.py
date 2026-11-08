"""Audit identity evidence and merge provenance without inventing identities.

The user rule merges creators whose names are exactly equal and creators that share one
platform account structure. This audit recomputes both link sets from hash-verified
inputs, checks every redirect and account placement, verifies that no cross-name merge
lacks shared-account evidence, and confirms that ambiguous interaction accounts stay
unknown unless the merge rule resolves them.
"""
import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from pipeline.normalize.account_mapping import prepare
from pipeline.normalize.profile_scope import extract, mapping_candidates

ROOT = Path(__file__).resolve().parents[1]
POLICY = 'user-exact-display-name-shared-account-and-subtag-v4'
PLATFORMS = {'1': 'niconico', '2': 'youtube', '3': 'bilibili', '4': 'twitter', '5': 'bluesky', '6': 'soundcloud'}


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def mapping_sha256(rows):
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode()).hexdigest()


def recompute_mappings(dataset, social, identity_evidence, overrides):
    roots = sorted({(Path(r['directory']) if Path(r['directory']).is_absolute() else ROOT / r['directory']).resolve() for r in social.get('requests', [])})
    profiles = extract(roots, [account['id'] for account in social['accounts']])
    candidates = list(identity_evidence) + mapping_candidates(dataset, profiles)
    return prepare(dataset, social, candidates, overrides, roots)


def union_find(groups):
    parent = {}

    def find(value):
        while parent.setdefault(value, value) != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    for ids in groups:
        for other in ids[1:]:
            parent[find(other)] = find(ids[0])
    return find


def recompute_shared_accounts(dataset):
    owners = defaultdict(set)
    for row in dataset['accounts']:
        if row['content_id'] and row['tag_id'] in dataset['creators']:
            owners[row['site'], row['content_id']].add(row['tag_id'])
    recomputed = {(site, content): sorted(ids, key=int) for (site, content), ids in owners.items() if len(ids) > 1}
    declared = {(row['site'], row['content_id']): sorted(row['creator_ids'], key=int)
                for row in dataset.get('audit', {}).get('shared_account_conflicts', [])}
    if recomputed != declared:
        raise ValueError('Shared-account audit differs from recomputed account owners')
    return recomputed




def recompute_subtag_links(dataset):
    creators = set(dataset.get('creators') or {})
    by_parent = defaultdict(set)
    for relation in dataset.get('tag_relations') or []:
        parent = str(relation.get('canonical_parent_id') or relation.get('parent_id') or '')
        child = str(relation.get('canonical_tag_id') or relation.get('tag_id') or '')
        if parent in creators and child in creators and parent != child:
            by_parent[parent].add(child)
    links = []
    for parent in sorted(by_parent, key=int):
        children = sorted(by_parent[parent], key=int)
        if len(children) <= 3:
            links.append([parent, *children])
    return links


def verify_identity_groups(dataset, graph, shared):
    identity = graph.get('meta', {}).get('identity') or {}
    if identity.get('policy') != POLICY:
        raise ValueError('Unexpected identity merge policy')
    nodes = {node['id']: node for node in graph['nodes']}
    redirects = identity.get('redirects') or {}
    subtag = recompute_subtag_links(dataset)
    find = union_find([*shared.values(), *subtag])
    expected = {}
    groups = []
    for group in identity.get('groups') or []:
        canonical = group['canonical_id']
        node = nodes.get(canonical)
        if node is None:
            raise ValueError('Missing identity canonical node: ' + canonical)
        if not group['label']:
            raise ValueError('Identity group has empty label')
        members = node.get('identity_members') or []
        if {member['id'] for member in members} != set(group['source_node_ids']):
            raise ValueError('Identity members mismatch: ' + canonical)
        otodb_ids = [member['otodb_id'] for member in members if member.get('otodb_id')]
        expected_canonical = 'otodb:' + min(otodb_ids, key=int) if otodb_ids else min(group['source_node_ids'])
        if canonical != expected_canonical:
            raise ValueError('Identity canonical choice mismatch: ' + canonical)
        labels = [member['label'] for member in members]
        bases = list(group.get('bases') or [])
        if len(labels) != len(set(labels)) and 'user_exact_display_name' not in bases:
            raise ValueError('Exact-name merge lacks its stated basis: ' + canonical)
        if len(set(labels)) > 1:
            if 'shared_platform_account' not in bases and 'user_subtag_parent_3_or_fewer' not in bases:
                raise ValueError('Cross-name merge lacks shared-account or subtag basis: ' + canonical)
            if len({find(cid) for cid in otodb_ids}) != 1:
                raise ValueError('Cross-name merge lacks shared-account/subtag evidence: ' + canonical)
        for source in group['source_node_ids']:
            if source != canonical:
                if redirects.get(source) != canonical:
                    raise ValueError('Identity redirect mismatch: ' + source)
                expected[source] = canonical
        groups.append({'canonical_id': canonical, 'label': group['label'],
                       'source_node_ids': group['source_node_ids'], 'otodb_ids': otodb_ids,
                       'labels': labels, 'bases': bases,
                       'shared_accounts': group.get('shared_accounts') or []})
    if expected != redirects:
        raise ValueError('Identity redirects do not match groups')
    if any(source in nodes for source in redirects):
        raise ValueError('Merged identity still present as graph node')
    return groups


def verify_shared_merges(graph, shared, groups):
    nodes = {node['id']: node for node in graph['nodes']}
    redirects = (graph.get('meta', {}).get('identity') or {}).get('redirects') or {}

    def canonical(node_id):
        seen = set()
        while node_id in redirects:
            if node_id in seen:
                raise ValueError('Identity redirect cycle')
            seen.add(node_id)
            node_id = redirects[node_id]
        return node_id if node_id in nodes else None

    merged = []
    expected = set()
    for (site, content), ids in sorted(shared.items()):
        present = {canonical('otodb:' + cid) for cid in ids}
        present.discard(None)
        if len(present) > 1:
            raise ValueError('Shared platform account remained split: %s/%s' % (site, content))
        if len(present) == 1:
            expected.add((site, content))
            if sum(1 for cid in ids if canonical('otodb:' + cid) is not None) >= 2:
                merged.append({'site': site, 'content_id': content, 'creator_ids': ids,
                               'canonical_id': next(iter(present))})
    in_graph = {(site, content) for (site, content), ids in shared.items()
                if any(canonical('otodb:' + cid) is not None for cid in ids)}
    if expected != in_graph:
        raise ValueError('Shared account merge coverage mismatch')
    return merged


def verify_accounts(dataset, social, graph, mapping_rows, groups):
    nodes = {node['id']: node for node in graph['nodes']}
    redirects = (graph.get('meta', {}).get('identity') or {}).get('redirects') or {}
    creators = {cid: creator for cid, creator in dataset['creators'].items() if creator.get('deprecated') != 't'}
    accounts = {account['id']: account for account in social['accounts']}
    account_nodes = {}
    for node in graph['nodes']:
        for account in node.get('accounts') or []:
            if account['id'] in account_nodes:
                raise ValueError('Account mapped to more than one node: ' + account['id'])
            account_nodes[account['id']] = node['id']
    if set(account_nodes) != set(accounts):
        raise ValueError('Social account projection mismatch')

    def canonical(creator_id):
        node_id = redirects.get('otodb:' + creator_id, 'otodb:' + creator_id)
        return node_id

    by_name = defaultdict(list)
    for cid, creator in creators.items():
        by_name[creator['name']].append(cid)
    group_labels = {group['label']: group['canonical_id'] for group in groups}
    mapped = Counter()
    name_only = []
    outside = []
    conflicts = []
    for row in mapping_rows:
        account_id = row['account_id']
        username = accounts[account_id]['username']
        creator_id = row['creator_id']
        candidates = row.get('candidate_creator_ids') or []
        targets = set()
        if creator_id:
            if creator_id not in creators:
                raise ValueError('Mapped account resolves to inactive creator: ' + account_id)
            target = canonical(creator_id)
            if account_nodes[account_id] != target:
                raise ValueError('Mapped account placed on wrong node: ' + account_id)
            mapped['same_name' if creators[creator_id]['name'] == username else 'different_name'] += 1
            others = [cid for cid in by_name.get(username, []) if cid != creator_id and canonical(cid) != target]
            if others:
                conflicts.append({'account_id': account_id, 'username': username, 'mapped_creator_id': creator_id,
                                  'reason': 'account_display_name_matches_another_creator',
                                  'other_creator_ids': others})
            continue
        matches = [cid for cid in by_name.get(username, []) if canonical(cid) in nodes]
        targets = {canonical(cid) for cid in matches}
        if targets:
            if len(targets) > 1:
                raise ValueError('Same display name resolves to several identity nodes: ' + account_id)
            target = next(iter(targets))
            if account_nodes[account_id] != target:
                raise ValueError('Name-matched account placed on wrong node: ' + account_id)
            name_only.append({'account_id': account_id, 'username': username, 'canonical_id': target,
                              'basis': 'user_exact_display_name', 'creator_ids': matches})
        elif username in group_labels:
            if account_nodes[account_id] != group_labels[username]:
                raise ValueError('Name-matched account placed on wrong node: ' + account_id)
            name_only.append({'account_id': account_id, 'username': username,
                              'canonical_id': group_labels[username], 'basis': 'user_exact_display_name'})
        elif username in by_name:
            outside.append({'account_id': account_id, 'username': username,
                            'reason': 'matching_creator_absent_from_graph'})
        if len(candidates) > 1 and (targets or username in group_labels):
            raise ValueError('Ambiguous platform evidence silently merged by display name: ' + account_id)
    return {'states': dict(Counter(row['state'] for row in mapping_rows)), 'mapped': dict(mapped),
            'name_only_merges': name_only, 'name_matches_outside_graph': outside,
            'cross_platform_conflicts': conflicts}


def shared_accounts(dataset, graph):
    nodes = {node['id']: node for node in graph['nodes']}
    redirects = (graph.get('meta', {}).get('identity') or {}).get('redirects') or {}
    works = defaultdict(set)
    for row in dataset.get('participation', []):
        works[row['work_tag_id']].add(row['work_id'])
    recomputed = recompute_shared_accounts(dataset)

    def canonical(node_id):
        seen = set()
        while node_id in redirects:
            if node_id in seen:
                raise ValueError('Identity redirect cycle')
            seen.add(node_id)
            node_id = redirects[node_id]
        return node_id if node_id in nodes else None

    rows = []
    for (site, content), ids in sorted(recomputed.items()):
        shared_works = set.intersection(*(works[cid] for cid in ids)) if ids else set()
        endpoints = []
        for cid in ids:
            creator = dataset['creators'][cid]
            node_id = 'otodb:' + cid
            target = canonical(node_id)
            endpoints.append({'creator_id': cid, 'name': creator['name'], 'slug': creator['slug'],
                              'deprecated': creator.get('deprecated') == 't',
                              'alias_ids': [alias['id'] for alias in creator.get('aliases') or []],
                              'work_count': len(works[cid]), 'in_graph': target is not None,
                              'canonical_id': target})
        present = {endpoint['canonical_id'] for endpoint in endpoints if endpoint['in_graph']}
        present_endpoints = [endpoint for endpoint in endpoints if endpoint['in_graph']]
        if len(present) == 0:
            decision, reason = 'endpoints_absent_from_graph', 'neither_creator_is_in_the_graph'
        elif len(present) == 1 and len(present_endpoints) >= 2:
            decision, reason = 'merged_shared_platform_account', 'user_shared_platform_account_rule'
        elif len(present) == 1:
            decision, reason = 'single_endpoint_in_graph', 'only_one_creator_is_in_the_graph'
        else:
            raise ValueError('Shared platform account remained split: %s/%s' % (site, content))
        rows.append({'platform': PLATFORMS.get(site, 'unknown'), 'site': site, 'content_id': content,
                     'creator_ids': ids, 'creators': endpoints,
                     'shared_work_count': len(shared_works),
                     'both_creators_in_graph': all(endpoint['in_graph'] for endpoint in endpoints),
                     'decision': decision, 'decision_reason': reason})
    return rows


def verify_interaction(shared, verification):
    verification = verification or {}
    ambiguous = []
    for uid, row in sorted(verification.items()):
        canonical = row.get('canonical_creator_ids') or []
        if len(canonical) > 1:
            if row.get('mapping_state') != 'unknown' or row.get('state') == 'otodb_creator_evidence':
                raise ValueError('Ambiguous interaction identity treated as resolved: ' + uid)
            ambiguous.append(uid)
    checks = []
    for group in shared:
        if group['platform'] != 'bilibili':
            continue
        uid = group['content_id']
        row = verification.get(uid)
        if row is None:
            continue
        canonical = row.get('canonical_creator_ids') or []
        if set(row.get('creator_ids') or []) != set(group['creator_ids']):
            raise ValueError('Interaction account ownership differs from otoDB: ' + uid)
        if len(canonical) != 1:
            raise ValueError('Shared Bilibili account not merged in interaction review: ' + uid)
        checks.append({'uid': uid, 'creator_ids': group['creator_ids'], 'canonical_creator_ids': canonical,
                       'mapping_state': row.get('mapping_state'), 'identity_state': row.get('state'),
                       'decision': 'merged_shared_account'})
    return checks, ambiguous


def audit(dataset, social, graph, mapping_rows=None, overrides=(), identity_evidence=(), interaction_verification=None):
    shared = recompute_shared_accounts(dataset)
    subtag = recompute_subtag_links(dataset)
    groups = verify_identity_groups(dataset, graph, shared)
    if mapping_rows is None:
        mapping_rows = recompute_mappings(dataset, social, list(identity_evidence), list(overrides))
    account_report = verify_accounts(dataset, social, graph, mapping_rows, groups)
    shared_merges = verify_shared_merges(graph, shared, groups)
    shared_rows = shared_accounts(dataset, graph)
    interaction, ambiguous = verify_interaction(shared_rows, interaction_verification)
    computed = mapping_sha256(mapping_rows)
    recorded = (graph.get('meta') or {}).get('mapping_sha256')
    if recorded and recorded != computed:
        raise ValueError('Published account mapping hash does not match these inputs')
    exact_name = sum('user_exact_display_name' in group['bases'] for group in groups)
    shared_basis = sum('shared_platform_account' in group['bases'] for group in groups)
    summary = {
        'graph_nodes': len(graph['nodes']),
        'identity_policy': POLICY,
        'merge_groups': len(groups),
        'merge_groups_exact_name': exact_name,
        'merge_groups_shared_account': shared_basis,
        'merge_groups_subtag': sum('user_subtag_parent_3_or_fewer' in group['bases'] for group in groups),
        'subtag_candidate_groups': len(subtag),
        'identity_redirects': len((graph.get('meta', {}).get('identity') or {}).get('redirects') or {}),
        'account_mappings': len(mapping_rows),
        'mapping_states': account_report['states'],
        'mapped_accounts': sum(account_report['mapped'].values()),
        'mapped_same_name': account_report['mapped'].get('same_name', 0),
        'mapped_different_name': account_report['mapped'].get('different_name', 0),
        'name_only_exact_merges': len(account_report['name_only_merges']),
        'name_matches_outside_graph': len(account_report['name_matches_outside_graph']),
        'cross_platform_conflicts': len(account_report['cross_platform_conflicts']),
        'shared_account_groups': len(shared_rows),
        'shared_accounts_by_platform': dict(sorted(Counter(group['platform'] for group in shared_rows).items())),
        'shared_groups_merged': sum(group['decision'] == 'merged_shared_platform_account' for group in shared_rows),
        'shared_groups_both_creators_in_graph': sum(group['both_creators_in_graph'] for group in shared_rows),
        'shared_groups_absent_from_graph': sum(group['decision'] == 'endpoints_absent_from_graph' for group in shared_rows),
        'shared_groups_single_endpoint_in_graph': sum(group['decision'] == 'single_endpoint_in_graph' for group in shared_rows),
        'shared_merge_components': len({item['canonical_id'] for item in shared_merges}),
        'manual_overrides': len(overrides),
        'interaction_shared_accounts_checked': len(interaction),
        'interaction_shared_accounts_merged': sum(item['decision'] == 'merged_shared_account' for item in interaction),
        'interaction_ambiguous_accounts_kept_unknown': len(ambiguous),
        'mapping_sha256_matches_graph': bool(recorded) and recorded == computed,
        'checks': ['identity_policy', 'redirect_provenance', 'shared_account_merge', 'subtag_merge',
                   'account_placement', 'mapping_provenance', 'interaction_identity'],
    }
    return {'summary': summary,
            'identity_groups': groups,
            'account_mapping': account_report,
            'shared_accounts': shared_rows,
            'shared_merges': shared_merges,
            'interaction_identity': interaction,
            'interaction_ambiguous_accounts': ambiguous,
            'manual_overrides': [{'account_id': row['account_id'], 'decision': row['decision'],
                                  'creator_id': row.get('creator_id') or None,
                                  'reason': row['reason'], 'reviewed_at': row['reviewed_at'],
                                  'source_urls': row['source_urls']} for row in overrides],
            'state': 'identity evidence audit passed; exact-name, shared-platform-account and creator-subtag (<=3 children) merges verified; not a private-identity certification'}


def audit_files(dataset_path, social_path, graph_path, interaction_review=None):
    dataset, social, graph = load(dataset_path), load(social_path), load(graph_path)
    recorded = {row['sha256'] for row in (graph.get('meta') or {}).get('input_hashes') or []}
    if recorded:
        for path in (Path(dataset_path), Path(social_path)):
            if digest(path) not in recorded:
                raise ValueError('Published graph input hash mismatch: ' + str(path))
    identity_path = ROOT / 'data/normalized/otomadsite/round2-identity-evidence.json'
    identity_evidence = load(identity_path) if identity_path.is_file() else []
    overrides_path = ROOT / 'data/manual/account_mappings.csv'
    with overrides_path.open(encoding='utf-8-sig', newline='') as stream:
        overrides = list(csv.DictReader(stream))
    verification = None
    files = [dataset_path, social_path, graph_path, overrides_path]
    if interaction_review:
        verification = load(Path(interaction_review) / 'creator_verification.json')
        files.append(Path(interaction_review) / 'creator_verification.json')
    if identity_path.is_file():
        files.append(identity_path)
    result = audit(dataset, social, graph, overrides=overrides, identity_evidence=identity_evidence,
                   interaction_verification=verification)
    result['inputs'] = [{'file': str(path), 'sha256': digest(path)} for path in files]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dataset', type=Path)
    parser.add_argument('social', type=Path)
    parser.add_argument('graph', type=Path)
    parser.add_argument('--interaction-review', type=Path,
                        help='Reviewed Bilibili interaction directory; checks shared UIDs resolve by the merge rule')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit_files(args.dataset, args.social, args.graph, args.interaction_review)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result['summary'], ensure_ascii=False))


if __name__ == '__main__':
    main()
