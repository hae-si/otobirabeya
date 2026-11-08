const VERSION='author-follow-binary-v1';
function aggregateAuthorFollows(edges){
  const directions=new Map(),self=[];
  for(const e of edges){
    if(e.type!=='follow')continue;
    if(e.source===e.target){self.push(e);continue;}
    const key=JSON.stringify([e.source,e.target]);
    if(!directions.has(key))directions.set(key,{id:'author-follow:'+key,type:'follow',source:e.source,target:e.target,weight:1,account_edge_ids:[]});
    const r=directions.get(key);if(!r.account_edge_ids.includes(e.id))r.account_edge_ids.push(e.id);
  }
  const result=[...directions.entries()].sort(([a],[b])=>a.localeCompare(b)).map(([,e])=>({...e,account_edge_ids:e.account_edge_ids.sort(),mutual:directions.has(JSON.stringify([e.target,e.source]))}));
  return {version:VERSION,edges:result,self_account_evidence:self};
}
function observationState(sourceAccounts,targetAccounts,coverage,observed=false){
  if(observed)return 'observed';
  if(!sourceAccounts.length||!targetAccounts.length)return 'unknown';
  const complete=(id,direction)=>coverage.some(r=>r.user_id===id&&r.endpoint===direction&&r.state==='visible_list_exhausted');
  return sourceAccounts.every(a=>targetAccounts.every(b=>complete(a,'following')||complete(b,'followers')))?'known_no_observation':'unknown';
}
module.exports={VERSION,aggregateAuthorFollows,observationState};
