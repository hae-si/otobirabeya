const {test}=require('node:test'),assert=require('node:assert/strict');
const {aggregateAuthorFollows,observationState}=require('../web/author-follow.cjs');
test('merged-author PageRank does not amplify repeated account directions',()=>{
 const {followRanking}=require('../web/network-analysis.cjs');
 const nodes=['a','b','c'].map(id=>({id,accounts:[{id}]}));
 const edges=[['1','b'],['2','b'],['3','c']].map(([id,target])=>({id,source:'a',target,type:'follow',weight:1}));
 const r=followRanking(nodes,edges);assert.equal(r.scores.b,r.scores.c);
});
test('binary author directions preserve multiple account evidence, reciprocity and self observations',()=>{
 const rows=[['1','a','b'],['2','a','b'],['3','b','a'],['4','a','a']].map(([id,source,target])=>({id,source,target,type:'follow',weight:1}));
 const r=aggregateAuthorFollows(rows.concat(rows[0]));assert.equal(r.edges.length,2);assert.equal(r.self_account_evidence.length,1);
 assert.ok(r.edges.every(e=>e.mutual&&e.weight===1));assert.equal(r.edges.find(e=>e.source==='a').account_edge_ids.length,2);
});
test('unknown, hidden, partial and complete lists have different implications',()=>{
 const coverage=[{user_id:'a',endpoint:'following',state:'visible_list_exhausted'},{user_id:'c',endpoint:'following',state:'not_public_skipped'}];
 assert.equal(observationState(['a'],['b'],coverage),'known_no_observation');
 assert.equal(observationState(['a','c'],['b'],coverage),'unknown');
 assert.equal(observationState(['c'],['b'],coverage,true),'observed');
 assert.equal(observationState([],['b'],coverage),'unknown');
 assert.equal(observationState(['c'],['b'],coverage.concat({user_id:'b',endpoint:'followers',state:'visible_list_exhausted'})),'known_no_observation');
});
