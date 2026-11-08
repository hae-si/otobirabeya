const {test}=require('node:test'),assert=require('node:assert/strict'),{resolve}=require('../web/interaction-identity.cjs');
test('new known creators reuse exact-name policy and compose prior source redirects',()=>{
 const input={nodes:[{id:'otodb:5',otodb_id:'5',label:'Exact'},{id:'otomadsite:x',label:'Else'}],
  redirects:{'otodb:9':'otodb:5'},creators:[{id:'2',name:'Exact'},{id:'11',name:'exact'}]};
 const before=JSON.stringify(input),result=resolve(input);
 assert.equal(result['otodb:5'],'otodb:2');assert.equal(result['otodb:9'],'otodb:2');assert.equal(result['otodb:11'],undefined);
 assert.equal(JSON.stringify(input),before);
});
