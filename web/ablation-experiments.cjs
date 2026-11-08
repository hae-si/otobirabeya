const fs=require('fs'),crypto=require('crypto');
const {makeGraph,partition,ari}=require('./network-analysis.cjs');
const {partitionLayers}=require('./multilayer-partition.cjs');
const {aggregateAuthorFollows}=require('./author-follow.cjs');
const {nmi}=require('./partition-metrics.cjs');
const raw=fs.readFileSync(process.argv[2]),data=JSON.parse(raw),socialRaw=fs.readFileSync(process.argv[3]),social=JSON.parse(socialRaw);
const state=new Map(social.coverage.map(r=>[JSON.stringify([r.user_id,r.endpoint]),r.state]));
const isComplete=(n,d)=>n.accounts?.length&&n.accounts.every(a=>state.get(JSON.stringify([a.id,d]))==='visible_list_exhausted');
const binary=aggregateAuthorFollows(data.edges),creation=data.edges.filter(e=>e.type==='creation');
function layers(nodes,edges){return [{name:'collaboration',graph:makeGraph(nodes,edges.filter(e=>e.type==='creation')),share:.5},{name:'following',graph:makeGraph(nodes,aggregateAuthorFollows(edges).edges),share:.5}];}
const baseline=partitionLayers(layers(data.nodes,data.edges));
const configurations=[];
for(const cutoff of [20,100])configurations.push({name:'exclude_events_over_'+cutoff,nodes:data.nodes,
 edges:[...creation.map(e=>({...e,weight:e.event_ids.reduce((s,id)=>s+(data.events[id].n<=cutoff?1/(data.events[id].n-1):0),0)})).filter(e=>e.weight>0),...binary.edges]});
const prolific=new Map(data.nodes.map(n=>[n.id,new Set()])),incoming=new Map(),outgoing=new Map();
for(const e of creation)for(const id of [e.source,e.target])for(const event of e.event_ids)prolific.get(id).add(event);
for(const e of binary.edges){incoming.set(e.target,(incoming.get(e.target)||0)+1);outgoing.set(e.source,(outgoing.get(e.source)||0)+1);}
for(const [name,measure] of [['prolific',new Map([...prolific].map(([id,set])=>[id,set.size]))],['popular',incoming],['high_follow_out',outgoing]]){
 const removed=new Set([...measure].sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0])).slice(0,name==='prolific'?Math.ceil(data.nodes.length*.01):5).map(x=>x[0]));
 configurations.push({name:'exclude_'+name,nodes:data.nodes,edges:data.edges.filter(e=>!removed.has(e.source)&&!removed.has(e.target)),removedIds:[...removed]});
}
const bots=new Set(data.nodes.filter(n=>n.accounts?.length&&n.accounts.every(a=>a.isBot===true)).map(n=>n.id));
configurations.push({name:'exclude_explicit_bots',nodes:data.nodes,edges:data.edges.filter(e=>!bots.has(e.source)&&!bots.has(e.target)),removedIds:[...bots]});
for(const direction of ['following','both']){
 const nodes=data.nodes.filter(n=>isComplete(n,'following')&&(direction!=='both'||isComplete(n,'followers'))),ids=new Set(nodes.map(n=>n.id));
 configurations.push({name:'coverage_complete_'+direction,nodes,edges:data.edges.filter(e=>ids.has(e.source)&&ids.has(e.target))});
}
const runs=[];
for(const config of configurations)for(const seed of [42,123,2026]){
 const start=performance.now(),r=partitionLayers(layers(config.nodes,config.edges),{seed});
 const legacy=partition(makeGraph(config.nodes,config.edges),{seed});
 runs.push({name:config.name,seed,nodes:config.nodes.length,edges:config.edges.length,removedIds:config.removedIds||[],
 count:r.count,score:r.score,ariToFull:ari(baseline.communities,r.communities),nmiToFull:nmi(baseline.communities,r.communities),
 ariToInducedLegacy:ari(legacy.communities,r.communities),communities:r.communities,elapsedMs:performance.now()-start});
}
const fullRuns=JSON.parse(fs.readFileSync(process.argv[4]));
const families=new Map();for(const r of fullRuns.experiments){const key=JSON.stringify({...r.parameters,seed:null});if(!families.has(key))families.set(key,[]);families.get(key).push(r);}
const stability=[...families].map(([parameters,runs])=>({parameters:JSON.parse(parameters),pairs:runs.flatMap((a,i)=>runs.slice(i+1).map(b=>({seeds:[a.parameters.seed,b.parameters.seed],ari:ari(a.communities,b.communities),nmi:nmi(a.communities,b.communities)})))}));
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
fs.writeFileSync(process.argv[5],JSON.stringify({algorithm_version:baseline.version,input_sha256:hash(raw),social_sha256:hash(socialRaw),runs,stability,
 coverageStates:Object.fromEntries(social.coverage.reduce((m,r)=>m.set(r.state,(m.get(r.state)||0)+1),new Map())),
 limitations:['Coverage subsets are induced cohorts, not missing-edge estimates; unknown does not mean absent','Explicit isBot evidence only; official accounts have no reviewed registry and are not guessed from names','ARI/NMI use common assigned nodes; report cohort size alongside values','High production measured by retained events, incomplete outside projection'],peakRssBytes:process.resourceUsage().maxRSS*1024}));
console.log(JSON.stringify({runs:runs.length,stability:stability.length}));
