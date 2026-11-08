function mergeProjection(author,redirects,normalized={}){
 const resolve=id=>redirects.get('otodb:'+id)||'otodb:'+id,events={},buckets=new Map(),self=[];
 for(const [id,e] of Object.entries(author.events||{})){
  const participants={},roles={};for(const [aid,works] of Object.entries(e.participants||{})){const cid=resolve(aid).replace('otodb:','');participants[cid]=[...new Set([...(participants[cid]||[]),...works])];roles[cid]=(roles[cid]||0)|((e.roles||{})[aid]||0);}
  const changed=Object.keys(participants).length!==Object.keys(e.participants||{}).length||Object.keys(e.participants||{}).some(a=>resolve(a)!=='otodb:'+a);
  events[id]=changed?{...e,source_participants:e.participants,source_n:e.n,source_roles:e.roles||{},participants,roles,n:Object.keys(participants).length}:e;
 }
 for(const e of author.edges){let s=resolve(e.source),t=resolve(e.target);if(s===t){self.push(e);continue;}if(s.localeCompare(t,'en',{numeric:true})>0)[s,t]=[t,s];const key=s+'|'+t;if(!buckets.has(key))buckets.set(key,[]);buckets.get(key).push(e);}
 const edges=[];
 for(const [key,rows] of buckets){const [s,t]=key.split('|'),ids=[...new Set(rows.flatMap(e=>e.event_ids||[]))];
  const changed=rows.length>1||rows.some(e=>resolve(e.source)!=='otodb:'+e.source||resolve(e.target)!=='otodb:'+e.target)||ids.some(id=>events[id]?.source_n!=null);
  let weights={affiliation:rows[0].weights?.affiliation||0,project:rows[0].weights?.project||0};
  if(changed){if(!ids.length)throw Error('Merged creator projection requires event evidence');weights={affiliation:0,project:0};for(const id of ids){const e=events[id];if(!e||e.n<2)throw Error('Missing identity-adjusted event');weights.affiliation+=1/(e.n-1);if(e.type==='project')weights.project+=1/(e.n-1);}
   for(const k of Object.keys(weights))weights[k]=Number(weights[k].toFixed(10));
  }
  const cooperation=rows.flatMap(e=>e.cooperation_event_ids||[]),collaboration=rows.flatMap(e=>e.collaboration_event_ids||[]);
  const e={id:'creation:'+s.replace('otodb:','')+':'+t.replace('otodb:',''),source:s,target:t,type:'creation',weight:weights.affiliation,event_ids:ids,cooperation_event_ids:[...new Set(cooperation)],collaboration_event_ids:[...new Set(collaboration)],relation_weights:weights};
  if(changed)e.source_projection=rows;if(e.weight>0)edges.push(e);
 }
 return {edges,events,self};
}
module.exports={mergeProjection};
