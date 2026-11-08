"""Project public interaction events to a separate directed, video-supported layer."""
import hashlib
import math


def integrate(graph,interactions):
    nodes={n['id']:n for n in graph['nodes']};original_nodes=set(nodes);accounts=interactions['accounts'];events=interactions.get('observed_events',interactions['events'])
    redirects=graph.get('meta',{}).get('identity',{}).get('redirects',{})
    event_uids={e['source_uid'] for e in events}|{e['target_uid'] for e in events}
    endpoints={}
    for uid,account in accounts.items():
        canonical=redirects.get(account['creator_id'],account['creator_id'])
        if canonical not in nodes and uid not in event_uids:
            account['node_id']=None;account['graph_excluded_reason']='no_interaction_events'
            continue
        if canonical not in nodes and account['identity_state']!='confirmed' and account['scope']=='all':
            account['node_id']=None;account['graph_excluded_reason']='fewer_than_two_observed_comments'
            continue
        endpoints[uid]=canonical
        if canonical not in nodes:
            known=account['identity_state']=='confirmed'
            node={'id':canonical,'label':account['label'],'type':'creator' if known or canonical.startswith('otodb:') else 'account','chinese_scope':False,'has_bilibili_account':True,
                  'scope':'相关作者' if known or account['scope']=='related' else '最外围作者（资格待判定）',
                  'interaction_scope':'related' if known or account['scope']=='related' else 'all',
                  'identity_state':account['identity_state'],'bilibili_uids':[],'accounts':[],
                  'appearance_video_ids':list(account['appearance_video_ids']),'community':None,'pagerank':None,'x':0,'y':0}
            if canonical.startswith('otodb:'):node['otodb_id']=canonical.removeprefix('otodb:')
            graph['nodes'].append(node);nodes[canonical]=node
        node=nodes[canonical];uids=node.setdefault('bilibili_uids',[]);node['has_bilibili_account']=True
        if account.get('selected_work_publisher'):
            node['chinese_scope']=True;node['has_bilibili_account']=True;node['scope']='榜单作品发布作者'
            node.setdefault('core_evidence',[]).append({'basis':'selected_work_publication_user_policy','uid':uid,'publications':account['selected_publications']})
        if uid not in uids:uids.append(uid)
        if not node.get('chinese_scope') and (account['identity_state']=='confirmed' or account['scope']=='related'):
            node['interaction_scope']='related'
        node['appearance_video_ids']=sorted(set(node.get('appearance_video_ids',[]))|set(account['appearance_video_ids']))
        account['node_id']=canonical
    pairs={};excluded_self=[]
    for e in events:
        if e['source_uid'] not in endpoints or e['target_uid'] not in endpoints:continue
        source=endpoints[e['source_uid']];target=endpoints[e['target_uid']]
        if source==target:excluded_self.append(e['event_id']);continue
        key=(source,target)
        pair=pairs.setdefault(key,{'videos':set(),'event_ids':set(),'units':set(),'pending':set(),'confirmed':set(),'analysis_videos':set(),'analysis_events':set()})
        pair['videos'].add(e['video_id']);pair['event_ids'].add(e['event_id'])
        pair['units'].add((e['video_id'],e['rpid'] or 'description'))
        pair['pending' if e.get('identity_state')=='unknown' else 'confirmed'].add(e['event_id'])
        if all(accounts[uid]['identity_state']=='confirmed' or accounts[uid]['scope'] in {'core','related','peripheral'} for uid in [e['source_uid'],e['target_uid']]):
            pair['analysis_videos'].add(e['video_id']);pair['analysis_events'].add(e['event_id'])
    edges=[]
    for (source,target),p in sorted(pairs.items()):
        eligible=bool(p['analysis_videos'])
        edges.append({'id':'interaction:'+hashlib.sha256((source+'\0'+target).encode()).hexdigest()[:24],
                      'source':source,'target':target,'type':'interaction','directed':True,
                      'weight':len(p['videos']),'distinct_video_count':len(p['videos']),
                      'analysis_weight':len(p['analysis_videos']),'analysis_video_count':len(p['analysis_videos']),
                      'analysis_video_ids':sorted(p['analysis_videos']),'analysis_event_ids':sorted(p['analysis_events']),
                      'video_ids':sorted(p['videos']),'event_ids':sorted(p['event_ids']),
                      'observation_unit_count':len(p['units']),'confirmed_event_count':len(p['confirmed']),
                      'pending_event_count':len(p['pending']),'analysis_enabled':eligible})
    graph['interaction_edges']=edges
    incident={e['source'] for e in edges}|{e['target'] for e in edges}
    removed={cid for cid,node in list(nodes.items()) if cid not in original_nodes and cid not in incident and len(node.get('appearance_video_ids') or [])<=1}
    if removed:
        graph['nodes']=[n for n in graph['nodes'] if n['id'] not in removed]
        for cid in removed:nodes.pop(cid,None)
        for account in accounts.values():
            if account.get('node_id') in removed:account['node_id']=None;account['graph_excluded_reason']='no_projected_interaction_edge'
    interactions['meta'].update(integrated=True,graph_changed=True)
    interactions['meta']['graph_excluded_accounts']=sum(a.get('node_id') is None for a in accounts.values())
    interactions['meta']['graph_excluded_no_event_accounts']=sum(a.get('graph_excluded_reason')=='no_interaction_events' for a in accounts.values())
    interactions['meta']['graph_excluded_weak_isolated_nodes']=sum(a.get('graph_excluded_reason')=='no_projected_interaction_edge' for a in accounts.values())
    interactions['meta']['graph_policy']='selected_publishers_core_comment_count_peripheral_v4_no_isolated_events'
    graph['meta']['interaction']={**interactions['meta'],'integrated':True,'edge_count':len(edges),
                                 'analysis_edge_count':sum(e['analysis_enabled'] for e in edges),
                                 'excluded_identity_self_events':excluded_self,
                                 'weight_formula':'number of distinct supporting videos per directed identity pair',
                                 'analysis_eligibility':'production-supported, selected-work publisher or at least two observed comments; pending peripheral status retained'}
    return edges
