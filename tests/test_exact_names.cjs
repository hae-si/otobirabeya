const {test}=require('node:test'),assert=require('node:assert/strict');
const {mergeExactNames}=require('../web/exact-name-identity.cjs');
const {mergeProjection}=require('../web/identity-projection.cjs');
test('exact names merge deterministically, preserve accounts and IDs, without case or whitespace folding',()=>{
 const nodes=[{id:'social:x',label:'Name',accounts:[{id:'x'}],chinese_scope:true},{id:'otodb:2',otodb_id:'2',label:'Name',accounts:[]},{id:'otodb:1',otodb_id:'1',label:'Name',accounts:[]},{id:'lower',label:'name'},{id:'space',label:'Name '},{id:'empty',label:''},{id:'empty2',label:''}],before=JSON.stringify(nodes);
 const r=mergeExactNames(nodes),n=r.nodes.find(n=>n.id==='otodb:1');assert.equal(r.nodes.length,5);assert.equal(r.redirects.get('social:x'),'otodb:1');assert.equal(n.chinese_scope,true);assert.deepEqual(n.accounts,[{id:'x'}]);assert.equal(n.identity_members.length,3);assert.deepEqual(n.otodb_ids,['1','2']);assert.equal(JSON.stringify(nodes),before);
 assert.equal(mergeExactNames(nodes.slice().reverse()).redirects.get('otodb:2'),'otodb:1');
});
test('platform placeholder display names stay separate while normal exact names still merge',()=>{
 const nodes=[{id:'bilibili:1',label:'账号已注销'},{id:'bilibili:2',label:'账号已注销'},{id:'otodb:1',otodb_id:'1',label:'Same'},{id:'otodb:2',otodb_id:'2',label:'Same'}];
 const r=mergeExactNames(nodes);assert.equal(r.nodes.length,3);
 assert.deepEqual(r.nodes.filter(n=>n.label==='账号已注销').map(n=>n.id).sort(),['bilibili:1','bilibili:2']);
 assert.equal(r.redirects.get('otodb:2'),'otodb:1');
});
test('merged creator projection deduplicates events and self edges with original evidence retained',()=>{
 const ids=new Map([['otodb:1','otodb:1'],['otodb:2','otodb:1'],['otodb:3','otodb:3']]);
 const author={events:{e:{id:'e',n:3,type:'work',participants:{1:['w'],2:['w'],3:['w']}}},edges:[[1,2],[1,3],[2,3]].map(([a,b])=>({id:a+':'+b,source:String(a),target:String(b),weights:{affiliation:.5,project:0,creation:0},event_ids:['e']}))};
 const r=mergeProjection(author,ids);assert.equal(r.edges.length,1);assert.equal(r.edges[0].weight,1);assert.deepEqual(r.edges[0].event_ids,['e']);assert.equal(r.edges[0].source_projection.length,2);assert.equal(r.events.e.n,2);assert.equal(r.events.e.source_n,3);assert.equal(r.self.length,1);
});
