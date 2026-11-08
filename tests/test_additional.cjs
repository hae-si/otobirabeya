const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),os=require('os'),path=require('path');
const {readAdditional}=require('../web/additional-relations.cjs');
const {unifiedPartition}=require('../web/unified-algorithm.cjs');
const {layoutUnified}=require('../web/unified-layout.cjs');
test('artificial relations validate endpoints and provenance; no label-based matching',()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'additional-')),file=path.join(dir,'relations.json'),nodes=[{id:'a'},{id:'b'}];
 const row={id:'egg',source:'a',target:'b',weight:1,basis:'user_requested_easter_egg',requested_at:'2026-10-30'};
 try{fs.writeFileSync(file,JSON.stringify([row]));assert.equal(readAdditional(file,nodes)[0].artificial,true);
  for(const bad of [{...row,target:'missing'},{...row,weight:1000},{...row,weight:-1},{...row,basis:'friendship'}]){fs.writeFileSync(file,JSON.stringify([bad]));assert.throws(()=>readAdditional(file,nodes));}
  fs.writeFileSync(file,JSON.stringify([row,row]));assert.throws(()=>readAdditional(file,nodes));
  fs.writeFileSync(file,JSON.stringify([{...row,source:'old:a',basis:'user_annotation',relation:'reviewed_link'}]));
  const aliases=[{id:'a',source_node_ids:['old:a']},{id:'b'}],resolved=readAdditional(file,aliases)[0];
  assert.equal(resolved.source,'a');assert.deepEqual(resolved.source_endpoints,['old:a','b']);assert.equal(resolved.relation,'reviewed_link');
  fs.writeFileSync(file,JSON.stringify([{...row,source:'old:a',target:'a'}]));assert.equal(readAdditional(file,aliases)[0].excluded_self,true);
 }finally{fs.rmSync(dir,{recursive:true});}
});

test('annotation aliases, self exclusions and bounded duplicate-pair budgets remain auditable',()=>{
 const {normalAdditional,makeLayers,DEFAULT}=require('../web/unified-algorithm.cjs');
 const nodes=[{id:'a'},{id:'b'},{id:'c'}],social=[{id:'e',source:'a',target:'b',type:'creation',weight:1}],one={id:'x',source:'b',target:'c',weight:1};
 const a=makeLayers(nodes,social,[],DEFAULT,[one]).at(-1),b=makeLayers(nodes,social,[],DEFAULT,[one,{...one,id:'duplicate',source:'c',target:'b'}]).at(-1);
 assert.equal(a.share,b.share);assert.equal(a.graph.size,b.graph.size);assert.equal(normalAdditional([{...one,source:'c'}]).length,0);
 assert.equal(normalAdditional([{...one,analysis_enabled:false}]).length,0);
 const {scoreLayers}=require('../web/layer-objective.cjs'),layers=makeLayers(nodes,social,[],DEFAULT,[one]);
 const share=scoreLayers(layers,{a:'1',b:'1',c:'2'}).contributions.find(l=>l.name==='additional').effectiveShare;assert.ok(share<=DEFAULT.additionalShare+1e-12);
});
test('additional layer influences partition and layout, empirical-only result is reproducible',()=>{
 const nodes=['a','b','c','d'].map(id=>({id})),social=[{id:'ab',source:'a',target:'b',type:'creation',weight:1},{id:'cd',source:'c',target:'d',type:'creation',weight:1}],additionalEdges=[{id:'ac',source:'a',target:'c',type:'additional',weight:1}];
 const before=JSON.stringify([nodes,social]),options={minCommunitySize:1,fragmentMergeSize:1};
 const baseline=unifiedPartition(nodes,social,[],options),r=unifiedPartition(nodes,social,[],{...options,additionalEdges});
 assert.notEqual(baseline.communities.a,baseline.communities.c);assert.notEqual(r.communities.a,r.communities.c);
 assert.ok(Math.abs(r.score.contributions.find(l=>l.name==='additional').effectiveShare-.05)<1e-12);
 const layout=layoutUnified(nodes,social,[],r.parameters,{iterations:20,additionalEdges});assert.equal(layout.meta.additionalEdges,1);
 assert.ok(layout.meta.additionalSpringCap<=layout.meta.maxEmpiricalSpring*2);
 assert.deepEqual(layout,layoutUnified(nodes,social,[],{...r.parameters,additionalShare:.8},{iterations:20,additionalEdges}));
 assert.ok(Object.values(layout.positions).every(p=>Number.isFinite(p.x)&&Number.isFinite(p.y)));
 assert.deepEqual(unifiedPartition(nodes,social,[],options).communities,baseline.communities);assert.equal(JSON.stringify([nodes,social]),before);
});

test('ordinary annotations cannot repartition authors outside their endpoints',()=>{
 const nodes=Array.from({length:12},(_,i)=>({id:String(i)})),edges=[];
 for(let i=0;i<12;i++)for(let j=i+1;j<12;j++)if(Math.floor(i/6)===Math.floor(j/6))edges.push({id:i+':'+j,source:String(i),target:String(j),type:'creation',weight:1});
 const base=unifiedPartition(nodes,edges,[],{minCommunitySize:1,fragmentMergeSize:1}),r=unifiedPartition(nodes,edges,[],{minCommunitySize:1,fragmentMergeSize:1,additionalEdges:[{id:'a',source:'0',target:'6',weight:1}]});
 for(const a of nodes.filter(n=>!['0','6'].includes(n.id)))for(const b of nodes.filter(n=>!['0','6'].includes(n.id)))assert.equal(base.communities[a.id]===base.communities[b.id],r.communities[a.id]===r.communities[b.id]);
 assert.ok(r.annotationMoves.every(m=>['0','6'].includes(m.id)));
});

test('warm local optimization respects fixed groups and improves the evaluated objective',()=>{
 const {partitionLayers}=require('../web/multilayer-partition.cjs'),{makeGraph}=require('../web/network-analysis.cjs'),{scoreLayers}=require('../web/layer-objective.cjs');
 const nodes=['a','b','c'].map(id=>({id})),graph=makeGraph(nodes,[{id:'ac',source:'a',target:'c',type:'creation',weight:10},{id:'bc',source:'b',target:'c',type:'creation',weight:10}]),layers=[{name:'test',graph,share:1}],initial={a:'left',b:'right',c:'right'},before=JSON.stringify(initial);
 const r=partitionLayers(layers,{initialCommunities:initial,movableNodes:new Set(['a']),contract:false,maxLevels:1});
 assert.equal(r.communities.a,r.communities.b);assert.equal(r.communities.b,r.communities.c);assert.ok(r.score.total>scoreLayers(layers,initial).total);assert.equal(JSON.stringify(initial),before);
});
