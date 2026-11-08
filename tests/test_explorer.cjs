const {test}=require('node:test'),assert=require('node:assert/strict');
const {filterView:rawFilterView,statistics,csvTable}=require('../web/explorer.cjs');
const filterView=(nodes,edges,options={})=>rawFilterView(nodes,edges,{minimumStrength:0,density:8,...options});
const ns=[{id:'a',core:true,community:'1',macro_community:'m'},{id:'b',core:true,community:'2',macro_community:'m'},{id:'c',community:null,community_status:'small_sample'},{id:'d',community:null}];
const es=[{id:'c',source:'a',target:'b',type:'creation',weight:.4,event_ids:['w']},{id:'f',source:'a',target:'b',type:'follow',weight:1,mutual:false},{id:'s',source:'a',target:'b',type:'content',category:'3',weight:.7,similarity:.7,shared_tag_count:2,distinct_work_tag_support:1,confidence_flags:[]},{id:'weak',source:'c',target:'d',type:'content',category:'2',weight:1,similarity:1,shared_tag_count:1,distinct_work_tag_support:0,confidence_flags:['single_shared_tag']}];
test('independent thresholds, grouping and unknowns do not mutate facts',()=>{
 const before=JSON.stringify([ns,es]);assert.equal(filterView(ns,es,{similarity:.8}).qualifying.edges.length,2);
 assert.equal(filterView(ns,es,{edgeMode:'within'}).edges.length,0);
 assert.equal(filterView(ns,es,{edgeMode:'within',groupMode:'macro_community'}).edges.length,3);
 assert.equal(filterView(ns,es,{groups:['1']}).nodes.length,1);
 assert.equal(filterView(ns,es,{scope:'all',weak:true,edgeMode:'within'}).edges.length,0);
 assert.equal(JSON.stringify([ns,es]),before);
});
test('drawing top-k leaves statistics population intact and layers separate',()=>{
 const extra={...es[0],id:'other',target:'c',weight:.2};
 const r=filterView(ns,[...es,extra],{scope:'all',density:1});assert.equal(r.qualifying.edges.length,4);
 const a=statistics(r.nodes,r.qualifying.edges),b=statistics(r.nodes,r.edges);assert.ok(a.layers.creation>=b.layers.creation);
 assert.deepEqual(a.layers,{creation:2,follow:1,song:0,source:1,interaction:0});
});
test('follow statistics deduplicate directions and calculate observed reciprocity',()=>{
 const r=statistics(ns,[es[1],{...es[1],id:'anotherAccount'},{...es[1],id:'reverse',source:'b',target:'a'}]);
 assert.equal(r.layers.follow,2);assert.equal(r.duplicateAccountDirections,1);assert.equal(r.rows[0].observed_reciprocity,1);
 assert.deepEqual(statistics([],[]).layers,{creation:0,follow:0,song:0,source:0,interaction:0});
});
test('neighbors expand only selected depth and preserve endpoint integrity',()=>{
 const more={...es[0],id:'bc',source:'b',target:'c'};
 const a=filterView(ns,[...es,more],{scope:'all',neighbors:true,selected:'a',depth:1});assert.deepEqual(a.nodes.map(n=>n.id),['a','b']);
 const b=filterView(ns,[...es,more],{scope:'all',neighbors:true,selected:'a',depth:2});assert.deepEqual(b.nodes.map(n=>n.id),['a','b','c']);
});
test('CSV escapes quotes and spreadsheet-like names without altering numeric metrics',()=>{
 const csv=csvTable([{label:'=1+2',score:-1},{label:'a"b',score:null}],['label','score']);
 assert.ok(csv.includes('"\'=1+2"'));assert.ok(csv.includes('"a""b"'));assert.ok(csv.includes('"-1"'));
});

test('unified display threshold applies to creation, content, follows; hidden backend relations never enter browsing or statistics',()=>{
 const nodes=['a','b','c'].map(id=>({id,core:true}));
 const edges=[{id:'low',source:'a',target:'b',type:'creation',weight:.1},{id:'high',source:'a',target:'c',type:'creation',weight:10},
  {id:'song-low',source:'a',target:'b',type:'content',category:'2',similarity:.1,shared_tag_count:2,distinct_work_tag_support:1},
  {id:'song-high',source:'a',target:'c',type:'content',category:'2',similarity:.9,shared_tag_count:2,distinct_work_tag_support:1},
  {id:'oneway',source:'a',target:'b',type:'follow',weight:1},
  {id:'mutual',source:'b',target:'c',type:'follow',weight:1,mutual:true},
  {id:'egg',source:'a',target:'b',type:'additional',weight:1000}];
 const before=JSON.stringify(edges),r=rawFilterView(nodes,edges);
 assert.deepEqual(r.qualifying.edges.map(e=>e.id),['high','song-high','oneway','mutual']);
 assert.equal(rawFilterView(nodes,edges,{minimumStrength:0}).qualifying.edges.length,6);
 assert.equal(rawFilterView(nodes,edges,{groups:[]}).strengths.get('high'),1);
 assert.equal(rawFilterView(nodes,edges,{minimumStrength:.99}).qualifying.edges.length,4);
 const stats=statistics(nodes,edges);assert.equal(stats.layers.additional,undefined);assert.equal(stats.rows[0].creation_strength,10.1);assert.equal(stats.rows[0].follow_out,1);
 assert.equal(rawFilterView(nodes,edges).qualifying.edges.some(e=>e.type==='additional'),false);
 assert.equal(JSON.stringify(edges),before);
});

test('display ranks use full input and retain ties independently of scope',()=>{
 const nodes=[{id:'a',core:true},{id:'b',core:true},{id:'c',core:false}];
 const edges=[{id:'weak',source:'a',target:'b',type:'creation',weight:1},{id:'strong',source:'a',target:'c',type:'creation',weight:10}];
 assert.equal(rawFilterView(nodes,edges).qualifying.edges.length,0);
 assert.equal(rawFilterView(nodes,edges,{scope:'all'}).qualifying.edges.length,1);
 const ties=edges.map(e=>({...e,weight:1}));assert.equal(rawFilterView(nodes,ties,{scope:'all'}).qualifying.edges.length,2);
});
