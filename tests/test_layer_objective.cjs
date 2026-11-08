const {test}=require('node:test'),assert=require('node:assert/strict');
const {makeGraph,partition}=require('../web/network-analysis.cjs');
const {modularity,scoreLayers}=require('../web/layer-objective.cjs');
const nodes=['a','b','c','d'].map(id=>({id}));
const edges=[{id:'c',source:'a',target:'b',type:'creation',weight:1},{id:'f',source:'c',target:'d',type:'follow',weight:1}];
test('independent null models differ from mixed null model',()=>{
 const p={a:0,b:0,c:1,d:1},cg=makeGraph(nodes,edges.filter(e=>e.type==='creation')),fg=makeGraph(nodes,edges.filter(e=>e.type==='follow'));
 const r=scoreLayers([{name:'c',graph:cg,share:.5},{name:'f',graph:fg,share:.5}],p);
 assert.equal(r.total,0);assert.equal(modularity(makeGraph(nodes,edges),p),.5);
});
test('scorer agrees with installed directed Louvain objective',()=>{
 const g=makeGraph(nodes,edges),p=partition(g);assert.ok(Math.abs(modularity(g,p.communities)-p.modularity)<1e-12);
});
test('empty layer renormalizes only active shares',()=>{
 const r=scoreLayers([{name:'empty',graph:makeGraph(nodes,[]),share:.9},{name:'f',graph:makeGraph(nodes,[edges[1]]),share:.1}],{a:null,b:null,c:0,d:0});
 assert.equal(r.contributions[1].effectiveShare,1);assert.equal(r.total,0);
});
test('invalid parameters and missing assignments fail',()=>{
 assert.throws(()=>modularity(makeGraph(nodes,edges),{}));
 assert.throws(()=>modularity(makeGraph(nodes,[]),{},-1));
});
