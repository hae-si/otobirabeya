import json
import unittest

from pipeline.audit_identity import audit, mapping_sha256


class IdentityAuditTests(unittest.TestCase):
    def setUp(self):
        self.dataset = {
            'creators': {
                '1': {'name': 'Same', 'slug': 'same'},
                '2': {'name': 'Same', 'slug': 'same_2'},
                '3': {'name': 'Other', 'slug': 'other'},
                '4': {'name': 'PairA', 'slug': 'pair_a'},
                '5': {'name': 'PairB', 'slug': 'pair_b'},
            },
            'accounts': [
                {'tag_id': '4', 'site': '3', 'content_id': '900', 'dead': 'f'},
                {'tag_id': '5', 'site': '3', 'content_id': '900', 'dead': 'f'},
            ],
            'participation': [
                {'work_tag_id': '4', 'work_id': '10'},
                {'work_tag_id': '5', 'work_id': '11'},
            ],
            'audit': {'shared_account_conflicts': [
                {'site': '3', 'content_id': '900', 'creator_ids': ['4', '5']},
            ]},
        }
        self.social = {'accounts': [
            {'id': 'u1', 'username': 'Same'},
            {'id': 'u2', 'username': 'PairA'},
            {'id': 'u3', 'username': 'Other'},
        ], 'mappings': []}
        self.graph = {
            'nodes': [
                {'id': 'otodb:1', 'otodb_id': '1', 'label': 'Same', 'core': True,
                 'accounts': [{'id': 'u1'}],
                 'identity_members': [{'id': 'otodb:1', 'label': 'Same', 'otodb_id': '1'},
                                      {'id': 'otodb:2', 'label': 'Same', 'otodb_id': '2'}],
                 'otodb_ids': ['1', '2']},
                {'id': 'otodb:3', 'otodb_id': '3', 'label': 'Other', 'accounts': [{'id': 'u3'}]},
                {'id': 'otodb:4', 'otodb_id': '4', 'label': 'PairA', 'core': False,
                 'accounts': [{'id': 'u2'}],
                 'identity_members': [{'id': 'otodb:4', 'label': 'PairA', 'otodb_id': '4'},
                                      {'id': 'otodb:5', 'label': 'PairB', 'otodb_id': '5'}],
                 'otodb_ids': ['4', '5'],
                 'identity_shared_accounts': [{'site': '3', 'content_id': '900'}]},
            ],
            'meta': {'identity': {
                'policy': 'user-exact-display-name-shared-account-and-subtag-v4',
                'redirects': {'otodb:2': 'otodb:1', 'otodb:5': 'otodb:4'},
                'groups': [
                    {'canonical_id': 'otodb:1', 'label': 'Same',
                     'source_node_ids': ['otodb:1', 'otodb:2'],
                     'bases': ['user_exact_display_name'], 'shared_accounts': []},
                    {'canonical_id': 'otodb:4', 'label': 'PairA',
                     'source_node_ids': ['otodb:4', 'otodb:5'],
                     'bases': ['shared_platform_account'],
                     'shared_accounts': [{'site': '3', 'content_id': '900'}]},
                ],
            }},
        }
        self.mapping = [
            {'account_id': 'u1', 'creator_id': None, 'state': 'unresolved', 'candidate_creator_ids': []},
            {'account_id': 'u2', 'creator_id': '5', 'state': 'mapped_candidate', 'candidate_creator_ids': ['5']},
            {'account_id': 'u3', 'creator_id': '3', 'state': 'mapped_candidate', 'candidate_creator_ids': ['3']},
        ]
        self.graph['meta']['mapping_sha256'] = mapping_sha256(self.mapping)
        self.verification = {'900': {'account_id': '900', 'state': 'otodb_creator_evidence',
                                     'mapping_state': 'resolved', 'creator_ids': ['4', '5'],
                                     'canonical_creator_ids': ['otodb:4']}}

    def run_audit(self, verification='default'):
        if verification == 'default':
            verification = self.verification
        return audit(self.dataset, self.social, self.graph, mapping_rows=self.mapping,
                     interaction_verification=verification)

    def test_shared_account_merge_and_identity_provenance_are_audited(self):
        result = self.run_audit()
        summary = result['summary']
        self.assertEqual(summary['merge_groups'], 2)
        self.assertEqual(summary['merge_groups_exact_name'], 1)
        self.assertEqual(summary['merge_groups_shared_account'], 1)
        self.assertEqual(summary['shared_account_groups'], 1)
        self.assertEqual(summary['shared_groups_merged'], 1)
        self.assertEqual(summary['interaction_shared_accounts_merged'], 1)
        self.assertEqual(summary['interaction_ambiguous_accounts_kept_unknown'], 0)
        self.assertEqual(summary['name_only_exact_merges'], 1)
        self.assertEqual(summary['mapped_accounts'], 2)
        self.assertEqual(summary['mapped_different_name'], 1)
        self.assertEqual(summary['cross_platform_conflicts'], 0)
        self.assertTrue(summary['mapping_sha256_matches_graph'])
        shared = result['shared_accounts'][0]
        self.assertEqual(shared['decision'], 'merged_shared_platform_account')
        self.assertEqual(result['shared_merges'][0]['canonical_id'], 'otodb:4')

    def test_tampered_redirect_is_rejected(self):
        self.graph['meta']['identity']['redirects']['otodb:2'] = 'otodb:4'
        with self.assertRaises(ValueError):
            self.run_audit()

    def test_cross_name_merge_without_shared_evidence_is_rejected(self):
        self.graph['meta']['identity']['groups'][1]['bases'] = ['user_exact_display_name']
        with self.assertRaises(ValueError):
            self.run_audit()

    def test_shared_account_left_split_is_rejected(self):
        self.graph['nodes'][2]['identity_members'] = [
            {'id': 'otodb:4', 'label': 'PairA', 'otodb_id': '4'}]
        self.graph['nodes'][2]['otodb_ids'] = ['4']
        self.graph['meta']['identity']['groups'][1] = {
            'canonical_id': 'otodb:4', 'label': 'PairA',
            'source_node_ids': ['otodb:4'], 'bases': ['user_exact_display_name'], 'shared_accounts': []}
        self.graph['meta']['identity']['redirects'].pop('otodb:5')
        self.graph['nodes'].append({'id': 'otodb:5', 'otodb_id': '5', 'label': 'PairB', 'accounts': []})
        with self.assertRaises(ValueError):
            self.run_audit()

    def test_ambiguous_interaction_uid_must_stay_unknown(self):
        self.verification['900']['canonical_creator_ids'] = ['otodb:4', 'otodb:5']
        with self.assertRaises(ValueError):
            self.run_audit()
        result = self.run_audit(verification={})
        self.assertEqual(result['summary']['interaction_shared_accounts_checked'], 0)

    def test_shared_account_recompute_mismatch_is_rejected(self):
        self.dataset['audit']['shared_account_conflicts'] = []
        with self.assertRaises(ValueError):
            self.run_audit()

    def test_mapping_provenance_mismatch_is_rejected(self):
        self.graph['meta']['mapping_sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            self.run_audit()


if __name__ == '__main__':
    unittest.main()
