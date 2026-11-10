#!/usr/bin/env python3
"""verify_claim_support.py CLI 测试（含中文 claim-support 用例）。"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'verify_claim_support.py')
ENV = {**os.environ, 'PYTHONIOENCODING': 'utf-8'}


def run_vcs(*args: str, expect_fail: bool = False) -> dict | str:
    """运行 verify_claim_support.py。"""
    result = subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True, text=True, encoding='utf-8', env=ENV,
    )
    if result.returncode != 0 and not expect_fail:
        raise RuntimeError(f'Exit {result.returncode}: {result.stderr}\n{result.stdout}')
    stdout = result.stdout.strip()
    if stdout.startswith('{'):
        return json.loads(stdout)
    return stdout


def write_jsonl(path: str, rows: list[dict]):
    with open(path, 'w', encoding='utf-8') as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')


class TestVerifySupported(unittest.TestCase):
    """有匹配证据的论点应为 supported。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        write_jsonl(os.path.join(self.tmpdir, '来源.jsonl'), [
            {'source_id': 'src_quantum_001', 'title': 'Quantum Computing 2024'},
        ])
        write_jsonl(os.path.join(self.tmpdir, '证据.jsonl'), [
            {
                'evidence_id': 'ev_shor_001',
                'source_id': 'src_quantum_001',
                'quote': "Shor's algorithm can factor large integers exponentially faster than any known classical algorithm, threatening RSA-2048 encryption.",
                'evidence_type': 'direct_quote',
            },
        ])
        write_jsonl(os.path.join(self.tmpdir, '论点.jsonl'), [
            {
                'claim_id': 'clm_factor_001',
                'section_id': 'finding_1',
                'text': "Shor's algorithm can factor large numbers exponentially faster than classical methods, threatening RSA-2048.",
                'claim_type': 'factual',
                'cited_source_ids': ['src_quantum_001'],
                'evidence_ids': ['ev_shor_001'],
                'support_status': 'unverified',
            },
        ])

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_supported_claim(self):
        out = run_vcs('verify', '--dir', self.tmpdir)
        self.assertEqual(out['status'], 'pass')
        self.assertEqual(out['factual_unsupported'], 0)
        with open(os.path.join(self.tmpdir, '论点.jsonl'), encoding='utf-8') as f:
            claims = [json.loads(line) for line in f]
        self.assertEqual(claims[0]['support_status'], 'supported')


class TestVerifyChinese(unittest.TestCase):
    """中文 claim-support 用例：纯中文句子不能恒为 needs_review。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        write_jsonl(os.path.join(self.tmpdir, '来源.jsonl'), [
            {'source_id': 'src_caam_001', 'title': '中国汽车工业协会出口数据'},
        ])
        write_jsonl(os.path.join(self.tmpdir, '证据.jsonl'), [
            {
                'evidence_id': 'ev_caam_001',
                'source_id': 'src_caam_001',
                'quote': '2026年前三季度，中国新能源汽车出口约176万辆，同比增长32%。',
                'evidence_type': 'direct_quote',
            },
            {
                'evidence_id': 'ev_banana_001',
                'source_id': 'src_other_001',
                'quote': '香蕉富含钾元素和膳食纤维，适合作为日常水果。',
                'evidence_type': 'direct_quote',
            },
        ])
        write_jsonl(os.path.join(self.tmpdir, '论点.jsonl'), [
            {
                'claim_id': 'clm_caam_001',
                'section_id': 'main_analysis',
                'text': '2026年前三季度，中国新能源汽车出口量达到约176万辆，同比增长32%。',
                'claim_type': 'factual',
                'cited_source_ids': ['src_caam_001'],
                'evidence_ids': ['ev_caam_001'],
                'support_status': 'unverified',
            },
            {
                'claim_id': 'clm_unrelated_001',
                'section_id': 'main_analysis',
                'text': '量子计算可能改变密码学格局。',
                'claim_type': 'factual',
                'cited_source_ids': ['src_other_001'],
                'evidence_ids': ['ev_banana_001'],
                'support_status': 'unverified',
            },
        ])

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_chinese_claim_supported(self):
        run_vcs('verify', '--dir', self.tmpdir)
        with open(os.path.join(self.tmpdir, '论点.jsonl'), encoding='utf-8') as f:
            claims = {row['claim_id']: row for row in (json.loads(line) for line in f)}
        self.assertEqual(claims['clm_caam_001']['support_status'], 'supported')
        self.assertGreater(claims['clm_caam_001']['_support_score'], 0.6)

    def test_chinese_unrelated_not_supported(self):
        run_vcs('verify', '--dir', self.tmpdir)
        with open(os.path.join(self.tmpdir, '论点.jsonl'), encoding='utf-8') as f:
            claims = {row['claim_id']: row for row in (json.loads(line) for line in f)}
        self.assertIn(claims['clm_unrelated_001']['support_status'], ('needs_review', 'unsupported'))


class TestVerifyUnsupported(unittest.TestCase):
    """无证据的论点应为 unsupported。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        write_jsonl(os.path.join(self.tmpdir, '来源.jsonl'), [])
        write_jsonl(os.path.join(self.tmpdir, '证据.jsonl'), [])
        write_jsonl(os.path.join(self.tmpdir, '论点.jsonl'), [
            {
                'claim_id': 'clm_no_ev_001',
                'section_id': 'finding_1',
                'text': 'The population of Mars is 500 million as of 2025.',
                'claim_type': 'factual',
                'cited_source_ids': [],
                'evidence_ids': [],
                'support_status': 'unverified',
            },
        ])

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_unsupported_no_evidence(self):
        out = run_vcs('verify', '--dir', self.tmpdir)
        self.assertEqual(out['factual_unsupported'], 1)
        self.assertEqual(out['status'], 'pass')

    def test_strict_fails(self):
        out = run_vcs('verify', '--dir', self.tmpdir, '--strict', expect_fail=True)
        self.assertEqual(out['status'], 'fail')

    def test_direct_profile_strict_only_warns(self):
        out = run_vcs('verify', '--dir', self.tmpdir, '--strict', '--profile', 'direct')
        self.assertEqual(out['status'], 'pass')
        self.assertEqual(out['hard_factual_unsupported'], 1)

    def test_deep_profile_included_in_output(self):
        out = run_vcs('verify', '--dir', self.tmpdir, '--profile', 'deep')
        self.assertEqual(out['profile'], 'deep')


