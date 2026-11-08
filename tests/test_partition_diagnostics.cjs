const test=require('node:test'),assert=require('node:assert/strict');
const {partitionDiagnostics}=require('../web/partition-diagnostics.cjs');
test('diagnostics distinguish connected omissions from display isolates and deduplicate neighbours',()=>{
 const nodes=['a','b','c','d'].map(id=>({id,label:id}));
 const layer=(name,share,pairs)=>({name,share,graph:{forEachEdge:fn=>pairs.forEach(([s,t],i)=>fn(i,{},s,t))}});
 const result=partitionDiagnostics(nodes,[layer('creation',.3,[['a','b']]),layer('interaction',.1,[['b','a'],['b','c']]),layer('additional',.1,[['c','d']])],{communities:{a:'0',b:'0',c:null,d:null}});
 assert.equal(result.connectedNodes,3);assert.equal(result.isolates,1);
 assert.deepEqual(result.connectedUnassigned.map(n=>n.id),['c']);assert.equal(result.mostConnected[0].id,'b');assert.equal(result.mostConnected[0].neighbours,2);
 assert.deepEqual(result.groupSizes,[2]);
});
