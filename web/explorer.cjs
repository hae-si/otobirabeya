const {scopeGraph}=require('./unified-scope.cjs');
const DEFAULT_FILTERS={scope:'core',creation:true,follow:true,content:true,source:true,song:true,interaction:true,minimumStrength:.8,creationWeight:0,eventCount:0,creationKind:'all',mutual:false,category:'all',similarity:0,sharedTags:0,distinctWorks:0,weak:false,groupMode:'community',groups:[],edgeMode:'all',neighbors:false,depth:1,selected:null,density:2,percentile:0};
const channel=e=>e.type==='content'?'content:'+e.category:e.type;
const displayValue=e=>e.type==='creation'?(e.analysis_weight??e.weight):(e.similarity??e.weight);
function displayStrengths(edges){
 const buckets=new Map(),result=new Map();
 for(const e of edges){if(!['creation','content','interaction','follow'].includes(e.type))continue;const key=channel(e);if(!buckets.has(key))buckets.set(key,[]);buckets.get(key).push(e);}
 for(const es of buckets.values()){es.sort((a,b)=>displayValue(a)-displayValue(b));for(let i=0;i<es.length;){let j=i+1;while(j<es.length&&displayValue(es[j])===displayValue(es[i]))j++;for(let k=i;k<j;k++)result.set(es[k].id,j/es.length);i=j;}}
 return result;
}
function groupKey(n,mode='community'){
 const value=n[mode];return value!=null?String(value):n.community_status==='small_sample'?'__small':'__unassigned';
}
function sameGroup(a,b,mode){return a[mode]!=null&&b[mode]!=null&&String(a[mode])===String(b[mode]);}
function filterView(nodes,edges,options={}){
 const c={...DEFAULT_FILTERS,...options};
 const scopedEdges=c.scope==='all'?edges:edges.filter(e=>e.type!=='interaction'||e.analysis_enabled!==false).map(e=>e.type==='interaction'&&e.analysis_weight!=null?{...e,weight:e.analysis_weight,distinct_video_count:e.analysis_video_count,video_ids:e.analysis_video_ids,event_ids:e.analysis_event_ids}:e);
 const strength=displayStrengths(scopedEdges);
 let view=scopeGraph(nodes,scopedEdges.filter(e=>e.type==='creation'||e.type==='follow'),c.scope);
 const scopeIds=new Set(view.nodes.map(n=>n.id)),chineseIds=new Set(nodes.filter(n=>n.language_class==='inferred_chinese').map(n=>n.id));
 view.edges=scopedEdges.filter(e=>scopeIds.has(e.source)&&scopeIds.has(e.target)&&(nodes.some(n=>n.language_class)||c.scope!=='related'||e.type==='interaction'||chineseIds.has(e.source)||chineseIds.has(e.target)));
 if(c.groups.length)view.nodes=view.nodes.filter(n=>c.groups.includes(groupKey(n,c.groupMode)));
 const byId=new Map(view.nodes.map(n=>[n.id,n]));
 view.edges=view.edges.filter(e=>{
   if(!byId.has(e.source)||!byId.has(e.target))return false;
   if(strength.get(e.id)<c.minimumStrength)return false;
   const equal=sameGroup(byId.get(e.source),byId.get(e.target),c.groupMode);
   if(c.edgeMode==='within'&&!equal||c.edgeMode==='between'&&(equal||byId.get(e.source)[c.groupMode]==null||byId.get(e.target)[c.groupMode]==null))return false;
   if(e.type==='creation')return c.creation&&e.weight>=c.creationWeight&&(e.event_ids?.length||0)>=c.eventCount&&(c.creationKind==='all'||(c.creationKind==='cooperation'?(e.cooperation_event_ids?.length||0)>0:(e.collaboration_event_ids?.length||0)>0));
   if(e.type==='follow')return c.follow&&(!c.mutual||e.mutual);
   if(e.type==='interaction')return c.interaction;
   if(e.type==='content')return c.content&&(e.category==='2'?c.song:c.source)&&(c.category==='all'||e.category===c.category)&&e.similarity>=c.similarity&&e.shared_tag_count>=c.sharedTags&&e.distinct_work_tag_support>=c.distinctWorks&&(c.weak||!e.confidence_flags?.length);
   return false;
 });
 if(c.percentile>0)view.edges=view.edges.filter(e=>e.type==='follow'||(strength.get(e.id)??0)>=c.percentile/100);
 if(c.neighbors&&c.selected){const ids=new Set([c.selected]);for(let i=0;i<c.depth;i++){const next=new Set(ids);for(const e of view.edges)if(ids.has(e.source)||ids.has(e.target)){next.add(e.source);next.add(e.target);}for(const id of next)ids.add(id);}view.nodes=view.nodes.filter(n=>ids.has(n.id));view.edges=view.edges.filter(e=>ids.has(e.source)&&ids.has(e.target));}
 const qualifying={nodes:view.nodes,edges:view.edges};let drawn=view.edges;
 if(c.density>0){const buckets=new Map(),keep=new Set();for(const e of drawn)for(const id of [e.source,e.target]){const key=JSON.stringify([id,channel(e)]);if(!buckets.has(key))buckets.set(key,[]);buckets.get(key).push(e);}for(const list of buckets.values())list.sort((a,b)=>displayValue(b)-displayValue(a)||a.id.localeCompare(b.id)).slice(0,c.density).forEach(e=>keep.add(e.id));drawn=drawn.filter(e=>keep.has(e.id));}
 return {nodes:view.nodes,edges:drawn,qualifying,filters:c,strengths:strength};
}
function statistics(nodes,edges,{groupMode='community',events={}}={}){
 const metrics=new Map(nodes.map(n=>[n.id,{id:n.id,label:n.label,language:n.language_class||null,group:groupKey(n,groupMode),pagerank:n.pagerank??null,interaction_pagerank:n.interaction_pagerank??null,creation_neighbors:new Set(),creation_strength:0,follow_in:0,follow_out:0,interaction_in:0,interaction_out:0,reciprocal_out:0,song_neighbors:new Set(),source_neighbors:new Set(),works:new Set()}]));
 const groups=new Map(),layers={creation:0,follow:0,song:0,source:0,interaction:0},matrix={creation:new Map(),follow:new Map(),song:new Map(),source:new Map(),interaction:new Map()},pairs=new Set(),active=new Set();
 const byId=new Map(nodes.map(n=>[n.id,n]));let duplicateAccountDirections=0;
 for(const e of edges){if(!['creation','follow','content','interaction'].includes(e.type)||!metrics.has(e.source)||!metrics.has(e.target))continue;
   const a=metrics.get(e.source),b=metrics.get(e.target),kind=e.type==='content'?(e.category==='2'?'song':'source'):e.type;
   if(e.type==='follow'){const key=JSON.stringify([e.source,e.target]);if(pairs.has(key)){duplicateAccountDirections++;continue;}pairs.add(key);a.follow_out++;b.follow_in++;}
   else if(e.type==='creation'){a.creation_neighbors.add(e.target);b.creation_neighbors.add(e.source);a.creation_strength+=e.weight;b.creation_strength+=e.weight;for(const id of e.event_ids||[]){const event=events[id];for(const [m,aid] of [[a,e.source],[b,e.target]])for(const wid of event?.participants?.[aid.replace('otodb:','')]||[])m.works.add(wid);}}
   else if(e.type==='interaction'){a.interaction_out++;b.interaction_in++;}
   else if(e.type==='content'){a[kind+'_neighbors'].add(e.target);b[kind+'_neighbors'].add(e.source);}
   layers[kind]++;active.add(e.source);active.add(e.target);
   const ga=byId.get(e.source)[groupMode],gb=byId.get(e.target)[groupMode];
   if(ga!=null&&gb!=null){let s=String(ga),t=String(gb);if(!['follow','interaction'].includes(e.type)&&s.localeCompare(t)>0)[s,t]=[t,s];const key=JSON.stringify([s,t]);matrix[kind].set(key,(matrix[kind].get(key)||0)+1);}
 }
 for(const key of pairs){const [s,t]=JSON.parse(key);if(pairs.has(JSON.stringify([t,s])))metrics.get(s).reciprocal_out++;}
 for(const n of nodes){const key=groupKey(n,groupMode);if(!groups.has(key))groups.set(key,{id:key,total:0,chinese:0});const g=groups.get(key);g.total++;g.chinese+=n.language_class==='inferred_chinese';}
 const rows=[...metrics.values()].map(m=>({...m,creation_neighbors:m.creation_neighbors.size,song_neighbors:m.song_neighbors.size,source_neighbors:m.source_neighbors.size,evidence_works:m.works.size,works:undefined,observed_reciprocity:m.follow_out?m.reciprocal_out/m.follow_out:null}));
 return {nodeCount:nodes.length,chineseNodes:nodes.filter(n=>n.language_class==='inferred_chinese').length,nonChineseNodes:nodes.filter(n=>n.language_class==='inferred_non_chinese').length,bilibiliNodes:nodes.filter(n=>n.language_basis==='bilibili_account').length,independent:nodes.filter(n=>!n.otodb_id).length,smallSample:nodes.filter(n=>['small_sample','assigned_small'].includes(n.community_status)).length,unassigned:nodes.filter(n=>n.community==null).length,withoutVisibleEdges:nodes.length-active.size,layers,duplicateAccountDirections,groups:[...groups.values()].sort((a,b)=>b.total-a.total||a.id.localeCompare(b.id)),rows,matrix:Object.fromEntries(Object.entries(matrix).map(([kind,m])=>[kind,[...m].map(([key,count])=>({pair:JSON.parse(key),count}))]))};
}
function csvTable(rows,columns){const escape=v=>{if(typeof v==='string'&&/^[=+@\-\t\r]/.test(v))v="'"+v;return '"'+String(v??'').replace(/"/g,'""')+'"';};return '\uFEFF'+[columns.map(escape).join(','),...rows.map(r=>columns.map(k=>escape(r[k])).join(','))].join('\r\n');}
module.exports={DEFAULT_FILTERS,filterView,statistics,groupKey,csvTable,displayStrengths};
