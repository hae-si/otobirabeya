function scopeGraph(nodes, edges, mode='core') {
  if (!['core','related','all'].includes(mode)) throw new Error('Unknown scope');
  if(nodes.some(n=>n.language_class)){const kept=new Set(nodes.filter(n=>mode==='all'||n.language_class===(mode==='core'?'inferred_chinese':'inferred_non_chinese')).map(n=>n.id));return {nodes:nodes.filter(n=>kept.has(n.id)),edges:edges.filter(e=>kept.has(e.source)&&kept.has(e.target))};}
  const core=new Set(nodes.filter(n=>n.core===true).map(n=>n.id));
  const kept=new Set(mode==='all'?nodes.map(n=>n.id):core);
  if(mode==='related')for(const n of nodes)if(n.interaction_scope==='related')kept.add(n.id);
  if(mode==='related') for(const e of edges) {
    if(core.has(e.source))kept.add(e.target);
    if(core.has(e.target))kept.add(e.source);
  }
  return {nodes:nodes.filter(n=>kept.has(n.id)),edges:edges.filter(e=>kept.has(e.source)&&kept.has(e.target)&&(mode!=='related'||e.type==='interaction'||core.has(e.source)||core.has(e.target)))};
}
module.exports={scopeGraph};
