const {test}=require('node:test'),assert=require('node:assert/strict');
const {mergeIdentities}=require('../web/exact-name-identity.cjs');
const {sharedAccountGroups}=require('../web/shared-account-identity.cjs');

test('shared platform account groups include dead and website accounts',()=>{
	const groups=sharedAccountGroups({accounts:[
		{tag_id:'4',site:'3',content_id:'900',dead:'f'},
		{tag_id:'5',site:'3',content_id:'900',dead:'f'},
		{tag_id:'6',site:'1',content_id:'n',dead:'t'},
		{tag_id:'7',site:'1',content_id:'n',dead:'f'},
		{tag_id:'8',site:'0',content_id:'https://example.test/@a',dead:'f'},
		{tag_id:'9',site:'0',content_id:'https://example.test/@a',dead:'t'},
	],creatorIds:['4','5','6','7','8','9']});
	assert.deepEqual(groups,[
		{site:'0',content_id:'https://example.test/@a',creator_ids:['8','9']},
		{site:'1',content_id:'n',creator_ids:['6','7']},
		{site:'3',content_id:'900',creator_ids:['4','5']},
	]);
});

test('shared-account links merge transitively with deterministic canonical choice and provenance',()=>{
	const nodes=[
		{id:'otodb:3',otodb_id:'3',label:'Three',chinese_scope:false,accounts:[]},
		{id:'otodb:2',otodb_id:'2',label:'Two',chinese_scope:true,accounts:[{id:'a'}]},
		{id:'otodb:1',otodb_id:'1',label:'One',chinese_scope:false,accounts:[]},
	];
	const result=mergeIdentities(nodes,[
		{basis:'shared_platform_account',ids:['otodb:2','otodb:3'],evidence:{site:'1',content_id:'x'}},
		{basis:'shared_platform_account',ids:['otodb:1','otodb:3'],evidence:{site:'2',content_id:'y'}},
	]);
	assert.equal(result.nodes.length,1);
	const node=result.nodes[0];
	assert.equal(node.id,'otodb:1');
	assert.equal(node.label,'One');
	assert.equal(node.chinese_scope,true);
	assert.deepEqual(node.otodb_ids,['1','2','3']);
	assert.deepEqual(node.accounts,[{id:'a'}]);
	assert.ok(node.identity_merge_bases.includes('shared_platform_account'));
	assert.equal(node.identity_shared_accounts.length,2);
	assert.deepEqual(result.meta.redirects,{'otodb:2':'otodb:1','otodb:3':'otodb:1'});
});

test('exact-name and shared-account rules combine in one merge',()=>{
	const nodes=[
		{id:'otodb:1',otodb_id:'1',label:'Same',chinese_scope:false,accounts:[]},
		{id:'social:x',label:'Same',chinese_scope:true,accounts:[{id:'u'}]},
		{id:'otodb:2',otodb_id:'2',label:'Other',chinese_scope:false,accounts:[]},
	];
	const result=mergeIdentities(nodes,[{basis:'shared_platform_account',ids:['otodb:1','otodb:2'],evidence:{site:'3',content_id:'9'}}]);
	assert.equal(result.nodes.length,1);
	assert.deepEqual(result.nodes[0].source_node_ids,['otodb:1','otodb:2','social:x']);
	assert.deepEqual(result.nodes[0].identity_merge_bases.sort(),['shared_platform_account','user_exact_display_name']);
	assert.equal(result.meta.groups.length,1);
});

test('links to creators absent from this graph are ignored',()=>{
	const nodes=[{id:'otodb:1',otodb_id:'1',label:'One',chinese_scope:false,accounts:[]}];
	const result=mergeIdentities(nodes,[{basis:'shared_platform_account',ids:['otodb:1','otodb:9'],evidence:{site:'1',content_id:'x'}}]);
	assert.equal(result.nodes.length,1);
	assert.deepEqual(result.meta.redirects,{});
});
