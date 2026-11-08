const {test}=require('node:test'),assert=require('node:assert/strict');
const {orientForReading}=require('../web/reading-layout.cjs');
test('reading orientation is fixed and rigid, with core centroid above the whole graph',()=>{
 const nodes=[{id:'a',x:0,y:0,language_class:'inferred_chinese'},{id:'b',x:4,y:0},{id:'c',x:0,y:3}];
 const result=orientForReading(nodes),p=result.positions;
 assert.ok(p.a.y>0);
 assert.ok(Math.abs(Math.hypot(p.b.x-p.a.x,p.b.y-p.a.y)-4)<1e-10);
 assert.deepEqual(orientForReading(nodes.slice().reverse()).positions,result.positions);
 assert.deepEqual(nodes[0],{id:'a',x:0,y:0,language_class:'inferred_chinese'});
});
