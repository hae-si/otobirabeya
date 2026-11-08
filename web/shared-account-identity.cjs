function sharedAccountGroups({accounts = [], creatorIds = null} = {}) {
	const known = creatorIds ? new Set(creatorIds.map(String)) : null;
	const owners = new Map();
	for (const account of accounts) {
		const tag = String(account.tag_id);
		if (known && !known.has(tag)) continue;
		const content = String(account.content_id ?? '');
		if (!content) continue;
		const key = String(account.site) + '\0' + content;
		if (!owners.has(key)) owners.set(key, {site: String(account.site), content_id: content, creator_ids: new Set()});
		owners.get(key).creator_ids.add(tag);
	}
	const groups = [];
	for (const owner of owners.values()) {
		if (owner.creator_ids.size > 1) {
			groups.push({site: owner.site, content_id: owner.content_id,
				creator_ids: [...owner.creator_ids].sort((a, b) => Number(a) - Number(b) || a.localeCompare(b, 'en', {numeric: true}))});
		}
	}
	groups.sort((a, b) => a.site.localeCompare(b.site) || a.content_id.localeCompare(b.content_id) || a.creator_ids.join(',').localeCompare(b.creator_ids.join(',')));
	return groups;
}
function sharedAccountLinks(dataset = {}) {
	return sharedAccountGroups({accounts: dataset.accounts || [], creatorIds: Object.keys(dataset.creators || {})}).map(group => ({
		basis: 'shared_platform_account',
		ids: group.creator_ids.map(id => 'otodb:' + id),
		evidence: {site: group.site, content_id: group.content_id},
	}));
}
module.exports = {sharedAccountGroups, sharedAccountLinks};
