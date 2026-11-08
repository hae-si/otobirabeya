function attachFragments(nodes,labels,layers,minSize){
 const groups=new Map(),moves=[];
 for(const n of nodes){const g=labels[n.id];if(g==null)continue;if(!groups.has(g))groups.set(g,[]);groups.get(g).push(n.id);}
 const affinity=new Map();
 for(const l of layers){if(!l.share||l.name==='additional')continue;
  l.graph.forEachDirectedEdge((key,a,s,t)=>{
   for(const [from,to] of [[labels[s],labels[t]],[labels[t],labels[s]]]){
    if(from==null||to==null||from===to||groups.get(from).length>=minSize||groups.get(to).length<minSize)continue;
    if(!affinity.has(from))affinity.set(from,new Map());const target=affinity.get(from);
    target.set(to,(target.get(to)||0)+a.weight*l.share);
   }
  });
 }
 for(const [from,targets] of affinity){
  const ranked=[...targets].map(([to,weight])=>({to,weight,score:weight/Math.sqrt(groups.get(to).length)})).sort((a,b)=>b.score-a.score||String(a.to).localeCompare(String(b.to)));
  const best=ranked[0];if(!(best?.weight>0))continue;
  for(const id of groups.get(from))labels[id]=best.to;
  moves.push({from,to:best.to,members:groups.get(from),affinity:best.weight,sizeAdjustedAffinity:best.score});
 }
 return moves;
}
module.exports={attachFragments};
