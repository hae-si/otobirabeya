const {DirectedGraph}=require('graphology');
const louvain=require('graphology-communities-louvain');
function makeGraph(nodes,edges,{creationShare=.5,excludeBots=false}={}){
  if(creationShare<0||creationShare>1)throw Error('Invalid layer share');
  const allIds=new Set(nodes.map(n=>n.id));
  if(allIds.size!==nodes.length)throw Error('Duplicate node');
  const keep=nodes.filter(n=>!excludeBots||!n.accounts?.length||!n.accounts.every(a=>a.isBot===true));
  const ids=new Set(keep.map(n=>n.id));if(ids.size!==keep.length)throw Error('Duplicate node');
  const unique=new Map();
  for(const e of edges){if(!['creation','follow'].includes(e.type))throw Error('Unknown edge type');if(!allIds.has(e.source)||!allIds.has(e.target))throw Error('Missing endpoint');if(!Number.isFinite(e.weight)||e.weight<0)throw Error('Invalid weight');
    if(unique.has(e.id)){if(JSON.stringify(unique.get(e.id))!==JSON.stringify(e))throw Error('Conflicting edge ID');continue;}unique.set(e.id,e);}
  const included=[...unique.values()].filter(e=>ids.has(e.source)&&ids.has(e.target)&&e.source!==e.target&&e.weight>0);
  const cm=included.filter(e=>e.type==='creation').reduce((s,e)=>s+2*e.weight,0),fm=included.filter(e=>e.type==='follow').length;
  const graph=new DirectedGraph();[...ids].sort().forEach(id=>graph.addNode(id));
  for(const e of included){const w=e.type==='creation'?(fm?creationShare:1)*e.weight/cm:(cm?1-creationShare:1)/fm;if(!w)continue;
    const add=(s,t)=>graph.hasEdge(s,t)?graph.updateEdgeAttribute(s,t,'weight',v=>v+w):graph.addDirectedEdge(s,t,{weight:w});add(e.source,e.target);if(e.type==='creation')add(e.target,e.source);}
  return graph;
}
function makeDirectedWeightedGraph(nodes,edges){
 const graph=makeGraph(nodes,[]),seen=new Map();let mass=0;
 for(const e of edges){if(!graph.hasNode(e.source)||!graph.hasNode(e.target))throw Error('Missing interaction endpoint');if(!Number.isFinite(e.weight)||e.weight<0)throw Error('Invalid interaction weight');
  if(e.source===e.target||!e.weight)continue;
  if(seen.has(e.id)){if(JSON.stringify(seen.get(e.id))!==JSON.stringify(e))throw Error('Conflicting interaction ID');continue;}seen.set(e.id,e);mass+=e.weight;
 }
 for(const e of seen.values()){const w=e.weight/mass;if(graph.hasEdge(e.source,e.target))graph.updateEdgeAttribute(e.source,e.target,'weight',v=>v+w);else graph.addDirectedEdge(e.source,e.target,{weight:w});}
 return graph;
}
function partition(graph,{resolution=1,seed=42}={}){
  let state=seed>>>0;const rng=()=>{state=(1664525*state+1013904223)>>>0;return state/4294967296;};
  if(!graph.size)return {communities:Object.fromEntries(graph.nodes().map(id=>[id,null])),count:0,modularity:null};
  const result=louvain.detailed(graph,{resolution,rng,getEdgeWeight:'weight'});
  for(const id of graph.nodes())if(!graph.degree(id))result.communities[id]=null;
  return {communities:result.communities,count:new Set(Object.values(result.communities).filter(c=>c!==null)).size,modularity:result.modularity};
}
function ari(a,b){const keys=Object.keys(a).filter(k=>a[k]!=null&&b[k]!=null);if(keys.length<2)return null;
  const cells=new Map(),rows=new Map(),cols=new Map(),add=(map,k)=>map.set(k,(map.get(k)||0)+1),comb=n=>n*(n-1)/2;
  for(const k of keys){add(cells,JSON.stringify([a[k],b[k]]));add(rows,a[k]);add(cols,b[k]);}
  const sum=m=>[...m.values()].reduce((s,n)=>s+comb(n),0),expected=sum(rows)*sum(cols)/comb(keys.length),den=(sum(rows)+sum(cols))/2-expected;
  return den?(sum(cells)-expected)/den:1;
}
function pageRank(graph,{alpha=.85,tolerance=1e-12,maxIterations=1000}={}){
  const ids=graph.nodes(),n=ids.length;if(!n)return {scores:{},iterations:0,residual:0};let scores=Object.fromEntries(ids.map(id=>[id,1/n])),residual=Infinity;
  const outgoing=new Map(ids.map(id=>[id,[]])),strength=new Map(ids.map(id=>[id,0]));graph.forEachDirectedEdge((key,attrs,s,t)=>{outgoing.get(s).push([t,attrs.weight]);strength.set(s,strength.get(s)+attrs.weight);});
  for(let i=0;i<maxIterations;i++){const dangling=ids.filter(id=>!strength.get(id)).reduce((s,id)=>s+scores[id],0),next=Object.fromEntries(ids.map(id=>[id,(1-alpha)/n+alpha*dangling/n]));for(const id of ids)for(const [target,w] of outgoing.get(id))next[target]+=alpha*scores[id]*w/strength.get(id);residual=ids.reduce((s,id)=>s+Math.abs(next[id]-scores[id]),0);scores=next;if(residual<tolerance)return {scores,iterations:i+1,residual};}
  throw Error('PageRank did not converge');
}
function followRanking(nodes,edges){
  const socialNodes=nodes.filter(n=>n.accounts?.length);
  const {aggregateAuthorFollows}=require('./author-follow.cjs');
  return pageRank(makeGraph(socialNodes,aggregateAuthorFollows(edges).edges,{creationShare:0}));
}
function applyInteractionRanking(graph){
  const edges=(graph.interaction_edges||[]).filter(e=>e.analysis_enabled&&e.analysis_weight>0);
  const ids=new Set(edges.flatMap(e=>[e.source,e.target]));
  const nodes=graph.nodes.filter(n=>ids.has(n.id));
  const weighted=edges.map(e=>({...e,weight:e.analysis_weight}));
  const alpha=.85;
  const {scores,iterations,residual}=pageRank(makeDirectedWeightedGraph(nodes,weighted),{alpha});
  for(const node of graph.nodes)node.interaction_pagerank=scores[node.id]??null;
  graph.meta.interaction_pagerank={alpha,iterations,residual,node_count:nodes.length,edge_count:edges.length,weight:'distinct_eligible_videos',scope:'eligible_interaction_endpoints'};
}
module.exports={makeGraph,makeDirectedWeightedGraph,partition,ari,pageRank,followRanking,applyInteractionRanking};
