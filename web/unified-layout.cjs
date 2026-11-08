const {UndirectedGraph}=require('graphology');
const fa2=require('graphology-layout-forceatlas2');
const {makeLayers,DEFAULT,normalAdditional}=require('./unified-algorithm.cjs');
const LAYOUT_DEFAULT={iterations:300,additionalSpringFactor:1};
function layoutUnified(nodes,social,content,parameters=DEFAULT,{iterations=LAYOUT_DEFAULT.iterations,additionalEdges=[],interactionEdges=[],additionalSpringFactor=LAYOUT_DEFAULT.additionalSpringFactor}={}){
 if(!Number.isInteger(iterations)||iterations<0||!Number.isFinite(additionalSpringFactor)||additionalSpringFactor<=0)throw Error('Invalid layout parameters');
 const graph=new UndirectedGraph();
 nodes.slice().sort((a,b)=>a.id.localeCompare(b.id)).forEach((n,i)=>graph.addNode(n.id,{x:Math.cos(i*2.39996)*Math.sqrt(i+1),y:Math.sin(i*2.39996)*Math.sqrt(i+1)}));
 const layers=makeLayers(nodes,social,content,parameters,[],interactionEdges);let active=0;const masses=layers.map(l=>{let m=0;l.graph.forEachEdge((k,a)=>m+=a.weight);if(m)active+=l.share;return m;});
 const socialIds=new Set([...social,...interactionEdges.filter(e=>e.analysis_enabled!==false)].flatMap(e=>[e.source,e.target])),contentOnly=new Set();
 let interactionSpringCap=null,clippedInteractionSprings=0;
 for(let i=0;i<layers.length;i++){
   const l=layers[i],mass=masses[i];if(!mass||!l.share)continue;
   if(l.name==='interaction'){let base=0;graph.forEachEdge((k,a)=>base=Math.max(base,a.weight));interactionSpringCap=base||1;}
   l.graph.forEachDirectedEdge((key,a,s,t)=>{
     if(s===t)return;
     const rawWeight=a.weight/mass*l.share/active*nodes.length,weight=l.name==='interaction'?Math.min(rawWeight,interactionSpringCap):rawWeight;
     if(weight<rawWeight)clippedInteractionSprings++;
     if(graph.hasEdge(s,t))graph.updateEdgeAttribute(s,t,'weight',v=>v+weight);else graph.addEdge(s,t,{weight});
     if(l.name==='song'||l.name==='source')for(const id of [s,t])if(!socialIds.has(id))contentOnly.add(id);
   });
 }
 let maxEmpiricalSpring=0;graph.forEachEdge((k,a)=>maxEmpiricalSpring=Math.max(maxEmpiricalSpring,a.weight));
 const springCap=(maxEmpiricalSpring||1)*additionalSpringFactor;
 const annotations=normalAdditional(additionalEdges);
 for(const e of annotations){
   if(!graph.hasNode(e.source)||!graph.hasNode(e.target)||e.source===e.target||!Number.isFinite(e.weight)||e.weight<=0)throw Error('Invalid additional layout edge');
   const weight=Math.min(e.weight,springCap);
   if(graph.hasEdge(e.source,e.target))graph.updateEdgeAttribute(e.source,e.target,'weight',v=>v+weight);else graph.addEdge(e.source,e.target,{weight});
 }
 if(graph.size)fa2.assign(graph,{iterations,settings:{...fa2.inferSettings(graph),barnesHutOptimize:true,edgeWeightInfluence:1,gravity:1}});
 return {positions:Object.fromEntries(graph.nodes().map(id=>[id,graph.getNodeAttributes(id)])),
   meta:{version:'unified-layer-layout-v5',iterations,layerMasses:layers.map((l,i)=>({name:l.name,share:l.share,mass:masses[i]})),interactionSpringCap,clippedInteractionSprings,additionalSpringFactor,maxEmpiricalSpring,additionalSpringCap:springCap,additionalEdges:annotations.length,contentOnlyConnected:contentOnly.size,edges:graph.size,
   meaning:'Empirical mass normalization plus bounded additional springs; community objective shares do not control physics; positions are not evidence'}};
}
module.exports={layoutUnified,LAYOUT_DEFAULT};
