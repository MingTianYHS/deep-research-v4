#!/usr/bin/env python3
"""evidence_store.py CLI 冒烟测试。"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'evidence_store.py')
ENV = {**os.environ, 'PYTHONIOENCODING': 'utf-8'}


def run_es(*args: str) -> dict | list:
    """运行 evidence_store.py，返回解析后的 JSON。"""
    result = subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True, text=True, encoding='utf-8', env=ENV,
    )
    if result.returncode != 0:
        raise RuntimeError(f'Exit {result.returncode}: {result.stderr}')
    return json.loads(result.stdout)


class TestInit(unittest.TestCase):
    def test_creates_empty_file(self):
        with tempfile.TemporaryDirectory() as d:
            out = run_es('init', '--dir', d)
            self.assertEqual(out['status'], 'ok')
            path = os.path.join(d, '证据.jsonl')
            self.assertTrue(os.path.exists(path))
            self.assertEqual(os.path.getsize(path), 0)


class TestAddEvidence(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        run_es('init', '--dir', self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_add_and_dedup(self):
        ev = json.dumps({
            'source_id': 'abcdef0123456789',
            'quote': 'FActScore decomposes generation into atomic facts.',
            'evidence_type': 'direct_quote',
            'locator': 'page 3',
            'retrieval_query': 'factuality evaluation methods',
        })
        out1 = run_es('add', '--json', ev, '--dir', self.tmpdir)
        self.assertEqual(out1['status'], 'added')
        self.assertEqual(len(out1['evidence_id']), 16)

        out2 = run_es('add', '--json', ev, '--dir', self.tmpdir)
        self.assertEqual(out2['status'], 'duplicate')
        self.assertEqual(out2['evidence_id'], out1['evidence_id'])

    def test_chinese_quote_roundtrip(self):
        ev = json.dumps({
            'source_id': 'abcdef0123456789',
            'quote': '2026年前三季度，中国新能源汽车出口约176万辆。',
            'evidence_type': 'direct_quote',
        }, ensure_ascii=False)
        out = run_es('add', '--json', ev, '--dir', self.tmpdir)
        self.assertEqual(out['status'], 'added')
        exported = run_es('export', '--dir', self.tmpdir)
        self.assertEqual(exported[0]['quote'], '2026年前三季度，中国新能源汽车出口约176万辆。')

    def test_whitespace_normalization(self):
        ev1 = json.dumps({
            'source_id': 'abcdef0123456789',
            'quote': '  FActScore   decomposes   generation  into atomic facts.  ',
            'evidence_type': 'direct_quote',
        })
        ev2 = json.dumps({
            'source_id': 'abcdef0123456789',
            'quote': 'FActScore decomposes generation into atomic facts.',
            'evidence_type': 'direct_quote',
        })
        out1 = run_es('add', '--json', ev1, '--dir', self.tmpdir)
        out2 = run_es('add', '--json', ev2, '--dir', self.tmpdir)
        self.assertEqual(out1['evidence_id'], out2['evidence_id'])
        self.assertEqual(out2['status'], 'duplicate')

    def test_different_sources_different_ids(self):
        ev1 = json.dumps({
            'source_id': 'aaaaaaaaaaaaaaaa',
            'quote': 'Same quote text.',
            'evidence_type': 'paraphrase',
        })
        ev2 = json.dumps({
            'source_id': 'bbbbbbbbbbbbbbbb',
            'quote': 'Same quote text.',
            'evidence_type': 'paraphrase',
        })
        out1 = run_es('add', '--json', ev1, '--dir', self.tmpdir)
        out2 = run_es('add', '--json', ev2, '--dir', self.tmpdir)
        self.assertNotEqual(out1['evidence_id'], out2['evidence_id'])
        self.assertEqual(out2['status'], 'added')

    def test_rejects_figure_reference_type(self):
        ev = json.dumps({
            'source_id': 'abcdef0123456789',
            'quote': '图表编号引用。',
            'evidence_type': 'figure_reference',
        }, ensure_ascii=False)
        out = run_es('add', '--json', ev, '--dir', self.tmpdir)
        exported = run_es('export', '--dir', self.tmpdir)
        # 已移除图表能力：非法类型回退为 direct_quote
        self.assertEqual(exported[0]['evidence_type'], 'direct_quote')


class TestListAndExport(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        run_es('init', '--dir', self.tmpdir)
        for src, quote in [
            ('src_aaa', 'First quote from source A.'),
            ('src_aaa', 'Second quote from source A.'),
            ('src_bbb', 'Quote from source B.'),
        ]:
            run_es('add', '--json', json.dumps({
                'source_id': src,
                'quote': quote,
                'evidence_type': 'direct_quote',
            }), '--dir', self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_list_all(self):
        out = run_es('list', '--dir', self.tmpdir)
        self.assertEqual(out['count'], 3)

    def test_list_filtered(self):
        out = run_es('list', '--dir', self.tmpdir, '--source-id', 'src_aaa')
        self.assertEqual(out['count'], 2)
        out = run_es('list', '--dir', self.tmpdir, '--source-id', 'src_bbb')
        self.assertEqual(out['count'], 1)

    def test_export(self):
        out = run_es('export', '--dir', self.tmpdir)
        self.assertIsInstance(out, list)
        self.assertEqual(len(out), 3)
        for row in out:
            self.assertIn('evidence_id', row)
            self.assertIn('source_id', row)
            self.assertIn('quote', row)
            self.assertIn('evidence_type', row)
            self.assertIn('captured_at', row)


class TestEvidenceID(unittest.TestCase):
    """compute_evidence_id 单元测试。"""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
        from evidence_store import compute_evidence_id, normalize_quote
        cls.compute_id = staticmethod(compute_evidence_id)
        cls.normalize = staticmethod(normalize_quote)

    def test_deterministic(self):
        self.assertEqual(
            self.compute_id('src_a', 'test quote', 'page 1'),
            self.compute_id('src_a', 'test quote', 'page 1'),
        )

    def test_locator_matters(self):
        self.assertNotEqual(
            self.compute_id('src_a', 'test quote', 'page 1'),
            self.compute_id('src_a', 'test quote', 'page 2'),
        )

    def test_normalize_whitespace(self):
        self.assertEqual(self.normalize('  hello   world  '), 'hello world')


if __name__ == '__main__':
    unittest.main()