class TestVerifyMixed(unittest.TestCase):
    """混合类型论点的不同阈值。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        write_jsonl(os.path.join(self.tmpdir, '来源.jsonl'), [])
        write_jsonl(os.path.join(self.tmpdir, '证据.jsonl'), [])
        write_jsonl(os.path.join(self.tmpdir, '论点.jsonl'), [
            {
                'claim_id': 'clm_spec_001',
                'section_id': 'finding_1',
                'text': 'Quantum computers might eventually solve protein folding in real time.',
                'claim_type': 'speculation',
                'cited_source_ids': [],
                'evidence_ids': [],
                'support_status': 'unverified',
            },
            {
                'claim_id': 'clm_rec_001',
                'section_id': 'recommendations',
                'text': 'Organizations should begin PQC migration planning immediately.',
                'claim_type': 'recommendation',
                'cited_source_ids': [],
                'evidence_ids': [],
                'support_status': 'unverified',
            },
        ])

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_speculation_passes(self):
        run_vcs('verify', '--dir', self.tmpdir)
        with open(os.path.join(self.tmpdir, '论点.jsonl'), encoding='utf-8') as f:
            claims = [json.loads(line) for line in f]
        spec = [c for c in claims if c['claim_type'] == 'speculation'][0]
        self.assertEqual(spec['support_status'], 'supported')

    def test_recommendation_without_links_needs_review(self):
        run_vcs('verify', '--dir', self.tmpdir)
        with open(os.path.join(self.tmpdir, '论点.jsonl'), encoding='utf-8') as f:
            claims = [json.loads(line) for line in f]
        rec = [c for c in claims if c['claim_type'] == 'recommendation'][0]
        self.assertEqual(rec['support_status'], 'needs_review')


class TestVerifyPartial(unittest.TestCase):
    """部分重叠的证据应得到 partial 或 needs_review。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        write_jsonl(os.path.join(self.tmpdir, '来源.jsonl'), [
            {'source_id': 'src_nist_001', 'title': 'NIST PQC Standards'},
        ])
        write_jsonl(os.path.join(self.tmpdir, '证据.jsonl'), [
            {
                'evidence_id': 'ev_nist_001',
                'source_id': 'src_nist_001',
                'quote': 'NIST announced the standardization of CRYSTALS-Kyber for key encapsulation.',
                'evidence_type': 'direct_quote',
            },
        ])
        write_jsonl(os.path.join(self.tmpdir, '论点.jsonl'), [
            {
                'claim_id': 'clm_nist_time',
                'section_id': 'finding_2',
                'text': 'NIST standardized four lattice-based algorithms in 2024, covering both encryption and signatures.',
                'claim_type': 'factual',
                'cited_source_ids': ['src_nist_001'],
                'evidence_ids': ['ev_nist_001'],
                'support_status': 'unverified',
            },
        ])

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_partial_support(self):
        run_vcs('verify', '--dir', self.tmpdir)
        with open(os.path.join(self.tmpdir, '论点.jsonl'), encoding='utf-8') as f:
            claims = [json.loads(line) for line in f]
        self.assertIn(claims[0]['support_status'], ('partial', 'needs_review', 'supported'))


class TestSupportScore(unittest.TestCase):
    """compute_support_score 与 token 提取单元测试。"""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
        from verify_claim_support import compute_support_score, extract_tokens, extract_years
        cls.score = staticmethod(compute_support_score)
        cls.tokens = staticmethod(extract_tokens)
        cls.years = staticmethod(extract_years)

    def test_identical_text(self):
        status, score, _ = self.score(
            'RSA-2048 uses 2048-bit keys for encryption.',
            ['RSA-2048 uses 2048-bit keys for encryption.'],
        )
        self.assertEqual(status, 'supported')
        self.assertGreater(score, 0.8)

    def test_no_evidence(self):
        status, score, _ = self.score('Any claim text.', [])
        self.assertEqual(status, 'unsupported')
        self.assertEqual(score, 0.0)

    def test_unrelated_evidence(self):
        status, score, _ = self.score(
            'The moon landing occurred in 1969.',
            ['Bananas are a good source of potassium and fiber.'],
        )
        self.assertIn(status, ('needs_review', 'unsupported'))
        self.assertLess(score, 0.35)

    def test_chinese_bigrams(self):
        tokens = self.tokens('中国新能源汽车出口')
        self.assertIn('中国', tokens)
        self.assertIn('汽车', tokens)
        self.assertIn('出口', tokens)

    def test_chinese_identical_supported(self):
        text = '2026年前三季度，中国新能源汽车出口约176万辆，同比增长32%。'
        status, score, _ = self.score(text, [text])
        self.assertEqual(status, 'supported')
        self.assertGreater(score, 0.9)

    def test_year_extraction_returns_full_year(self):
        self.assertEqual(self.years('2026年出口增长32%'), {'2026'})


if __name__ == '__main__':
    unittest.main()
