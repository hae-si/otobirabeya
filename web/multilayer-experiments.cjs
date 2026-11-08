const fs=require('fs'),crypto=require('crypto');
const {makeGraph,partition,ari}=require('./network-analysis.cjs');
const {partitionLayers,VERSION}=require('./multilayer-partition.cjs');
const {aggregateAuthorFollows}=require('./author-follow.cjs');
const digest=b=>crypto.createHash('sha256').update(b).digest('hex');
const raw=fs.readFileSync(process.argv[2]),data=JSON.parse(raw),contentRaw=fs.readFileSync(process.argv[3]),content=JSON.parse(contentRaw);
const baseline=partition(makeGraph(data.nodes,data.edges));
const creation=data.edges.filter(e=>e.type==='creation'),follow=aggregateAuthorFollows(data.edges).edges;
const strength=new Map(data.nodes.map(n=>[n.id,0]));for(const e of creation)for(const id of [e.source,e.target])strength.set(id,strength.get(id)+e.weight);
const schemes={newman:creation,strength:creation.map(e=>({...e,weight:e.weight/Math.sqrt(strength.get(e.source)*strength.get(e.target))})),
 countSaturation:creation.map(e=>{const n=e.event_ids?.length||1;return {...e,weight:e.weight*Math.log1p(n)/n};})};
const fg=makeGraph(data.nodes,follow),experiments=[];let defaultIndependent;
function measure(layers,parameters){
 const started=performance.now(),r=partitionLayers(layers,{seed:parameters.seed});
 const sizes=new Map(),overlap=new Map();for(const [id,c] of Object.entries(r.communities)){if(c===null)continue;sizes.set(c,(sizes.get(c)||0)+1);const b=baseline.communities[id];if(b!==null){if(!overlap.has(c))overlap.set(c,new Map());const row=overlap.get(c);row.set(b,(row.get(b)||0)+1);}}
 const assigned=Object.values(r.communities).filter(c=>c!==null).length;
 const bestOverlap=[...overlap.values()].reduce((sum,m)=>sum+Math.max(...m.values()),0);
 const entry={parameters,count:r.count,communitySizes:[...sizes.values()].sort((a,b)=>b-a),isolates:data.nodes.length-assigned,
   score:r.score,ariToLegacy:ari(baseline.communities,r.communities),majorityOverlapToLegacy:assigned?bestOverlap/assigned:null,
   elapsedMs:performance.now()-started,history:r.history,communities:r.communities};
 experiments.push(entry);return entry;
}
for(const [scheme,edges] of Object.entries(schemes)){
 const cg=makeGraph(data.nodes,edges);
 for(const share of [1,.9,.7,.5,.3,0])for(const seed of [42,123,2026]){
   const r=measure([{name:'collaboration',graph:cg,share},{name:'following',graph:fg,share:1-share}],{scheme,creationShare:share,contentShare:0,seed});
   if(scheme==='newman'&&share===.5&&seed===42)defaultIndependent=r;
 }
}
const contentGraphs=['2','3'].map(category=>makeGraph(data.nodes,content.edges.filter(e=>e.category===category).map(e=>({...e,type:'creation',weight:e.similarity}))));
const cg=makeGraph(data.nodes,creation);
for(const share of [.1,.25,1])for(const seed of [42,123,2026])measure([
 {name:'collaboration',graph:cg,share:(1-share)/2},{name:'following',graph:fg,share:(1-share)/2},
 ...contentGraphs.map((graph,i)=>({name:i?'source':'song',graph,share:share/2}))],{scheme:'newman',creationShare:(1-share)/2,contentShare:share,seed});
for(const run of experiments)run.ariToIndependentDefault=ari(defaultIndependent.communities,run.communities);
const result={version:VERSION,input_sha256:digest(raw),content_sha256:digest(contentRaw),parameters:{resolution:1,seeds:[42,123,2026],
 countSaturation:'w_newman * log1p(event_count) / event_count',strength:'w_newman / sqrt(s_i*s_j)',content:'category independent null models, equal content mass per category'},
 legacy:{count:baseline.count,modularity:baseline.modularity},experiments,peakRssBytes:process.resourceUsage().maxRSS*1024,
 limitations:['Experimental optimization; objective maximum is not semantic validation','Reported majority overlap allows many new groups to map to a legacy group; not a matching accuracy','Content confidence flags retained; no identity or social inference']};
fs.writeFileSync(process.argv[4],JSON.stringify(result));console.log(JSON.stringify({runs:experiments.length,default:{count:defaultIndependent.count,score:defaultIndependent.score,ari:defaultIndependent.ariToLegacy},peakRssBytes:result.peakRssBytes}));
