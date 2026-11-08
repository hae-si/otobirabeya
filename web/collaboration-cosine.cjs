const COOPERATION_WEIGHT=.3, DIRECTOR_WEIGHT=1.5, DIRECTOR_ROLE=4;
function applyCollaborationCosine(graph){
 const features=new Map(graph.nodes.map(n=>[n.id,new Map()])),N=graph.nodes.length;
 for(const [id,event] of Object.entries(graph.events||{})){
  const people=Object.keys(event.participants||{}).map(x=>x.startsWith('otodb:')?x:'otodb:'+x).filter(x=>features.has(x));
  const base=Math.log((N+1)/(people.length+1))/Math.max(1,people.length);
  const value=base*(event.cooperation?COOPERATION_WEIGHT:1);
  for(const author of people)features.get(author).set(id,value);
 }
 const norms=new Map([...features].map(([id,f])=>[id,Math.sqrt([...f.values()].reduce((s,v)=>s+v*v,0))]));
 let directorEdges=0;
 for(const edge of graph.edges)if(edge.type==='creation'){
  let dot=0;for(const [id,value] of features.get(edge.source))dot+=value*(features.get(edge.target).get(id)||0);
  edge.analysis_weight=norms.get(edge.source)&&norms.get(edge.target)?dot/(norms.get(edge.source)*norms.get(edge.target)):0;
  const roleOf=(e,id)=>(e.roles?.[id]||e.roles?.[id.replace(/^otodb:/,'')]||0);
  const director=(edge.event_ids||[]).some(eid=>{const e=graph.events?.[eid];if(!e)return false;return (roleOf(e,edge.source)|roleOf(e,edge.target))&DIRECTOR_ROLE;});
  if(director){edge.analysis_weight*=DIRECTOR_WEIGHT;edge.director_weight_applied=true;directorEdges++;}
 }
 graph.meta.collaboration={version:'author-event-tfidf-cosine-v3',cooperation_weight:COOPERATION_WEIGHT,director_weight:DIRECTOR_WEIGHT,director_role_bit:DIRECTOR_ROLE,director_rule:'edges incident to a director in any shared event are multiplied by 1.5 after cosine',director_edges:directorEdges,formula:'X_ae=log((N+1)/(participants_e+1))/participants_e * (cooperation?0.3:1); cosine(X_a,X_b); director incident edges *1.5',overlapping_works_removed:false};
}
module.exports={applyCollaborationCosine,COOPERATION_WEIGHT,DIRECTOR_WEIGHT,DIRECTOR_ROLE};
