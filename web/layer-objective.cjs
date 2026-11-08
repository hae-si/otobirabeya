const VERSION='independent-layer-score-v1';
function modularity(graph, communities, resolution=1){
  if(!Number.isFinite(resolution)||resolution<0)throw Error('Invalid resolution');
  const groups=new Map(); let mass=0,internal=0;
  for(const id of graph.nodes()){
    if(!Object.hasOwn(communities,id))throw Error('Missing partition node');
    const label=communities[id]??Symbol(id);
    groups.set(id,label);
  }
  const out=new Map(),inc=new Map();
  graph.forEachDirectedEdge((key,a,s,t)=>{
    const w=a.weight;if(!Number.isFinite(w)||w<0)throw Error('Invalid weight');
    mass+=w;const x=groups.get(s),y=groups.get(t);
    out.set(x,(out.get(x)||0)+w);inc.set(y,(inc.get(y)||0)+w);
    if(x===y)internal+=w;
  });
  if(!mass)return null;
  let expected=0;for(const [g,w] of out)expected+=w*(inc.get(g)||0);
  return internal/mass-resolution*expected/(mass*mass);
}
function scoreLayers(layers,communities){
  let total=0,active=0;const contributions=[];
  for(const {name,graph,share,resolution=1} of layers){
    if(!Number.isFinite(share)||share<0)throw Error('Invalid share');
    const q=modularity(graph,communities,resolution);
    if(q!==null)active+=share;
    contributions.push({name,share,resolution,q});
  }
  for(const c of contributions){c.effectiveShare=c.q===null||!active?0:c.share/active;c.contribution=c.q===null?0:c.effectiveShare*c.q;total+=c.contribution;}
  return {version:VERSION,total:active?total:null,contributions};
}
module.exports={VERSION,modularity,scoreLayers};
