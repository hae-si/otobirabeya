const fs=require('fs'),crypto=require('crypto');
const {unifiedPartition}=require('./unified-algorithm.cjs');
const dir=process.argv[2],graph=JSON.parse(fs.readFileSync(dir+'/graph.json')),raw=fs.readFileSync(dir+'/content-graph.json'),content=JSON.parse(raw);
require('./language-scope.cjs').classifyLanguage(graph,content.edges);
require('./collaboration-cosine.cjs').applyCollaborationCosine(graph);
if(content.meta.available||graph.additional_edges?.length||graph.interaction_edges?.length){
 const additionalEdges=graph.additional_edges||[],interactionEdges=graph.interaction_edges||[],result=unifiedPartition(graph.nodes,graph.edges,content.edges,{additionalEdges,interactionEdges});
 graph.meta.legacy_baseline={community_count:graph.meta.community_count,modularity:graph.meta.modularity,formula:graph.meta.formula};
 const layout=require('./unified-layout.cjs').layoutUnified(graph.nodes,graph.edges,content.edges,result.parameters,{additionalEdges,interactionEdges});
 const legacy=unifiedPartition(graph.nodes,graph.edges,content.edges,{contentEnabled:false});
 for(const node of graph.nodes){node.legacy_community=legacy.communities[node.id]??null;node.community=result.communities[node.id];node.macro_community=result.macroCommunities[node.id];node.community_status=result.statuses[node.id];node.provisional_community=result.provisional[node.id]??null;Object.assign(node,layout.positions[node.id]);}
 graph.meta.layout=layout.meta;
 graph.meta.community_count=result.count;graph.meta.modularity=result.score.total;
 graph.meta.algorithm={version:result.version,parameters:result.parameters,score:result.score,history:result.history,macro_score:result.macroScore,refinements:result.refinements,fragment_attachments:result.fragmentAttachments,annotation_moves:result.annotationMoves,connectivity_splits:result.connectivitySplits,community_connectivity:result.communityConnectivity,objective_scope:result.objectiveScope,
   content_input_sha256:crypto.createHash('sha256').update(raw).digest('hex'),interaction_input_sha256:fs.existsSync(dir+'/interaction.json')?crypto.createHash('sha256').update(fs.readFileSync(dir+'/interaction.json')).digest('hex'):null,eligible_content_edges:result.eligibleContentEdges,content_rule:result.contentRule};
 graph.meta.formula='sum_l lambda_l Q_l; independent configuration null model per layer; directed following/interaction; symmetric collaboration/song/source/additional arcs; additional is artificial';
 fs.writeFileSync(dir+'/graph.json',JSON.stringify(graph));
 console.log(JSON.stringify({algorithm:result.version,groups:result.count,eligibleContentEdges:result.eligibleContentEdges,score:result.score.total}));
}
