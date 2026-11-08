const fs=require('fs'),crypto=require('crypto');
const {makeGraph,partition,ari}=require('./network-analysis.cjs');
const {scoreLayers,VERSION}=require('./layer-objective.cjs');
const raw=fs.readFileSync(process.argv[2]),data=JSON.parse(raw);
const creation=makeGraph(data.nodes,data.edges.filter(e=>e.type==='creation'));
const follow=makeGraph(data.nodes,data.edges.filter(e=>e.type==='follow'));
const baseline=partition(makeGraph(data.nodes,data.edges));
const pairs=new Set(),counts={accountEdges:0,authorDirections:0,duplicateAuthorDirections:0};
for(const e of data.edges.filter(e=>e.type==='follow')){counts.accountEdges++;pairs.add(JSON.stringify([e.source,e.target]));}
counts.authorDirections=pairs.size;counts.duplicateAuthorDirections=counts.accountEdges-pairs.size;
const experiments=[];
for(const share of [1,.9,.7,.5,.3,0])for(const seed of [42,123,2026]){
 const start=performance.now(),r=partition(makeGraph(data.nodes,data.edges,{creationShare:share}),{seed});
 experiments.push({creationShare:share,seed,count:r.count,mixedQ:r.modularity,ariToBaseline:ari(baseline.communities,r.communities),independentScore:scoreLayers([{name:'collaboration',graph:creation,share},{name:'following',graph:follow,share:1-share}],r.communities),elapsedMs:performance.now()-start});
}
const report={version:VERSION,input_sha256:crypto.createHash('sha256').update(raw).digest('hex'),parameters:{resolution:1,seeds:[42,123,2026]},counts,experiments,peakRssBytes:process.resourceUsage().maxRSS*1024,interpretation:'Partitions optimized using legacy mixed null model, independently rescored; NOT independent-layer optimization or evidence of superiority.'};
fs.writeFileSync(process.argv[3],JSON.stringify(report,null,2));console.log(JSON.stringify({counts,default:experiments.find(e=>e.creationShare===.5&&e.seed===42)}));
