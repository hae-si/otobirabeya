function selectInteractions(data,{video='',type='',query='',scope='confirmed',nodeIds=null,eventIds=null}={}){
 if(!['confirmed','related','all'].includes(scope))throw Error('Unknown interaction scope');
 const q=query.trim().toLowerCase(),accounts=data.accounts;
 const allowed=a=>(!nodeIds||nodeIds.has(a.node_id||a.creator_id))&&(!a.identity_state||a.identity_state==='confirmed'||scope==='all'||scope==='related'&&['core','related'].includes(a.scope));
 const events=(scope==='confirmed'?data.events:data.observed_events||data.events).filter(e=>(!eventIds||eventIds.has(e.event_id))&&allowed(accounts[e.source_uid])&&allowed(accounts[e.target_uid])&&(!video||e.video_id===video)&&(!type||e.event_type===type)&&(!q||[accounts[e.source_uid].label,accounts[e.target_uid].label,e.source_uid,e.target_uid,e.excerpt??''].some(s=>s.toLowerCase().includes(q))));
 const users=Object.values(accounts).filter(a=>allowed(a)&&(!video||(a.appearance_video_ids?.includes(video)||a.selected_publications?.some(v=>v.aid===video)))&&(!q||(a.label+' '+a.uid).toLowerCase().includes(q)));
 return {events,users,count:events.length,confirmedCount:events.filter(e=>e.identity_state!=='unknown').length,pendingCount:events.filter(e=>e.identity_state==='unknown').length,comments:new Set(events.filter(e=>e.rpid).map(e=>JSON.stringify([e.video_id,e.rpid]))).size,videos:new Set(events.map(e=>e.video_id)).size,
  sources:new Set(events.map(e=>accounts[e.source_uid].creator_id)).size,targets:new Set(events.map(e=>accounts[e.target_uid].creator_id)).size};
}
module.exports={selectInteractions};
