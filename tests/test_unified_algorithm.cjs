const {test}=require('node:test'),assert=require('node:assert/strict');
const {unifiedPartition,DEFAULT,splitDisconnectedCommunities}=require('../web/unified-algorithm.cjs');
const {makeGraph,partition}=require('../web/network-analysis.cjs');
const nodes=['a','b','c','d'].map(id=>({id}));
const social=[{id:'c',source:'a',target:'b',type:'creation',weight:1}];
const content=[{id:'song',source:'b',target:'c',category:'2',similarity:.8,shared_tag_count:2,distinct_work_tag_support:2}];
test('content defaults participate in independent objective with explicit budget',()=>{
 const r=unifiedPartition(nodes,social,content,{minCommunitySize:1,fragmentMergeSize:1});assert.equal(r.eligibleContentEdges,1);
 assert.equal(r.parameters.songShare,.25);assert.ok(Math.abs(Object.values(DEFAULT).slice(0,5).reduce((a,b)=>a+b,0)-1)<1e-12);
 assert.notEqual(r.communities.c,null);assert.equal(r.communities.d,null);
 assert.equal(r.score.contributions.find(l=>l.name==='song').q!==null,true);
});
test('content disabled reproduces old partition exactly',()=>{
 const r=unifiedPartition(nodes,social,content,{contentEnabled:false}),old=partition(makeGraph(nodes,social));
 assert.deepEqual(r.communities,old.communities);assert.equal(r.modularity,old.modularity);
});
test('single tags and same-work-only content cannot affect default grouping',()=>{
 const a=unifiedPartition(nodes,social,[]),b=unifiedPartition(nodes,social,[{...content[0],shared_tag_count:1},{...content[0],id:'same',distinct_work_tag_support:0}]);
 assert.deepEqual(a.communities,b.communities);assert.equal(b.eligibleContentEdges,0);
});
test('disconnected components inside one community are split deterministically',()=>{
 const three=[{id:'a'},{id:'b'},{id:'c'}],graph=makeGraph(three,[{id:'ab',source:'a',target:'b',type:'creation',weight:1}]);
 const labels={a:'0',b:'0',c:'0'},splits=splitDisconnectedCommunities(labels,[{name:'creation',graph,share:1}],three);
 assert.equal(splits.length,1);assert.equal(labels.a,'0');assert.equal(labels.b,'0');assert.notEqual(labels.c,'0');
 assert.deepEqual(splits[0].components.map(c=>c.size),[2,1]);
});
