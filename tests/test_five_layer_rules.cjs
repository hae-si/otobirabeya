const {test}=require('node:test'),assert=require('node:assert/strict');
const {applyCollaborationCosine}=require('../web/collaboration-cosine.cjs');
const {classifyLanguage}=require('../web/language-scope.cjs');
test('event cosine normalizes author production and retains Newman evidence',()=>{
 const g={nodes:['otodb:1','otodb:2','otodb:3'].map(id=>({id})),events:{a:{participants:{1:[],2:[]}},b:{participants:{1:[]}}},meta:{},edges:[{source:'otodb:1',target:'otodb:2',type:'creation',weight:7}]};
 applyCollaborationCosine(g);assert.equal(g.edges[0].weight,7);assert.ok(g.edges[0].analysis_weight>0&&g.edges[0].analysis_weight<1);
});
test('cooperation-tagged events receive a lower collaboration weight',()=>{
 const build=cooperation=>({nodes:['otodb:1','otodb:2','otodb:3'].map(id=>({id})),events:{e1:{participants:{1:[],2:[]},cooperation},e2:{participants:{1:[],3:[]}}},meta:{},edges:[{source:'otodb:1',target:'otodb:2',type:'creation',weight:1}]});
 const normal=build(false),cooperative=build(true);applyCollaborationCosine(normal);applyCollaborationCosine(cooperative);
 assert.ok(cooperative.edges[0].analysis_weight<normal.edges[0].analysis_weight);
 assert.equal(cooperative.meta.collaboration.cooperation_weight,0.3);
});
test('language score uses Bilibili account, foreign account platforms and primary work platform',()=>{
 const g={meta:{},nodes:[
  {id:'a',has_bilibili_account:true,account_sites:['3'],platform_counts:{bilibili:2}},
  {id:'b',account_sites:['1','2','4'],platform_counts:{niconico:2}},
  {id:'c',account_sites:['1','2'],primary_platform:'bilibili'},
  {id:'d',has_bilibili_account:true,account_sites:['1','2','3'],primary_platform:'bilibili'},
  {id:'e',account_sites:['2','4'],primary_platform:'bilibili'},
  {id:'f',has_bilibili_account:true}],edges:[]};
 classifyLanguage(g,[]);const by=new Map(g.nodes.map(n=>[n.id,n]));
 assert.equal(by.get('a').language_score,4);assert.equal(by.get('a').language_class,'inferred_chinese');
 assert.equal(by.get('b').language_score,-5);assert.equal(by.get('b').language_class,'inferred_non_chinese');
 assert.equal(by.get('c').language_score,0);assert.equal(by.get('c').language_class,'inferred_non_chinese');
 assert.equal(by.get('d').language_score,2);assert.equal(by.get('d').language_class,'inferred_chinese');
 assert.equal(by.get('e').language_score,0);assert.equal(by.get('e').language_class,'inferred_non_chinese');
 assert.equal(by.get('f').language_score,2);assert.equal(by.get('f').language_class,'inferred_chinese');
 assert.equal(g.meta.language.neighbor_ratio_enabled,false);
});
test('content and interaction edges do not participate in language inference',()=>{
 const g={meta:{},nodes:[{id:'a',has_bilibili_account:true},{id:'b',has_bilibili_account:true},{id:'c'}],edges:[],interaction_edges:[{source:'a',target:'c',type:'interaction',analysis_enabled:true}]};
 classifyLanguage(g,[{source:'a',target:'c',type:'content',shared_tag_count:2,distinct_work_tag_support:1}]);
 const c=g.nodes.find(n=>n.id==='c');
 assert.equal(c.language_neighbor_count,undefined);
 assert.equal(c.language_class,'inferred_non_chinese');
});
test('director incident creation edges receive the 1.5 multiplier',()=>{
 const build=roles=>{const g={nodes:[{id:'otodb:1'},{id:'otodb:2'},{id:'otodb:3'}],events:{e:{participants:{1:[],2:[]},roles}},meta:{},edges:[{source:'otodb:1',target:'otodb:2',type:'creation',event_ids:['e'],weight:1},{source:'otodb:1',target:'otodb:3',type:'creation',event_ids:['e'],weight:1}]};applyCollaborationCosine(g);return g};
 const normal=build({1:0,2:0}),director=build({1:4,2:0});
 assert.ok(director.edges[0].analysis_weight>normal.edges[0].analysis_weight);
 assert.equal(director.edges[0].director_weight_applied,true);
 assert.equal(director.meta.collaboration.director_weight,1.5);
});
const {filterView:fiveLayerView}=require('../web/explorer.cjs');
test('source and song switches independently filter content without changing facts',()=>{
 const nodes=[{id:'a',core:true},{id:'b',core:true}],edges=['2','3'].map(category=>({id:category,source:'a',target:'b',type:'content',category,similarity:.8,shared_tag_count:2,distinct_work_tag_support:1}));
 assert.deepEqual(fiveLayerView(nodes,edges,{source:false}).edges.map(e=>e.category),['2']);
 assert.deepEqual(fiveLayerView(nodes,edges,{song:false}).edges.map(e=>e.category),['3']);
 assert.equal(fiveLayerView(nodes,edges,{song:false,source:false}).edges.length,0);
 assert.equal(edges.length,2);
});
