const {test}=require('node:test'),assert=require('node:assert/strict');
const {selectInteractions}=require('../web/interaction-view.cjs');
test('statistics selection requires both endpoints and qualifying event evidence',()=>{
 const accounts={a:{label:'a',node_id:'A'},b:{label:'b',node_id:'B'},c:{label:'c',node_id:'C'}};
 const data={accounts,events:[{event_id:'ab',source_uid:'a',target_uid:'b'},{event_id:'ac',source_uid:'a',target_uid:'c'}]};
 assert.equal(selectInteractions(data,{nodeIds:new Set(['A','B'])}).count,1);
 assert.equal(selectInteractions(data,{nodeIds:new Set(['A','B']),eventIds:new Set()}).count,0);
 assert.equal(selectInteractions(data,{nodeIds:new Set(['A'])}).count,0);
});
test('interaction subtypes share a comment denominator; description excluded',()=>{
 const data={accounts:{a:{label:'Author A',creator_id:'A'},b:{label:'B',creator_id:'B'},alias:{label:'A alias',creator_id:'A'}},events:[
  {source_uid:'a',target_uid:'b',video_id:'1',rpid:'2',event_type:'video_comment',excerpt:'text'},
  {source_uid:'alias',target_uid:'b',video_id:'1',rpid:'2',event_type:'comment_mention',excerpt:'@B'},
  {source_uid:'a',target_uid:'b',video_id:'1',rpid:'',event_type:'description_mention',excerpt:'@B'}]};
 const r=selectInteractions(data);assert.equal(r.count,3);assert.equal(r.comments,1);assert.equal(r.sources,1);
 assert.equal(selectInteractions(data,{query:'AUTHOR A'}).count,2);
 assert.equal(selectInteractions(data,{type:'comment_mention'}).count,1);
 delete data.events[1].excerpt;
 assert.equal(selectInteractions(data,{query:'AUTHOR A'}).count,2);
 assert.equal(selectInteractions(data,{video:'missing'}).count,0);
});
test('unknown singleton is all-only; repeat is related without changing confirmed counts',()=>{
 const data={accounts:{a:{uid:'a',label:'A',creator_id:'A',identity_state:'confirmed',appearance_video_ids:['1']},
  b:{uid:'b',label:'repeat',creator_id:'b',identity_state:'unknown',scope:'related',appearance_video_ids:['1','2']},
  c:{uid:'c',label:'single',creator_id:'c',identity_state:'unknown',scope:'all',appearance_video_ids:['1']}},events:[],observed_events:[
   {source_uid:'a',target_uid:'b',video_id:'1',rpid:'2',event_type:'comment_mention',identity_state:'unknown',excerpt:'x'},
   {source_uid:'c',target_uid:'a',video_id:'1',rpid:'3',event_type:'video_comment',identity_state:'unknown',excerpt:'x'}]};
 assert.equal(selectInteractions(data).count,0);
 const related=selectInteractions(data,{scope:'related'});assert.equal(related.count,1);assert.equal(related.pendingCount,1);assert.equal(related.confirmedCount,0);assert.equal(related.users.length,2);
 assert.equal(selectInteractions(data,{scope:'all'}).count,2);
 assert.equal(selectInteractions(data,{scope:'all',video:'2'}).users.length,1);
 assert.throws(()=>selectInteractions(data,{scope:'invalid'}));
});
test('selected work publisher belongs to default scope even without comment appearances',()=>{
 const a={uid:'1',label:'publisher',creator_id:'p',identity_state:'unknown',scope:'core',appearance_video_ids:[],selected_publications:[{aid:'v'}]},b={uid:'2',label:'repeat',creator_id:'b',identity_state:'unknown',scope:'related',appearance_video_ids:['v','w']};
 const data={accounts:{1:a,2:b},events:[],observed_events:[{source_uid:'2',target_uid:'1',video_id:'v',rpid:'r',identity_state:'unknown',excerpt:'x'}]};
 const result=selectInteractions(data,{scope:'related',video:'v'});
 assert.equal(result.count,1);assert.equal(result.users.length,2);assert.equal(result.confirmedCount,0);
});
