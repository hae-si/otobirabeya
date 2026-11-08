import unittest
from pathlib import Path
from unittest.mock import patch
from io import StringIO
from pipeline.normalize.organizations import read_records


class OrganizationTests(unittest.TestCase):
    def load(self,status='observed',creator='otodb:creator:1',dates=','):
        org='organization_id,name,source_url,recorded_at,status,notes\no,Test,https://example.org/org,2026-10-29,observed,\n'
        membership='creator_id,organization_id,start_date,end_date,source_url,recorded_at,status,notes\n'+creator+',o,'+dates+',https://example.org/members,2026-10-29,'+status+',\n'
        with patch.object(Path,'open',side_effect=[StringIO(org),StringIO(membership)]):
            return read_records(Path('org'),Path('members'),{'1':{}})
    def test_sourced_membership_is_separate_fact(self):
        result=self.load();self.assertEqual(len(result['membership_facts']),1);self.assertNotIn('edges',result)
    def test_pending_not_a_membership_fact(self):
        result=self.load('pending');self.assertEqual(len(result['memberships']),1);self.assertEqual(result['membership_facts'],[])
    def test_unknown_identity_not_matched_by_name(self):
        with self.assertRaises(ValueError):self.load(creator='Test')
    def test_dates_are_checked(self):
        with self.assertRaises(ValueError):self.load(dates='2026-10-29,2026-01-01')
