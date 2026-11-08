const {DirectedGraph}=require('graphology');
const {scoreLayers}=require('./layer-objective.cjs');
const VERSION='independent-layer-louvain-v1';
function partitionLayers(input,{seed=42,maxSweeps=200,maxLevels=100,initialCommunities=null,movableNodes=null,contract=true}={}){
  if(!Number.isInteger(seed)||maxSweeps<1||maxLevels<1)throw Error('Invalid optimizer parameters');
  if(!input.length)throw Error('At least one layer required');
  const ids=input[0].graph.nodes().sort(),expected=new Set(ids);
  for(const l of input){
    if(!Number.isFinite(l.share)||l.share<0||!Number.isFinite(l.resolution??1)||(l.resolution??1)<0)throw Error('Invalid layer parameter');
    if(l.graph.order!==ids.length||l.graph.nodes().some(id=>!expected.has(id)))throw Error('Layer node sets differ');
  }
  let state=seed>>>0;const rng=()=>{state=(1664525*state+1013904223)>>>0;return state/4294967296;};
  let layers=input.map(l=>({...l,resolution:l.resolution??1})),mapping=new Map(ids.map(id=>[id,id]));
  const history=[];let converged=false;
  for(let level=0;level<maxLevels;level++){
    const connected=new Set();for(const l of layers)if(l.share>0)l.graph.forEachDirectedEdge((key,a,s,t)=>{if(a.weight>0){connected.add(s);connected.add(t);}});
    const nodes=layers[0].graph.nodes().sort((a,b)=>Number(connected.has(b))-Number(connected.has(a))||a.localeCompare(b)),initial=new Map(),labels=new Map(nodes.map((id,i)=>{
      if(!initialCommunities||level)return [id,i];
      if(!Object.hasOwn(initialCommunities,id))throw Error('Missing initial partition node');
      const key=initialCommunities[id]??Symbol(id);if(!initial.has(key))initial.set(key,initial.size);return [id,initial.get(key)];
    }));let nextLabel=nodes.length;
    const active=layers.filter(l=>l.graph.size&&l.share>0),shareSum=active.reduce((s,l)=>s+l.share,0);
    const prepared=active.map(l=>{
      const outgoing=new Map(nodes.map(id=>[id,0])),incoming=new Map(nodes.map(id=>[id,0]));
      const links=new Map(nodes.map(id=>[id,[]]));let mass=0;
      l.graph.forEachDirectedEdge((k,a,s,t)=>{
        if(!Number.isFinite(a.weight)||a.weight<0)throw Error('Invalid edge weight');
        mass+=a.weight;outgoing.set(s,outgoing.get(s)+a.weight);incoming.set(t,incoming.get(t)+a.weight);
        if(s!==t&&a.weight){links.get(s).push([t,a.weight]);links.get(t).push([s,a.weight]);}
      });
      const groupOut=new Map(),groupIn=new Map();for(const id of nodes){const key=labels.get(id);groupOut.set(key,(groupOut.get(key)||0)+outgoing.get(id));groupIn.set(key,(groupIn.get(key)||0)+incoming.get(id));}
      return {outgoing,incoming,links,mass,share:l.share/shareSum,gamma:l.resolution,groupOut,groupIn};
    }).filter(l=>l.mass>0);
    let settled=false,sweeps=0,moves=0;
    for(;sweeps<maxSweeps;sweeps++){
      let changed=false;const order=nodes.filter(id=>connected.has(id));
      for(let i=order.length-1;i>0;i--){const j=Math.floor(rng()*(i+1));[order[i],order[j]]=[order[j],order[i]];}
      for(const id of order){
        if(movableNodes&&!movableNodes.has(id))continue;
        const old=labels.get(id),singleton=nextLabel++,candidates=new Set([old,singleton]);
        const neighborWeights=prepared.map(l=>{
          const weights=new Map();for(const [other,w] of l.links.get(id)){const c=labels.get(other);weights.set(c,(weights.get(c)||0)+w);candidates.add(c);}
          l.groupOut.set(old,(l.groupOut.get(old)||0)-l.outgoing.get(id));
          l.groupIn.set(old,(l.groupIn.get(old)||0)-l.incoming.get(id));return weights;
        });
        const value=c=>prepared.reduce((s,l,i)=>s+l.share*((neighborWeights[i].get(c)||0)/l.mass-l.gamma*(l.outgoing.get(id)*(l.groupIn.get(c)||0)+l.incoming.get(id)*(l.groupOut.get(c)||0))/(l.mass*l.mass)),0);
        const previous=value(old);let best=old,bestValue=previous;
        for(const c of candidates){const v=value(c);if(v>bestValue+1e-12){best=c;bestValue=v;}}
        labels.set(id,best);
        for(const l of prepared){l.groupOut.set(best,(l.groupOut.get(best)||0)+l.outgoing.get(id));l.groupIn.set(best,(l.groupIn.get(best)||0)+l.incoming.get(id));}
        if(best!==old){changed=true;moves++;}
      }
      if(!changed){settled=true;sweeps++;break;}
    }
    if(!settled)throw Error('Multilayer optimizer sweep limit reached');
    for(const [original,current] of mapping)mapping.set(original,String(labels.get(current)));
    const communities=Object.fromEntries(mapping),score=scoreLayers(input,communities);
    if(history.length&&score.total<history.at(-1).score-1e-9)throw Error('Objective decreased across contraction');
    history.push({level,sweeps,moves,nodes:nodes.length,groups:new Set(labels.values()).size,score:score.total});
    if(!contract||new Set(labels.values()).size===nodes.length||!moves){converged=true;break;}
    layers=layers.map(l=>{
      const g=new DirectedGraph();for(const c of [...new Set(labels.values())].sort((a,b)=>a-b))g.addNode(String(c));
      l.graph.forEachDirectedEdge((key,a,s,t)=>{s=String(labels.get(s));t=String(labels.get(t));if(g.hasEdge(s,t))g.updateEdgeAttribute(s,t,'weight',w=>w+a.weight);else g.addDirectedEdge(s,t,{weight:a.weight});});
      return {...l,graph:g};
    });
  }
  if(!converged)throw Error('Multilayer optimizer level limit reached');
  const communities=Object.fromEntries(mapping);
  for(const id of ids)if(!input.some(l=>l.share>0&&l.graph.degree(id)>0))communities[id]=null;
  return {version:VERSION,seed,communities,count:new Set(Object.values(communities).filter(c=>c!==null)).size,
    score:scoreLayers(input,communities),history,converged};
}
module.exports={VERSION,partitionLayers};
