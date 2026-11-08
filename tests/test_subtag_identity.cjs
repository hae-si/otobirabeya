const {test}=require('node:test'),assert=require('node:assert/strict');
const {mergeIdentities}=require('../web/exact-name-identity.cjs');
const {subtagIdentityLinks}=require('../web/subtag-identity.cjs');
test('subtag links merge parents with at most three creator children and skip larger groups',()=>{
 const creators={1:{},2:{},3:{},4:{},5:{},6:{},7:{},8:{},9:{}};
 const rel=(parent,child)=>({canonical_parent_id:parent,canonical_tag_id:child});
 const dataset={creators,tag_relations:[rel(1,2),rel(1,3),rel(1,4),rel(5,6),rel(5,7),rel(5,8),rel(5,9)]};
 const links=subtagIdentityLinks(dataset);
 assert.equal(links.length,1);
 assert.deepEqual(links[0].ids,['otodb:1','otodb:2','otodb:3','otodb:4']);
 const nodes=[1,2,3,4,5,6,7,8,9].map(id=>({id:'otodb:'+id,otodb_id:String(id),label:'N'+id,
  account_sites:id===2?['3']:[],platform_counts:id===3?{bilibili:2}:{}}));
 const merged=mergeIdentities(nodes,links);
 assert.equal(merged.redirects.get('otodb:2'),'otodb:1');
 assert.equal(merged.redirects.get('otodb:4'),'otodb:1');
 assert.equal(merged.redirects.get('otodb:6'),'otodb:6');
 const node=merged.nodes.find(n=>n.id==='otodb:1');
 assert.deepEqual(node.account_sites,['3']);
 assert.deepEqual(node.platform_counts,{bilibili:2});
 assert.equal(node.primary_platform,'bilibili');
 assert.ok(node.identity_merge_bases.includes('user_subtag_parent_3_or_fewer'));
});
