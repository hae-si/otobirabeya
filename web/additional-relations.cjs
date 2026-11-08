const fs=require('fs');
function readAdditional(path,nodes){
 const rows=JSON.parse(fs.readFileSync(path,'utf8')),aliases=new Map(nodes.flatMap(n=>[n.id,...(n.source_node_ids||[])].map(id=>[id,n.id]))),seen=new Set();
 return rows.map(r=>{
  const source=aliases.get(r.source),target=aliases.get(r.target);
  if(r.relation!=null&&typeof r.relation!=='string'||r.analysis_enabled!=null&&typeof r.analysis_enabled!=='boolean')throw Error('Invalid annotation metadata');
  if(!r.id||seen.has(r.id)||!source||!target||!Number.isFinite(r.weight)||r.weight<=0||r.weight>1||!['user_annotation','user_requested_easter_egg'].includes(r.basis)||!r.requested_at)throw Error('Invalid additional relation: '+r.id);
  seen.add(r.id);return {...r,source,target,source_endpoints:[r.source,r.target],type:'additional',artificial:true,directed:false,excluded_self:source===target};
 });
}
module.exports={readAdditional};
