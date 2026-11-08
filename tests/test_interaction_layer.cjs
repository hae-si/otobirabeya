const {test}=require('node:test'),assert=require('node:assert/strict');
const {makeDirectedWeightedGraph}=require('../web/network-analysis.cjs');
const {unifiedPartition,makeLayers,DEFAULT,LEGACY_THREE_LAYER}=require('../web/unified-algorithm.cjs');
const {layoutUnified}=require('../web/unified-layout.cjs');
const {filterView,statistics}=require('../web/explorer.cjs');
const {partitionLayers}=require('../web/multilayer-partition.cjs');
const {makeGraph}=require('../web/network-analysis.cjs');
const nodes=['a','b','c'].map(id=>({id}));
const interaction=[{id:'ab',source:'a',target:'b',weight:1,analysis_enabled:true},{id:'bc',source:'b',target:'c',weight:3,analysis_enabled:false}];
test('weighted interaction preserves direction and ratios with independent unit mass',()=>{
 const g=makeDirectedWeightedGraph(nodes,interaction);assert.equal(g.size,2);assert.equal(g.getEdgeAttribute('a','b','weight'),.25);assert.equal(g.hasEdge('b','a'),false);
 const layers=makeLayers(nodes,[],[],DEFAULT,[],interaction),layer=layers.find(l=>l.name==='interaction');assert.equal(layer.graph.size,1);assert.equal(layer.share,.25);
 const r=unifiedPartition(nodes,[],[],{interactionEdges:interaction,fragmentMergeSize:1});assert.notEqual(r.communities.a,null);assert.equal(r.communities.c,null);
 const absent=unifiedPartition(nodes,[],[],{...LEGACY_THREE_LAYER});assert.equal(absent.communities.a,null);
});
test('sparse interactions have a physical spring cap and finite layout',()=>{
 const social=[{id:'s',source:'b',target:'c',type:'creation',weight:1}];
 const r=layoutUnified(nodes,social,[],DEFAULT,{interactionEdges:interaction,iterations:2});
 assert.ok(r.meta.interactionSpringCap>0);for(const p of Object.values(r.positions))assert.ok(Number.isFinite(p.x)&&Number.isFinite(p.y));
});
test('related scope uses frozen repetition eligibility; full scope shows singleton evidence',()=>{
 const ns=[{id:'a',core:true,community:'0'},{id:'b',core:false,interaction_scope:'related',community:'1'},
  {id:'c',core:false,interaction_scope:'all',community:null}];
 const edges=[{id:'ab',source:'a',target:'b',type:'interaction',weight:1,distinct_video_count:2},
  {id:'ca',source:'c',target:'a',type:'interaction',weight:1,distinct_video_count:1}];
 const related=filterView(ns,edges,{scope:'related',minimumStrength:0,density:0});assert.deepEqual(related.nodes.map(n=>n.id),['a','b']);assert.equal(related.edges.length,1);
 const full=filterView(ns,edges,{scope:'all',minimumStrength:0,density:0});assert.equal(full.edges.length,2);
 const stats=statistics(full.nodes,full.edges);assert.equal(stats.layers.interaction,2);assert.equal(stats.layers.follow,0);
 assert.equal(stats.rows.find(n=>n.id==='a').interaction_in,1);assert.equal(stats.rows.find(n=>n.id==='a').interaction_out,1);
 assert.equal(filterView(ns,edges,{scope:'all',interaction:false,minimumStrength:0}).edges.length,0);
});
test('adding display-only isolates cannot perturb seeded empirical communities',()=>{
 const base=Array.from({length:12},(_,i)=>({id:'node'+i})),extra=Array.from({length:27},(_,i)=>({id:'display'+i})),edges=[];
 for(let i=0;i<12;i++)edges.push({id:'e'+i,source:'node'+i,target:'node'+((i+1)%12),type:'creation',weight:i%3+1});
 for(const seed of [42,123,2026]){
  const a=partitionLayers([{graph:makeGraph(base,edges),share:1}],{seed});
  const b=partitionLayers([{graph:makeGraph([...base,...extra],edges),share:1}],{seed});
  for(const x of base)for(const y of base)assert.equal(a.communities[x.id]===a.communities[y.id],b.communities[x.id]===b.communities[y.id]);
  for(const x of extra)assert.equal(b.communities[x.id],null);
 }
});
test('pending singleton evidence cannot boost a mapped identity pair in default analysis',()=>{
 const ns=[{id:'a',core:true},{id:'b',core:true}],edge={id:'ab',type:'interaction',source:'a',target:'b',weight:Math.log(3),distinct_video_count:2,
  analysis_weight:Math.log(2),analysis_video_count:1,analysis_video_ids:['1'],analysis_event_ids:['known'],analysis_enabled:true,event_ids:['known','pending']};
 assert.equal(filterView(ns,[edge],{minimumStrength:.6}).edges.length,1);
 assert.equal(filterView(ns,[edge],{scope:'all',minimumStrength:.6}).edges.length,1);
 const layer=makeLayers(ns,[],[],DEFAULT,[],[edge]).find(l=>l.name==='interaction');assert.equal(layer.graph.getEdgeAttribute('a','b','weight'),1);
 const shown=filterView(ns,[edge],{minimumStrength:0}).edges[0];assert.deepEqual(shown.event_ids,['known']);assert.equal(shown.weight,Math.log(2));
});
