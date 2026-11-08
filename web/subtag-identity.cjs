const MAX_CHILDREN = 3;

function subtagIdentityLinks(dataset = {}) {
	const creators = new Set(Object.keys(dataset.creators || {}).map(String));
	const byParent = new Map();
	for (const relation of dataset.tag_relations || []) {
		const parent = String(relation.canonical_parent_id ?? relation.parent_id ?? '');
		const child = String(relation.canonical_tag_id ?? relation.tag_id ?? '');
		if (!parent || !child || parent === child || !creators.has(parent) || !creators.has(child)) continue;
		if (!byParent.has(parent)) byParent.set(parent, new Set());
		byParent.get(parent).add(child);
	}
	const links = [];
	for (const [parent, children] of [...byParent].sort((a, b) => Number(a[0]) - Number(b[0]))) {
		if (children.size > MAX_CHILDREN) continue;
		const ids = [parent, ...[...children].sort((a, b) => Number(a) - Number(b) || a.localeCompare(b, 'en', {numeric: true}))];
		links.push({basis: 'user_subtag_parent_3_or_fewer', ids: ids.map(id => 'otodb:' + id),
			evidence: {parent_id: parent, child_ids: [...children], child_count: children.size}});
	}
	return links;
}

module.exports = {MAX_CHILDREN, subtagIdentityLinks};
