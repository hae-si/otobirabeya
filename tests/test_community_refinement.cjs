const {test}=require('node:test'),assert=require('node:assert/strict');
const {unifiedPartition}=require('../web/unified-algorithm.cjs');
const {layoutUnified}=require('../web/unified-layout.cjs');
test('large macro group refines without forcing small supported groups together',()=>{
 const nodes=Array.from({length:12},(_,i)=>({id:String(i),language_class:'inferred_chinese'})),edges=[];
 for(let i=0;i<12;i++)for(let j=i+1;j<12;j++)edges.push({id:i+':'+j,source:String(i),target:String(j),type:'creation',weight:Math.floor(i/4)===Math.floor(j/4)?1:.01});
 const r=unifiedPartition(nodes,edges,[],{resolution:.01,localResolution:1,refineChineseThreshold:8,minCommunitySize:3,fragmentMergeSize:3});
 assert.equal(r.refinements.length,1);assert.equal(new Set(Object.values(r.macroCommunities)).size,1);assert.equal(r.count,3);
 assert.equal(r.communities['0'],r.communities['3']);assert.notEqual(r.communities['0'],r.communities['4']);
});
test('small connected group retains a community and explicit limited-support status',()=>{
 const ns=[{id:'a'},{id:'b'}],es=[{id:'e',source:'a',target:'b',type:'creation',weight:1}];
 const r=unifiedPartition(ns,es,[]);assert.equal(r.count,0);assert.equal(r.statuses.a,'small_sample');assert.equal(r.communities.a,r.communities.b);assert.notEqual(r.provisional.a,undefined);assert.equal(es.length,1);
});

test('large non-core group also refines; all empirically connected nodes get assignments',()=>{
 const nodes=Array.from({length:12},(_,i)=>({id:String(i)})),edges=[];
 for(let i=0;i<12;i++)for(let j=i+1;j<12;j++)edges.push({id:i+':'+j,source:String(i),target:String(j),type:'creation',weight:Math.floor(i/4)===Math.floor(j/4)?1:.01});
 nodes.push({id:'isolated'});
 const r=unifiedPartition(nodes,edges,[],{resolution:.01,localResolution:1,refineTotalThreshold:8,minCommunitySize:3,fragmentMergeSize:3});
 assert.equal(r.refinements.length,1);assert.equal(r.count,3);assert.equal(r.communities.isolated,null);
 assert.ok(nodes.filter(n=>n.id!=='isolated').every(n=>r.communities[n.id]!=null));
});

test('fragment attachment follows incoming or outgoing evidence and does not split a fragment',()=>{
 const {attachFragments}=require('../web/community-support.cjs'),{makeGraph}=require('../web/network-analysis.cjs');
 const nodes=['a','b','c','d','e','f','isolated'].map(id=>({id})),labels={a:'small',b:'small',c:'large',d:'large',e:'large',f:'separate',isolated:null};
 const graph=makeGraph(nodes,[{id:'incoming',source:'c',target:'a',type:'follow',weight:1}]);
 const moves=attachFragments(nodes,labels,[{name:'following',share:1,graph}],3);
 assert.equal(moves.length,1);assert.equal(labels.a,'large');assert.equal(labels.b,'large');assert.equal(labels.f,'separate');assert.equal(labels.isolated,null);
});

test('well-connected authors cannot be stranded in a tiny artificial-linked fragment',()=>{
 const nodes=Array.from({length:80},(_,i)=>({id:'n'+i})).concat([{id:'a'},{id:'b'}]),edges=[];
 for(let i=0;i<80;i++)for(let j=i+1;j<80;j++)if(Math.floor(i/40)===Math.floor(j/40))edges.push({id:i+':'+j,source:'n'+i,target:'n'+j,type:'creation',weight:1});
 for(let i=0;i<20;i++)edges.push({id:'in:'+i,source:'n'+i,target:'a',type:'follow',weight:1});
 for(let i=0;i<8;i++)edges.push({id:'out:'+i,source:'b',target:'n'+i,type:'follow',weight:1});
 const r=unifiedPartition(nodes,edges,[],{additionalEdges:[{id:'pair',source:'a',target:'b',weight:1000}]});
 assert.equal(r.statuses.a,'assigned');assert.equal(r.statuses.b,'assigned');
 for(const id of ['a','b'])assert.ok(Object.values(r.communities).filter(g=>g===r.communities[id]).length>=8);
});
test('content-only connected nodes participate in layout; source facts remain unchanged',()=>{
 const nodes=[{id:'a'},{id:'b'},{id:'c'}],content=[{id:'c',source:'a',target:'b',category:'3',similarity:.8,shared_tag_count:2,distinct_work_tag_support:1}],before=JSON.stringify(nodes);
 const r=layoutUnified(nodes,[],content,undefined,{iterations:20});assert.equal(r.meta.contentOnlyConnected,2);assert.equal(r.meta.edges,1);assert.equal(JSON.stringify(nodes),before);
 assert.ok(Object.values(r.positions).every(p=>Number.isFinite(p.x)&&Number.isFinite(p.y)));
 assert.deepEqual(r,layoutUnified(nodes,[],content,undefined,{iterations:20}));
});
