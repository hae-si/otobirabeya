import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from pipeline.config import interaction_inputs
from pipeline.sources.bilibili_catalog_supplement import freeze


class InteractionConfigTests(unittest.TestCase):
    def test_default_inputs_are_a_paired_project_local_configuration(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'tmp') as root:
            p=Path(root);(p/'config').mkdir();config=p/'config/data_sources.json'
            config.write_text(json.dumps({'bilibili_collection':'data/normalized/c','bilibili_review':'data/normalized/r','bilibili_manifest':'data/normalized/m.json'}))
            with patch('pipeline.config.ROOT',p):
                self.assertEqual(interaction_inputs()['review'],p/'data/normalized/r')
                config.write_text(json.dumps({'bilibili_collection':'../elsewhere','bilibili_review':'data/normalized/r','bilibili_manifest':'data/normalized/m.json'}))
                with self.assertRaises(ValueError):interaction_inputs()
                config.write_text(json.dumps({'bilibili_collection':'data/normalized/c'}))
                with self.assertRaises(ValueError):interaction_inputs()

    def test_supplement_preserves_full_scope_and_only_adds_prior_otodb_provenance(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'tmp') as root:
            p=Path(root);base=p/'base.json';prior=p/'prior.json'
            base.write_text(json.dumps([{'bvid':'BVsame','source_entries':[{'family':'author_pick'}]}]))
            prior.write_text(json.dumps([{'bvid':'BVsame','source_entries':[{'family':'otodb','work_id':'1'}]},
                                         {'aid':'2','source_entries':[{'family':'otodb','work_id':'2'}]},
                                         {'aid':'3','source_entries':[{'family':'viewer_pick'}]}]))
            result=freeze(base,prior,p/'out');rows=json.loads((p/'out/manifest.json').read_bytes())
            self.assertEqual(result['final_aliases'],2);self.assertEqual(len(rows[0]['source_entries']),2)
            self.assertEqual(len(json.loads(base.read_bytes())[0]['source_entries']),1)
