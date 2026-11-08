"""Synthetic fixtures only; real upstream content is not redistributed."""
import unittest
from pipeline.run import decode_copy, normalize


def fixture():
    return {'sha256': 'synthetic', 'tables': {
        'otodb_mediawork': [{'id': '1', 'title': r'a\tb'}],
        'otodb_worksource': [{'id': '1', 'media_id': '1', 'url': 'https://example.org/1'},
                             {'id': '2', 'media_id': '1', 'url': 'https://example.org/2'}],
        'otodb_tagwork': [{'id': str(i), 'category': '4', 'name': f'synthetic-{i}'} for i in range(1, 7)],
        'otodb_tagworkinstance': [{'work_id': '1', 'work_tag_id': str(i), 'creator_roles': role,
                                   'used_as_source': 't' if i == 5 else 'f'}
                                  for i, role in enumerate(['3', '16', '32', r'\N', '1', '64'], 1)],
    }}


class PipelineTests(unittest.TestCase):
    def test_copy(self):
        self.assertIsNone(decode_copy(r'\N'))
        self.assertEqual(decode_copy(r'\\N'), r'\N')
        self.assertEqual(decode_copy(r'a\tb\n\141\x62'), 'a\tb\nab')

    def test_roles_and_publications(self):
        data, graph = normalize(fixture(), {'1'})
        self.assertEqual(len(data['participation']), 2)
        self.assertEqual(len(data['work']), 1)
        self.assertEqual(len(data['work'][0]['publications']), 2)
        self.assertEqual(sum(e['type'] == 'co_creation' for e in graph['edges']), 1)
        self.assertEqual({i['reason'] for i in data['issues']},
                         {'thanks_only', 'missing_roles', 'sample_reference', 'unknown_role_bits'})
        self.assertEqual(normalize(fixture(), {'1'}), (data, graph))

    def test_unclassified_no_projection(self):
        _, graph = normalize(fixture(), set())
        self.assertFalse(any(e['type'] == 'co_creation' for e in graph['edges']))

    def test_supplement_layers(self):
        supplement = {'collab_project': [{'id': 'p'}], 'organization': [{'id': 'o'}],
                      'sources': [{'id': 's', 'url': 'https://example.org/evidence'}],
                      'participation': [{'creator_id': f'otodb:creator:{i}', 'target_id': 'p',
                                         'target_type': 'collab_project', 'source_ids': ['s']} for i in [1, 2]],
                      'membership': [{'creator_id': 'otodb:creator:1', 'organization_id': 'o', 'source_ids': ['s']}]}
        _, graph = normalize(fixture(), set(), supplement)
        self.assertEqual(sum(e['type'] == 'collab_event' for e in graph['edges']), 2)
        self.assertEqual(sum(e['type'] == 'membership' for e in graph['edges']), 1)
        self.assertFalse(any(e['type'] == 'co_creation' for e in graph['edges']))
        supplement['membership'][0]['organization_id'] = 'missing'
        with self.assertRaises(ValueError):
            normalize(fixture(), set(), supplement)


if __name__ == '__main__':
    unittest.main()
