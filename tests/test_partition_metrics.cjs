const {test}=require('node:test'),assert=require('node:assert/strict');
const {nmi}=require('../web/partition-metrics.cjs');
test('NMI label invariant, null aware and zero for orthogonal balanced partitions',()=>{
 assert.equal(nmi({a:0,b:0,c:1},{a:9,b:9,c:8}),1);
 assert.equal(nmi({a:null},{a:1}),null);
 assert.ok(Math.abs(nmi({a:0,b:0,c:1,d:1},{a:0,b:1,c:0,d:1}))<1e-12);
});
