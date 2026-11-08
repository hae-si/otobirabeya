const {test}=require('node:test'),assert=require('node:assert/strict');
const {makeGraph}=require('../web/network-analysis.cjs');
const {partitionLayers}=require('../web/multilayer-partition.cjs');
const {scoreLayers}=require('../web/layer-objective.cjs');
const nodes=['a','b','c','d','isolated'].map(id=>({id}));
const c=[['a','b'],['c','d']].map(([source,target],i)=>({id:String(i),source,target,type:'creation',weight:1}));
const f=[{id:'f',source:'b',target:'c',type:'follow',weight:1}];
test('independent optimizer recovers disconnected cooperation, keeps isolates and deterministic seed',()=>{
 const layers=[{name:'c',graph:makeGraph(nodes,c),share:1}];const r=partitionLayers(layers);
 assert.equal(r.communities.a,r.communities.b);assert.equal(r.communities.c,r.communities.d);assert.notEqual(r.communities.a,r.communities.c);assert.equal(r.communities.isolated,null);
 assert.equal(r.score.total,.5);assert.deepEqual(r,partitionLayers(layers));
});
test('every contraction preserves increasing independently recomputed objective',()=>{
 const layers=[{name:'c',graph:makeGraph(nodes,c),share:.7},{name:'f',graph:makeGraph(nodes,f),share:.3}];
 const r=partitionLayers(layers);assert.equal(r.score.total,scoreLayers(layers,r.communities).total);
 for(let i=1;i<r.history.length;i++)assert.ok(r.history[i].score>=r.history[i-1].score-1e-10);
});
test('zero layers, zero shares, invalid sets and explicit resource limit',()=>{
 const g=makeGraph(nodes,[]);assert.equal(partitionLayers([{graph:g,share:1}]).count,0);
 assert.equal(partitionLayers([{graph:makeGraph(nodes,c),share:0}]).count,0);
 assert.throws(()=>partitionLayers([{graph:g,share:-1}]));
 assert.throws(()=>partitionLayers([{graph:g,share:1},{graph:makeGraph([],[]),share:1}]));
 assert.throws(()=>partitionLayers([{graph:makeGraph(nodes,c),share:1}],{maxLevels:1}));
});
