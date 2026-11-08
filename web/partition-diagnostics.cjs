function partitionDiagnostics(nodes,layers,result){
 const neighbours=new Map(nodes.map(n=>[n.id,new Set()]));
 for(const layer of layers){
  if(!(layer.share>0)||layer.name==='additional')continue;
  layer.graph.forEachEdge((id,attrs,source,target)=>{if(source!==target){neighbours.get(source).add(target);neighbours.get(target).add(source);}});
 }
 const groups=new Map();for(const node of nodes){const group=result.communities[node.id];if(group!=null)groups.set(group,(groups.get(group)||0)+1);}
 const connected=nodes.filter(n=>neighbours.get(n.id).size>0),sizes=[...groups.values()].sort((a,b)=>a-b);
 const cases=connected.map(n=>({id:n.id,label:n.label,neighbours:neighbours.get(n.id).size,group:result.communities[n.id],groupSize:groups.get(result.communities[n.id])||0}));
 return {connectedNodes:connected.length,connectedUnassigned:cases.filter(n=>n.group==null),isolates:nodes.length-connected.length,
  groupSizes:sizes,medianGroupSize:sizes.length?sizes[Math.floor(sizes.length/2)]:0,
  smallGroups:sizes.filter(n=>n<8).length,largestGroupFraction:sizes.length?Math.max(...sizes)/sizes.reduce((a,b)=>a+b,0):0,
  mostConnected:cases.sort((a,b)=>b.neighbours-a.neighbours||a.id.localeCompare(b.id)).slice(0,30)};
}
module.exports={partitionDiagnostics};
