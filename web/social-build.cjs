const fs=require('fs'),crypto=require('crypto');
const {DirectedGraph,UndirectedGraph}=require('graphology');
const louvain=require('graphology-communities-louvain');
const fa2=require('graphology-layout-forceatlas2');
const input=process.argv[2],output=process.argv[3],raw=fs.readFileSync(input),d=JSON.parse(raw);
const ids=d.accounts.map(a=>a.id).sort(),pairs=new Map(),out=new Map(ids.map(id=>[id,0]));
for(const e of d.edges){const f=e.fact;if(f.followerId===f.followeeId)continue;const k=f.followerId+':'+f.followeeId;if(!pairs.has(k))pairs.set(k,{...f,evidence:e.evidence});}
for(const e of pairs.values())out.set(e.followerId,out.get(e.followerId)+1);
function rng(seed){return()=>{seed=(1664525*seed+1013904223)>>>0;return seed/4294967296;};}
if(!ids.length){fs.writeFileSync(output,JSON.stringify({meta:{coverage:d.coverage||[],community_count:0,modularity:null},nodes:[],edges:[]}));console.log(JSON.stringify({nodes:0,edges:0,groups:0}));process.exit(0);}
const experiments=[];let primary;
for(const bonus of [0,.5,1])for(const resolution of [.5,1,1.5])for(const seed of [42,123,2026]){
 const g=new DirectedGraph();ids.forEach(id=>g.addNode(id));
 for(const [k,e] of [...pairs].sort())g.addDirectedEdge(e.followerId,e.followeeId,{weight:1+(pairs.has(e.followeeId+':'+e.followerId)?bonus:0)});
 const r=g.size?louvain.detailed(g,{getEdgeWeight:'weight',resolution,rng:rng(seed),randomWalk:true}):{communities:Object.fromEntries(ids.map(id=>[id,null])),count:0,modularity:null};
 experiments.push({bonus,resolution,seed,count:r.count,modularity:r.modularity,communities:r.communities});
 if(bonus===0&&resolution===1&&seed===42)primary=r;
}
let rank=new Map(ids.map(id=>[id,1/ids.length]));let iterations=0,residual;
for(;iterations<1000;iterations++){
 const dangling=ids.filter(id=>!out.get(id)).reduce((s,id)=>s+rank.get(id),0);
 const next=new Map(ids.map(id=>[id,(1-.85)/ids.length+.85*dangling/ids.length]));
 for(const e of pairs.values())next.set(e.followeeId,next.get(e.followeeId)+.85*rank.get(e.followerId)/out.get(e.followerId));
 residual=ids.reduce((s,id)=>s+Math.abs(next.get(id)-rank.get(id)),0);rank=next;if(residual<1e-12)break;
}
if(residual>=1e-12)throw Error('PageRank did not converge');
const layout=new UndirectedGraph();ids.forEach((id,i)=>layout.addNode(id,{x:Math.cos(i*2.39996)*Math.sqrt(i+1),y:Math.sin(i*2.39996)*Math.sqrt(i+1)}));
for(const e of pairs.values())if(!layout.hasEdge(e.followerId,e.followeeId))layout.addEdge(e.followerId,e.followeeId);
fa2.assign(layout,{iterations:150,settings:{...fa2.inferSettings(layout),gravity:1,scalingRatio:5}});
const mapping=new Map(d.mappings.map(m=>[m.otomadsite_id,m]));
const graph={meta:{input_sha256:crypto.createHash('sha256').update(raw).digest('hex'),algorithm:'Directed Louvain',version:require('graphology-communities-louvain/package.json').version,resolution:1,seed:42,reciprocal_bonus:0,modularity:primary.modularity,community_count:primary.count,pagerank:{alpha:.85,iterations:iterations+1,residual},coverage:d.coverage,experiments},nodes:d.accounts.map(a=>({...a,label:mapping.get(a.id)?.user_provided_name||a.username||a.id,mapping:mapping.get(a.id)||null,pagerank:rank.get(a.id),community:primary.communities[a.id],...layout.getNodeAttributes(a.id)})),edges:[...pairs.values()].map(e=>({...e,source:e.followerId,target:e.followeeId,weight:1,mutual:pairs.has(e.followeeId+':'+e.followerId)}))};
fs.writeFileSync(output,JSON.stringify(graph));console.log(JSON.stringify({nodes:graph.nodes.length,edges:graph.edges.length,groups:primary.count,modularity:primary.modularity,rankSum:[...rank.values()].reduce((a,b)=>a+b,0)}));
