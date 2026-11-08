"""Verify the produced fourth layer against event evidence, not its own counters."""
import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path


def audit(graph_path,interaction_path,require_complete=True):
    graph=json.loads(graph_path.read_bytes());data=json.loads(interaction_path.read_bytes())
    source_audit=data['meta'].get('collection_audit',{})
    if require_complete and (not data['meta'].get('catalog_complete') or not source_audit.get('passed') or source_audit.get('scope')!='full_finite_catalog'):
        raise ValueError('Full catalog audit required')
    if require_complete and not data['meta'].get('event_audit',{}).get('passed'):
        raise ValueError('Independent raw event audit required')
    nodes={n['id']:n for n in graph['nodes']};accounts=data['accounts']
    if require_complete and data['meta'].get('graph_policy')=='selected_publishers_core_comment_count_peripheral_v4_no_isolated_events':
        counts_hash=hashlib.sha256(json.dumps({uid:a.get('observed_comment_count',0) for uid,a in accounts.items()},sort_keys=True).encode()).hexdigest()
        if counts_hash!=data['meta']['event_audit'].get('observed_comment_counts_sha256'):raise ValueError('Observed comment counts differ from raw event audit')
        for a in accounts.values():
            if a['identity_state']=='unknown' and not a.get('selected_work_publisher') and a['scope']!=('peripheral' if a.get('observed_comment_count',0)>=2 else 'all'):raise ValueError('Peripheral author threshold mismatch')
    if len(nodes)!=len(graph['nodes']):raise ValueError('Duplicate node IDs')
    redirects=graph['meta'].get('identity',{}).get('redirects',{})
    selected_publishers={v['publisher_uid'] for v in data.get('videos',[]) if any(s.get('family') in {'viewer_pick','author_pick'} for s in v.get('source_entries',[]))}
    def canonical(value):
        seen=set()
        while value in redirects:
            if value in seen:raise ValueError('Identity redirect cycle')
            seen.add(value);value=redirects[value]
        return value
    for uid,a in accounts.items():
        cid=canonical(a['creator_id'])
        if data['meta'].get('graph_policy') in {'selected_publishers_core_exclude_singleton_commenters_v2','selected_publishers_core_comment_count_peripheral_v4_no_isolated_events'}:
            if bool(a.get('selected_work_publisher'))!=(uid in selected_publishers):raise ValueError('Selected publisher classification mismatch')
            if uid in selected_publishers and a.get('node_id') is not None and (a['scope']!='core' or not nodes.get(cid,{}).get('has_bilibili_account')):raise ValueError('Selected publisher missing Bilibili account status')
        if a.get('node_id') is None:
            if cid in nodes:raise ValueError('Incorrectly excluded interaction account')
            if a.get('graph_excluded_reason') not in {'no_interaction_events','fewer_than_two_observed_comments','no_projected_interaction_edge'}:raise ValueError('Incorrectly excluded interaction account')
            if a.get('graph_excluded_reason')=='fewer_than_two_observed_comments' and (a['identity_state']=='confirmed' or a['scope']!='all'):raise ValueError('Incorrectly excluded interaction account')
            continue
        if cid not in nodes or a.get('node_id')!=cid:raise ValueError('Interaction account missing or misdirected')
        if uid not in nodes[cid].get('bilibili_uids',[]):raise ValueError('Missing UID lineage')
    pairs={};event_ids=set();confirmed=[];self_events=[]
    for event in data['observed_events']:
        if event['event_id'] in event_ids:raise ValueError('Duplicate event ID')
        event_ids.add(event['event_id'])
        s=canonical(accounts[event['source_uid']]['creator_id']);t=canonical(accounts[event['target_uid']]['creator_id'])
        if s not in nodes or t not in nodes:continue
        if s==t:self_events.append(event['event_id']);continue
        pair=pairs.setdefault((s,t),{'videos':set(),'events':set(),'units':set(),'eligible_videos':set(),'eligible_events':set()})
        pair['videos'].add(event['video_id']);pair['events'].add(event['event_id']);pair['units'].add((event['video_id'],event['rpid'] or 'description'))
        actors=[accounts[event[k]] for k in ['source_uid','target_uid']]
        if all(a['identity_state']=='confirmed' for a in actors):confirmed.append(event)
        if all(a['identity_state']=='confirmed' or a['scope'] in {'core','related','peripheral'} for a in actors):
            pair['eligible_videos'].add(event['video_id']);pair['eligible_events'].add(event['event_id'])
    if {e['event_id'] for e in confirmed}!={e['event_id'] for e in data['events']}:raise ValueError('Confirmed event set differs from identity evidence')
    edges=graph.get('interaction_edges',[])
    if len(edges)!=len(pairs) or len({(e['source'],e['target']) for e in edges})!=len(edges):raise ValueError('Interaction pair set or uniqueness mismatch')
    connected=set()
    for edge in edges:
        pair=pairs.get((edge['source'],edge['target']))
        if pair is None:raise ValueError('Unexpected projected interaction')
        checks=[(set(edge['video_ids']),pair['videos']),(set(edge['event_ids']),pair['events']),
                (set(edge['analysis_video_ids']),pair['eligible_videos']),(set(edge['analysis_event_ids']),pair['eligible_events'])]
        if any(actual!=expected for actual,expected in checks):raise ValueError('Projected support provenance mismatch')
        if edge['distinct_video_count']!=len(pair['videos']) or edge['analysis_video_count']!=len(pair['eligible_videos']):raise ValueError('Projected video support count mismatch')
        if not math.isclose(edge['weight'],len(pair['videos']),abs_tol=1e-12) or not math.isclose(edge['analysis_weight'],len(pair['eligible_videos']),abs_tol=1e-12):
            raise ValueError('Projected video weight mismatch')
        if edge['observation_unit_count']!=len(pair['units']) or edge['analysis_enabled']!=bool(pair['eligible_videos']):raise ValueError('Observation unit or analysis eligibility mismatch')
        if edge['analysis_enabled']:connected.update([edge['source'],edge['target']])
    algorithm=graph['meta'].get('algorithm',{})
    if algorithm.get('interaction_input_sha256')!=hashlib.sha256(interaction_path.read_bytes()).hexdigest():raise ValueError('Production algorithm used different interaction input')
    contribution=next((c for c in algorithm.get('score',{}).get('contributions',[]) if c['name']=='interaction'),None)
    if connected and (not contribution or contribution['effectiveShare']<=0):raise ValueError('Fourth layer absent from production community objective')
    layout=graph['meta'].get('layout',{})
    channel=next((l for l in layout.get('layerMasses',[]) if l['name']=='interaction'),None)
    if connected and (not channel or channel['mass']<=0 or channel['share']<=0 or not math.isfinite(layout.get('interactionSpringCap',math.nan))):
        raise ValueError('Fourth layer absent from bounded production layout')
    unassigned=[cid for cid in connected if nodes[cid].get('community') is None]
    if any(nodes[cid].get('community_status')!='small_sample' for cid in unassigned):raise ValueError('Interaction-connected account missing community without small-group evidence')
    if any(not isinstance(n.get(k),(int,float)) or not math.isfinite(n[k]) for n in nodes.values() for k in ['x','y']):raise ValueError('Invalid layout coordinates')
    social={n['id']:n for n in nodes.values() if n.get('accounts')}
    directed={(e['source'],e['target']) for e in graph['edges'] if e['type']=='follow'}
    if any(e['type'] not in {'creation','follow'} for e in graph['edges']):raise ValueError('Interaction facts mixed into original social edge array')
    rank_error=0
    if social:
        outgoing={cid:[] for cid in social}
        for s,t in directed:
            if s not in social or t not in social:raise ValueError('Follow endpoint without social account')
            outgoing[s].append(t)
        scores={cid:1/len(social) for cid in social}
        for _ in range(1000):
            dangling=sum(scores[cid] for cid in social if not outgoing[cid]);next_scores={cid:(.15+.85*dangling)/len(social) for cid in social}
            for s,targets in outgoing.items():
                for t in targets:next_scores[t]+=.85*scores[s]/len(targets)
            error=sum(abs(next_scores[cid]-scores[cid]) for cid in social);scores=next_scores
            if error<1e-12:break
        else:raise ValueError('Independent PageRank did not converge')
        rank_error=max(abs(scores[cid]-(social[cid].get('pagerank') or 0)) for cid in social)
        if rank_error>1e-10:raise ValueError('Stored PageRank differs from follow-only calculation')
    return {'passed':True,'scope':'full_finite_catalog' if require_complete else 'partial_preflight_not_completion','graph_sha256':hashlib.sha256(graph_path.read_bytes()).hexdigest(),
            'interaction_sha256':hashlib.sha256(interaction_path.read_bytes()).hexdigest(),
            'directed_interaction_pairs':len(edges),'eligible_pairs':sum(e['analysis_enabled'] for e in edges),
            'confirmed_events':len(confirmed),'self_events_after_projection':len(self_events),
            'interaction_connected_nodes':len(connected),'connected_unassigned':len(unassigned),
            'follow_only_pagerank_max_error':rank_error,'layout_coordinates_finite':True,
            'interaction_effective_share':contribution['effectiveShare'] if contribution else 0}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['graph','interactions','output']:p.add_argument(name,type=Path)
    p.add_argument('--allow-incomplete',action='store_true')
    a=p.parse_args();result=audit(a.graph,a.interactions,not a.allow_incomplete)
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
