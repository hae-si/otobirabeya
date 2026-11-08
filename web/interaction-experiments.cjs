const fs=require('fs'),crypto=require('crypto');
const {unifiedPartition,makeLayers}=require('./unified-algorithm.cjs');
const {partitionDiagnostics}=require('./partition-diagnostics.cjs');
const {ari}=require('./network-analysis.cjs'),{nmi}=require('./partition-metrics.cjs');
const [graphPath,contentPath,outputPath,seedArg='42,123,2026',shareArg='0,0.05,0.1,0.2']=process.argv.slice(2);
const raw=fs.readFileSync(graphPath),contentRaw=fs.readFileSync(contentPath),graph=JSON.parse(raw),content=JSON.parse(contentRaw);
const seeds=seedArg.split(',').map(Number),shares=shareArg.split(',').map(Number),runs=[];let baseline;
const codeHashes=Object.fromEntries(['interaction-experiments.cjs','partition-diagnostics.cjs','unified-algorithm.cjs','multilayer-partition.cjs','network-analysis.cjs','community-support.cjs','layer-objective.cjs'].map(name=>[name,crypto.createHash('sha256').update(fs.readFileSync(require('path').join(__dirname,name))).digest('hex')]));
for(const seed of seeds)for(const share of shares){
 if(!(share>=0&&share<=.3)||!Number.isInteger(seed))throw Error('Invalid experimental parameter');
 const start=Date.now(),r=unifiedPartition(graph.nodes,graph.edges,content.edges,{interactionEdges:graph.interaction_edges||[],additionalEdges:graph.additional_edges||[],seed,
  interactionShare:share,creationShare:.35-share/2,followShare:.30-share/2,songShare:.05,sourceShare:.30});
 if(!baseline){if(share!==0)throw Error('First experiment must be the three-layer baseline');baseline=r;}
 const sizes=new Map();for(const group of Object.values(r.communities))if(group!=null)sizes.set(group,(sizes.get(group)||0)+1);
 const result={seed,interactionShare:share,algorithm:r.version,parameters:r.parameters,score:r.score,groups:r.count,
  largestGroup:Math.max(0,...sizes.values()),unassigned:Object.values(r.communities).filter(c=>c==null).length,
  ariToBaseline:ari(baseline.communities,r.communities),nmiToBaseline:nmi(baseline.communities,r.communities),milliseconds:Date.now()-start,
  diagnostics:partitionDiagnostics(graph.nodes,makeLayers(graph.nodes,graph.edges,content.edges,r.parameters,[],graph.interaction_edges||[]),r),
  communities:r.communities};runs.push(result);
 fs.writeFileSync(outputPath,JSON.stringify({complete:false,code_hashes:codeHashes,input_sha256:crypto.createHash('sha256').update(raw).digest('hex'),content_sha256:crypto.createHash('sha256').update(contentRaw).digest('hex'),runs},null,2));
 console.log(JSON.stringify({...result,communities:undefined,score:result.score.total,parameters:undefined}));
}
const stability=[];for(const share of shares){const selected=runs.filter(r=>r.interactionShare===share);for(let i=0;i<selected.length;i++)for(let j=i+1;j<selected.length;j++)stability.push({interactionShare:share,seeds:[selected[i].seed,selected[j].seed],ari:ari(selected[i].communities,selected[j].communities),nmi:nmi(selected[i].communities,selected[j].communities)});}
fs.writeFileSync(outputPath,JSON.stringify({complete:true,code_hashes:codeHashes,input_sha256:crypto.createHash('sha256').update(raw).digest('hex'),content_sha256:crypto.createHash('sha256').update(contentRaw).digest('hex'),runs,stability,meaning:'Selected catalog sensitivity; objective score alone does not establish correctness'},null,2));
