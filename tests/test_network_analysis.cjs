const {test}=require('node:test'),assert=require('node:assert/strict'),{makeGraph,partition,ari,pageRank,applyInteractionRanking}=require('../web/network-analysis.cjs');
const nodes=[{id:'a'},{id:'b'},{id:'isolated'},{id:'bot',accounts:[{isBot:true}]}],e={id:'f',source:'a',target:'b',type:'follow',weight:1};
test('duplicates not counted twice; no mutation',()=>{const before=JSON.stringify(nodes);assert.equal(makeGraph(nodes,[e,e]).size,1);assert.equal(JSON.stringify(nodes),before);});
test('zero-edge layers and isolates are explicit',()=>{const r=partition(makeGraph(nodes,[]));assert.equal(r.count,0);assert.equal(r.communities.isolated,null);});
test('single available layer has unit mass',()=>{const g=makeGraph(nodes,[e]);assert.equal(g.getEdgeAttribute('a','b','weight'),1);});
test('symmetric creation plus directed follow normalized per layer',()=>{const c={id:'c',source:'b',target:'a',type:'creation',weight:2};const g=makeGraph(nodes,[e,c]);let sum=0;g.forEachEdge((k,a)=>sum+=a.weight);assert.equal(sum,1);assert.equal(g.getEdgeAttribute('a','b','weight'),.75);});
test('PageRank converges, includes dangling nodes and sums to one',()=>{const r=pageRank(makeGraph(nodes,[e]));assert.ok(r.residual<1e-12);assert.ok(Math.abs(Object.values(r.scores).reduce((a,b)=>a+b,0)-1)<1e-10);assert.ok(r.scores.b>r.scores.a);});
test('explicit bots only are excluded; unknown accounts retained',()=>{const g=makeGraph(nodes,[e],{excludeBots:true});assert.equal(g.order,3);assert.ok(g.hasNode('isolated'));});
test('missing endpoints and conflicting IDs fail',()=>{assert.throws(()=>makeGraph(nodes,[{...e,target:'missing'}]));assert.throws(()=>makeGraph(nodes,[e,{...e,weight:2}]));});
test('ARI ignores group label numbering',()=>assert.equal(ari({a:0,b:0,c:1},{a:8,b:8,c:9}),1));

test('interaction PageRank uses eligible distinct-video weights and excludes isolates',()=>{
 const graph={nodes:['source','heavy','light','excluded'].map(id=>({id,pagerank:.1})),meta:{},interaction_edges:[
  {id:'a',source:'source',target:'heavy',analysis_weight:3,analysis_enabled:true,weight:3},
  {id:'b',source:'source',target:'light',analysis_weight:1,analysis_enabled:true,weight:10},
  {id:'c',source:'heavy',target:'excluded',analysis_weight:10,analysis_enabled:false,weight:10},
 ]};
 applyInteractionRanking(graph);
 const [source,heavy,light,excluded]=graph.nodes;
 assert.ok(heavy.interaction_pagerank>light.interaction_pagerank);
 assert.ok(light.interaction_pagerank>source.interaction_pagerank);
 assert.equal(excluded.interaction_pagerank,null);
 assert.ok(Math.abs(source.interaction_pagerank+heavy.interaction_pagerank+light.interaction_pagerank-1)<1e-10);
 assert.ok(graph.nodes.every(node=>node.pagerank===.1));
});
