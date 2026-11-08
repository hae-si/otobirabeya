const FOREIGN_SITES = new Set(['1', '2', '4']);
const CHINESE_PLATFORMS = new Set(['bilibili', 'acfun']);
const NON_CHINESE_PLATFORMS = new Set(['niconico', 'youtube', 'soundcloud', 'twitter']);
const VERSION = 'account-platform-score-v1';

function platformOfNode(node) {
	if (node.primary_platform) return node.primary_platform;
	const counts = node.platform_counts || {};
	const entries = Object.entries(counts).filter(([, count]) => Number(count) > 0);
	if (!entries.length) return 'none';
	const top = Math.max(...entries.map(([, count]) => Number(count)));
	const tops = entries.filter(([, count]) => Number(count) === top).map(([platform]) => platform);
	return tops.length === 1 ? tops[0] : 'tie';
}

function classifyLanguage(graph) {
	const counts = {inferred_chinese: 0, inferred_non_chinese: 0};
	const bases = {};
	const scores = {};
	let bilibiliAccounts = 0;
	for (const node of graph.nodes) {
		const sites = new Set((node.account_sites || []).map(String));
		const hasBilibili = Boolean(node.has_bilibili_account || node.bilibili_uids?.length || sites.has('3'));
		const foreign = [...sites].filter(site => FOREIGN_SITES.has(site)).sort();
		const primary = platformOfNode(node);
		const score = (hasBilibili ? 2 : 0) - foreign.length +
			(CHINESE_PLATFORMS.has(primary) ? 2 : NON_CHINESE_PLATFORMS.has(primary) ? -2 : 0);
		node.language_score = score;
		node.language_class = score >= 1 ? 'inferred_chinese' : 'inferred_non_chinese';
		node.language_basis = hasBilibili ? 'bilibili_account'
			: score >= 1 ? 'platform_score_positive' : 'platform_score_non_positive';
		node.language_evidence = {bilibili_account: hasBilibili, foreign_account_count: foreign.length,
			foreign_sites: foreign, primary_platform: primary, score};
		counts[node.language_class] += 1;
		bases[node.language_basis] = (bases[node.language_basis] || 0) + 1;
		scores[score] = (scores[score] || 0) + 1;
		if (hasBilibili) bilibiliAccounts += 1;
	}
	graph.meta.language = {
		version: VERSION,
		neighbor_ratio_enabled: false,
		node_threshold: 1,
		threshold_comparison: 'score>=1 => inferred_chinese; score<=0 => inferred_non_chinese',
		score_weights: {bilibili_account: 2, foreign_account: -1, chinese_platform: 2, non_chinese_platform: -2},
		account_evidence: {foreign_sites: [...FOREIGN_SITES], note: 'distinct non-Chinese account platforms, not rows'},
		platform_evidence: {chinese: [...CHINESE_PLATFORMS], non_chinese: [...NON_CHINESE_PLATFORMS],
			source: 'otodb worksource platform, primary by work count; role-missing works included; thanks/citation not special-cased'},
		bilibili_account_count: bilibiliAccounts,
		chinese_scope_count: graph.nodes.filter(node => node.chinese_scope).length,
		classification_counts: counts,
		basis_counts: bases,
		score_distribution: scores,
		threshold_basis: 'account and primary work platform score',
		caution: 'inferred community scope, not verified nationality or mother tongue'
	};
}
module.exports = {classifyLanguage, VERSION, FOREIGN_SITES, CHINESE_PLATFORMS, NON_CHINESE_PLATFORMS};
