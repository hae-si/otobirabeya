import json
import unittest
from unittest.mock import patch
from pathlib import Path
from pipeline.sources.otomadsite import import_pages


class OtomadSiteImportTests(unittest.TestCase):
    def run_import(self, rows, endpoint='following', repeat=False):
        with patch.object(Path, 'read_bytes', return_value=json.dumps(rows).encode()):
            p = Path('sample.json')
            return import_pages([p, p] if repeat else [p], endpoint, 'alice', '2026-10-28')

    def row(self):
        return {'id': 'rel1', 'followerId': 'alice', 'followeeId': 'bob',
                'createdAt': '2026-10-16T11:52:11.438Z',
                'followee': {'id': 'bob', 'username': 'bot', 'host': None,
                             'isBot': True, 'birthday': 'private', 'onlineStatus': 'active'}}

    def test_dedup_direction_and_minimization(self):
        result = self.run_import([self.row()], repeat=True)
        self.assertEqual(len(result['edges']), 1)
        self.assertEqual(result['duplicate_rows'], 1)
        self.assertEqual(result['edges'][0]['source'], 'alice')
        self.assertEqual(result['edges'][0]['target'], 'bob')
        self.assertNotIn('birthday', json.dumps(result))
        self.assertNotIn('onlineStatus', json.dumps(result))

    def test_conflicting_id_rejected(self):
        a, b = self.row(), self.row()
        b['createdAt'] = '2026-10-17T11:52:11.438Z'
        with self.assertRaises(ValueError):
            self.run_import([a, b])

    def test_wrong_direction_rejected(self):
        with self.assertRaises(ValueError):
            self.run_import([self.row()], endpoint='followers')

    def test_nested_account_mismatch_rejected(self):
        row = self.row()
        row['followee']['id'] = 'wrong'
        with self.assertRaises(ValueError):
            self.run_import([row])

    def test_api_error_rejected(self):
        with self.assertRaises(ValueError):
            self.run_import({'error': {'code': 'AUTH_REQUIRED'}})


if __name__ == '__main__':
    unittest.main()
