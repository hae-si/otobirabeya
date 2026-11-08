const {test}=require('node:test'),assert=require('node:assert/strict');
const {scopeGraph}=require('../web/unified-scope.cjs');
const nodes=[{id:'core',core:true},{id:'isolated',core:true},{id:'account',otodb_id:null},{id:'hop2'},{id:'unrelated'}];
const edges=[{id:'a',source:'core',target:'account',type:'follow'},{id:'b',source:'account',target:'hop2',type:'follow'},{id:'c',source:'hop2',target:'unrelated',type:'creation'}];
test('default only explicitly core, preserves core isolates',()=>{assert.deepEqual(scopeGraph(nodes,edges).nodes.map(n=>n.id),['core','isolated']);assert.equal(scopeGraph(nodes,edges).edges.length,0);});
test('related includes independent account but does not recurse',()=>{const r=scopeGraph(nodes,edges,'related');assert.deepEqual(r.nodes.map(n=>n.id),['core','isolated','account']);assert.deepEqual(r.edges.map(e=>e.id),['a']);assert.equal(r.nodes.at(-1).core,undefined);});
test('full preserves unmapped and unrelated sample; no mutation',()=>{const before=JSON.stringify({nodes,edges});assert.equal(scopeGraph(nodes,edges,'all').nodes.length,5);assert.equal(JSON.stringify({nodes,edges}),before);});
test('unknown scope fails explicitly',()=>assert.throws(()=>scopeGraph(nodes,edges,'invalid')));
