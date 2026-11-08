const {mergeIdentities} = require('./exact-name-identity.cjs');
const {sharedAccountGroups} = require('./shared-account-identity.cjs');
function resolve({nodes, redirects = {}, creators = [], accounts = []}) {
	const candidates = nodes.map(node => ({id: node.id, label: node.label, otodb_id: node.otodb_id})), ids = new Set(candidates.map(node => node.id));
	for (const creator of creators) {
		const id = 'otodb:' + creator.id, existing = redirects[id] || id;
		if (ids.has(id) || ids.has(existing)) continue;
		candidates.push({id, label: creator.name, otodb_id: creator.id});
		ids.add(id);
	}
	const creatorIds = [...new Set(candidates.map(node => node.otodb_id).filter(Boolean).map(String))];
	const links = sharedAccountGroups({accounts, creatorIds}).map(group => ({basis: 'shared_platform_account',
		ids: group.creator_ids.map(id => 'otodb:' + id), evidence: {site: group.site, content_id: group.content_id}}));
	const merged = mergeIdentities(candidates, links);
	const result = {...redirects, ...merged.meta.redirects};
	for (const id of Object.keys(result)) {
		let target = result[id];
		const seen = new Set([id]);
		while (result[target]) {
			if (seen.has(target)) throw Error('Identity redirect cycle');
			seen.add(target);
			target = result[target];
		}
		result[id] = target;
	}
	return result;
}
if (require.main === module) {
	const fs = require('fs');
	process.stdout.write(JSON.stringify(resolve(JSON.parse(fs.readFileSync(0, 'utf8')))));
}
module.exports = {resolve};
