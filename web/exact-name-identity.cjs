const POLICY = 'user-exact-display-name-shared-account-and-subtag-v4';
const PLACEHOLDER_LABELS = new Set(['账号已注销']);

function rawLabelOf(node) {
	return typeof node.label === 'string' && node.label.length ? node.label : null;
}
function labelOf(node) {
	const label = rawLabelOf(node);
	return label && !PLACEHOLDER_LABELS.has(label) ? label : null;
}

function compareNodes(a, b) {
	return Number(!a.otodb_id) - Number(!b.otodb_id) ||
		(a.otodb_id && b.otodb_id ? String(a.otodb_id).localeCompare(String(b.otodb_id), 'en', {numeric: true}) : a.id.localeCompare(b.id));
}

function mergePlatformEvidence(members) {
	const accountSites = new Set(), platformCounts = {};
	for (const member of members) {
		for (const site of member.account_sites || []) accountSites.add(String(site));
		for (const [platform, count] of Object.entries(member.platform_counts || {})) platformCounts[platform] = (platformCounts[platform] || 0) + Number(count || 0);
	}
	const entries = Object.entries(platformCounts).filter(([, count]) => count > 0);
	const top = entries.length ? Math.max(...entries.map(([, count]) => count)) : 0;
	const tops = entries.filter(([, count]) => count === top).map(([platform]) => platform).sort();
	return {account_sites: [...accountSites].sort(), platform_counts: platformCounts,
		primary_platform: tops.length === 1 ? tops[0] : tops.length > 1 ? 'tie' : 'none'};
}

function mergeIdentities(input, links = []) {
	const order = new Map(input.map((node, index) => [node.id, index]));
	const byId = new Map(input.map(node => [node.id, node]));
	const parent = new Map(input.map(node => [node.id, node.id]));
	const find = value => {
		while (parent.get(value) !== value) {
			parent.set(value, parent.get(parent.get(value)));
			value = parent.get(value);
		}
		return value;
	};
	const union = (a, b) => {
		const left = find(a), right = find(b);
		if (left !== right) parent.set(left, right);
	};
	const labels = new Map();
	for (const node of input) {
		const label = labelOf(node);
		if (!label) continue;
		if (!labels.has(label)) labels.set(label, []);
		labels.get(label).push(node.id);
	}
	for (const ids of labels.values()) {
		for (let index = 1; index < ids.length; index += 1) union(ids[0], ids[index]);
	}
	const effective = [];
	for (const link of links || []) {
		const ids = (link.ids || []).filter(id => byId.has(id));
		if (ids.length < 2) continue;
		for (let index = 1; index < ids.length; index += 1) union(ids[0], ids[index]);
		effective.push({...link, ids});
	}
	const components = new Map();
	for (const node of input) {
		const root = find(node.id);
		if (!components.has(root)) components.set(root, []);
		components.get(root).push(node);
	}
	const linksByRoot = new Map();
	for (const link of effective) {
		const root = find(link.ids[0]);
		if (!linksByRoot.has(root)) linksByRoot.set(root, []);
		linksByRoot.get(root).push(link);
	}
	const orderedComponents = [...components.values()].sort((a, b) =>
		Math.min(...a.map(node => order.get(node.id))) - Math.min(...b.map(node => order.get(node.id))));
	const nodes = [], redirects = new Map(), merged = [];
	for (const members of orderedComponents) {
		const ordered = members.slice().sort(compareNodes);
		const primary = ordered[0];
		for (const node of members) redirects.set(node.id, primary.id);
		if (members.length === 1) {
			nodes.push({...primary});
			continue;
		}
		const sharedLinks = linksByRoot.get(find(primary.id)) || [];
		const memberLabels = ordered.map(labelOf).filter(Boolean);
		const linkBases = new Set(sharedLinks.map(link => link.basis).filter(Boolean));
		const basis = [];
		if (memberLabels.length !== new Set(memberLabels).size) basis.push('user_exact_display_name');
		if (linkBases.has('shared_platform_account')) basis.push('shared_platform_account');
		if (linkBases.has('user_subtag_parent_3_or_fewer')) basis.push('user_subtag_parent_3_or_fewer');
		const accounts = new Map();
		for (const node of ordered) for (const account of node.accounts || []) accounts.set(account.id, account);
		const scopeNode = ordered.find(node => node.chinese_scope && node.scope) || primary;
		const platformEvidence = mergePlatformEvidence(ordered);
		const node = {
			...primary,
			chinese_scope: ordered.some(member => member.chinese_scope), has_bilibili_account: ordered.some(member => member.has_bilibili_account),
			...platformEvidence,
			accounts: [...accounts.values()],
			scope: scopeNode.scope,
			otodb_ids: [...new Set(ordered.map(member => member.otodb_id).filter(Boolean))],
			source_node_ids: ordered.map(member => member.id),
			identity_merge_basis: basis.join('+'),
			identity_merge_bases: basis,
			identity_members: ordered.map(member => ({id: member.id, label: member.label,
				otodb_id: member.otodb_id ?? null, url: member.url ?? null, scope: member.scope ?? null, chinese_scope: !!member.chinese_scope, has_bilibili_account: !!member.has_bilibili_account})),
			scope_evidence: ordered.flatMap(member => member.scope_evidence || []),
			pagerank: ordered.reduce((sum, member) => sum + (member.pagerank || 0), 0),
		};
		const sharedAccountLinks = sharedLinks.filter(link => link.basis === 'shared_platform_account');
		const subtagLinks = sharedLinks.filter(link => link.basis === 'user_subtag_parent_3_or_fewer');
		if (sharedAccountLinks.length) node.identity_shared_accounts = sharedAccountLinks.map(link => link.evidence);
		if (subtagLinks.length) node.identity_subtag_merges = subtagLinks.map(link => link.evidence);
		nodes.push(node);
		merged.push({canonical_id: primary.id, label: primary.label, source_node_ids: node.source_node_ids,
			bases: basis, shared_accounts: node.identity_shared_accounts || [], subtag_merges: node.identity_subtag_merges || []});
	}
	return {nodes, redirects, meta: {policy: POLICY, redirects: Object.fromEntries([...redirects].filter(([source, target]) => source !== target)), groups: merged}};
}

function mergeExactNames(input) {
	return mergeIdentities(input, []);
}

module.exports = {POLICY, PLACEHOLDER_LABELS, mergeIdentities, mergeExactNames};
