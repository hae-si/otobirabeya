const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),os=require('os'),path=require('path'),{execFileSync}=require('child_process');
function build(author,social,decisions=[]){
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'otobirabeya-test-'));
 try{
  for(const [name,data] of Object.entries({'graph.json':{events:{},works:{},...author},'social-graph.json':social,'dataset.json':{creators:{a:{name:'A'},b:{name:'B'}}},'identity.json':[],'decisions.json':decisions,'profile-scope.json':{}}))fs.writeFileSync(path.join(dir,name),JSON.stringify(data));
  execFileSync(process.execPath,[path.resolve(__dirname,'../web/unified-build.cjs'),dir,path.join(dir,'dataset.json'),path.join(dir,'identity.json'),path.join(dir,'decisions.json')],{stdio:'pipe'});
  return JSON.parse(fs.readFileSync(path.join(dir,'unified-graph.json')));
 }finally{fs.rmSync(dir,{recursive:true,force:true});}
}
test('production builder keeps peripheral creators and isolates with no social layer',()=>{
 const g=build({nodes:[{id:'a',core:true},{id:'b',core:false},{id:'c',core:true}],edges:[{id:'ab',source:'a',target:'b',weights:{affiliation:.5},event_ids:[]}]},{nodes:[],edges:[]});
 assert.equal(g.nodes.length,3);assert.equal(g.edges.length,1);assert.equal(g.nodes.find(n=>n.id==='otodb:c').community,null);assert.ok(g.nodes.every(n=>n.pagerank===null));
});
test('production builder handles zero edges',()=>{
 const g=build({nodes:[{id:'a',core:true}],edges:[]},{nodes:[],edges:[]});assert.equal(g.meta.community_count,0);assert.equal(g.meta.modularity,null);
});
test('production builder merges accounts, excludes self follows and recomputes reciprocity',()=>{
 const social={nodes:['u','v','w'].map(id=>({id,username:id,pagerank:.3})),edges:[{id:'1',source:'u',target:'w',weight:1,mutual:false},{id:'2',source:'w',target:'v',weight:1,mutual:false},{id:'3',source:'u',target:'v',weight:1,mutual:false}]};
 const g=build({nodes:[{id:'a',core:true},{id:'b',core:false}],edges:[]},social,[{account_id:'u',creator_id:'a'},{account_id:'v',creator_id:'a'},{account_id:'w',creator_id:'b'}]);
 assert.equal(g.nodes.length,2);assert.equal(g.edges.length,2);assert.ok(g.edges.every(e=>e.mutual&&!e.account_mutual));assert.ok(g.nodes.every(n=>Math.abs(n.pagerank-.5)<1e-10));
});
test('duplicate account follows aggregate into one author-level edge',()=>{
 const social={nodes:['u','v','w'].map(id=>({id,username:id,pagerank:.3})),edges:[{id:'1',source:'u',target:'v',weight:1,mutual:false},{id:'2',source:'w',target:'v',weight:1,mutual:false}]};
 const g=build({nodes:[{id:'a',chinese_scope:true},{id:'b'}],edges:[]},social,[{account_id:'u',creator_id:'a'},{account_id:'w',creator_id:'a'},{account_id:'v',creator_id:'b'}]);
 const follows=g.edges.filter(e=>e.type==='follow');
 assert.equal(follows.length,1);assert.equal(follows[0].source,'otodb:a');assert.equal(follows[0].target,'otodb:b');
 assert.equal(follows[0].weight,1);assert.deepEqual(follows[0].account_edge_ids,['follow:1','follow:2']);
 assert.equal(g.meta.follow_aggregation.account_edges,2);assert.equal(g.meta.follow_aggregation.author_edges,1);
});
