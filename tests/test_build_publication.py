import argparse
import tempfile
import unittest
import os
from pathlib import Path
from unittest.mock import patch
from pipeline.author_site import publish_build


class PublicationTests(unittest.TestCase):
    def test_content_files_restore_with_social_graph_on_late_failure(self):
        names=['app.js','style.css','THIRD_PARTY_NOTICES.md','index.html','graph.json',
               'content-graph.json','content-evidence-00.json.gz','interaction.json']
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'tmp') as root:
            output=Path(root)/'current';output.mkdir()
            for name in names:(output/name).write_bytes(('original '+name).encode())
            def complete(args):
                for name in names:(args.output/name).write_bytes(('replacement '+name).encode())
                (args.output/'content-evidence-01.json.gz').write_bytes(b'new shard')
            real_replace=os.replace
            def fail_once(source,target):
                if Path(source).name=='graph.json' and Path(source).parent.name!='rollback':
                    raise PermissionError('simulated graph publication failure')
                return real_replace(source,target)
            with patch('pipeline.author_site.build',side_effect=complete),patch('pipeline.author_site.os.replace',side_effect=fail_once):
                with self.assertRaises(PermissionError):publish_build(argparse.Namespace(output=output))
            for name in names:self.assertEqual((output/name).read_bytes(),('original '+name).encode())
            self.assertFalse((output/'content-evidence-01.json.gz').exists())

    def test_mid_publication_failure_restores_all_existing_files(self):
        names=['app.js','style.css','THIRD_PARTY_NOTICES.md','index.html','graph.json']
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'tmp') as root:
            output=Path(root)/'current';output.mkdir()
            for name in names:(output/name).write_text('original '+name)
            (output/'user-note.txt').write_text('keep')
            def complete(args):
                for name in names:(args.output/name).write_text('replacement '+name)
            real_replace=os.replace
            def fail_once(source,target):
                if Path(source).name=='index.html' and Path(source).parent.name!='rollback':
                    raise PermissionError('simulated locked file')
                return real_replace(source,target)
            with patch('pipeline.author_site.build',side_effect=complete),patch('pipeline.author_site.os.replace',side_effect=fail_once):
                with self.assertRaises(PermissionError):publish_build(argparse.Namespace(output=output))
            for name in names:self.assertEqual((output/name).read_text(),'original '+name)
            self.assertEqual((output/'user-note.txt').read_text(),'keep')

    def test_failed_build_preserves_current_page_and_graph(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'tmp') as root:
            output=Path(root)/'current';output.mkdir()
            (output/'graph.json').write_text('current graph')
            (output/'index.html').write_text('current page')
            def fail(args):
                (args.output/'graph.json').write_text('unfinished graph')
                raise ValueError('failed input validation')
            with patch('pipeline.author_site.build',side_effect=fail):
                with self.assertRaises(ValueError):publish_build(argparse.Namespace(output=output))
            self.assertEqual((output/'graph.json').read_text(),'current graph')
            self.assertEqual((output/'index.html').read_text(),'current page')
            self.assertEqual(list(Path(root).iterdir()),[output])
