const fs=require('fs'),crypto=require('crypto');
const {unifiedPartition,VERSION,DEFAULT}=require('./unified-algorithm.cjs');
const {ari,followRanking,makeGraph,partition}=require('./network-analysis.cjs');
const {nmi}=require('./partition-metrics.cjs');
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
const raw=fs.readFileSync(process.argv[2]),data=JSON.parse(raw),cr=fs.readFileSync(process.argv[3]),content=JSON.parse(cr),runs=[];
const production=Object.fromEntries(data.nodes.map(n=>[n.id,n.community]));
let baseline;const defaultContent=DEFAULT.songShare+DEFAULT.sourceShare;
const layerOptions={interactionEdges:data.interaction_edges||[],additionalEdges:data.additional_edges||[]};
for(const share of [0,.15,defaultContent,.6,1])for(const seed of [42,123,2026]){
 const start=performance.now(),r=unifiedPartition(data.nodes,data.edges,content.edges,{...layerOptions,creationShare:(1-share)*DEFAULT.creationShare/(1-defaultContent),followShare:(1-share)*DEFAULT.followShare/(1-defaultContent),songShare:share*DEFAULT.songShare/defaultContent,sourceShare:share*DEFAULT.sourceShare/defaultContent,seed});
 if(share===defaultContent&&seed===42)baseline=r;
 runs.push({contentShare:share,seed,count:r.count,score:r.score,communities:r.communities,elapsedMs:performance.now()-start,ariToProduction:ari(production,r.communities),nmiToProduction:nmi(production,r.communities)});
}
if(data.nodes.some(n=>baseline.communities[n.id]!==n.community))throw Error('Production partition differs from shared algorithm');
const repeated=unifiedPartition(data.nodes,data.edges,content.edges,layerOptions);
if(JSON.stringify(repeated.communities)!==JSON.stringify(baseline.communities))throw Error('Repeated partition differs');
const ranking=followRanking(data.nodes,data.edges);
if(data.nodes.some(n=>Math.abs((n.pagerank||0)-(ranking.scores[n.id]||0))>1e-12))throw Error('PageRank differs');
const legacy=unifiedPartition(data.nodes,data.edges,content.edges,{contentEnabled:false});
if(data.nodes.some(n=>legacy.communities[n.id]!==n.legacy_community))throw Error('Legacy baseline not reproducible');
const creationOnly=partition(makeGraph(data.nodes,data.edges.filter(e=>e.type==='creation')));
const memberships=new Map();for(const n of data.nodes){if(n.community==null||creationOnly.communities[n.id]==null)continue;if(!memberships.has(n.community))memberships.set(n.community,new Map());const m=memberships.get(n.community),c=creationOnly.communities[n.id];m.set(c,(m.get(c)||0)+1);}
const keyAuthors=data.nodes.filter(n=>n.pagerank!=null).sort((a,b)=>b.pagerank-a.pagerank).slice(0,20).map(n=>({id:n.id,label:n.label,pagerank:n.pagerank,legacyCommunity:n.legacy_community,community:n.community,seedCommunities:runs.filter(r=>r.contentShare===defaultContent).map(r=>({seed:r.seed,community:r.communities[n.id]}))}));
for(const author of keyAuthors){const node=data.nodes.find(n=>n.id===author.id),oldSet=new Set(data.nodes.filter(n=>node.legacy_community!=null&&n.legacy_community===node.legacy_community).map(n=>n.id)),newSet=new Set(data.nodes.filter(n=>node.community!=null&&n.community===node.community).map(n=>n.id));author.legacyMembershipJaccard=oldSet.size||newSet.size?[...oldSet].filter(id=>newSet.has(id)).length/new Set([...oldSet,...newSet]).size:null;}
const seedStability=[0,.15,defaultContent,.6,1].map(share=>{const group=runs.filter(r=>r.contentShare===share);return {contentShare:share,pairs:group.flatMap((a,i)=>group.slice(i+1).map(b=>({seeds:[a.seed,b.seed],ari:ari(a.communities,b.communities),nmi:nmi(a.communities,b.communities)})))};});
const sourceFiles=['unified-algorithm.cjs','unified-layout.cjs','multilayer-partition.cjs','layer-objective.cjs','author-follow.cjs','network-analysis.cjs'];
const result={version:VERSION,input_sha256:hash(raw),content_sha256:hash(cr),source_sha256:Object.fromEntries(sourceFiles.map(f=>[f,hash(fs.readFileSync(__dirname+'/'+f))])),
 verified:{productionMatches:true,repeatedPartitionIdentical:true,pageRankUnchanged:true,legacyReproducible:true},
 runs,seedStability,keyAuthors,creationCommunityComposition:[...memberships].map(([community,groups])=>({community,creationGroups:[...groups]})),
 notes:['Composition is a bridge diagnostic, not proof a merge is unreasonable','Seed community IDs are arbitrary; compare ARI/NMI and composition, not numeric labels','Content weights and support threshold are engineering choices, not validated optimum'],peakRssBytes:process.resourceUsage().maxRSS*1024};
fs.writeFileSync(process.argv[4],JSON.stringify(result));console.log(JSON.stringify({verified:result.verified,seedStability,peakRssBytes:result.peakRssBytes}));
