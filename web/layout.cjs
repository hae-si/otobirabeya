const fs=require('node:fs');
const {UndirectedGraph}=require('graphology');
const fa2=require('graphology-layout-forceatlas2');
const file=process.argv[2], data=JSON.parse(fs.readFileSync(file,'utf8'));
const graph=new UndirectedGraph();
const core=data.nodes.filter(n=>n.chinese_scope), degrees=new Map(core.map(n=>[n.id,0]));
for(const n of core){const i=graph.order,a=i*2.399963,r=Math.sqrt((i+.5)/core.length);graph.addNode(n.id,{x:Math.cos(a)*r,y:Math.sin(a)*r,size:2});}
for(const e of data.edges)if(graph.hasNode(e.source)&&graph.hasNode(e.target)){graph.addEdge(e.source,e.target,{weight:e.weights.affiliation});degrees.set(e.source,degrees.get(e.source)+1);degrees.set(e.target,degrees.get(e.target)+1);}
console.log(`ForceAtlas2: ${graph.order} core authors, ${graph.size} edges`);
fa2.assign(graph,{iterations:150,settings:{...fa2.inferSettings(graph),barnesHutOptimize:true,gravity:1,scalingRatio:8,slowDown:5,edgeWeightInfluence:.5}});
const connected=core.filter(n=>degrees.get(n.id)>0);
const xs=connected.map(n=>graph.getNodeAttribute(n.id,'x')),ys=connected.map(n=>graph.getNodeAttribute(n.id,'y'));
const cx=(Math.min(...xs)+Math.max(...xs))/2,cy=(Math.min(...ys)+Math.max(...ys))/2;
const scale=Math.max(Math.max(...xs)-Math.min(...xs),Math.max(...ys)-Math.min(...ys),1)/2;
let isolated=0;
for(const n of core){if(degrees.get(n.id)>0){n.x=(graph.getNodeAttribute(n.id,'x')-cx)/scale;n.y=(graph.getNodeAttribute(n.id,'y')-cy)/scale;}else{let a=isolated++*2.399963;n.x=Math.cos(a)*1.35;n.y=Math.sin(a)*1.35;}}
const positions=new Map(core.map(n=>[n.id,n]));
const neighborPositions=new Map();
for(const e of data.edges){const a=positions.get(e.source),b=positions.get(e.target);if(a&&!b){if(!neighborPositions.has(e.target))neighborPositions.set(e.target,[]);neighborPositions.get(e.target).push(a);}if(b&&!a){if(!neighborPositions.has(e.source))neighborPositions.set(e.source,[]);neighborPositions.get(e.source).push(b);}}
data.nodes.filter(n=>!n.chinese_scope).forEach((n,i)=>{const near=neighborPositions.get(n.id)||[];const a=i*2.399963;n.x=near.reduce((s,v)=>s+v.x,0)/(near.length||1)+.12*Math.cos(a);n.y=near.reduce((s,v)=>s+v.y,0)/(near.length||1)+.12*Math.sin(a);});
data.meta.layout='Graphology ForceAtlas2 / 150 iterations / full Chinese projection';
data.meta.isolated_core_authors=isolated;
fs.writeFileSync(file,JSON.stringify(data));
