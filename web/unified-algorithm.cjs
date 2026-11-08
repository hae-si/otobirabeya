const {makeGraph,makeDirectedWeightedGraph,partition}=require('./network-analysis.cjs');
const {aggregateAuthorFollows}=require('./author-follow.cjs');
const {partitionLayers}=require('./multilayer-partition.cjs');
const {scoreLayers}=require('./layer-objective.cjs');
const {attachFragments}=require('./community-support.cjs');
const VERSION='unified-five-layer-v7';
const LEGACY_THREE_LAYER={creationShare:.35,followShare:.30,songShare:.05,sourceShare:.30,interactionShare:0};
const DEFAULT={creationShare:.20,followShare:.25,songShare:.25,sourceShare:.05,interactionShare:.25,additionalShare:.05,seed:42,resolution:1,refineChineseThreshold:160,refineTotalThreshold:350,localResolution:.75,refinementResolutions:[.75,1,1.25,1.5],maxRefinementDepth:4,minCommunitySize:8,fragmentMergeSize:16};
function eligibleContent(edges){return edges.filter(e=>e.shared_tag_count>=2&&e.distinct_work_tag_support>0);}
function normalAdditional(edges){
 const pairs=new Map();for(const e of edges){if(e.analysis_enabled===false||e.excluded_self||e.source===e.target)continue;if(!Number.isFinite(e.weight)||e.weight<=0)throw Error('Invalid annotation weight');
  const key=JSON.stringify([e.source,e.target].sort()),old=pairs.get(key),edge={...e,weight:Math.min(1,e.weight)};if(!old||edge.weight>old.weight)pairs.set(key,edge);
 }return [...pairs.values()];
}
function makeLayers(nodes,socialEdges,contentEdges,parameters,additionalEdges=[],interactionEdges=[]){
 const eligible=eligibleContent(contentEdges);
 const empirical=[{name:'collaboration',graph:makeGraph(nodes,socialEdges.filter(e=>e.type==='creation').map(e=>({...e,weight:e.analysis_weight??e.weight}))),share:parameters.creationShare},
   {name:'following',graph:makeGraph(nodes,aggregateAuthorFollows(socialEdges).edges),share:parameters.followShare},
   ...['2','3'].map((category,i)=>({name:i?'source':'song',share:i?parameters.sourceShare:parameters.songShare,
     graph:makeGraph(nodes,eligible.filter(e=>e.category===category).map(e=>({...e,type:'creation',weight:e.similarity})))})),
   {name:'interaction',graph:makeDirectedWeightedGraph(nodes,interactionEdges.filter(e=>e.analysis_enabled!==false).map(e=>({...e,weight:e.analysis_weight??e.weight}))),share:parameters.interactionShare??0}]
   .map(l=>({...l,resolution:parameters.resolution}));
 const annotations=normalAdditional(additionalEdges),mass=annotations.reduce((s,e)=>s+e.weight,0),reference=empirical.filter(l=>l.share>0).reduce((s,l)=>s+l.graph.size/(['following','interaction'].includes(l.name)?1:2),0),cap=parameters.additionalShare??DEFAULT.additionalShare;
 if(!Number.isFinite(cap)||cap<0||cap>=1)throw Error('Invalid annotation budget cap');
 const fraction=mass?Math.min(cap,mass/(reference+mass)):0,active=empirical.filter(l=>l.graph.size).reduce((s,l)=>s+l.share,0),share=active?active*fraction/(1-fraction):(cap?1:0);
 return empirical.concat(annotations.length?[{name:'additional',share,resolution:parameters.resolution,graph:makeGraph(nodes,annotations.map(e=>({...e,type:'creation'})))}]:[]);
}
function splitDisconnectedCommunities(labels,layers,nodes){
 const adjacency=new Map(nodes.map(n=>[n.id,new Set()]));
 for(const l of layers){if(!(l.share>0))continue;
  l.graph.forEachDirectedEdge((key,a,s,t)=>{if(a.weight>0&&s!==t){adjacency.get(s)?.add(t);adjacency.get(t)?.add(s);}});
 }
 const groups=new Map();for(const n of nodes){const g=labels[n.id];if(g==null)continue;if(!groups.has(g))groups.set(g,[]);groups.get(g).push(n.id);}
 const splits=[];
 for(const [label,ids] of groups){
  const allowed=new Set(ids),seen=new Set(),components=[];
  for(const start of ids){if(seen.has(start))continue;const comp=[];const queue=[start];seen.add(start);
   while(queue.length){const id=queue.pop();comp.push(id);for(const other of adjacency.get(id)||[])if(allowed.has(other)&&!seen.has(other)){seen.add(other);queue.push(other);}}
   components.push(comp);}
  if(components.length<2)continue;
  components.sort((a,b)=>b.length-a.length||a.slice().sort().join('\u0000').localeCompare(b.slice().sort().join('\u0000')));
  for(let i=1;i<components.length;i++){const newLabel=label+'~'+i;for(const id of components[i])labels[id]=newLabel;}
  splits.push({label,components:components.map(members=>({size:members.length,members:members.slice().sort()}))});
 }
 return splits;
}
function unifiedPartition(nodes,socialEdges,contentEdges,{contentEnabled=true,additionalEdges=[],interactionEdges=[],...options}={}){
 const parameters={...DEFAULT,...options};
 if(!contentEnabled)return {...partition(makeGraph(nodes,socialEdges),{seed:parameters.seed,resolution:parameters.resolution}),version:'legacy-mixed-mass-v1'};
 if(!(parameters.refineChineseThreshold>=1)||!(parameters.refineTotalThreshold>=1)||!(parameters.minCommunitySize>=1)||!(parameters.fragmentMergeSize>=1)||!Number.isInteger(parameters.maxRefinementDepth)||parameters.maxRefinementDepth<0)throw Error('Invalid community support thresholds');
 const layers=makeLayers(nodes,socialEdges,contentEdges,parameters,additionalEdges,interactionEdges),empiricalLayers=makeLayers(nodes,socialEdges,contentEdges,parameters,[],interactionEdges),macro=partitionLayers(empiricalLayers,{seed:parameters.seed});
 const labels={...macro.communities},groups=new Map(),refinements=[];
 for(const node of nodes){const g=labels[node.id];if(g==null)continue;if(!groups.has(g))groups.set(g,[]);groups.get(g).push(node);}
 function refine(parent,members,depth){
   if(depth>=parameters.maxRefinementDepth||members.filter(n=>n.language_class==='inferred_chinese').length<=parameters.refineChineseThreshold&&members.length<=parameters.refineTotalThreshold)return;
   const ids=new Set(members.map(n=>n.id)),social=socialEdges.filter(e=>ids.has(e.source)&&ids.has(e.target)),content=contentEdges.filter(e=>ids.has(e.source)&&ids.has(e.target));
   for(const resolution of [...new Set([parameters.localResolution,...parameters.refinementResolutions])]){
    const local=partitionLayers(makeLayers(members,social,content,{...parameters,resolution},[],interactionEdges.filter(e=>ids.has(e.source)&&ids.has(e.target))),{seed:parameters.seed});
    const children=new Map();for(const n of members){const child=local.communities[n.id]??'boundary:'+n.id;if(!children.has(child))children.set(child,[]);children.get(child).push(n);}
    if([...children.values()].filter(ns=>ns.length>=parameters.minCommunitySize).length<2||Math.max(...[...children.values()].map(ns=>ns.length))>=members.length*.95)continue;
    const childSizes=Object.fromEntries([...children].map(([key,ns])=>[key,ns.length]));
    refinements.push({parent,depth,chineseCount:members.filter(n=>n.language_class==='inferred_chinese').length,memberCount:members.length,localResolution:resolution,localScore:local.score,childSizes});
    for(const [child,ns] of children){const label=parent+':'+child;for(const n of ns)labels[n.id]=label;refine(label,ns,depth+1);}
    return;
   }
 }
 for(const [parent,members] of groups)refine(parent,members,0);
 const fragmentAttachments=attachFragments(nodes,labels,empiricalLayers,parameters.fragmentMergeSize);
 const annotations=normalAdditional(additionalEdges),movable=new Set(annotations.flatMap(e=>[e.source,e.target])),annotationMoves=[];
 if(movable.size&&layers.some(l=>l.name==='additional'&&l.share>0)){
  const adjusted=partitionLayers(layers,{seed:parameters.seed,initialCommunities:labels,movableNodes:movable,contract:false});
  const names=new Map();for(const n of nodes)if(!movable.has(n.id)&&labels[n.id]!=null)names.set(adjusted.communities[n.id],labels[n.id]);
  const taken=new Set(names.values());
  for(const n of nodes)if(adjusted.communities[n.id]!=null&&!names.has(adjusted.communities[n.id])){
   const old=labels[n.id],name=old!=null&&!taken.has(old)?old:'annotation:'+n.id;
   names.set(adjusted.communities[n.id],name);taken.add(name);
  }
  for(const id of movable){const next=adjusted.communities[id]==null?null:names.get(adjusted.communities[id]);if(next!==labels[id])annotationMoves.push({id,from:labels[id],to:next});labels[id]=next;}
 }
 const connectivitySplits=splitDisconnectedCommunities(labels,layers,nodes);
 const finalGroups=new Map();for(const n of nodes){const g=labels[n.id];if(g==null)continue;if(!finalGroups.has(g))finalGroups.set(g,[]);finalGroups.get(g).push(n.id);}
 const communities={},statuses={},provisional={},palette=new Map();let count=0;
 for(const [g,ids] of [...finalGroups].sort(([a],[b])=>String(a).localeCompare(String(b)))){
   const small=ids.length<parameters.fragmentMergeSize;
   if(small){for(const id of ids){communities[id]=null;statuses[id]='small_sample';provisional[id]=g;}continue;}
   palette.set(g,count++);for(const id of ids){communities[id]=String(palette.get(g));statuses[id]=small?'assigned_small':'assigned';if(small)provisional[id]=g;}
 }
 for(const n of nodes)if(!Object.hasOwn(communities,n.id)){communities[n.id]=null;statuses[n.id]=layers.some(l=>l.share>0&&l.graph.degree(n.id)>0)?'boundary_unresolved':'isolated';}
 return {version:VERSION,parameters,communities,count,score:scoreLayers(layers,communities),history:macro.history,
   macroCommunities:macro.communities,macroScore:macro.score,refinements,fragmentAttachments,annotationMoves,statuses,provisional,
   connectivitySplits,communityConnectivity:{splitGroups:connectivitySplits.length,splitNodes:connectivitySplits.reduce((n,s)=>n+s.components.slice(1).reduce((m,c)=>m+c.size,0),0)},
   objectiveScope:'empirical macro/refinement and fragment attachment, followed by bounded annotation-endpoint-only local moves; final global score is diagnostic, not an optimized global maximum',
   eligibleContentEdges:eligibleContent(contentEdges).length,contentRule:'at least two shared tags and positive distinct-work support; not social facts'};
}
module.exports={VERSION,DEFAULT,LEGACY_THREE_LAYER,unifiedPartition,makeLayers,eligibleContent,normalAdditional,splitDisconnectedCommunities};
